# Post-Repair Verification — Intelligent Firehose Audit Fixes

Generated: 2026-08-21T00:10Z (UTC)

## Git

- HEAD before audit fixes: `583e559`
- HEAD after: see `git rev-parse HEAD` at read time (commit: "aegis: audit fixes 1-16 ...")
- Branch: main, pushed to origin/main
- Commits this repair: audit-fix commit series (watcher/ingest/selection/governance/tests/artifacts)

## Tests

- Full suite: **659 passed, 0 failed, 0 skipped** (~58s)
- New regression coverage added for every confirmed defect:
  - watcher heartbeat accepts+persists `ingest`/`throughput` (defect 1)
  - `_parse_stdout_json` robust last-JSON parsing (defect 2)
  - maturity cursor: immature bar NOT labelled in cycle 1, labelled exactly once later; sequential cycles grow index without duplicates (defects 3/4)
  - cursor v2 round-trip + v1 migration (defect 3)
  - LEVEL A OOS family contamination FAILS the trained family (defect 6)
  - LEVEL C per-symbol OOS gates: negative-OOS symbol receives NO opportunity (defect 7)
  - strict OOS gate spot-checks incl. payoff floor (defect 8)
  - ML relative improvement with negative absolute EV is FAILURE (defect 10)
  - 20 new closed positions -> `new_closed_trades` trigger fires once; no repeat after marker advance; backward-compatible exit-row inference (defect 12)

## Root-cause fixes shipped

1. `write_heartbeat(..., ingest=..., throughput=...)` — persisted in watcher heartbeat.
2. `_run_script()` now returns `stdout_json` (last complete JSON object in stdout); `run_cycle` derives `ingest_added`; `added>0 => evidence_changed => research runs same cycle`.
3. Cursor v2 with separate `raw_cursor` / `label_cursor`. A bar observed before its forward horizon matured stays pending and is labelled exactly once later (dedupe by symbol/bar_time backs this). Live evidence: raw_cursor `2026-08-21 00:02`, label_cursor held at `2026-08-20 23:05`.
4. Fetch window includes pre-cursor warm-up (`WARMUP_BARS=400`); only NEW matured targets are appended. Labelling bounded to pending region.
5. Incremental labelling is step=1 (complete eligible-event sampling). No subsampling.
6. LEVEL A OOS filters by the SAME setup/family it trained on; real `strategy_family` persisted. Pre-existing zip bug that silently broke all LEVEL A validation found+fixed.
7. LEVEL C inheritance requires pool OOS pass AND per-symbol OOS gate pass.
8. `oos_gate`: n>=10, losses>=5, expectancy>0, PF>1, bootstrap p05>0, payoff>=0.25.
9. Measured cost profiles from journal spread observations (price->pips converted): per symbol/session p50/p75/p90 + observations + slippage + commission; validation cost = p75+slippage+commission; documented conservative fallback (2x config bps) when observations<30. Artifact: `intel/cost_profiles.json` (26 symbols measured; e.g. AUDCAD 0.7 vs AUDUSD 2.0 pips).
10. `ml_advances()` gate recorded in ml_pipeline report: absolute costed OOS expectancy must be >0 regardless of improvement.
11. Exit research n_rows=0 cause: it only runs on `--fetch` cadence ticks (MT5 M1 fetch); latest report predated a fetch tick. Not a code defect; next fetch tick populates it. Watcher summary exposes `exit_recommended`.
12. Outcome schema: writers emit `event_type: "position_exit"` (+`is_exit:true`); `is_exit_row()` infers safely for historical rows (is_exit / action exit|reduce / reconcile+pnl).
13. REAL council proof (free agents only, no Claude): case `identify-one-falsifiable-aegis-research-_e80e48`, mode REAL, 387s:
    - opencode AVAILABLE model `opencode/x-preview-f-free` proposal 115.0s + critique 111.3s
    - gemini AVAILABLE proposal 20.4s (then quota-limited on critique: honest)
    - codex/cursor UNAVAILABLE_QUOTA (honest)
    - decision: defer_validation / CHALLENGER_CREATED; artifacts under `ai_council/cases/case_.../`
14. Reproducibility: `.gitignore` whitelists the deterministic decision artifacts; committed to main: `validated_opportunities.json`, `validated_states.json`, `cost_profiles.json`, `demo_canary.json` (when a survivor exists). Each carries dataset_hash/config_hash/code_version.
15. Thesis ownership: thesis_id = symbol|side|setup_family|regime|session; tickets bound to exactly one thesis at fill time (`bind_tickets`); exits close ONLY owned tickets; unclaimed positions adopt a single held-key per side. Regression: two EURUSD BUY theses own distinct tickets; closing A does not mutate B.
16. Canary governance: global flag replaced by generated `demo_canary.v1` artifact bound to opportunity identity + dataset hash(index sha256) + validation hash + risk fraction + expiry. No artifact/expired/hash-mismatch => bootstrap stays UNVALIDATED_RESEARCH (shadow-only).

## Current state (post-fix, live)

- Validated opportunities: **0** — with measured costs and strict gates nothing currently qualifies (previous pooled GBPJPY survivor fails family-filtered OOS gates). Honest zero; not throttled artificially.
- Champion/canary: none. Heartbeat reports `strategy_status: UNQUALIFIED_NO_VALIDATED_MODEL`. No canary artifact => shadow decisions only, zero canary orders.
- Absolute OOS expectancy (ML proxy): still negative (all-holdout ≈ -0.91 pips/trade) → `ml_advances: false`. NOT a strategy.
- Runner: single instance (launcher 9868 -> interpreter 10940), heartbeat fresh (<5s), MT5 DEMO (trade_mode 0, MetaQuotes-Demo), `allow_live: false`.
- Watcher: scheduled task active (20-min cadence); each cycle ingests incrementally, refreshes throughput report, triggers council only on evidence.
- Fresh throughput snapshot (post-restart counters reset on runner side; journal aggregates include history): scans 35,424 | FIRE candidates 1,759 (historical window) | SCALE 0 | skip rate 94.9% dominated by `no_validated_strategy_model` (23,805) and `state_not_in_validated_set` (5,313). With zero validated opportunities, FIRE=0 going forward is CORRECT behavior until incremental ingestion accumulates enough per-symbol evidence to validate new opportunities.

## Why FIRE=0 is valid right now

Every entry requires: validated opportunity membership (symbol-aware, strict OOS gates, measured costs) AND a trading-stage model (champion or canary artifact). Neither exists at this HEAD. The system continues scanning, ingesting, labelling, reconciling, and researching; when a symbol's own evidence clears the gates, the pipeline regenerates opportunities + canary artifact automatically and legitimate throughput resumes.
