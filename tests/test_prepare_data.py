import importlib.util
import json

import pandas as pd
import yaml

from fxbot.data.providers import ParquetProvider

from .conftest import ROOT, make_candles

spec = importlib.util.spec_from_file_location("prepare_data", ROOT / "scripts" / "prepare_data.py")
prepare_data = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare_data)


def write_duka(path, df):
    out = pd.DataFrame(
        {
            "Gmt time": df.index.strftime("%d.%m.%Y %H:%M:%S.000"),
            "Open": df["open"],
            "High": df["high"],
            "Low": df["low"],
            "Close": df["close"],
            "Volume": df["volume"],
        }
    )
    out.to_csv(path, index=False)


def setup(tmp_path, gap=False):
    raw = tmp_path / "raw"
    raw.mkdir()
    # Two weeks of continuous candles; the weekend is dropped by cleaning.
    bid = make_candles("2024-01-07 22:00", 4 * 24 * 12, seed=3)
    if gap:
        bid = bid.drop(bid.index[100:110])
    ask = bid + [0.00012, 0.00012, 0.00012, 0.00012, 0, 0]
    write_duka(raw / "EUR_USD_bid.csv", bid)
    write_duka(raw / "EUR_USD_ask.csv", ask)

    cfg = yaml.safe_load((ROOT / "config.yaml").read_text())
    cfg["data"]["dir"] = str(tmp_path / "data")
    cfg["data"]["history_start"] = "2024-01-01"
    cfg["logging"]["dir"] = str(tmp_path / "logs")
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(yaml.safe_dump(cfg))
    return raw, cfg_path


def test_end_to_end(tmp_path):
    raw, cfg_path = setup(tmp_path)
    rc = prepare_data.main(["--config", str(cfg_path), "--raw-dir", str(raw), "--pairs", "EUR_USD"])
    assert rc == 0

    p = ParquetProvider(tmp_path / "data")
    m15 = p.latest("EUR_USD", "M15", 10_000)
    assert m15["spread"].round(6).eq(1.2).all()
    for tf in ("H1", "H4", "D"):
        assert not p.latest("EUR_USD", tf, 10_000).empty
    summary = json.loads((tmp_path / "data" / "reports" / "clean_summary.json").read_text())
    assert summary[0]["gaps_unexpected"] == 0
    assert summary[0]["weekend_dropped"] > 0
    assert list((tmp_path / "logs").glob("*.jsonl"))


def test_gap_fails_run_and_is_reported(tmp_path):
    raw, cfg_path = setup(tmp_path, gap=True)
    rc = prepare_data.main(["--config", str(cfg_path), "--raw-dir", str(raw), "--pairs", "EUR_USD"])
    assert rc == 1
    gaps = pd.read_csv(tmp_path / "data" / "reports" / "gaps.csv")
    assert gaps["missing_candles"].tolist() == [10]


def test_missing_pair_fails(tmp_path):
    raw, cfg_path = setup(tmp_path)
    rc = prepare_data.main(["--config", str(cfg_path), "--raw-dir", str(raw), "--pairs", "GBP_USD"])
    assert rc == 1
