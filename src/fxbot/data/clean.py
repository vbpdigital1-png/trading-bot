"""Cleaning rules for raw OHLC candles.

1. All timestamps in UTC, timezone-aware.
2. Drop weekend candles; report weekday gaps longer than `max_gap_candles`.
3. Reject candles where high < low, or open/close falls outside high-low.
4. Spread per candle (in pips) where available, else the per-pair default.

Canonical candle frame: DatetimeIndex `time` (UTC, candle open time), columns
open, high, low, close, volume, spread. `spread` is in pips.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import time

import pandas as pd

from fxbot.instruments import pip_size, timeframe_delta

COLUMNS = ["open", "high", "low", "close", "volume", "spread"]


@dataclass(frozen=True)
class MarketHours:
    """The forex week closes Friday at `week_close` and reopens Sunday at the same
    time, in `timezone` (17:00 New York by default, so DST is handled for free)."""

    timezone: str = "America/New_York"
    week_close: time = time(17, 0)
    holiday_closures: tuple[str, ...] = ("12-25", "01-01")

    def is_weekend(self, index: pd.DatetimeIndex) -> pd.Series:
        local = index.tz_convert(self.timezone)
        dow = local.dayofweek  # Mon=0 .. Sun=6
        minutes = local.hour * 60 + local.minute
        after_close = minutes >= self.week_close.hour * 60 + self.week_close.minute
        weekend = (dow == 5) | ((dow == 4) & after_close) | ((dow == 6) & ~after_close)
        return pd.Series(weekend, index=index)


@dataclass
class CleanReport:
    pair: str
    timeframe: str
    rows_in: int = 0
    rows_out: int = 0
    duplicates_dropped: int = 0
    weekend_dropped: int = 0
    invalid_rejected: int = 0
    spread_filled_default: int = 0
    gaps: pd.DataFrame = field(default_factory=lambda: _empty_gaps())

    @property
    def unexpected_gaps(self) -> pd.DataFrame:
        return self.gaps[~self.gaps["expected"]]

    def summary(self) -> dict:
        return {
            "pair": self.pair,
            "timeframe": self.timeframe,
            "rows_in": self.rows_in,
            "rows_out": self.rows_out,
            "duplicates_dropped": self.duplicates_dropped,
            "weekend_dropped": self.weekend_dropped,
            "invalid_rejected": self.invalid_rejected,
            "spread_filled_default": self.spread_filled_default,
            "gaps_total": len(self.gaps),
            "gaps_unexpected": len(self.unexpected_gaps),
        }


def _empty_gaps() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "pair": pd.Series(dtype=str),
            "after": pd.Series(dtype="datetime64[ns, UTC]"),
            "before": pd.Series(dtype="datetime64[ns, UTC]"),
            "missing_candles": pd.Series(dtype=int),
            "expected": pd.Series(dtype=bool),
        }
    )


def to_utc_index(df: pd.DataFrame, time_col: str = "time") -> pd.DataFrame:
    """Rule 1. Naive timestamps are rejected, never guessed: the source must say
    what timezone it is in (importers localize before calling this)."""
    if time_col in df.columns:
        df = df.set_index(time_col)
    idx = pd.DatetimeIndex(df.index)
    if idx.tz is None:
        raise ValueError("timestamps are timezone-naive; localize them before cleaning")
    df = df.copy()
    df.index = idx.tz_convert("UTC").as_unit("ns")
    df.index.name = "time"
    return df.sort_index()


def invalid_mask(df: pd.DataFrame) -> pd.Series:
    """Rule 3."""
    lo = df[["open", "close"]].min(axis=1)
    hi = df[["open", "close"]].max(axis=1)
    bad = (df["high"] < df["low"]) | (lo < df["low"]) | (hi > df["high"])
    bad |= df[["open", "high", "low", "close"]].isna().any(axis=1)
    bad |= (df[["open", "high", "low", "close"]] <= 0).any(axis=1)
    return bad


def find_gaps(
    index: pd.DatetimeIndex,
    timeframe: str,
    hours: MarketHours,
    max_gap_candles: int,
    pair: str = "",
) -> pd.DataFrame:
    """Rule 2: report runs of more than `max_gap_candles` missing candles while the
    market is open. Time across the weekend close is not a gap. Gaps touching a
    holiday closure date are reported with expected=True."""
    if len(index) < 2:
        return _empty_gaps()
    step = timeframe_delta(timeframe)
    missing = (index[1:] - index[:-1]) // step - 1
    candidates = (missing > max_gap_candles).nonzero()[0]
    rows = []
    for i in candidates:
        a, b = index[i], index[i + 1]
        # Count only the missing slots that fall inside market hours.
        slots = pd.date_range(a + step, b - step, freq=step, tz="UTC")
        open_slots = slots[~hours.is_weekend(slots).to_numpy()]
        if len(open_slots) <= max_gap_candles:
            continue
        local_days = {d.strftime("%m-%d") for d in open_slots.tz_convert(hours.timezone)}
        expected = bool(local_days & set(hours.holiday_closures))
        rows.append(
            {"pair": pair, "after": a, "before": b, "missing_candles": len(open_slots), "expected": expected}
        )
    if not rows:
        return _empty_gaps()
    return pd.DataFrame(rows)


def clean_candles(
    raw: pd.DataFrame,
    pair: str,
    timeframe: str,
    hours: MarketHours,
    max_gap_candles: int,
    default_spread_pips: float,
) -> tuple[pd.DataFrame, CleanReport]:
    """Apply all four rules. `raw` must have a tz-aware `time` column or index and
    open/high/low/close columns; volume and spread are optional. If `bid_close` and
    `ask_close` are present, spread is computed from them."""
    report = CleanReport(pair=pair, timeframe=timeframe, rows_in=len(raw))
    df = to_utc_index(raw)

    dup = df.index.duplicated(keep="last")
    report.duplicates_dropped = int(dup.sum())
    df = df[~dup]

    weekend = hours.is_weekend(df.index).to_numpy()
    report.weekend_dropped = int(weekend.sum())
    df = df[~weekend]

    bad = invalid_mask(df)
    report.invalid_rejected = int(bad.sum())
    df = df[~bad]

    # Rule 4: spread in pips.
    pip = pip_size(pair)
    if "spread" not in df.columns:
        df = df.assign(spread=float("nan"))
    if {"bid_close", "ask_close"} <= set(df.columns):
        from_quotes = (df["ask_close"] - df["bid_close"]) / pip
        df["spread"] = df["spread"].fillna(from_quotes.where(from_quotes > 0))
    missing_spread = df["spread"].isna() | (df["spread"] <= 0)
    report.spread_filled_default = int(missing_spread.sum())
    df.loc[missing_spread, "spread"] = default_spread_pips

    if "volume" not in df.columns:
        df = df.assign(volume=0)
    df = df[COLUMNS].astype(
        {"open": float, "high": float, "low": float, "close": float, "volume": "int64", "spread": float}
    )

    report.gaps = find_gaps(df.index, timeframe, hours, max_gap_candles, pair)
    report.rows_out = len(df)
    return df, report
