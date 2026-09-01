# Firehose Cooperative Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep MT5 DEMO position management, confirmed-close finalization, heartbeat truth, and slot reuse responsive while the complete global opportunity universe is being generated.

**Architecture:** The existing single-threaded broker runner gains a monotonic cooperative checkpoint and calls it from symbol, mechanism, horizon, ranking, and execution boundaries. Both the normal management pass and checkpoint path use one idempotent confirmed-close finalizer; candidate generation remains complete and frozen candidates still receive fresh broker revalidation.

**Tech Stack:** Python 3.12, pytest, pandas, MetaTrader5 adapter, existing AEGIS FastExit/TradeController/turnover/outcome-memory components.

**Spec:** `docs/superpowers/specs/2026-08-28-firehose-cooperative-runtime-design.md`

## Global Constraints

- The only broker execution owner remains `bot/scripts/run_broker_paper.py`.
- Keep `engine=mt5`, `mode=mt5_demo`, `allow_live=false`, `paper_trading_enabled=true`, and `dry_run=false`.
- Do not create a broker-mutating thread or second trading brain.
- Do not force trades, raise risk, martingale, authorize symbols manually, or turn 95% into an entry threshold.
- Preserve fresh-quote, broker geometry, spread/economics, margin, per-trade risk, portfolio, OMS, and self-hedge protections.
- Preserve all valid dirty work; stage only files named by the current task.
- Use focused tests after each task and run full pytest once in final verification.

## File Map

- Create `bot/aegis/intel/runtime_checkpoint.py`: monotonic scheduling, scan progress, and checkpoint-gap telemetry only; no broker access.
- Modify `bot/aegis/intel/fast_firehose.py`: optional cooperative callback at mechanism/horizon boundaries.
- Modify `bot/aegis/intel/firehose_brain.py`: pass the callback through candidate generation/economics evaluation without changing ranking or authority.
- Modify `bot/scripts/run_broker_paper.py`: one checkpoint callback, one canonical confirmed-close finalizer, heartbeat integration, and prepared-frame caching.
- Modify `bot/aegis/research/outcome_learning.py`: preserve the already-started daily lifecycle report and expose confirmed-close behavior truth.
- Modify `bot/scripts/research_fast_trade_autopsy.py`: write daily JSON/Markdown reports.
- Test with `bot/tests/test_runtime_checkpoint.py`, `bot/tests/test_fast_firehose.py`, `bot/tests/test_exploration_firehose.py`, `bot/tests/test_run_broker_paper_helpers.py`, `bot/tests/test_fast_exit_production.py`, and `bot/tests/test_outcome_learning.py`.

---

### Task 1: Monotonic Runtime Checkpoint State

**Files:**
- Create: `bot/aegis/intel/runtime_checkpoint.py`
- Create: `bot/tests/test_runtime_checkpoint.py`

**Interfaces:**
- Produces: `ScanProgress(symbol_index: int, symbol_count: int, cycle_started_mono: float)`.
- Produces: `RuntimeCheckpointState(interval_s: float, max_samples: int = 1024)`.
- Produces: `RuntimeCheckpointState.due(now_mono: float) -> bool`.
- Produces: `RuntimeCheckpointState.record(now_mono: float, now_wall: float, progress: ScanProgress, open_ticket_rechecks: int = 0, confirmed_closes: int = 0, close_to_rescan_ms: float | None = None) -> dict[str, object]`.

- [ ] **Step 1: Write failing monotonic scheduling tests**

