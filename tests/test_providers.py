from datetime import UTC, datetime

import pandas as pd
import pytest

from fxbot.data.clean import clean_candles
from fxbot.data.providers import ParquetProvider, read_candles, write_candles

from .conftest import make_candles


@pytest.fixture
def m15(hours):
    out, _ = clean_candles(make_candles("2024-01-08 00:00", 200), "EUR_USD", "M15", hours, 2, 1.0)
    return out


def test_parquet_roundtrip_preserves_schema(tmp_path, m15):
    write_candles(m15, tmp_path, "EUR_USD", "M15")
    back = read_candles(tmp_path, "EUR_USD", "M15")
    pd.testing.assert_frame_equal(back, m15, check_freq=False)
    assert (tmp_path / "EUR_USD" / "M15.parquet").exists()


def test_history_window_is_half_open(tmp_path, m15):
    write_candles(m15, tmp_path, "EUR_USD", "M15")
    p = ParquetProvider(tmp_path)
    df = p.history("EUR_USD", "M15", datetime(2024, 1, 8, 1, tzinfo=UTC), datetime(2024, 1, 8, 2, tzinfo=UTC))
    assert len(df) == 4
    assert df.index[0] == pd.Timestamp("2024-01-08 01:00", tz="UTC")


def test_history_requires_aware_datetimes(tmp_path, m15):
    write_candles(m15, tmp_path, "EUR_USD", "M15")
    with pytest.raises(ValueError):
        ParquetProvider(tmp_path).history("EUR_USD", "M15", datetime(2024, 1, 8), datetime(2024, 1, 9))


def test_latest(tmp_path, m15):
    write_candles(m15, tmp_path, "EUR_USD", "M15")
    p = ParquetProvider(tmp_path)
    df = p.latest("EUR_USD", "M15", 5)
    pd.testing.assert_frame_equal(df, m15.iloc[-5:], check_freq=False)
    with pytest.raises(ValueError):
        p.latest("EUR_USD", "M15", 0)


def test_returned_frames_are_copies(tmp_path, m15):
    write_candles(m15, tmp_path, "EUR_USD", "M15")
    p = ParquetProvider(tmp_path)
    df = p.latest("EUR_USD", "M15", 3)
    df.loc[:, "close"] = 0.0
    assert (p.latest("EUR_USD", "M15", 3)["close"] > 0).all()


def test_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        ParquetProvider(tmp_path).latest("EUR_USD", "H1", 1)
