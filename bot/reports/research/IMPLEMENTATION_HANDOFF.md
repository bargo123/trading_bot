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

## SECOND INDEPENDENT AUDIT (completed)

Reread MASTER_SPEC line by line against the ledger, git diff, tests, runtime:

| Spec section | Ledger IDs | Status |
|---|---|---|
| Protocol steps 1-12 | process | executed (spec saved verbatim; ledger maintained; verifier built; this doc maintained) |
| A corpus/statuses/taxonomy/conflicts/generation/retrieval | EF-100..106 | VERIFIED |
| B/C/D/E/F profit mgmt + per-ticket + 0.01-lot | EF-107..111 | VERIFIED |
| G exit learning / H capture metrics / I screenshot scenario | EF-112..114 | VERIFIED |
| J self-hedge / K margin / L exits-from-books / M point-in-time / N gates intact | EF-115..119 | VERIFIED |
| O heartbeat / P exit-layer replacement + explicit exit plans | EF-120..121 | VERIFIED |
| Prior merge-blockers (governance, caps, funnel, rates, council, artifacts, thesis ownership, costs, ingestion) | EF-001..016 | VERIFIED |

Honest notes:
- Trailing STRUCTURAL stop (spec D4) exists as tighten-only lock + candidate
  policy; full swing-based trailing is a listed extension, not silently claimed.
- Live book_logic fires await qualifying geometry: current candidates are ALL
  hard-rejected (exploration_destructive_payoff 189+, exploration_min_lot_
  exceeds_risk_budget 113+) - FIRE=0 is the correct, explained outcome.
- Legacy 198 ACTIVE experiments predate the reachable lifecycle; they drain to
  EXHAUSTED/REJECTED as their closes flow through the new _judge.

## FRESH RUNTIME EVIDENCE (post-fix runner)

- reports/research/exploration_fresh_report.json: funnel, PM decision counts
  (HOLD=1480 / LOCK=2 / EXIT=1 live), experiment distribution, journal-since-
  fix counters (classified triggers, hard rejects, inventory events),
  last position inventory with legacy flags, economic claim.
- Heartbeat blocks: profit_management (per-ticket table incl entry_ev vs
  remaining_ev + status), exposure (per-symbol hedged + est cost),
  funnel, rates, skip_reasons.
- Journal: position_inventory classifies every open ticket (origin/
  exploration/hypothesis/thesis/legacy/comment/risk); exploration_limit_skip
  reasons include margin pressure; pm_exit/pm_lock decisions persisted.

## Economic claim (audit item 14)

NO VALIDATED PROFITABLE CHAMPION EXISTS. Historical aggregate remains
~n=2471 WR=67.83% PF=0.769 expectancy=-0.0110 net=-27.17. Exploration trades
are information purchases, never proof of edge.

## Rollback

Each concern is isolated: revert the branch commit range; runtime artifacts
(`intel/exploration_experiments.json`, `bot/knowledge/*`) are append-only or
regenerable via the two build scripts.