```python
from aegis.intel.runtime_checkpoint import RuntimeCheckpointState, ScanProgress


def test_checkpoint_due_uses_monotonic_elapsed_time():
    state = RuntimeCheckpointState(interval_s=1.0)
    assert state.due(10.0)
    state.record(10.0, 1000.0, ScanProgress(1, 26, 9.0))
    assert not state.due(10.999)
    assert state.due(11.0)


def test_checkpoint_snapshot_reports_gap_and_scan_progress():
    state = RuntimeCheckpointState(interval_s=1.0)
    state.record(10.0, 1000.0, ScanProgress(3, 26, 7.0), open_ticket_rechecks=2)
    snapshot = state.record(
        11.25, 1001.25, ScanProgress(4, 26, 7.0),
        open_ticket_rechecks=1, confirmed_closes=1, close_to_rescan_ms=40.0,
    )
    assert snapshot["LAST_RUNTIME_CHECKPOINT_AT"] == 1001.25
    assert snapshot["RUNTIME_CHECKPOINT_GAP_MS"] == 1250.0
    assert snapshot["OPEN_TICKET_RECHECKS"] == 3
    assert snapshot["CONFIRMED_CLOSES_FINALIZED"] == 1
    assert snapshot["SCAN_SYMBOL_INDEX"] == 4
    assert snapshot["SCAN_SYMBOL_COUNT"] == 26
    assert snapshot["SCAN_CYCLE_AGE_MS"] == 4250.0
```

- [ ] **Step 2: Run tests and verify RED**

Run:
`..\.venv\Scripts\python.exe -m pytest -q tests/test_runtime_checkpoint.py`

Expected: collection fails because `aegis.intel.runtime_checkpoint` does not exist.

- [ ] **Step 3: Implement the state object**

```python
@dataclass(frozen=True)
class ScanProgress:
    symbol_index: int
    symbol_count: int
    cycle_started_mono: float


class RuntimeCheckpointState:
    def __init__(self, interval_s: float, max_samples: int = 1024) -> None:
        self.interval_s = max(0.05, float(interval_s))
        self._last_mono: float | None = None
        self._gaps_ms: deque[float] = deque(maxlen=max_samples)
        self._open_ticket_rechecks = 0
        self._confirmed_closes = 0
        self._last_close_to_rescan_ms: float | None = None

    def due(self, now_mono: float) -> bool:
        return self._last_mono is None or now_mono - self._last_mono >= self.interval_s
```

`record()` must reject non-finite times with `ValueError`, append the measured gap after the first call, accumulate counters, compute p95 from the sorted retained samples, and return all telemetry fields named in the interface.

- [ ] **Step 4: Run tests and verify GREEN**

Run:
`..\.venv\Scripts\python.exe -m pytest -q tests/test_runtime_checkpoint.py`

Expected: `2 passed`.

- [ ] **Step 5: Commit only Task 1 files**

```powershell
git add bot/aegis/intel/runtime_checkpoint.py bot/tests/test_runtime_checkpoint.py
git commit -m "runtime: add cooperative checkpoint telemetry"
```

---

### Task 2: Candidate-Generation Checkpoint Boundaries

**Files:**
- Modify: `bot/aegis/intel/fast_firehose.py:414-600`
- Modify: `bot/aegis/intel/firehose_brain.py:1360-1510`
- Modify: `bot/tests/test_fast_firehose.py`
- Modify: `bot/tests/test_exploration_firehose.py`

**Interfaces:**
- Consumes: a callback `checkpoint(stage: str, mechanism: str, side: str, horizon_s: int | None) -> None`.
- Produces: optional keyword `checkpoint` on `generate_micro_search_candidates()`, `generate_runtime_search_candidates()`, and `IntelligentFirehoseBrain.evaluate()`.
- Existing callers that omit the callback remain behaviorally identical.

- [ ] **Step 1: Write failing complete-universe callback tests**

```python
def test_runtime_search_checkpoints_do_not_change_candidate_identity(matching_context):
    baseline = generate_runtime_search_candidates(matching_context, horizons=(3, 10))
    calls = []
    observed = generate_runtime_search_candidates(
        matching_context,
        horizons=(3, 10),
        checkpoint=lambda stage, mechanism, side, horizon: calls.append(
            (stage, mechanism, side, horizon)
        ),
    )
    assert [(c.variant_id, c.side, c.max_hold_s) for c in observed] == [
        (c.variant_id, c.side, c.max_hold_s) for c in baseline
    ]
    assert {call[2] for call in calls if call[2]} == {"buy", "sell"}
    assert {call[3] for call in calls if call[3]} == {3, 10}
```

