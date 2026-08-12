# IBKR Paper Reliability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a paper-only IBKR stack with durable macOS supervision, convergent cancel/flatten behavior, trustworthy order display, explicit bracket TIF, cost gating, and one status/control command.

**Architecture:** A shared IB order-state module defines working statuses and deduplication. `IBKREngine` owns broker mutation and convergence. A launchd-owned watchdog owns bot/dashboard child processes, while `scripts/aegis_paper.py` provides start, stop, restart, status, and flatten commands.

**Tech Stack:** Python 3.9, `ib_insync` 0.9.86, pandas, PyYAML, macOS launchd/launchctl, direct assertion-based Python tests.

## Global Constraints

- Gateway paper port is 4002; mutation commands refuse ports 4001 and 7496 and any non-paper port.
- Keep `allow_live: false`; do not implement live trading.
- Do not start the supervisor or send/cancel/flatten broker orders during implementation verification.
- Preserve existing uncommitted user work and do not stage logs, journal data, account data, or unrelated files.
- Every-bar firehose is disabled by default and is never presented as a profitable edge.

---

### Task 1: Shared IB order state and account polling

**Files:**
- Create: `bot/aegis/engines/ibkr_order_state.py`
- Modify: `bot/aegis/engines/base.py`
- Modify: `bot/aegis/engines/ibkr.py`
- Modify: `bot/aegis/engines/mt5.py`
- Test: `bot/tests/test_ibkr_order_hygiene.py`

**Interfaces:**
- Produces: `WORKING_STATUSES`, `CANCELLING_STATUSES`, `is_working_status(status: str) -> bool`, `trade_identity(trade) -> tuple`, and `working_trades(trades) -> list`.
- Produces: `IBKREngine.working_orders()`, `IBKREngine.cancel_all_orders(timeout_s=10.0, poll_s=0.2)`, and `IBKREngine.flatten_positions(symbol=None, timeout_s=15.0)`.

- [ ] **Step 1: Write failing status and account tests**

```python
def test_pending_cancel_is_not_displayed_as_working():
    assert is_working_status("Submitted")
    assert not is_working_status("PendingCancel")
    assert not is_working_status("Cancelled")

def test_account_uses_cached_values_without_summary_subscription():
    fake = FakeIB(account_values=ACCOUNT_VALUES)
    engine = connected_engine(fake)
    snapshot = engine.account()
    assert snapshot.equity == 250_000.0
    assert fake.account_summary_calls == 0
```

- [ ] **Step 2: Run the tests and confirm RED**

Run: `cd bot && python3 tests/test_ibkr_order_hygiene.py`

Expected: import failure for `ibkr_order_state` or missing engine methods.

- [ ] **Step 3: Implement status classification, deduplication, and accountValues-only polling**

```python
WORKING_STATUSES = frozenset({"PendingSubmit", "ApiPending", "PreSubmitted", "Submitted"})
CANCELLING_STATUSES = frozenset({"PendingCancel"})
TERMINAL_STATUSES = frozenset({"Filled", "Cancelled", "ApiCancelled", "Inactive"})

def trade_identity(trade):
    perm_id = int(getattr(trade.order, "permId", 0) or 0)
    if perm_id:
        return ("perm", perm_id)
    return ("client_order", int(trade.order.clientId or 0), int(trade.order.orderId or 0))
```

Remove all `accountSummary()` fallback behavior. Raise a clear runtime error if cached `NetLiquidation` is unavailable after connection warm-up.

- [ ] **Step 4: Add explicit bracket TIF and acknowledgement tests**

```python
def test_bracket_sets_explicit_tif_and_atomic_transmit_chain():
    result = engine.place_order(bracket_request())
    parent, take_profit, stop_loss = fake_ib.placed_orders
    assert [o.tif for o in (parent, take_profit, stop_loss)] == ["GTC", "GTC", "GTC"]
    assert [o.transmit for o in (parent, take_profit, stop_loss)] == [False, False, True]
    assert take_profit.parentId == parent.orderId == stop_loss.parentId
    assert result.ok

def test_cancelled_parent_returns_failure_and_cancels_children():
    fake_ib.parent_status = "Cancelled"
    result = engine.place_order(bracket_request())
    assert not result.ok
    assert fake_ib.cancelled_order_ids == set(fake_ib.child_order_ids)
```

- [ ] **Step 5: Run the bracket tests and confirm RED**

Run: `cd bot && python3 tests/test_ibkr_order_hygiene.py`

Expected: assertions show empty parent TIF, unconditional success, or children not cancelled.

- [ ] **Step 6: Implement bracket IDs, explicit TIF, acknowledgement, and failure cleanup**

