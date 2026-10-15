from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from fxbot.config import load_config
from fxbot.data.clean import MarketHours

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def cfg():
    return load_config(ROOT / "config.yaml")


@pytest.fixture
def hours():
    return MarketHours()


def make_candles(start: str, periods: int, freq: str = "15min", seed: int = 0) -> pd.DataFrame:
    """Valid random-walk M15 candles starting at `start` (UTC), no weekend filtering."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range(start, periods=periods, freq=freq, tz="UTC", name="time")
    close = 1.1 + np.cumsum(rng.normal(0, 0.0005, periods))
    open_ = np.r_[1.1, close[:-1]]
    high = np.maximum(open_, close) + rng.uniform(0, 0.0003, periods)
    low = np.minimum(open_, close) - rng.uniform(0, 0.0003, periods)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": 100, "spread": 1.0}, index=idx
    )