Add a brain-level test that passes a counting callback and asserts the returned
decision and candidate-evaluation identities match an evaluation without the
callback.

- [ ] **Step 2: Run tests and verify RED**

Run:
`..\.venv\Scripts\python.exe -m pytest -q tests/test_fast_firehose.py tests/test_exploration_firehose.py -k checkpoint`

Expected: failure because the three APIs reject `checkpoint`.

- [ ] **Step 3: Add optional callback plumbing**

```python
Checkpoint = Callable[[str, str, str, int | None], None]


def _checkpoint(
    callback: Checkpoint | None,
    stage: str,
    mechanism: str,
    side: str,
    horizon_s: int | None,
) -> None:
    if callback is not None:
        callback(stage, mechanism, side, horizon_s)
```

Call `_checkpoint()` before each family/side evaluation, before each horizon
variant, before each compiled strategy/horizon variant, and before each
candidate economics evaluation. Do not catch callback exceptions inside the
candidate layer; the runner owns stop and technical-failure policy.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run:
`..\.venv\Scripts\python.exe -m pytest -q tests/test_fast_firehose.py tests/test_exploration_firehose.py`

Expected: all tests pass and existing exact candidate-set tests remain green.

- [ ] **Step 5: Commit only Task 2 files**

```powershell
git add bot/aegis/intel/fast_firehose.py bot/aegis/intel/firehose_brain.py bot/tests/test_fast_firehose.py bot/tests/test_exploration_firehose.py
git commit -m "runtime: interleave checkpoints through candidate search"
```

---

### Task 3: Canonical Confirmed-Close Finalizer

**Files:**
- Modify: `bot/scripts/run_broker_paper.py:1465-1655,2030-2115`
- Modify: `bot/tests/test_run_broker_paper_helpers.py`

**Interfaces:**
- Produces:

```python
def finalize_confirmed_firehose_close(
    *,
    root: Path,
    engine: Any,
    ticket: str,
    position: Any,
    metadata: Any,
    metadata_store: Any,
    reentry_guard: Any,
    trade_controller: TradeController,
    turnover: Any,
    profit_summary: Mapping[str, Any],
    close_facts: Mapping[str, Any],
    quote_buffer: Any,
    outcome_memory: Any,
    journal_append: Callable[[dict[str, Any]], None],
    closed_at: float,
    quote_fingerprint_value: str | None,
    contract: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Finalize one broker-confirmed close idempotently."""
```

- Returns `{"status": "FINALIZED", "slot_released": bool, "learning_status": str | None}` on complete/idempotent success.
- Returns `{"status": "PENDING_CLEANUP", "reason": str}` when local durable cleanup cannot complete.
- It is called only after `close_ticket_confirmed` returns true.

- [ ] **Step 1: Write failing finalizer tests**

Add `_confirmed_close_case(tmp_path)` beside the existing `_contract()`,
`_ticket_metadata()`, and `_persisted_cleanup_state()` helpers. It returns a
`SimpleNamespace` containing `kwargs`, `controller_release_calls`,
`turnover_close_calls`, `learning_ids`, `metadata_store`, and `journal_events`.
Its fake controller appends in `release_ticket()`, its fake turnover appends in
`record_close()`, and its fake outcome memory appends the `outcome_id` passed to
`record_confirmed_close()`. Persist ticket `T1` and basket `basket-1001` using
the existing helpers before returning the case.

Then assert:

