# trading-bot

Rule-based forex bot: three strategies (London breakout, Donchian trend, Bollinger/RSI
mean reversion), a regime detector that switches them on and off, and a risk manager
with veto power over every order. **Practice accounts only.** No LLM makes trading
decisions; no martingale, grid or averaging down.

Build status and next steps: see [HANDOFF.md](HANDOFF.md).

## Setup

```bash
uv venv -p 3.12 .venv && uv pip install -p .venv -e ".[dev]"   # or: pip install -e ".[dev]"
.venv/bin/pytest
```

## Getting data (no broker needed)

1. Export M15 candles from Dukascopy (bid and ask separately, GMT time) for each pair
   from 2015-01-01 to today, and save them as `raw/EUR_USD_bid.csv`, `raw/EUR_USD_ask.csv`, etc.
2. Run:

   ```bash
   .venv/bin/python scripts/prepare_data.py --raw-dir raw/
   ```

This cleans the data, writes `data/{pair}/{M15,H1,H4,D}.parquet`, and writes
`data/reports/gaps.csv` and `data/reports/clean_summary.json`. It exits non-zero if
any pair fails or any unexpected gap is found.

## Layout

```
config.yaml            all tunable values (validated on startup)
src/fxbot/config.py    Pydantic schema; mode must be "practice"
src/fxbot/data/        CSV import, cleaning, resampling, Parquet provider
src/fxbot/monitor/     JSON-lines logging
scripts/               command-line entry points
tests/                 pytest suite
```
