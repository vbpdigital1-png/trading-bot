import pandas as pd
import pytest

from fxbot.data.clean import MarketHours, clean_candles
from fxbot.data.resample import resample

from .conftest import make_candles


def ts(s):
    return pd.Timestamp(s, tz="UTC")


@pytest.fixture
def week(hours):
    # One full winter trading week: Sun 2024-01-07 22:00 UTC to Fri 2024-01-12 22:00 UTC.
    raw = make_candles("2024-01-07 22:00", 4 * 24 * 5, seed=1)
    out, _ = clean_candles(raw, "EUR_USD", "M15", hours, 2, 1.0)
    return out


def test_h1_ohlc_values(week, hours):
    h1 = resample(week, "M15", "H1", hours)
    first = week.iloc[:4]
    row = h1.iloc[0]
    assert h1.index[0] == ts("2024-01-07 22:00")
    assert row["open"] == first["open"].iloc[0]
    assert row["high"] == first["high"].max()
    assert row["low"] == first["low"].min()
    assert row["close"] == first["close"].iloc[-1]
    assert row["volume"] == first["volume"].sum()
    assert row["spread"] == pytest.approx(first["spread"].mean())
    assert len(h1) == 24 * 5


def test_h4_aligned_to_new_york_close(week, hours):
    h4 = resample(week, "M15", "H4", hours)
    # Winter: 17:00 NY = 22:00 UTC, so H4 opens at 22, 02, 06, 10, 14, 18 UTC.
    assert set(h4.index.hour) == {22, 2, 6, 10, 14, 18}
    assert h4.index[0] == ts("2024-01-07 22:00")
    assert len(h4) == 6 * 5


def test_h4_alignment_shifts_with_dst(hours):
    raw = make_candles("2024-07-07 21:00", 4 * 24 * 5, seed=2)
    m15, _ = clean_candles(raw, "EUR_USD", "M15", hours, 2, 1.0)
    h4 = resample(m15, "M15", "H4", hours)
    assert set(h4.index.hour) == {21, 1, 5, 9, 13, 17}
    d = resample(m15, "M15", "D", hours)
    assert set(d.index.hour) == {21}


def test_daily_candles(week, hours):
    d = resample(week, "M15", "D", hours)
    assert len(d) == 5
    assert d.index[0] == ts("2024-01-07 22:00")
    day1 = week[(week.index >= ts("2024-01-07 22:00")) & (week.index < ts("2024-01-08 22:00"))]
    assert d.iloc[0]["high"] == day1["high"].max()
    assert d.iloc[0]["close"] == day1["close"].iloc[-1]


def test_incomplete_trailing_bucket_dropped(week, hours):
    partial = week.iloc[: 4 * 24 + 8]  # one full day plus 2 hours
    d = resample(partial, "M15", "D", hours)
    assert len(d) == 1
    h4 = resample(partial, "M15", "H4", hours)
    assert len(h4) == 6
    h1 = resample(partial, "M15", "H1", hours)
    assert len(h1) == 26


def test_no_downward_resampling(week, hours):
    h1 = resample(week, "M15", "H1", hours)
    with pytest.raises(ValueError, match="downward"):
        resample(h1, "H1", "M15", hours)


def test_same_timeframe_is_copy(week, hours):
    out = resample(week, "M15", "M15", hours)
    pd.testing.assert_frame_equal(out, week)
    assert out is not week


def test_empty_input(hours):
    empty = make_candles("2024-01-08", 0)
    assert resample(empty, "M15", "H1", hours).empty