```python
def test_confirmed_close_finalizer_releases_every_owner_once(tmp_path):
    case = _confirmed_close_case(tmp_path)
    result = finalize_confirmed_firehose_close(**case.kwargs)
    assert result["status"] == "FINALIZED"
    assert result["slot_released"] is True
    assert case.controller_release_calls == ["T1"]
    assert case.turnover_close_calls == ["T1"]
    assert case.learning_ids == ["T1"]
    assert case.metadata_store.get("T1") is None
    assert case.journal_events[-1]["event"] == "firehose_close"


def test_unconfirmed_close_never_enters_finalizer(tmp_path):
    case = _confirmed_close_case(tmp_path)
    position = PositionSnapshot(
        symbol="EURUSD", side="buy", quantity=0.01,
        avg_price=1.1000, stop_loss=1.0990, ticket="T1",
    )
    assert close_ticket_confirmed([position], "T1") is False
    assert case.controller_release_calls == []
    assert case.metadata_store.get("T1") is not None


def test_confirmed_close_finalizer_is_idempotent(tmp_path):
    case = _confirmed_close_case(tmp_path)
    first = finalize_confirmed_firehose_close(**case.kwargs)
    second = finalize_confirmed_firehose_close(**case.kwargs)
    assert first["status"] == "FINALIZED"
    assert second["status"] in {"FINALIZED", "ALREADY_FINALIZED"}
    assert case.learning_ids == ["T1"]
```

- [ ] **Step 2: Run tests and verify RED**

Run:
`..\.venv\Scripts\python.exe -m pytest -q tests/test_run_broker_paper_helpers.py -k confirmed_close_finalizer`

Expected: import/name failure because the finalizer is not defined.

- [ ] **Step 3: Extract the existing normal-close side effects**

Move, without changing their order or truth source, the confirmed branch’s
TradeController release, turnover update, broker-confirmed learning, close
journal, basket lifecycle journal, and
`remove_confirmed_firehose_basket_then_cleanup()` call into the exact signature
above. Use `close_facts["realized_net_usd"]` only when
`close_facts["status"] == "BROKER_CONFIRMED"`; never substitute floating PnL.

Use the metadata store’s persisted pending-cleanup state as the idempotency
boundary. If metadata was already removed, return `ALREADY_FINALIZED` without
recording a second learning row.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run:
`..\.venv\Scripts\python.exe -m pytest -q tests/test_run_broker_paper_helpers.py -k "confirmed_close or basket_cleanup or outcome_learning"`

Expected: all selected tests pass.

- [ ] **Step 5: Commit only Task 3 files**

```powershell
git add bot/scripts/run_broker_paper.py bot/tests/test_run_broker_paper_helpers.py
git commit -m "runtime: centralize confirmed close finalization"
```

---

### Task 4: Runner-Owned Cooperative Checkpoint and Heartbeat Truth

**Files:**
- Modify: `bot/scripts/run_broker_paper.py:1662-1835,2260-2330,2642-3005,4469-5885`
- Modify: `bot/tests/test_run_broker_paper_helpers.py`
- Test: `bot/tests/test_runtime_checkpoint.py`

**Interfaces:**
- Consumes: `RuntimeCheckpointState` and candidate callback from Tasks 1–2.
- Produces runner closure:

```python
def runtime_checkpoint(
    stage: str,
    mechanism: str = "",
    side: str = "",
    horizon_s: int | None = None,
    *,
    force: bool = False,
) -> dict[str, Any]:
    """Run one due management/heartbeat checkpoint in the broker owner."""
```

- `rapid_exit_recheck()` returns decisions and calls an injected
  `confirmed_close_finalizer(position, decision, close_facts, closed_at)` for
  confirmed closes instead of releasing partial state itself.

- [ ] **Step 1: Write failing slow-scan integration tests**

