"""Data providers. Strategies receive DataFrames only and never know which
provider supplied them. The live OandaProvider arrives with the broker work."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Protocol

import pandas as pd

from fxbot.data.clean import COLUMNS
from fxbot.instruments import timeframe_delta, validate_pair


class DataProvider(Protocol):
    def history(self, pair: str, tf: str, start: datetime, end: datetime) -> pd.DataFrame: ...
    def latest(self, pair: str, tf: str, n: int) -> pd.DataFrame: ...


def parquet_path(data_dir: str | Path, pair: str, tf: str) -> Path:
    return Path(data_dir) / validate_pair(pair) / f"{tf}.parquet"


def write_candles(df: pd.DataFrame, data_dir: str | Path, pair: str, tf: str) -> Path:
    path = parquet_path(data_dir, pair, tf)
    path.parent.mkdir(parents=True, exist_ok=True)
    df[COLUMNS].reset_index().to_parquet(path, index=False)
    return path


def read_candles(data_dir: str | Path, pair: str, tf: str) -> pd.DataFrame:
    path = parquet_path(data_dir, pair, tf)
    if not path.exists():
        raise FileNotFoundError(f"no {tf} data for {pair} at {path}")
    df = pd.read_parquet(path).set_index("time")
    df.index = pd.DatetimeIndex(df.index).tz_convert("UTC")
    return df[COLUMNS]


def _utc(ts: datetime) -> pd.Timestamp:
    t = pd.Timestamp(ts)
    if t.tz is None:
        raise ValueError("start/end must be timezone-aware")
    return t.tz_convert("UTC")


class ParquetProvider:
    """Reads cleaned candles from data/{pair}/{tf}.parquet. Used by backtests."""

    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir)
        self._cache: dict[tuple[str, str], pd.DataFrame] = {}

    def _load(self, pair: str, tf: str) -> pd.DataFrame:
        timeframe_delta(tf)
        key = (pair, tf)
        if key not in self._cache:
            self._cache[key] = read_candles(self.data_dir, pair, tf)
        return self._cache[key]

    def history(self, pair: str, tf: str, start: datetime, end: datetime) -> pd.DataFrame:
        """Candles whose open time is in [start, end)."""
        df = self._load(pair, tf)
        s, e = _utc(start), _utc(end)
        return df[(df.index >= s) & (df.index < e)].copy()

    def latest(self, pair: str, tf: str, n: int) -> pd.DataFrame:
        if n < 1:
            raise ValueError("n must be at least 1")
        return self._load(pair, tf).iloc[-n:].copy()
