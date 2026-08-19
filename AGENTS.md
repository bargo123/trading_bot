# AEGIS Intelligent Firehose — agent instructions

This is the autonomous quant research lab for the AEGIS Intelligent Firehose
trading bot. Everything here is **research-only unless explicitly governed**.

## Non-negotiable safety rules

1. **Never trade.** No order placement, no `allow_live`, no live account access.
   MT5 terminal access is **read-only** (fetch bars/quotes, never trade).
2. **Never edit live trading YAML.** `bot/config*.yaml`,
   `bot/aegis/research/ingest.py`'s `PROTECTED_LIVE_YAML`, and any runner
   config are immutable. Research configs are separate and safe.
3. **Champion promotion is governed.** `intel/intelligent_champion.json` is
   written ONLY by `bot/scripts/research_promote_champion.py` or
   `bot/scripts/research_asia_sell_strategy.py`, and only after every gate in
   `bot/aegis/research/promote.py` passes. A rejected challenger is kept on
   record (`bot/research/strategies/`, `bot/research/sealed_holdouts.jsonl`),
   never promoted.
4. **Every experiment is recorded.** Use `ExperimentRegistry`
   (`bot/research/experiments.sqlite`). Never skip the registry.
5. **No fabricated metrics.** If a script fails, record the failure honestly.
6. **Costs and lookahead matter.** Outcomes must be net of the runner's
   spread/slippage assumptions; features must never peek at the label.
7. **Run tests.** `bot` → `..\.venv\Scripts\python.exe -m pytest -q`. Baseline
   suite must stay green; report pass counts before/after any work.

## Repo layout (key paths, relative to repo root)

- `bot/aegis/research/` — research modules (analogues, book_memory, promote,
  exit_research, ml_pipeline, asia_sell_strategy, outcome_learning, ...)
- `bot/aegis/intel/` — runtime intel (lifecycle, expected_value,
  strategy_model, paths, ...)
- `bot/scripts/` — research entry points
- `bot/tests/` — pytest suite (must stay green)
- `bot/intel/` — runtime artifacts (analogue_index.json, outcome_log.jsonl,
  intelligent_champion.json, ...)
- `bot/research/` — experiment registry (experiments.sqlite), book memory,
  sealed holdouts, strategy specs
- `bot/reports/research/` — generated research reports (JSON + Markdown)
- `bot/mql5/` — EA skeletons (research, not enabled)

## Research cycle

Run the full cycle with the `/aegis-cycle` command or the 20-min fast watcher:
`bot` → `..\.venv\Scripts\python.exe scripts\research_fast_watcher.py`.

## Commit etiquette

- Only commit when asked. Commit on branch `opencode/aegis-infra`.
- Never commit secrets or live config. Generated reports and experiment
  records are welcome.
- Use concise messages describing findings, not just "done".