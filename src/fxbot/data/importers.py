"""Import candles from CSV files (no broker needed).

Supported layouts:
- Dukascopy exports: `Gmt time,Open,High,Low,Close,Volume` with times like
  `01.01.2015 00:00:00.000`, or `Local time,...` with `... GMT+0100` suffixes.
  Export bid and ask separately and pass both: mid = (bid + ask) / 2 and the
  spread comes from the quotes. A single file is used as-is with the default spread.
- Generic: `time,open,high,low,close[,volume][,spread]` with ISO timestamps that
  carry an offset, or naive timestamps plus an explicit `assume_tz`.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

_DUKA_GMT_OFFSET = re.compile(r"\s*GMT([+-]\d{2})(\d{2})$")


def _parse_dukascopy_time(col: pd.Series, local: bool) -> pd.DatetimeIndex:
    if not local:
        return pd.DatetimeIndex(pd.to_datetime(col, format="%d.%m.%Y %H:%M:%S.%f", utc=True))
    # "01.01.2015 00:00:00.000 GMT+0100" -> ISO with offset
    def to_iso(s: str) -> str:
        m = _DUKA_GMT_OFFSET.search(s)
        if not m:
            raise ValueError(f"Dukascopy local time without GMT offset: {s!r}")
        stamp = pd.to_datetime(s[: m.start()], format="%d.%m.%Y %H:%M:%S.%f")
        return f"{stamp.isoformat()}{m.group(1)}:{m.group(2)}"

    return pd.DatetimeIndex(pd.to_datetime(col.map(to_iso), utc=True, format="ISO8601"))


def read_csv_candles(path: str | Path, assume_tz: str | None = None) -> pd.DataFrame:
    """Read one CSV into a frame indexed by tz-aware `time` with lowercase OHLCV columns."""
    raw = pd.read_csv(path)
    cols = {c: c.strip().lower() for c in raw.columns}
    raw = raw.rename(columns=cols)

    if "gmt time" in raw.columns:
        idx = _parse_dukascopy_time(raw["gmt time"], local=False)
        raw = raw.drop(columns=["gmt time"])
    elif "local time" in raw.columns:
        idx = _parse_dukascopy_time(raw["local time"].astype(str), local=True)
        raw = raw.drop(columns=["local time"])
    elif "time" in raw.columns:
        idx = pd.DatetimeIndex(pd.to_datetime(raw["time"], format="ISO8601"))
        if idx.tz is None:
            if assume_tz is None:
                raise ValueError(f"{path}: timestamps have no timezone; pass assume_tz")
            idx = idx.tz_localize(assume_tz)
        raw = raw.drop(columns=["time"])
    else:
        raise ValueError(f"{path}: no recognised time column (Gmt time, Local time or time)")

    missing = {"open", "high", "low", "close"} - set(raw.columns)
    if missing:
        raise ValueError(f"{path}: missing columns {sorted(missing)}")
    raw.index = idx
    raw.index.name = "time"
    keep = [c for c in ("open", "high", "low", "close", "volume", "spread") if c in raw.columns]
    return raw[keep]


def combine_bid_ask(bid: pd.DataFrame, ask: pd.DataFrame) -> pd.DataFrame:
    """Mid OHLC from bid and ask candles, keeping bid_close/ask_close for the spread.
    Only timestamps present in both files are kept."""
    joined = bid.join(ask, how="inner", lsuffix="_bid", rsuffix="_ask")
    out = pd.DataFrame(index=joined.index)
    for c in ("open", "high", "low", "close"):
        out[c] = (joined[f"{c}_bid"] + joined[f"{c}_ask"]) / 2
    if "volume_bid" in joined.columns:
        out["volume"] = joined["volume_bid"].round().astype("int64")
    out["bid_close"] = joined["close_bid"]
    out["ask_close"] = joined["close_ask"]
    return out
