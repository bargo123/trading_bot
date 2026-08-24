# Task 4 Report: Firehose Turnover Evidence

## Delivered

- Added append-only Firehose lifecycle telemetry for confirmed opens, observed exit traces, and confirmed closes.
- Added `TurnoverMetrics.snapshot(now)` with hold-time, turnover, close-to-entry, utilization, capture, gross/net hourly, and cost metrics. Absent observed economics remain `null`.
- Added Firehose turnover metrics to runner heartbeat payloads without importing or calling Research Factory or AI Council.
- Added read-only analyzer support for confirmed `firehose_close` events and explicit `INCOMPLETE_JOURNAL_EVIDENCE` for malformed journals.
- Added integration tests covering two confirmed round trips, failed-close retention, confirmed close analysis, and malformed-history fail-closed reporting.

## Verification

- `python -m pytest tests/test_fast_firehose.py tests/test_fast_exit_production.py tests/test_fast_exit_integration.py tests/test_profit_harvester.py tests/test_firehose_turnover.py tests/test_firehose_harvest_research.py tests/test_firehose_harvest_integration.py -q`: 91 passed.
- `python -m pytest tests/test_research_factory.py tests/test_council_cycle.py tests/test_council_live.py -q`: 53 passed.
- Research Factory and AI Council import command: `imports-ok`.
- Read-only DEMO configuration assertion: `allow_live is False`; `exploration_max_risk_per_trade_usd == 0.15`.
- `python -m pytest -q`: 1024 passed, 1 existing event-loop deprecation warning.
- Historical analyzer completed and produced `reports/research/firehose_profit_harvest.{json,md}`.

## Evidence Result And Concern

The existing journal contains a NUL-prefixed malformed line at 136303. The generated report therefore states `INCOMPLETE_JOURNAL_EVIDENCE`, has zero completed lifecycles, null aggregate metrics, and `NO_EVIDENCE` policy comparison. No policy selection or profitability claim is made. No MT5/order/external process was started.
