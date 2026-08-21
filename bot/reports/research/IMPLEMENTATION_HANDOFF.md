# IMPLEMENTATION HANDOFF — Exploration Firehose + Master Spec

Branch: `opencode/exploration-firehose`
Ledger: `bot/reports/research/master_spec_status.json` (EF-001…EF-121)
Verifier: `python bot/scripts/verify_master_spec.py [--runtime]`
Spec: `docs/aegis/EXPLORATION_FIREHOSE_MASTER_SPEC.md`

## How to verify everything

```
cd bot
..\.venv\Scripts\python.exe -m pytest tests -q          # full suite
..\.venv\Scripts\python.exe scripts\verify_master_spec.py --runtime
..\.venv\Scripts\python.exe scripts\build_book_knowledge.py   # rebuild KB (restart-safe)
..\.venv\Scripts\python.exe scripts\firehose_throughput.py    # funnel report
..\.venv\Scripts\python.exe scripts\profit_report.py          # capture metrics
```

## Architecture map (by spec section)

| Spec | Implementation |
|---|---|
| A: corpus ingestion/statuses | `aegis/research/book_knowledge.py`, `scripts/build_book_knowledge.py` → `bot/knowledge/*` (6,332 records; 52 INDEXED / 2 PARTIALLY_INDEXED) |
| A: structured sinks | `bot/knowledge/{concepts,strategy_hypotheses,entry_patterns,exit_patterns,regime_rules→concepts,risk_rules,execution_rules,validation_rules}.jsonl` + `source_index.json` + `corpus_manifest.json` (corpus_version hash) |
| A: conflicts | polarity tags continuation/fade; records never merged; conflict_topic groups |
| A: book-backed generation | `aegis/intel/knowledge_retrieval.py` (state-hash+version LRU cache) → `firehose_brain._maybe_explore` attaches source hashes/exit_plan/book_logic to every registered experiment |
| B/C/D/E/F: profit management | `aegis/intel/profit_management.py` (per-ticket MFE/MAE/giveback/breakeven-lock/time-decay/regime/portfolio-pressure; WHY strings; 0.01-lot = close-or-tighten-stop) wired in `run_broker_paper.py` pre-pass (`pm_exit`/`pm_lock` journal events) |
| G: exit learning | `ProfitManager.close_summary` → `ExperimentStore.record_close(**extra)` stores pl_1m…60m + counterfactual policy profits per trade |
| H/M: metrics | `scripts/profit_report.py` → `reports/research/profit_capture.json` (capture ratios by family/symbol/side/session/regime/exit/stage; point-in-time note) |
| J: self-hedge | brain `_maybe_explore` blocks same-family opposite exposure (`self_hedge_blocked_same_family`); heartbeat `exposure` block (gross long/short/net/hedged) |
| K: margin | runner exploration guard: `exploration_min_free_margin_usd` (20) / `exploration_max_margin_fraction` (0.4) — blocks NEW exploration first |
| O: heartbeat | `profit_management` block (floating pnl/mfe/giveback, w2l count, capture ratio, lock counts, decision_counts, per-ticket table) + `exposure` |
| P: exit layer | intelligent-mode PM pre-pass replaces bypassed CORE quick-win path; every experiment registers an explicit `exit_plan` |

## Runtime evidence captured (2026-08-21)

- Runner single pair live; heartbeat fresh (<5s); `status: running`; no error field.
- Heartbeat `profit_management`: decision_counts HOLD=27+ on first cycles; 9 tickets tracked with per-ticket pnl/mfe/age.
- Heartbeat `exposure`: gross_long 0.05 / gross_short 0.04 lots, net 0.01, hedged 0.04.
- Funnel counters live in heartbeat (`scans/candidates/exploration_fire/skip`).
- Book KB build output: counts_by_status {INDEXED:52, PARTIALLY_INDEXED:2}; counts_by_type incl. STRATEGY_HYPOTHESIS 365, EXIT_PRINCIPLE 603.

## Observation items (non-blocking)

- First live SL/TP closes will populate `pl_*`/counterfactual fields inside
  `intel/exploration_experiments.json` trades and `profit_capture.json`;
  attribution is wired via `position_map` (entry-deal comment → position_id).
- codex quota resets ~18:39 local; cursor probe timed out once — both rejoin
  automatically via cached probes; never blocking, always truthful.

## Rollback

Each concern is isolated: revert the branch commit range; runtime artifacts
(`intel/exploration_experiments.json`, `bot/knowledge/*`) are append-only or
regenerable via the two build scripts.