Allocate all IDs with `ib.client.getReqId()`, set `account`, `tif`, `parentId`, and `transmit` before the first `placeOrder`, then place the chain back-to-back. Return `ok=True` only for `PreSubmitted`, `Submitted`, or `Filled`; cancel the complete chain on terminal status or timeout.

- [ ] **Step 7: Add cancel-all and flatten convergence tests**

```python
def test_cancel_all_waits_until_no_working_or_cancelling_orders():
    fake_ib.order_refreshes = [[submitted_trade()], [pending_cancel_trade()], []]
    result = engine.cancel_all_orders(timeout_s=0.1, poll_s=0)
    assert result.ok
    assert fake_ib.global_cancel_calls == 1

def test_flatten_cancels_closes_and_verifies():
    result = engine.flatten_positions("EURUSD", timeout_s=0.1)
    assert result.ok
    assert fake_ib.actions == ["global_cancel", "SELL", "global_cancel"]
    assert engine.positions("EURUSD") == []
```

- [ ] **Step 8: Implement convergent cancel and flatten**

Global cancel must be followed by fresh `reqAllOpenOrders()` results until both working and cancelling lists are empty. Flatten must refuse a non-paper port, cancel first, send one unbracketed opposite market order per nonzero configured position, wait for flat, cancel again, and verify.

- [ ] **Step 9: Run Task 1 tests GREEN**

Run: `cd bot && python3 tests/test_ibkr_order_hygiene.py && python3 tests/test_engines_unit.py`

Expected: both scripts print `OK` and exit 0.

### Task 2: Runner paper gate, cost gate, and single-instance lock

**Files:**
- Create: `bot/aegis/paper_control.py`
- Modify: `bot/scripts/run_broker_paper.py`
- Test: `bot/tests/test_paper_control.py`

**Interfaces:**
- Produces: `assert_paper_mutation_allowed(cfg: dict) -> None`, `estimated_target_net_usd(...) -> float`, `target_clears_costs(...) -> tuple[bool, float]`, and `ProcessLock(path: Path)`.

- [ ] **Step 1: Write failing safety and cost tests**

```python
def test_live_port_mutation_is_always_refused():
    for port in (4001, 7496, 9999):
        with raises_runtime_error():
            assert_paper_mutation_allowed({"ib_port": port, "allow_live": True})

def test_three_pip_twenty_thousand_target_fails_real_cost_gate():
    ok, net = target_clears_costs(
        quantity=20_000,
        entry=1.15430,
        target=1.15460,
        commission_round_trip_usd=4.0,
        spread_bps=0.5,
        slippage_bps=0.2,
        min_expected_net_usd=1.0,
    )
    assert not ok
    assert net < 0
```

- [ ] **Step 2: Run the tests and confirm RED**

Run: `cd bot && python3 tests/test_paper_control.py`

Expected: import failure for `aegis.paper_control`.

- [ ] **Step 3: Implement paper, cost, and lock helpers**

Use `fcntl.flock(LOCK_EX | LOCK_NB)` for process locks. For USD-quoted EURUSD, gross target dollars are `quantity * abs(target - entry)`; modeled spread/slippage are charged on round-trip notional and commission is added separately. Reject unsupported quote currencies rather than assuming conversion.

- [ ] **Step 4: Wire the runner to the safety helpers**

Acquire `reports/run_broker_paper.lock` before connecting. Require `paper_trading_enabled: true` in addition to `dry_run: false` before sending an order. Evaluate the cost gate immediately before `eng.place_order()`, journal a `cost_skip` event on rejection, and replace private `reqGlobalCancel()` max-hold logic with `eng.flatten_positions(symbol)`.

- [ ] **Step 5: Run Task 2 tests GREEN**

Run: `cd bot && python3 tests/test_paper_control.py && python3 tests/test_engines_unit.py`

Expected: all tests print `OK` and exit 0.

### Task 3: Dashboard uses fresh broker order truth

**Files:**
- Modify: `bot/scripts/run_dashboard.py`
- Test: `bot/tests/test_dashboard_order_state.py`

**Interfaces:**
- Consumes: `working_trades()` and `CANCELLING_STATUSES` from Task 1.
- Produces: dashboard JSON fields `open_orders` and `cancelling_orders` from the latest `reqAllOpenOrders()` response.

- [ ] **Step 1: Write a failing stale-cache regression test**

```python
def test_dashboard_uses_refresh_result_not_open_trade_cache():
    ib = FakeDashboardIB(
        refreshed=[],
        cached=[trade("Submitted", order_id=99)],
    )
    open_orders, cancelling = collect_order_rows(ib)
    assert open_orders == []
    assert cancelling == []
```

- [ ] **Step 2: Run the test and confirm RED**

Run: `cd bot && python3 tests/test_dashboard_order_state.py`

Expected: missing `collect_order_rows` or stale order 99 appears.

- [ ] **Step 3: Implement fresh order collection**

