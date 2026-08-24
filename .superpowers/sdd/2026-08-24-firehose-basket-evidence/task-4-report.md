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
