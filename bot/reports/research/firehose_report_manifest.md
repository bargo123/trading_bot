# Firehose evidence reports

This branch includes the concise, reviewable reports produced by the governed
Firehose research and DEMO verification work:

- `short_horizon_model_runtime_proof.json` — current model status, target,
  hashes, horizons, calibration, captured-WR, sealed OOS, and loss geometry.
- `fast_edge_experiment_handoff.json` — current experiment handoff.
- `fast_edge_factory_handoff.json` and `fast_edge_leaderboard.json` — Factory
  handoff and ranked experiment evidence.
- `fast_trade_autopsy.json`, `outcome_learning.json`, and
  `outcome_learning.md` — reconciled fast-trade outcome learning.
- `ml_pipeline.json` — pipeline evidence.
- `firehose_throughput.json`, `firehose_harvest_baseline.json`,
  `firehose_harvest_baseline.md`, and `firehose_reentry_guard.json` — turnover,
  harvest, and re-entry evidence.
- `claude/mt5_demo_check.json` — read-only MT5 DEMO connectivity/account
  verification.

Large raw quote/event traces, runtime logs, and mutable broker telemetry remain
local and are intentionally not committed as reports. The model runtime
artifact remains governed by the existing artifact-loading policy; its current
hashes and metrics are captured in `short_horizon_model_runtime_proof.json`.