Extract `collect_order_rows(ib)` from `_poll_once()`. Use only the list returned by `reqAllOpenOrders()`, apply shared deduplication, and keep `PendingCancel` in a separate field. Do not call `accountSummary()`.

- [ ] **Step 4: Add a dashboard process lock and run GREEN**

Acquire `reports/run_dashboard.lock` in `main()` and run:

`cd bot && python3 tests/test_dashboard_order_state.py`

Expected: `OK` and exit 0.

### Task 4: Launchd supervisor and unified operator command

**Files:**
- Create: `bot/scripts/aegis_paper.py`
- Modify: `bot/scripts/watchdog.py`
- Retire from documented use: `bot/scripts/keep_alive.sh`
- Test: `bot/tests/test_process_control.py`

**Interfaces:**
- Produces: `launch_agent_payload(root: Path, python: Path, config: Path) -> dict`, `service_label() -> str`, and CLI commands `start|stop|restart|status|flatten`.
- The supervisor owns two child handles and never uses `pgrep` to supervise them.

- [ ] **Step 1: Write failing LaunchAgent and status tests**

```python
def test_launch_agent_runs_watchdog_from_repo():
    payload = launch_agent_payload(ROOT, Path("/usr/bin/python3"), CONFIG)
    assert payload["Label"] == "com.aegis.ibpaper"
    assert payload["RunAtLoad"] is True
    assert payload["KeepAlive"] is True
    assert str(ROOT / "scripts" / "watchdog.py") in payload["ProgramArguments"]

def test_status_marks_stale_heartbeat_as_stopped():
    status = heartbeat_status({"pid": 123, "ts": 100.0}, now=200.0, max_age=15.0)
    assert not status["running"]
```

- [ ] **Step 2: Run the tests and confirm RED**

Run: `cd bot && python3 tests/test_process_control.py`

Expected: missing control functions.

- [ ] **Step 3: Refactor watchdog into an owned-child supervisor**

Hold `Popen` objects for bot and dashboard. Log PID and exit code. On SIGTERM/SIGINT, terminate each child, wait up to ten seconds, kill only a child that remains alive, close log files, and exit. Acquire `reports/watchdog.lock` to prevent a second supervisor.

- [ ] **Step 4: Implement the unified CLI**

`start` writes `~/Library/LaunchAgents/com.aegis.ibpaper.plist`, bootstraps it, and refuses when a fresh heartbeat or loaded service already exists. `stop` invokes paper flatten unless `--process-only`, bootouts the service, and confirms heartbeat/dashboard stop. `status` connects read-only with the configured status client ID and prints both human-readable text and `--json`. `flatten` delegates to the engine convergence methods.

- [ ] **Step 5: Run Task 4 tests GREEN**

Run: `cd bot && python3 tests/test_process_control.py`

Expected: `OK` and exit 0.

### Task 5: Safe defaults, documentation, and complete verification

**Files:**
- Modify: `bot/config_ib_paper_eurusd.yaml`
- Modify: `docs/IB_PAPER_SETUP.md`
- Create: `bot/reports/IB_PAPER_STACK_AUDIT.md`

**Interfaces:**
- Config adds `paper_trading_enabled`, `ib_dashboard_client_id`, `ib_status_client_id`, `ib_order_tif`, `ib_order_ack_timeout`, `ib_round_trip_commission_usd`, and `min_expected_net_usd`.

- [ ] **Step 1: Set safe paper defaults**

Set `paper_trading_enabled: false`, `dry_run: true`, `firehose_every_bar: false`, and `max_hold_seconds: 0`. Preserve paper port 4002, bot client 7, dashboard client 71, and `allow_live: false`.

- [ ] **Step 2: Document the single command and strategy decision**

Document `python3 scripts/aegis_paper.py status|start|stop|restart|flatten`, explain that `start` is observation-only by default, and record that Option A must pass real costed fills before activation while Option B is the slower fallback.

- [ ] **Step 3: Run every direct test**

Run each `bot/tests/test_*.py` with system `python3`, because the repository virtual environment currently lacks `pytest` and `ib_insync` while system Python has `ib_insync` 0.9.86.

- [ ] **Step 4: Run static verification**

Run:

```bash
python3 -m compileall -q bot/aegis bot/scripts bot/tests
git diff --check
```

- [ ] **Step 5: Run safe live verification**

Run only `python3 bot/scripts/aegis_paper.py status --json`. Confirm Gateway paper port 4002, paper account, no positions, no working/cancelling orders, stale or absent bot heartbeat, and dashboard state. Do not run `start`, `stop`, `restart`, or `flatten` during verification.

- [ ] **Step 6: Write the audit report**

Record exact pre-fix evidence, files changed, offline test results, safe live status, remaining limitations, and the recommendation against every-bar spray. Do not claim positive expectancy without new fill measurements.
