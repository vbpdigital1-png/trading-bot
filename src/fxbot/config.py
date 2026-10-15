"""Load and validate config.yaml. Every tunable value in the bot comes from here."""

from __future__ import annotations

import re
from datetime import date, time
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from fxbot.instruments import TIMEFRAMES, validate_pair


class _Strict(BaseModel):
    # Unknown keys are almost always typos; fail loudly instead of ignoring them.
    model_config = ConfigDict(extra="forbid", frozen=True)


Fraction = Field(gt=0, lt=1)


class DataConfig(_Strict):
    dir: Path = Path("data")
    pairs: list[str]
    base_timeframe: Literal["M15"] = "M15"
    timeframes: list[str]
    history_start: date
    market_timezone: str = "America/New_York"
    week_close: time = time(17, 0)
    max_gap_candles: int = Field(ge=0)
    holiday_closures: list[str] = []

    @field_validator("pairs")
    @classmethod
    def _pairs(cls, v: list[str]) -> list[str]:
        for p in v:
            validate_pair(p)
        if len(set(v)) != len(v):
            raise ValueError("duplicate pairs")
        return v

    @field_validator("timeframes")
    @classmethod
    def _timeframes(cls, v: list[str]) -> list[str]:
        unknown = set(v) - set(TIMEFRAMES)
        if unknown:
            raise ValueError(f"unknown timeframes: {sorted(unknown)}")
        return v

    @field_validator("holiday_closures")
    @classmethod
    def _holidays(cls, v: list[str]) -> list[str]:
        for h in v:
            if not re.fullmatch(r"\d{2}-\d{2}", h):
                raise ValueError(f"holiday must be MM-DD, got {h!r}")
        return v


class LoggingConfig(_Strict):
    dir: Path = Path("logs")
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"


class RiskConfig(_Strict):
    per_trade: float = Fraction
    max_open_trades: int = Field(ge=1)
    max_trades_per_pair: int = Field(ge=1)
    max_total_risk: float = Fraction
    max_same_direction_per_currency: int = Field(ge=1)
    daily_loss_limit: float = Fraction
    weekly_loss_limit: float = Fraction
    kill_switch_drawdown: float = Fraction
    breakeven_at_r: float = Field(gt=0)
    trail_atr_mult: float = Field(gt=0)
    min_stop_improvement_pips: float = Field(ge=0)

    @model_validator(mode="after")
    def _consistent(self) -> RiskConfig:
        if self.per_trade > self.max_total_risk:
            raise ValueError("risk.per_trade cannot exceed risk.max_total_risk")
        return self


class RegimeConfig(_Strict):
    timeframe: str
    adx_trend: float = Field(gt=0)
    adx_range: float = Field(gt=0)
    atr_volatile_pct: float = Field(gt=0, lt=100)
    atr_lookback: int = Field(ge=2)
    confirm_candles: int = Field(ge=1)

    @model_validator(mode="after")
    def _consistent(self) -> RegimeConfig:
        if self.timeframe not in TIMEFRAMES:
            raise ValueError(f"unknown regime timeframe {self.timeframe!r}")
        if self.adx_range >= self.adx_trend:
            raise ValueError("regime.adx_range must be below regime.adx_trend")
        return self


class _StrategyBase(_Strict):
    enabled: bool = True
    pairs: list[str]

    @field_validator("pairs")
    @classmethod
    def _pairs(cls, v: list[str]) -> list[str]:
        for p in v:
            validate_pair(p)
        return v


class LondonBreakoutConfig(_StrategyBase):
    target_r: float = Field(gt=0)


class DonchianTrendConfig(_StrategyBase):
    entry_period: int = Field(ge=2)
    exit_period: int = Field(ge=2)
    stop_atr_mult: float = Field(gt=0)


class MeanReversionConfig(_StrategyBase):
    bb_period: int = Field(ge=2)
    bb_std: float = Field(gt=0)
    rsi_low: float = Field(gt=0, lt=100)
    rsi_high: float = Field(gt=0, lt=100)

    @model_validator(mode="after")
    def _consistent(self) -> MeanReversionConfig:
        if self.rsi_low >= self.rsi_high:
            raise ValueError("rsi_low must be below rsi_high")
        return self


class StrategiesConfig(_Strict):
    london_breakout: LondonBreakoutConfig
    donchian_trend: DonchianTrendConfig
    mean_reversion: MeanReversionConfig


class CostsConfig(_Strict):
    slippage_pips: float = Field(ge=0)
    commission_per_million: float = Field(ge=0)
    default_spread_pips: dict[str, float]

    @field_validator("default_spread_pips")
    @classmethod
    def _spreads(cls, v: dict[str, float]) -> dict[str, float]:
        for pair, spread in v.items():
            validate_pair(pair)
            if spread <= 0:
                raise ValueError(f"default spread for {pair} must be positive")
        return v


class Config(_Strict):
    # The only accepted value. Trading a live account is out of scope for this build.
    mode: Literal["practice"]
    broker: Literal["oanda"]
    data: DataConfig
    logging: LoggingConfig = LoggingConfig()
    risk: RiskConfig
    regime: RegimeConfig
    strategies: StrategiesConfig
    costs: CostsConfig

    @model_validator(mode="after")
    def _cross_checks(self) -> Config:
        known = set(self.data.pairs)
        for name in ("london_breakout", "donchian_trend", "mean_reversion"):
            missing = set(getattr(self.strategies, name).pairs) - known
            if missing:
                raise ValueError(f"strategies.{name} uses pairs not in data.pairs: {sorted(missing)}")
        no_spread = known - set(self.costs.default_spread_pips)
        if no_spread:
            raise ValueError(f"costs.default_spread_pips missing for: {sorted(no_spread)}")
        if self.regime.timeframe not in self.data.timeframes:
            raise ValueError("regime.timeframe must be one of data.timeframes")
        return self


def load_config(path: str | Path = "config.yaml") -> Config:
    with open(path) as f:
        raw = yaml.safe_load(f)
    return Config.model_validate(raw)
