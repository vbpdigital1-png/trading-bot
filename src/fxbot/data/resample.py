"""Resample M15 candles upward to H1, H4 and D. Never downward.

H4 and D buckets are aligned to the forex day, which starts at the weekly close
time in the market timezone (17:00 New York). H1 is aligned to the clock hour.
Only complete buckets are returned: a higher-timeframe candle whose period has
not fully elapsed in the source data would leak the future into strategies.
"""

from __future__ import annotations

import pandas as pd

from fxbot.data.clean import COLUMNS, MarketHours
from fxbot.instruments import timeframe_delta

_AGG = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum", "spread": "mean"}


def _bucket_labels(index: pd.DatetimeIndex, tf: str, hours: MarketHours) -> pd.DatetimeIndex:
    """UTC open time of the target-timeframe bucket each source candle belongs to."""
    step = timeframe_delta(tf)
    if tf in ("M15", "H1"):
        return index.floor(step)
    # Shift the local wall clock so the forex day starts at 00:00, floor, shift back.
    # DST changes happen at weekends when there are no candles, so localizing back
    # is never ambiguous.
    offset = pd.Timedelta(hours=24 - hours.week_close.hour, minutes=-hours.week_close.minute)
    local = index.tz_convert(hours.timezone).tz_localize(None)
    floored = (local + offset).floor(step) - offset
    return floored.tz_localize(hours.timezone).tz_convert("UTC")


def resample(candles: pd.DataFrame, source_tf: str, target_tf: str, hours: MarketHours) -> pd.DataFrame:
    src, dst = timeframe_delta(source_tf), timeframe_delta(target_tf)
    if dst < src:
        raise ValueError(f"cannot resample downward from {source_tf} to {target_tf}")
    if dst % src:
        raise ValueError(f"{target_tf} is not a whole multiple of {source_tf}")
    if candles.empty:
        return candles[COLUMNS].copy()
    if dst == src:
        return candles[COLUMNS].copy()

    labels = _bucket_labels(candles.index, target_tf, hours)
    out = candles[COLUMNS].groupby(labels).agg(_AGG)
    out.index.name = "time"

    # Drop the trailing bucket if the source data stops before it closes.
    last_source_close = candles.index[-1] + src
    if out.index[-1] + dst > last_source_close:
        out = out.iloc[:-1]
    return out.astype({"volume": "int64"})
