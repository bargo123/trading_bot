# Task 4 Report

## RED/GREEN Evidence

- RED: `..\\.venv\\Scripts\\python.exe -m pytest tests\\test_research_factory_walk_forward.py -q`
  failed during collection with `ModuleNotFoundError: No module named 'aegis.research_factory.walk_forward'`.
- GREEN: the same command passed: `3 passed in 3.17s`.
- The Plan 1 terminal-outcome assertion was updated after the full suite proved it expected the intentionally replaced `FAILED` status.

## Verification

- Focused: `..\\.venv\\Scripts\\python.exe -m pytest tests\\test_research_factory_rules.py tests\\test_research_factory_replay.py tests\\test_research_factory_evaluation.py tests\\test_research_factory_walk_forward.py -q`
  Result: `124 passed in 4.07s`.
- Full: `..\\.venv\\Scripts\\python.exe -m pytest -q`
  Result: `956 passed, 1 warning in 89.44s`.
  The warning is the existing `eventkit` no-current-event-loop deprecation in `test_ibkr_order_hygiene.py`.

## Files And Hunks

- Added `bot/aegis/research_factory/walk_forward.py`: expanding chronological folds, fresh pipeline training on each prefix, prediction-gated replay, observed-only aggregation, and fail-closed terminal statuses.
- Updated `bot/aegis/research_factory/replay.py`: optional explicit ML entry-signal gate, preserving the existing replay cost and broker-spec calculations.
- Updated `bot/aegis/research_factory/core.py`: canonical compilation and evaluator delegation in `_test_hypothesis`; replaced the Plan 1 replay-not-configured failure with `NO_EVIDENCE`.
- Added `bot/tests/test_research_factory_walk_forward.py`: expanding-prefix/no-future, observed-cost decision, and outcome-persistence coverage.
- Updated `bot/tests/test_research_factory_data_integrity.py`: expected terminal status now matches Task 4's required missing-cost outcome.

## Self-Review And Concerns

- No factory, MT5, YAML, order, or external CLI operation was run.
- Fold sizing uses only the supplied non-sealed frame. Prefix rows are replay context only and are explicitly signal-gated off, so no prefix trade can occur.
- Missing costs are `NO_EVIDENCE`; failed, non-executable, no-data, and rejected results cannot become `CHALLENGER`.
- `core.py` retains inactive legacy helper methods below the new delegation path. They are not invoked by the Task 4 flow, but a follow-up cleanup should remove them rather than risk external callers using their obsolete fabricated-cost behavior.
- The pre-existing unrelated Claude/fallback cleanup in `core.py` remains unstaged.