```python
def test_slow_candidate_scan_manages_winner_before_universe_finishes():
    clock = FakeClock()
    visited = []
    closed = []

    def checkpoint(stage, mechanism, side, horizon):
        visited.append((stage, mechanism, side, horizon, clock.monotonic()))
        if clock.monotonic() >= 1.0 and not closed:
            closed.append("T-WIN")

    generate_runtime_search_candidates(
        matching_context,
        horizons=(1, 2, 3, 5, 8, 10, 15, 20),
        checkpoint=lambda *args: (clock.advance(0.25), checkpoint(*args)),
    )
    assert closed == ["T-WIN"]
    assert visited[-1][0:4] != visited[0][0:4]


def test_checkpoint_confirmed_close_finalizes_and_scan_continues():
    result = run_scan_with_checkpoint_fixture(close_confirmed=True)
    assert result.finalized_tickets == ["T1"]
    assert result.symbols_completed_after_close
    assert result.max_checkpoint_gap_ms <= 1000.0
    assert result.heartbeat["runtime_phase"] == "RUNNING_SCAN"
```

Also test `close_confirmed=False` retains controller, metadata, basket, and slot
state and emits `WAITING_BROKER_CONFIRMATION`.

- [ ] **Step 2: Run tests and verify RED**

Run:
`..\.venv\Scripts\python.exe -m pytest -q tests/test_runtime_checkpoint.py tests/test_run_broker_paper_helpers.py -k "slow_candidate_scan or checkpoint_confirmed or waiting_broker"`

Expected: failure because the runner checkpoint/finalizer injection is absent.

- [ ] **Step 3: Wire the checkpoint through the runner**

Instantiate `RuntimeCheckpointState` from
`runtime_checkpoint_interval_s` with a default of `1.0`. The callback must:

1. check `state.due(time.monotonic())` unless `force=True`;
2. write phase `RUNNING_MANAGEMENT_CHECKPOINT`;
3. refresh positions and their exact liquidation quotes;
4. call `rapid_exit_recheck()` using the canonical TradeController;
5. route confirmed closes through `finalize_confirmed_firehose_close()`;
6. update checkpoint telemetry and restore phase `RUNNING_SCAN`; and
7. raise a dedicated operator-stop exception if `STOP FIREHOSE` exists.

Pass this callback into `intelligent_brain.evaluate(checkpoint=runtime_checkpoint)`.
Invoke it before/after each symbol, global ranking, each execution attempt, and
after a confirmed close. Do not call `mt5.order_send()` from the candidate
layer.

- [ ] **Step 4: Verify heartbeat telemetry and one authority**

Run:
`..\.venv\Scripts\python.exe -m pytest -q tests/test_runtime_checkpoint.py tests/test_run_broker_paper_helpers.py tests/test_fast_exit_production.py tests/test_trade_controller.py`

Expected: all pass, including the existing test that intelligent mode has only
TradeController normal-exit authority.

- [ ] **Step 5: Commit only Task 4 files**

```powershell
git add bot/scripts/run_broker_paper.py bot/tests/test_run_broker_paper_helpers.py bot/tests/test_runtime_checkpoint.py
git commit -m "runtime: manage positions during global scans"
```

---

### Task 5: Measured Scan-Preparation Cache

**Files:**
- Modify: `bot/scripts/run_broker_paper.py:2642-2968`
- Modify: `bot/tests/test_run_broker_paper_helpers.py`

**Interfaces:**
- Produces:

```python
def cached_prepared_scan_frame(
    cache: dict[tuple[str, str, int], pd.DataFrame],
    *,
    symbol: str,
    timeframe: str,
    completed_bar_time_msc: int,
    build: Callable[[], pd.DataFrame],
) -> pd.DataFrame:
    """Return one prepared frame per completed-bar identity."""
```

- Key identity is `(symbol, timeframe, completed_bar_time_msc)`; current BID/ASK
  is never cached and frozen execution revalidation remains unchanged.

- [ ] **Step 1: Write failing cache truth tests**

