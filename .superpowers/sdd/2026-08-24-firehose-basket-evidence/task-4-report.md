# Task 4: Runtime Basket Observability Report

## Changed Files

- `bot/aegis/intel/firehose_turnover.py`
- `bot/scripts/run_broker_paper.py`
- `bot/tests/test_firehose_basket_runtime.py`
- `.superpowers/sdd/2026-08-24-firehose-basket-evidence/task-4-report.md`

The pre-existing deleted root `task-4-report.md` was not recreated or changed.

## TDD Evidence

### RED

Command:

```text
..\.venv\Scripts\python.exe -m pytest tests\test_firehose_basket_runtime.py -q
```

Output before production implementation:

```text
ImportError: cannot import name 'basket_lifecycle_trace' from 'aegis.intel.firehose_turnover'
1 error in 1.12s
```

### GREEN

Command:

```text
..\.venv\Scripts\python.exe -m pytest tests\test_firehose_basket_runtime.py -q
```

Output after implementation:

```text
6 passed in 0.89s
```

## Implementation

- Added exact basket lifecycle trace formatting for confirmed tickets with persisted basket ownership.
- Added a `basket_closed` cleanup result derived from the persisted `TicketMetadataStore` snapshot; the final owned ticket's confirmed close releases its slot and marks the basket closed.
- Appended basket observations only in existing confirmed fill and confirmed close branches.
- Preserved legacy behavior when there is no exact basket ownership, including the no-artifact path. This task does not instantiate, mutate, or add to `BasketMetadataStore`.
- Preserved stale quote-fingerprint re-entry rejection and fresh-trigger admission behavior.
- Did not import Research Factory or AI Council.

## Broader Verification

Commands and outputs:

```text
..\.venv\Scripts\python.exe -m pytest tests\test_firehose_basket_runtime.py tests\test_firehose_turnover.py tests\test_firehose_basket.py tests\test_firehose_basket_replay.py -q
56 passed in 3.63s

..\.venv\Scripts\python.exe -m pytest tests\test_research_factory.py -q
24 passed in 4.49s

..\.venv\Scripts\python.exe -m pytest tests\test_council_cycle.py -q
26 passed in 3.38s

..\.venv\Scripts\python.exe -m pytest tests\test_run_broker_paper_helpers.py tests\test_research_isolation.py -q
6 passed in 0.97s

..\.venv\Scripts\python.exe -m compileall -q aegis\intel\firehose_turnover.py scripts\run_broker_paper.py
exit 0; no output

..\.venv\Scripts\python.exe -m pytest -q
1085 passed, 1 warning in 80.79s
```

The full-suite warning is an existing `eventkit` `DeprecationWarning` about no current event loop in `test_ibkr_order_hygiene`; there were no test failures.

## Safety Confirmation

- No orders were placed and no runner, MT5 instance, live trading, or external service CLI was launched.
- No entry, signal, order-placement, policy activation, configuration, YAML, Research Factory, AI Council, Book Brain, or `bot/aegis/research_factory/core.py` behavior was changed.
- The only runner additions run after existing broker-confirmed fill/close checks. They do not alter their decisions or outcomes.
- No basket is added without a validated artifact. Task 3 artifacts remain research-only and this task adds no runtime artifact source.

## Self-Review

- Reviewed the scoped diff and staged diff with `git diff --check`; no whitespace errors.
- Confirmed `BasketMetadataStore` has no public removal API, so runtime state release is limited to its supported persisted ticket-metadata ownership path.
- Confirmed exact traces retain basket/ticket identity, geometry, risk, cost evidence, lifecycle metrics, regime, session, and slot/basket closure state.
- Confirmed unconfirmed closes and legacy tickets do not emit basket traces or release basket lifecycle state.

## Commit

Implementation commit: `6b677a0 feat: trace firehose basket evidence`

## Concerns

