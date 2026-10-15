import copy

import pytest
import yaml
from pydantic import ValidationError

from fxbot.config import Config, load_config

from .conftest import ROOT


@pytest.fixture
def raw():
    with open(ROOT / "config.yaml") as f:
        return yaml.safe_load(f)


def test_repo_config_loads(cfg):
    assert cfg.mode == "practice"
    assert len(cfg.data.pairs) == 8
    assert cfg.risk.per_trade == 0.01


@pytest.mark.parametrize("mode", ["live", "LIVE", "real", "", None])
def test_mode_must_be_practice(raw, mode):
    raw["mode"] = mode
    with pytest.raises(ValidationError):
        Config.model_validate(raw)


def test_mode_is_required(raw):
    del raw["mode"]
    with pytest.raises(ValidationError):
        Config.model_validate(raw)


def test_unknown_key_rejected(raw):
    raw["risk"]["per_trad"] = 0.02  # typo
    with pytest.raises(ValidationError):
        Config.model_validate(raw)


@pytest.mark.parametrize(
    "path,value",
    [
        (("risk", "per_trade"), 0),
        (("risk", "per_trade"), 1.5),
        (("risk", "per_trade"), 0.05),  # above max_total_risk
        (("risk", "max_open_trades"), 0),
        (("regime", "adx_range"), 30),  # above adx_trend
        (("strategies", "mean_reversion", "rsi_low"), 80),
        (("data", "timeframes"), ["M15", "M1"]),
        (("data", "pairs"), ["EURUSD"]),
    ],
)
def test_bad_values_rejected(raw, path, value):
    bad = copy.deepcopy(raw)
    node = bad
    for k in path[:-1]:
        node = node[k]
    node[path[-1]] = value
    with pytest.raises(ValidationError):
        Config.model_validate(bad)


def test_strategy_pair_must_be_in_data_pairs(raw):
    raw["strategies"]["london_breakout"]["pairs"].append("USD_CAD")
    with pytest.raises(ValidationError, match="USD_CAD"):
        Config.model_validate(raw)


def test_every_pair_needs_default_spread(raw):
    del raw["costs"]["default_spread_pips"]["AUD_NZD"]
    with pytest.raises(ValidationError, match="AUD_NZD"):
        Config.model_validate(raw)


def test_config_is_immutable(cfg):
    with pytest.raises(ValidationError):
        cfg.risk.per_trade = 0.5


def test_load_config_from_path(tmp_path, raw):
    p = tmp_path / "c.yaml"
    p.write_text(yaml.safe_dump(raw))
    assert load_config(p).broker == "oanda"
