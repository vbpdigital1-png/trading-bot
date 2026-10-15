"""Import raw M15 CSVs, clean them, store Parquet for every timeframe, and write
a gaps report.

Input files in --raw-dir (per pair, either):
    EUR_USD_bid.csv + EUR_USD_ask.csv   (Dukascopy bid/ask exports, preferred)
    EUR_USD.csv                         (single mid/bid file; default spread used)

Output:
    data/{pair}/{tf}.parquet
    data/reports/gaps.csv
    data/reports/clean_summary.json

Usage:
    python scripts/prepare_data.py --raw-dir raw/
    python scripts/prepare_data.py --raw-dir raw/ --pairs EUR_USD GBP_USD
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from fxbot.config import Config, load_config
from fxbot.data.clean import MarketHours, clean_candles
from fxbot.data.importers import combine_bid_ask, read_csv_candles
from fxbot.data.providers import write_candles
from fxbot.data.resample import resample
from fxbot.monitor.logger import get_logger, log_event, setup_logging

log = get_logger("data")


def load_raw(raw_dir: Path, pair: str, assume_tz: str | None) -> pd.DataFrame:
    bid, ask, single = raw_dir / f"{pair}_bid.csv", raw_dir / f"{pair}_ask.csv", raw_dir / f"{pair}.csv"
    if bid.exists() and ask.exists():
        return combine_bid_ask(read_csv_candles(bid, assume_tz), read_csv_candles(ask, assume_tz))
    if single.exists():
        return read_csv_candles(single, assume_tz)
    raise FileNotFoundError(f"no raw CSV for {pair} in {raw_dir} (expected {bid.name}+{ask.name} or {single.name})")


def market_hours(cfg: Config) -> MarketHours:
    d = cfg.data
    return MarketHours(d.market_timezone, d.week_close, tuple(d.holiday_closures))


def prepare_pair(cfg: Config, raw_dir: Path, pair: str, assume_tz: str | None):
    hours = market_hours(cfg)
    base = cfg.data.base_timeframe
    raw = load_raw(raw_dir, pair, assume_tz)
    start = pd.Timestamp(cfg.data.history_start, tz="UTC")
    raw = raw[raw.index >= start]

    m15, report = clean_candles(
        raw, pair, base, hours, cfg.data.max_gap_candles, cfg.costs.default_spread_pips[pair]
    )
    write_candles(m15, cfg.data.dir, pair, base)
    for tf in cfg.data.timeframes:
        if tf != base:
            write_candles(resample(m15, base, tf, hours), cfg.data.dir, pair, tf)

    summary = report.summary() | {
        "first": str(m15.index[0]) if len(m15) else None,
        "last": str(m15.index[-1]) if len(m15) else None,
    }
    log_event(log, "pair_prepared", **summary)
    return summary, report.gaps


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--raw-dir", required=True, type=Path)
    ap.add_argument("--pairs", nargs="*", help="default: all pairs in config")
    ap.add_argument("--assume-tz", help="timezone for naive timestamps in generic CSVs")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    setup_logging(cfg.logging.dir, cfg.logging.level)
    pairs = args.pairs or cfg.data.pairs

    summaries, gaps, failed = [], [], []
    for pair in pairs:
        try:
            s, g = prepare_pair(cfg, args.raw_dir, pair, args.assume_tz)
            summaries.append(s)
            gaps.append(g)
        except Exception as e:  # report every pair, then fail at the end
            log_event(log, "pair_failed", level=40, pair=pair, error=str(e))
            failed.append(pair)

    reports = Path(cfg.data.dir) / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    all_gaps = pd.concat(gaps, ignore_index=True) if gaps else pd.DataFrame()
    all_gaps.to_csv(reports / "gaps.csv", index=False)
    (reports / "clean_summary.json").write_text(json.dumps(summaries, indent=2))

    unexpected = int((~all_gaps["expected"]).sum()) if len(all_gaps) else 0
    log_event(log, "prepare_done", pairs_ok=len(summaries), pairs_failed=failed, unexpected_gaps=unexpected)
    return 1 if failed or unexpected else 0


if __name__ == "__main__":
    sys.exit(main())