```python
def test_prepared_frame_cache_reuses_same_completed_bar_but_not_new_bar():
    cache = {}
    calls = []
    def build():
        calls.append("build")
        return pd.DataFrame({"close": [1.1]})
    first = cached_prepared_scan_frame(
        cache, symbol="EURUSD", timeframe="M1",
        completed_bar_time_msc=1000, build=build,
    )
    second = cached_prepared_scan_frame(
        cache, symbol="EURUSD", timeframe="M1",
        completed_bar_time_msc=1000, build=build,
    )
    assert first is second
    assert len(calls) == 1
    advanced = cached_prepared_scan_frame(
        cache, symbol="EURUSD", timeframe="M1",
        completed_bar_time_msc=2000, build=build,
    )
    assert advanced is not first
    assert len(calls) == 2


def test_prepared_frame_cache_never_caches_execution_quote():
    frame = cached_prepared_scan_frame(
        {}, symbol="EURUSD", timeframe="M1", completed_bar_time_msc=1000,
        build=lambda: pd.DataFrame({"close": [1.1]}),
    )
    assert "current_bid" not in frame.attrs
    assert "current_ask" not in frame.attrs
```

- [ ] **Step 2: Run tests and verify RED**

Run:
`..\.venv\Scripts\python.exe -m pytest -q tests/test_run_broker_paper_helpers.py -k prepared_frame_cache`

Expected: failure because `cached_prepared_scan_frame` does not exist.

- [ ] **Step 3: Implement and integrate the bounded cache**

Derive `completed_bar_time_msc` from the latest completed bar, then cache only
the result of `bars_to_frame(bars)` plus `prepare(raw, prep_cfg)`. Clear a symbol’s prior keys when its completed bar
advances or live YAML reload changes feature preparation settings. Continue to
call `eng.quote(sym)` and fresh execution revalidation on every candidate path.

- [ ] **Step 4: Verify candidate-universe equivalence**

Run:
`..\.venv\Scripts\python.exe -m pytest -q tests/test_run_broker_paper_helpers.py tests/test_opportunity_engine.py tests/test_exploration_firehose.py`

Expected: all pass; candidate IDs, BUY/SELL comparison, global ranking, and
frozen identity tests remain unchanged.

- [ ] **Step 5: Commit only Task 5 files**

```powershell
git add bot/scripts/run_broker_paper.py bot/tests/test_run_broker_paper_helpers.py
git commit -m "runtime: cache point-in-time scan preparation"
```

---

### Task 6: Daily Lifecycle Report Completion

**Files:**
- Preserve/modify: `bot/aegis/research/outcome_learning.py`
- Preserve/modify: `bot/scripts/research_fast_trade_autopsy.py`
- Preserve/modify: `bot/tests/test_outcome_learning.py`

**Interfaces:**
- Produces: `build_daily_trade_behavior_reports(summary, timezone_name="Asia/Amman") -> dict[str, dict[str, Any]]`.
- Produces: `render_daily_trade_behavior_markdown(report) -> str`.
- Writes: `bot/reports/research/daily_trade_behavior/YYYY-MM-DD.json` and `.md`.

- [ ] **Step 1: Review and retain the existing red-green implementation**

Confirm the current dirty tests explicitly cover:

```python
assert trade["state_path"] == [
    "OPEN", "RED", "GREEN", "PEAK", "GREEN_TO_RED", "CLOSE_LOSS"
]
assert trade["broker_confirmed_net_pnl_usd"] == pytest.approx(-0.02)
assert trade["exit_action"] == "SCRATCH"
```

Add this test that a positive broker-confirmed close renders
`OPEN -> GREEN -> PEAK -> CLOSE_WIN` and that a non-confirmed floating value
cannot override broker-confirmed realized net PnL.

- [ ] **Step 2: Run focused report tests**

Run:
`..\.venv\Scripts\python.exe -m pytest -q tests/test_outcome_learning.py -k "daily_trade_behavior or fast_trade_autopsy"`

Expected: all selected tests pass.

- [ ] **Step 3: Generate the report through the production script**

Run:
`..\.venv\Scripts\python.exe scripts\research_fast_trade_autopsy.py`

Expected JSON output includes `daily_reports`, `mt5_touched: false`, and
`placed_orders: false`; the current local date has both JSON and Markdown
files.

