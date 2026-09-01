# AEGIS cycle status (fast watcher)

Tick: 548  |  UTC: 2026-09-01T18:28:12.026892+00:00

> Research-only watcher. No orders placed, no live YAML promoted. Champion
> promotion is reserved for the full `/aegis-cycle` run.

## Runtime health

- STALE: runner_process_down; runner_heartbeat_stale_1732s; journal_stale_1732s

## Outcome learning

- status: ok
- rows/exits: 3536 (report: outcome_learning.json)

## Book memory

- status: ok
- notes changed: False
- records: ?

## Strategy selection + ML

- status: ok
- exit research ran: False
- strategies shortlisted: 179.0
- unique actionable survivors: 36.0
- surviving hierarchy rows: 72.0
- ML improvement (expectancy): 1.6676

## Runtime

- outcome script: 1.4s
- book memory script: 0s
- ML script: 35.1s

## GitHub/book research DAG

- status: failed
- run: github-books-watcher-548-20260901T182807Z
- promotion: SHADOW_ONLY
- reasons: research_bundle_incomplete, required_node_not_successful, chronological_loss_observations_insufficient, missing_validation_metrics, sealed_expectancy_not_positive, sealed_profit_factor_not_above_one, sealed_loss_observations_insufficient, selected_strategy_evidence_missing, missing_or_invalid_p95_loss, missing_or_invalid_p99_loss, perturbation_not_stable, replay_parity_not_matched, validated_models_missing
