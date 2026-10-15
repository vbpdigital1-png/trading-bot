# HANDOFF

_Last updated: 2026-10-15_

## Current phase

**Phase 1: Foundations.** Code is complete and tested. The acceptance check is
**not yet met**, because no real market data has been loaded (see Open issues).

## Done

- Project skeleton, `pyproject.toml`, `.gitignore` (lists `.env` and data), `.env.example`, `Dockerfile`.
- `config.yaml` plus a strict Pydantic schema (`src/fxbot/config.py`):
  - `mode` only accepts `practice`, and unknown keys are rejected.
  - Values are range-checked, and pairs are cross-checked against strategies and spreads.
- JSON-lines logging to `logs/YYYY-MM-DD.jsonl` (`src/fxbot/monitor/logger.py`).
- Data layer (`src/fxbot/data/`):
  - `importers.py`: Dukascopy CSV (GMT or local time with offset, bid+ask merge) and generic CSV.
  - `clean.py`: the four cleaning rules.
    - Weekend = Friday 17:00 to Sunday 17:00 New York time, so DST is handled.
    - Gaps longer than `max_gap_candles` are reported; gaps on holiday closures are marked expected.
    - Spread is stored in pips.
  - `resample.py`: M15 up to H1/H4/D; refuses to resample downward.
    - H4 and D are aligned to the 17:00 New York close.
    - An incomplete trailing candle is dropped, so higher timeframes cannot see the future.
  - `providers.py`: the `DataProvider` protocol and `ParquetProvider`.
- `scripts/prepare_data.py`: import, clean, store all timeframes, write the gaps report and summary.
- 81 pytest tests, all passing. 11 years of M15 data for one pair cleans and resamples in under 1 second.

## Deliberately not built yet (needs broker / connectors)

- `OandaProvider` (live candles) and `scripts/download_data.py` (OANDA history download).
- Anything that talks to OANDA or Telegram. Those arrive in Phase 5 as planned.

## Next

1. Load real data:
   - Put Dukascopy bid/ask M15 CSVs for all 8 pairs (2015 to today) in `raw/`.
   - Run `scripts/prepare_data.py --raw-dir raw/`.
   - Review `data/reports/gaps.csv`.
2. If the gaps report is clean, Phase 1 is done. Then plan Phase 2 (London breakout and backtester) and get it approved.

## Open issues

- No real data yet, so the gaps report has not been checked against real feeds. Two things to watch:
  - Expect some quiet-period gaps around the daily 17:00 New York rollover.
  - We may need to decide whether those count as acceptable.
- Data from OANDA would need credentials. Dukascopy CSVs need none.
- Dockerfile pins Python 3.12. Dev here was also on 3.12.

## Latest validation numbers

None yet (no backtests until Phase 2).
