---
description: Run the full autonomous AEGIS research cycle (reports only; never trades, never promotes live YAML without the governed pipeline).
---

You are running the full AEGIS research cycle for the Intelligent Firehose at
`C:\Users\Zaid barghouthi\Desktop\trading_bot\bot`. This is a **research-only**
cycle: read artifacts, recompute evidence, record experiments, and write
reports. You must **never** place orders and **never** edit live trading YAML.

## Constraints (hard)

1. No orders. No `allow_live`. No editing `bot/config*.yaml` or any live runner
   config. `bot/aegis/research/ingest.py` defines `PROTECTED_LIVE_YAML` — treat
   it as immutable.
2. MT5 access is read-only (fetching bars / quotes is fine; trading is not).
3. Champion promotion is governed: it may only be written through
   `bot/scripts/research_promote_champion.py` or
   `bot/scripts/research_asia_sell_strategy.py`, and only when every gate passes.
4. Every experiment goes into `bot/research/experiments.sqlite` via
   `ExperimentRegistry`. Do not skip the registry.
5. Run the test suite before and after the cycle; report the pass count.
6. Never fabricate metrics. If a script fails, record the failure honestly.

## Steps (run from `bot` with `..\.venv\Scripts\python.exe`)

1. **Baseline**: run `..\.venv\Scripts\python.exe -m pytest -q` and record the
   pass count.
2. **Outcome learning**: `..\.venv\Scripts\python.exe scripts\research_outcome_learning.py`
   → consume `bot/intel/outcome_log.jsonl`, write
   `bot/reports/research/outcome_learning.json`.
3. **Book memory**: `..\.venv\Scripts\python.exe scripts\research_book_memory.py`
   → rebuild `bot/research/book_memory/` from `bot/research/source_notes/`.
4. **ML + exit research + strategy selection**:
   `..\.venv\Scripts\python.exe scripts\research_ml_pipeline.py --fetch`
   → writes `bot/reports/research/ml_pipeline.json` (exit horizons, strategy
   selection, ridge model, SVG equity/drawdown charts).
5. **Asia-session edge (periodic)**: run
   `..\.venv\Scripts\python.exe scripts\research_asia_edge.py` and, if the
   state survives the exclusions and walk-forward, run
   `..\.venv\Scripts\python.exe scripts\research_asia_sell_strategy.py`
   (which goes through the governed promotion and will reject on gate failure).
6. **Governed promotion**: only if the ML/exit research produced a candidate
   with a positive-costed holdout and the strategy model is ready, run
   `..\.venv\Scripts\python.exe scripts\research_promote_champion.py --spec <spec>`.
7. **Re-verify**: run `..\.venv\Scripts\python.exe -m pytest -q` again and
   report the pass count.
8. **Write status**: update `bot/reports/research/aegis_cycle_status.md` with a
   summary of each phase (experiment IDs, key metrics, rejections), and update
   the OpenCode `STATUS` file if present.
9. **Commit** the generated reports, new experiments, and code changes on the
   current branch (`opencode/aegis-infra`) with a message describing what the
   cycle found. Do not commit secrets or live config.

## Report format

End with a concise summary containing: experiment IDs recorded, key metrics
(expectancy/PF where meaningful), any rejections and why, the pytest pass
count before/after, and confirmation that `mt5_touched`, `placed_orders`, and
`promoted_live_yaml` are all `false` (unless a governed promotion legitimately
accepted a champion — in which case report the frozen/sealed hashes).