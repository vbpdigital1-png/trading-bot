import pandas as pd
import pytest

from fxbot.data.clean import MarketHours, clean_candles, find_gaps, invalid_mask, to_utc_index

from .conftest import make_candles


def ts(s):
    return pd.Timestamp(s, tz="UTC")


def run_clean(df, pair="EUR_USD", hours=None, max_gap=2, default_spread=1.0):
    return clean_candles(df, pair, "M15", hours or MarketHours(), max_gap, default_spread)


# Rule 1: UTC, timezone-aware


def test_naive_timestamps_rejected():
    df = make_candles("2024-01-08 00:00", 4)
    df.index = df.index.tz_localize(None)
    with pytest.raises(ValueError, match="naive"):
        run_clean(df)


def test_other_timezones_converted_to_utc():
    df = make_candles("2024-01-08 00:00", 4)
    df.index = df.index.tz_convert("Europe/London").tz_convert("Asia/Tokyo")
    out, _ = run_clean(df)
    assert str(out.index.tz) == "UTC"
    assert out.index[0] == ts("2024-01-08 00:00")


def test_time_column_accepted_and_sorted():
    df = make_candles("2024-01-08 00:00", 4).iloc[::-1].reset_index()
    out = to_utc_index(df)
    assert out.index.is_monotonic_increasing


def test_duplicates_keep_last():
    df = make_candles("2024-01-08 00:00", 3)
    dup = df.iloc[[1]].copy()
    dup["close"] = dup["open"]  # still valid, distinguishable
    out, rep = run_clean(pd.concat([df, dup]))
    assert rep.duplicates_dropped == 1
    assert len(out) == 3
    assert out.loc[ts("2024-01-08 00:15"), "close"] == dup["close"].iloc[0]


# Rule 2: weekends and gaps


@pytest.mark.parametrize(
    "stamp,weekend",
    [
        # Winter: NY = UTC-5, so the week closes Fri 22:00 UTC and opens Sun 22:00 UTC.
        ("2024-01-12 21:45", False),
        ("2024-01-12 22:00", True),
        ("2024-01-13 12:00", True),
        ("2024-01-14 21:45", True),
        ("2024-01-14 22:00", False),
        # Summer: NY = UTC-4, close Fri 21:00 UTC, open Sun 21:00 UTC.
        ("2024-07-12 20:45", False),
        ("2024-07-12 21:00", True),
        ("2024-07-14 20:45", True),
        ("2024-07-14 21:00", False),
        ("2024-07-10 03:00", False),
    ],
)
def test_weekend_boundaries_follow_new_york(stamp, weekend):
    idx = pd.DatetimeIndex([ts(stamp)])
    assert bool(MarketHours().is_weekend(idx).iloc[0]) is weekend


def test_weekend_candles_dropped():
    # Fri 2024-01-12 20:00 UTC through Mon 00:00: spans the weekend.
    df = make_candles("2024-01-12 20:00", 4 * 52)
    out, rep = run_clean(df)
    assert rep.weekend_dropped > 0
    assert not MarketHours().is_weekend(out.index).any()
    assert rep.gaps.empty  # the weekend itself is not a gap


def test_gap_longer_than_limit_reported():
    df = make_candles("2024-01-08 00:00", 40)
    df = df.drop(df.index[10:13])  # 3 missing > 2
    _, rep = run_clean(df)
    assert len(rep.gaps) == 1
    g = rep.gaps.iloc[0]
    assert g["missing_candles"] == 3
    assert g["after"] == ts("2024-01-08 02:15")
    assert g["before"] == ts("2024-01-08 03:15")
    assert not g["expected"]
    assert len(rep.unexpected_gaps) == 1


def test_gap_at_limit_not_reported():
    df = make_candles("2024-01-08 00:00", 40)
    df = df.drop(df.index[10:12])  # exactly 2 missing
    _, rep = run_clean(df)
    assert rep.gaps.empty


def test_holiday_gap_marked_expected():
    df = make_candles("2024-12-24 00:00", 4 * 72)
    df = df[(df.index < ts("2024-12-24 22:00")) | (df.index >= ts("2024-12-25 22:00"))]
    _, rep = run_clean(df)
    assert len(rep.gaps) == 1
    assert bool(rep.gaps.iloc[0]["expected"])
    assert rep.unexpected_gaps.empty


def test_find_gaps_handles_tiny_input():
    assert find_gaps(pd.DatetimeIndex([], tz="UTC"), "M15", MarketHours(), 2).empty


# Rule 3: invalid candles


@pytest.mark.parametrize(
    "o,h,l,c",
    [
        (1.10, 1.09, 1.11, 1.10),  # high < low
        (1.12, 1.11, 1.09, 1.10),  # open above high
        (1.10, 1.11, 1.09, 1.08),  # close below low
        (1.10, 1.11, 1.09, None),  # missing
        (0.0, 1.11, 0.0, 1.10),  # non-positive
    ],
)
def test_invalid_candle_rejected(o, h, l, c):
    df = make_candles("2024-01-08 00:00", 3)
    df.iloc[1, df.columns.get_indexer(["open", "high", "low", "close"])] = [o, h, l, c]
    assert invalid_mask(df).tolist() == [False, True, False]
    out, rep = run_clean(df)
    assert rep.invalid_rejected == 1
    assert len(out) == 2


def test_open_close_on_extremes_is_valid():
    df = make_candles("2024-01-08 00:00", 1)
    df.iloc[0, df.columns.get_indexer(["open", "high", "low", "close"])] = [1.09, 1.11, 1.09, 1.11]
    assert not invalid_mask(df).any()


# Rule 4: spread


def test_spread_from_bid_ask_in_pips():
    df = make_candles("2024-01-08 00:00", 2).drop(columns="spread")
    df["bid_close"] = [1.10000, 1.10010]
    df["ask_close"] = [1.10012, 1.10025]
    out, rep = run_clean(df)
    assert out["spread"].round(6).tolist() == [1.2, 1.5]
    assert rep.spread_filled_default == 0


def test_spread_jpy_pip_size():
    df = make_candles("2024-01-08 00:00", 1).drop(columns="spread") * [100, 100, 100, 100, 1]
    df["bid_close"] = [150.000]
    df["ask_close"] = [150.011]
    out, _ = run_clean(df, pair="USD_JPY")
    assert out["spread"].iloc[0] == pytest.approx(1.1)


def test_missing_spread_uses_default():
    df = make_candles("2024-01-08 00:00", 3)
    df["spread"] = [0.8, None, 0.0]
    out, rep = run_clean(df, default_spread=1.4)
    assert out["spread"].tolist() == [0.8, 1.4, 1.4]
    assert rep.spread_filled_default == 2


def test_output_schema():
    df = make_candles("2024-01-08 00:00", 3).drop(columns=["volume", "spread"])
    out, rep = run_clean(df)
    assert list(out.columns) == ["open", "high", "low", "close", "volume", "spread"]
    assert out.index.name == "time"
    assert out["volume"].dtype == "int64"
    assert rep.summary()["rows_out"] == 3
