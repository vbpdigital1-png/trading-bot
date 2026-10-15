import pandas as pd
import pytest

from fxbot.data.importers import combine_bid_ask, read_csv_candles


def ts(s):
    return pd.Timestamp(s, tz="UTC")


def test_dukascopy_gmt(tmp_path):
    p = tmp_path / "d.csv"
    p.write_text(
        "Gmt time,Open,High,Low,Close,Volume\n"
        "08.01.2024 00:00:00.000,1.0940,1.0945,1.0938,1.0942,1234.56\n"
        "08.01.2024 00:15:00.000,1.0942,1.0950,1.0941,1.0949,987.1\n"
    )
    df = read_csv_candles(p)
    assert df.index[0] == ts("2024-01-08 00:00")
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]


def test_dukascopy_local_time_with_offset(tmp_path):
    p = tmp_path / "d.csv"
    p.write_text(
        "Local time,Open,High,Low,Close,Volume\n"
        "08.01.2024 01:00:00.000 GMT+0100,1.0940,1.0945,1.0938,1.0942,10\n"
    )
    assert read_csv_candles(p).index[0] == ts("2024-01-08 00:00")


def test_generic_iso_with_offset(tmp_path):
    p = tmp_path / "g.csv"
    p.write_text("time,open,high,low,close\n2024-01-08T05:00:00+05:00,1,1.1,0.9,1\n")
    assert read_csv_candles(p).index[0] == ts("2024-01-08 00:00")


def test_generic_naive_requires_assume_tz(tmp_path):
    p = tmp_path / "g.csv"
    p.write_text("time,open,high,low,close\n2024-01-08 00:00,1,1.1,0.9,1\n")
    with pytest.raises(ValueError, match="assume_tz"):
        read_csv_candles(p)
    assert read_csv_candles(p, assume_tz="UTC").index[0] == ts("2024-01-08 00:00")


def test_missing_columns(tmp_path):
    p = tmp_path / "g.csv"
    p.write_text("time,open,close\n2024-01-08T00:00Z,1,1\n")
    with pytest.raises(ValueError, match="high"):
        read_csv_candles(p)


def test_unknown_time_column(tmp_path):
    p = tmp_path / "g.csv"
    p.write_text("date,open,high,low,close\n2024-01-08,1,1.1,0.9,1\n")
    with pytest.raises(ValueError, match="time column"):
        read_csv_candles(p)


def test_combine_bid_ask():
    idx = pd.DatetimeIndex([ts("2024-01-08 00:00"), ts("2024-01-08 00:15")], name="time")
    bid = pd.DataFrame(
        {"open": [1.0, 1.1], "high": [1.2, 1.2], "low": [0.9, 1.0], "close": [1.1, 1.15], "volume": [10.4, 20.6]},
        index=idx,
    )
    ask = bid.iloc[:1] + 0.0002
    out = combine_bid_ask(bid, ask)
    assert len(out) == 1  # only common timestamps
    assert out["close"].iloc[0] == pytest.approx(1.1001)
    assert out["ask_close"].iloc[0] - out["bid_close"].iloc[0] == pytest.approx(0.0002)
    assert out["volume"].iloc[0] == 10
