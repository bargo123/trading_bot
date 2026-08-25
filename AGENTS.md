# AEGIS Intelligent Firehose — agent instructions

This is the autonomous quant research lab for the AEGIS Intelligent Firehose
trading bot. Everything here is **research-only unless explicitly governed**.

## Non-negotiable safety rules

1. ## MT5 Trading Policy

MT5 DEMO order execution is explicitly allowed for the designated AEGIS Firehose execution runner.

Allowed:
- MT5 DEMO accounts only
- `engine: mt5`
- `mode: mt5_demo`
- `allow_live: false`
- `paper_trading_enabled: true`
- `dry_run: false`
- actual DEMO `mt5.order_send()` through the existing governed Firehose execution path
- opening, modifying, and closing DEMO positions
- exactly one broker-execution owner process

The designated execution owner is:
`bot/scripts/run_broker_paper.py`

Research components remain strictly read-only:
- AI Council
- Claude
- Hermes/free-model Council agents
- Research Factory
- Research Fast Watcher
- Book Brain
- research probes
- historical/ML processes

These components must never call `mt5.order_send()` or directly modify broker positions.

STRICTLY FORBIDDEN:
- real-money/live account execution
- `allow_live: true`
- bypassing the DEMO account check
- submitting orders from Council/Research processes
- silently increasing configured trading risk
- duplicate broker execution processes

Before any MT5 mutation, the runtime must verify:
- account is DEMO/contest
- `allow_live == false`
- `mode == mt5_demo`
- `paper_trading_enabled == true`
- terminal `trade_allowed == true`
- account `trade_expert == true`

If the account is not DEMO, fail closed and submit no order.

The Firehose may place actual MT5 DEMO positions when its existing strategy,
risk, quote, spread, economics, OMS, portfolio, and execution gates authorize
a trade.

Do not force trades merely to demonstrate execution.

2. **MT5 DEMO config policy.** Trading YAML remains protected by default.
   However, the designated DEMO Firehose config,
   `bot/config_mt5_demo_firehose_hw.yaml`, has an explicit operator-approved
   exception: `max_daily_loss_percent: 0`. This intentionally disables the
   global daily-loss halt for this MT5 DEMO research environment. Agents must
   not automatically restore or increase that value based on generic risk
   recommendations.

   This exception applies only to MT5 DEMO and does not authorize:
   - real-money execution or `allow_live: true`
   - changing away from `mode: mt5_demo`
   - bypassing DEMO-account verification
   - silently increasing per-trade quantity or risk
   - removing broker, quote, EV, spread, OMS, or total-drawdown checks
   - Council, Factory, Watcher, Book Brain, or research processes placing
     orders

   Loss containment must remain governed primarily by per-trade risk,
   prediction abstention, rapid invalidation/scratch, remaining-EV and
   tail-loss controls, confirmed close, and immediate rescan. The absence of
   a global daily halt is intentional and must not be treated as a defect.

   Any other protected trading-config change still requires explicit operator
   authorization. `bot/aegis/research/ingest.py`'s `PROTECTED_LIVE_YAML` and
   all non-designated trading YAML remain immutable. Research configs are
   separate and safe.
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

- Only commit when asked. For this work, commit on branch
  `opencode/exploration-firehose`.
- Never commit secrets or live config. Generated reports and experiment
  records are welcome.
- Use concise messages describing findings, not just "done".