- [ ] **Step 4: Commit source/tests only**

```powershell
git add bot/aegis/research/outcome_learning.py bot/scripts/research_fast_trade_autopsy.py bot/tests/test_outcome_learning.py
git commit -m "research: report daily trade lifecycle behavior"
```

Do not stage the multi-gigabyte runtime journal or unrelated generated reports.

---

### Task 7: Final Verification and Controlled DEMO Reload

**Files:**
- Verify: `bot/config_mt5_demo_firehose_hw.yaml`
- Verify all source/test files committed by Tasks 1–6.
- Do not modify protected YAML.

**Interfaces:**
- Consumes all prior tasks.
- Produces machine evidence; no new runtime API.

- [ ] **Step 1: Run the focused integration suite**

Run:

```powershell
..\.venv\Scripts\python.exe -m pytest -q `
  tests/test_runtime_checkpoint.py `
  tests/test_fast_firehose.py `
  tests/test_exploration_firehose.py `
  tests/test_fast_exit_production.py `
  tests/test_trade_controller.py `
  tests/test_opportunity_engine.py `
  tests/test_run_broker_paper_helpers.py `
  tests/test_outcome_learning.py
```

Expected: zero failures.

- [ ] **Step 2: Run full pytest exactly once**

Run:
`..\.venv\Scripts\python.exe -m pytest -q`

Expected: zero failures. Record the exact pass count and warning count.

- [ ] **Step 3: Verify immutable execution policy**

Run:

```powershell
rg -n "^(engine|mode|allow_live|dry_run|paper_trading_enabled):" config_mt5_demo_firehose_hw.yaml
rg -n "order_send\(" aegis scripts
```

Expected configuration:

```text
engine: mt5
mode: mt5_demo
allow_live: false
dry_run: false
paper_trading_enabled: true
```

Every reachable broker order-send call must remain under the MT5 engine used by
`run_broker_paper.py`; research processes must have none.

- [ ] **Step 4: Inspect scope before runtime mutation**

Run:

```powershell
git status --short
git diff --check
git log --oneline -10
```

Expected: no uncommitted source/test change from Tasks 1–6; unrelated runtime
and generated files may remain dirty and must not be staged.

- [ ] **Step 5: Restart exactly one DEMO runner process tree**

Resolve only Python processes whose command line contains both
`scripts/run_broker_paper.py` and `config_mt5_demo_firehose_hw.yaml`. Stop that
exact process tree, verify none remains, then launch once with hidden window:

```powershell
Start-Process -FilePath (Resolve-Path '..\.venv\Scripts\python.exe') `
  -ArgumentList @('-u','scripts/run_broker_paper.py','--config','config_mt5_demo_firehose_hw.yaml','--video-style') `
  -WorkingDirectory (Resolve-Path '.') -WindowStyle Hidden
```

- [ ] **Step 6: Verify fresh runtime evidence without forcing a trade**

Inspect the fresh heartbeat and focused journal tail. Require:

```text
[MT5 DEMO] CONNECTED
[DEMO ORDER PATH] ENABLED
[FAST_EXIT] ACTIVE
[TRADING_ELIGIBLE] TRUE
runtime_phase=RUNNING_SCAN or RUNNING_MANAGEMENT_CHECKPOINT
RUNTIME_CHECKPOINT_GAP_P95_MS present
SCAN_SYMBOL_INDEX present
SCAN_SYMBOL_COUNT=26
```

When a legitimate close occurs, verify the journal sequence contains one
TradeController decision, broker-confirmed close, canonical finalizer result,
slot release, outcome-learning event, and continued scan progress. If no trade
closes during the bounded observation window, report that live close proof is
pending rather than fabricating success.

- [ ] **Step 7: Push coherent commits without merging**

Run:

```powershell
git push origin opencode/exploration-firehose
```

Report every pushed SHA, exact focused/full test output, runner PID, current
heartbeat checkpoint gap, and any remaining evidence gap. Do not merge.
