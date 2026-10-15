"""Market conventions for currency pairs and timeframes. These are facts, not tunables."""

from __future__ import annotations

import re

import pandas as pd

# Timeframe name -> candle length.
TIMEFRAMES: dict[str, pd.Timedelta] = {
    "M15": pd.Timedelta(minutes=15),
    "H1": pd.Timedelta(hours=1),
    "H4": pd.Timedelta(hours=4),
    "D": pd.Timedelta(days=1),
}

_PAIR_RE = re.compile(r"^[A-Z]{3}_[A-Z]{3}$")


def validate_pair(pair: str) -> str:
    if not _PAIR_RE.match(pair):
        raise ValueError(f"pair must look like EUR_USD, got {pair!r}")
    return pair


def currencies(pair: str) -> tuple[str, str]:
    base, quote = validate_pair(pair).split("_")
    return base, quote


def pip_size(pair: str) -> float:
    """0.01 for JPY-quoted pairs, 0.0001 for everything else."""
    _, quote = currencies(pair)
    return 0.01 if quote == "JPY" else 0.0001


def timeframe_delta(tf: str) -> pd.Timedelta:
    try:
        return TIMEFRAMES[tf]
    except KeyError:
        raise ValueError(f"unknown timeframe {tf!r}; expected one of {list(TIMEFRAMES)}") from None