No runtime source for a Task 3 validated policy artifact exists by design. Therefore, this task correctly leaves new basket creation inactive and observes only exact persisted basket ownership if present. A future, separately approved artifact-consumption task is required before new runtime basket ownership can be created.

## Fix Round 1/5

### Findings And Root Cause

- `confirmed_close_cleanup` used a single `released` value for both metadata removal and basket slot release. A confirmed non-final basket clip therefore reported `slot_released=True` even though exact persisted ownership still contained another ticket.
- The confirmed `firehose_close` event already used null economics when no broker deal record was available. The subsequent basket trace contradicted that fail-closed path by using pre-close `close_summary()` floating PnL and metadata cost fields as realized economics.

### Changes

- Kept `metadata_removed=True` for every confirmed owned ticket close, but set `slot_released=True` only for a legacy non-basket ticket or the final exact ticket in a basket.
- Kept `realized_net_usd`, `cost_usd`, and derived `capture_ratio` null in basket close traces until broker-confirmed close economics are available. This leaves replay evidence incomplete rather than labeling local estimates as realized values.
- Removed the runner's local realized-PnL, cost, and capture calculations from the basket close observation.
- Added regression assertions for non-final basket slots and no-evidence close economics.

### RED / GREEN Evidence

Initial RED command:

```text
..\.venv\Scripts\python.exe -m pytest tests\test_firehose_basket_runtime.py -q
```

Initial RED output:

```text
2 failed, 4 passed in 1.22s
```

The failures were the expected local `realized_net_usd=3.0`, `cost_usd=0.3`, and `capture_ratio=0.75` values and the expected incorrect `slot_released=True` for the first of two owned tickets.

Self-review RED command after separating the slot result:

```text
..\.venv\Scripts\python.exe -m pytest tests\test_firehose_basket_runtime.py -q
```

Self-review RED output:

```text
1 failed, 5 passed in 1.15s
```

This caught that `metadata_removed` had been coupled to slot release. The final fix preserves metadata removal while withholding only the basket slot release.

Final GREEN command and output:

```text
..\.venv\Scripts\python.exe -m pytest tests\test_firehose_basket_runtime.py tests\test_firehose_turnover.py -q
12 passed in 1.06s
```

### Broader Verification

```text
..\.venv\Scripts\python.exe -m pytest tests\test_firehose_basket_runtime.py tests\test_firehose_turnover.py tests\test_firehose_basket.py tests\test_firehose_basket_replay.py -q
56 passed in 4.35s

..\.venv\Scripts\python.exe -m pytest tests\test_research_factory.py tests\test_council_cycle.py tests\test_run_broker_paper_helpers.py tests\test_research_isolation.py -q
56 passed in 7.88s

..\.venv\Scripts\python.exe -m compileall -q aegis\intel\firehose_turnover.py scripts\run_broker_paper.py
exit 0; no output

..\.venv\Scripts\python.exe -m pytest -q
1085 passed, 1 warning in 98.85s
```

The existing full-suite `eventkit` no-current-event-loop `DeprecationWarning` remains the only warning.

### Safety And Self-Review

- No orders, runner, MT5 process, live trading, configuration, YAML, entry path, or order-placement path was changed or invoked.
- No Research Factory, AI Council, Book Brain, or unrelated dirty file was changed.
- The runner still appends basket traces only after its existing broker-confirmed close check.
- The final review verified exact metadata remains removed for confirmed intermediate clips, while their basket slot remains unavailable until the final exact ticket closes.
- The final review verified no pre-close local PnL or metadata cost can populate realized/cost/capture close fields.
- `git diff --check` reported no whitespace errors (only pre-existing LF-to-CRLF warnings).

### Fix Commit

`527dd11 fix: fail close firehose basket traces`

### Remaining Concern

Broker-confirmed deal economics are not exposed in this runner path. Close traces now correctly remain `NO_EVIDENCE` for realized/cost/capture until a separately approved broker-deal reconciliation integration supplies those values.
