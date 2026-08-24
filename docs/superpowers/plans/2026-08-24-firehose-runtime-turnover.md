# Firehose Runtime Turnover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add fail-closed Firehose basket evidence capture and runtime observation so future fast-turnover behavior can be activated only by a governed, validated policy artifact.

**Architecture:** Preserve the current entry and exit decisions. Add a small runtime evidence adapter that translates exact ticket/basket metadata plus executable broker marks into append-only point-in-time snapshots and `NO_EVIDENCE` decisions when a trusted policy artifact is absent. Wire that adapter only after broker-confirmed fills and closes, then extend the existing replay/turnover reporting to reject incomplete lifecycle data rather than infer outcomes.

**Tech Stack:** Python, dataclasses, existing `BasketMetadataStore`, `TicketMetadataStore`, `FastExit`, Firehose turnover JSONL, pytest.

**Spec:** `docs/superpowers/specs/2026-08-24-firehose-runtime-turnover-design.md`

## Global Constraints

- Keep `engine: mt5`, `mode: mt5_demo`, `allow_live: false`, `paper_trading_enabled: true`, and `exploration_max_risk_per_trade_usd: 0.15` unchanged.
- Do not launch MT5, place orders, enable live trading, merge, or push.
- Do not modify Research Factory, AI Council, Book Brain, ML/replay governance, entry gates, stale-signal protection, spread/economics gates, margin controls, self-hedge protection, or per-trade risk.
- Runtime changes must use exact ticket metadata and broker-confirmed fill/close state; no symbol/side ownership inference.
- Missing book, lifecycle, cost, feature, policy, or OOS evidence returns `NO_EVIDENCE` or `NOT_IMPLEMENTED`; never fabricate a metric or decision.
- New quick harvest, extension, profit floor, scratch, abort, and clip-add actions remain inactive unless a trusted governed artifact exists.

---

### Task 1: Define Fail-Closed Runtime Evidence Types

**Files:**
- Create: `bot/aegis/intel/firehose_runtime_evidence.py`
- Create: `bot/tests/test_firehose_runtime_evidence.py`

**Interfaces:**
- Produces `build_runtime_snapshot(ticket, basket, mark, observed_at, costs, momentum, remaining_ev) -> dict`.
- Produces `evaluate_runtime_policy(snapshot, artifact) -> dict`.
- The only artifact-absent result is `{"action": "NO_EVIDENCE", "reason": "missing_validated_policy_artifact"}`.

- [ ] **Step 1: Write failing tests for snapshot completeness and executable marks**

```python
def test_buy_snapshot_uses_bid_mark_and_preserves_exact_identity():
    snapshot = build_runtime_snapshot(
        ticket={"ticket_id": 7, "basket_id": "b1", "side": "BUY", "entry_price": 1.1},
        basket={"basket_id": "b1", "hypothesis_id": "h1"},
        mark={"bid": 1.1002, "ask": 1.1003},
        observed_at=100.0,
        costs={"commission_usd": 0.01, "spread_usd": 0.02},
        momentum={"return_5s": 0.0, "return_15s": 0.0, "return_30s": 0.0},
        remaining_ev={"value": 0.0, "observed_at": 100.0},
    )
    assert snapshot["liquidation_mark"] == 1.1002
    assert snapshot["basket_id"] == "b1"
    assert snapshot["ticket_id"] == 7


def test_missing_cost_or_mark_returns_no_evidence_not_synthetic_values():
    result = build_runtime_snapshot(
        ticket={"ticket_id": 7, "basket_id": "b1", "side": "BUY", "entry_price": 1.1},
        basket={"basket_id": "b1", "hypothesis_id": "h1"},
        mark={"bid": 1.1002, "ask": 1.1003},
        observed_at=100.0,
        costs={},
        momentum={"return_5s": 0.0, "return_15s": 0.0, "return_30s": 0.0},
        remaining_ev={"value": 0.0, "observed_at": 100.0},
    )
    assert result == {"status": "NO_EVIDENCE", "reason": "missing_cost_evidence"}


def test_policy_is_inactive_without_trusted_artifact():
    decision = evaluate_runtime_policy(valid_snapshot, artifact=None)
    assert decision == {
        "action": "NO_EVIDENCE",
        "reason": "missing_validated_policy_artifact",
    }
```

- [ ] **Step 2: Run focused tests and confirm collection failure**

Run: `..\.venv\Scripts\python.exe -m pytest tests\test_firehose_runtime_evidence.py -q`

Expected: failure because `aegis.intel.firehose_runtime_evidence` does not exist.

- [ ] **Step 3: Implement minimal immutable snapshot validation**

```python
def build_runtime_snapshot(ticket, basket, mark, observed_at, costs, momentum, remaining_ev):
    side = str(ticket.get("side", "")).upper()
    liquidation_mark = mark.get("bid") if side == "BUY" else mark.get("ask")
    if side not in {"BUY", "SELL"} or not _finite_positive(liquidation_mark):
        return {"status": "NO_EVIDENCE", "reason": "missing_liquidation_mark"}
    if not _complete_costs(costs):
        return {"status": "NO_EVIDENCE", "reason": "missing_cost_evidence"}
    if ticket.get("basket_id") != basket.get("basket_id"):
        return {"status": "NO_EVIDENCE", "reason": "ticket_basket_mismatch"}
    return {"status": "OBSERVED", "basket_id": basket["basket_id"], "ticket_id": ticket["ticket_id"], "liquidation_mark": liquidation_mark}


def evaluate_runtime_policy(snapshot, artifact):
    if not _trusted_complete_artifact(artifact):
        return {"action": "NO_EVIDENCE", "reason": "missing_validated_policy_artifact"}
    return {"action": "NOT_IMPLEMENTED", "reason": "activation_requires_governed_runtime_contract"}
```

- [ ] **Step 4: Run focused tests and existing exit tests**

Run: `..\.venv\Scripts\python.exe -m pytest tests\test_firehose_runtime_evidence.py tests\test_firehose_basket_runtime.py tests\test_run_broker_paper_helpers.py -q`

Expected: pass; no existing close decision changes.

- [ ] **Step 5: Commit Task 1**

```powershell
git add bot/aegis/intel/firehose_runtime_evidence.py bot/tests/test_firehose_runtime_evidence.py
```

### Task 2: Wire Exact Basket Ownership After Confirmed Fills

**Files:**
- Modify: `bot/scripts/run_broker_paper.py`
- Modify: `bot/aegis/intel/ticket_metadata.py`
- Modify: `bot/aegis/intel/firehose_basket.py`
- Modify: `bot/tests/test_firehose_basket_runtime.py`

**Interfaces:**
- Consumes `BasketMetadataStore`, `TicketMetadataStore`, and confirmed MT5 fill result.
- Produces persisted exact basket/ticket ownership only after a confirmed broker ticket exists.

- [ ] **Step 1: Write failing runner-helper tests for confirmed-fill ownership**

```python
def test_confirmed_firehose_fill_persists_exact_ticket_and_basket_metadata(tmp_path):
    result = persist_confirmed_firehose_fill(
        ticket_id=123,
        metadata={"hypothesis_id": "h1", "symbol": "EURUSD", "side": "BUY", "entry_price": 1.1, "stop_price": 1.099, "volume": 0.01, "trigger_id": "q:100"},
        basket_store=BasketMetadataStore(tmp_path / "baskets.json", contracts={"EURUSD": ContractSpec(1.0, 0.00001)}),
        contract=ContractSpec(1.0, 0.00001),
    )
    assert result["ticket_id"] == 123
    assert result["basket_id"]


def test_unconfirmed_fill_does_not_create_basket_or_ticket_ownership(tmp_path):
    result = persist_confirmed_firehose_fill(
        ticket_id=None,
        metadata={"hypothesis_id": "h1", "symbol": "EURUSD", "side": "BUY"},
        basket_store=BasketMetadataStore(tmp_path / "baskets.json", contracts={}),
        contract=None,
    )
    assert result == {"status": "NO_EVIDENCE", "reason": "unconfirmed_fill"}


def test_missing_validated_artifact_keeps_clip_addition_unavailable(valid_basket):
    allowed, reason = can_add_clip(valid_basket, {"fresh_trigger": True, "same_side": True}, proposed_risk=0.01)
    assert allowed is False
    assert reason == "missing_validated_policy_artifact"
```

- [ ] **Step 2: Run the tests and confirm the missing integration**

Run: `..\.venv\Scripts\python.exe -m pytest tests\test_firehose_basket_runtime.py tests\test_firehose_basket.py -q`

Expected: failure proving the runner does not currently persist `BasketMetadataStore` ownership.

- [ ] **Step 3: Add a narrow confirmed-fill helper in the runner**

Implement a helper called only after the existing broker fill confirmation path. It must:

```python
def persist_confirmed_firehose_fill(*, ticket_id, metadata, basket_store, contract):
    if not ticket_id:
        return {"status": "NO_EVIDENCE", "reason": "unconfirmed_fill"}
    # Reuse BasketMetadataStore validation and trusted ContractSpec.
    # Persist ticket metadata and basket ownership atomically.
    # Do not add a clip or alter entry behavior when no artifact exists.
```

Pass broker-native contract evidence, immutable entry/stop geometry, exact
trigger/freshness ID, cost evidence, regime, and session. Preserve the existing
order request and fill decision path unchanged.

- [ ] **Step 4: Run focused ownership, restart, and safety tests**

Run: `..\.venv\Scripts\python.exe -m pytest tests\test_firehose_basket.py tests\test_firehose_basket_runtime.py tests\test_run_broker_paper_helpers.py -q`

Expected: pass, including restart ownership and no-artifact/no-add behavior.

- [ ] **Step 5: Commit Task 2**

```powershell
git add bot/scripts/run_broker_paper.py bot/aegis/intel/ticket_metadata.py bot/aegis/intel/firehose_basket.py bot/tests/test_firehose_basket_runtime.py
```

### Task 3: Emit Point-in-Time Append-Only Runtime Evidence

**Files:**
- Modify: `bot/aegis/intel/firehose_turnover.py`
- Modify: `bot/scripts/run_broker_paper.py`
- Modify: `bot/tests/test_firehose_basket_runtime.py`
- Modify: `bot/tests/test_firehose_turnover.py`

**Interfaces:**
- Consumes Task 1 snapshot and Task 2 exact ownership.
- Produces `firehose_exit_trace` and confirmed `firehose_close` observations with explicit evidence status.

- [ ] **Step 1: Write failing trace tests**

```python
def test_observation_trace_contains_required_point_in_time_fields(observed_snapshot):
    trace = basket_lifecycle_trace(snapshot=observed_snapshot, decision=no_evidence)
    assert trace["liquidation_mark_side"] == "BID"
    assert trace["mfe_usd"] is not None
    assert trace["remaining_ev_status"] == "NO_EVIDENCE"


def test_unconfirmed_close_writes_no_realized_outcome_and_keeps_slot(observed_snapshot):
    result = record_confirmed_firehose_close(snapshot=observed_snapshot, position_still_open=True, remaining_ticket_ids=[7])
    assert result["status"] == "NO_EVIDENCE"
    assert result["slot_released"] is False


def test_confirmed_final_ticket_close_releases_only_final_basket_slot(observed_snapshot):
    result = record_confirmed_firehose_close(snapshot=observed_snapshot, position_still_open=False, remaining_ticket_ids=[])
    assert result["slot_released"] is True
```

- [ ] **Step 2: Run focused tests and confirm missing fields/confirmation gates**

Run: `..\.venv\Scripts\python.exe -m pytest tests\test_firehose_turnover.py tests\test_firehose_basket_runtime.py -q`

Expected: failure because the current trace lacks the complete snapshot and confirmed-close schema.

- [ ] **Step 3: Extend trace construction without changing close behavior**

Add fields for exact IDs, family/hypothesis, executable mark and side, MFE/MAE,
peak net, age, returns, momentum, spread, costs, remaining EV/status, policy
decision/reason, clip count, regime/session, fresh trigger, and evidence status.
Only persist realized net, capture ratio, and close costs from broker-confirmed
economics. When those are unavailable, write null plus `NO_EVIDENCE` reason.

- [ ] **Step 4: Run focused trace and existing Factory/Council isolation tests**

Run: `..\.venv\Scripts\python.exe -m pytest tests\test_firehose_turnover.py tests\test_firehose_basket_runtime.py tests\test_research_factory.py tests\test_council_cycle.py -q`

Expected: pass; no Factory/Council import is added to runtime.

- [ ] **Step 5: Commit Task 3**

```powershell
git add bot/aegis/intel/firehose_turnover.py bot/scripts/run_broker_paper.py bot/tests/test_firehose_turnover.py bot/tests/test_firehose_basket_runtime.py
```

### Task 4: Add Replay-Ready Lifecycle Validation And Turnover Reporting

**Files:**
- Modify: `bot/aegis/research/firehose_basket_replay.py`
- Modify: `bot/aegis/intel/firehose_turnover.py`
- Create: `bot/tests/test_firehose_runtime_replay.py`

**Interfaces:**
- Consumes confirmed `firehose_open`, `firehose_exit_trace`, and `firehose_close` rows.
- Produces `NO_EVIDENCE` with explicit missing-field reasons or normalized replay rows for research.

- [ ] **Step 1: Write failing lifecycle and metric tests**

```python
def test_replay_row_rejects_close_attempt_without_confirmed_close():
    result = normalize_firehose_lifecycle_rows([pm_exit_attempt])
    assert result == {"status": "NO_EVIDENCE", "reason": "missing_confirmed_close"}


def test_replay_row_rejects_missing_cost_or_point_in_time_feature():
    assert normalize_firehose_lifecycle_rows([incomplete_row])["status"] == "NO_EVIDENCE"


def test_turnover_summary_reports_loss_geometry_only_from_confirmed_rows():
    summary = summarize_confirmed_baskets(rows)
    assert summary["wins_erased_by_avg_loss"] == 2.0
    assert summary["p95_loss"] == -0.4
```

- [ ] **Step 2: Run tests and confirm current journal cannot be treated as validated replay data**

Run: `..\.venv\Scripts\python.exe -m pytest tests\test_firehose_runtime_replay.py tests\test_firehose_basket_replay.py -q`

Expected: failure because no normalizer/confirmed-only turnover summary exists.

- [ ] **Step 3: Implement a confirmed-only normalizer and metrics summary**

`normalize_firehose_lifecycle_rows(rows)` must join only exact ticket/basket IDs,
validate chronological timestamps, require costs and point-in-time fields, and
never invent missing values. `summarize_confirmed_baskets(rows)` calculates
round trips/hour, hold quantiles, capture, cost/basket, net PnL/hour, payoff,
PF, tail/max loss, drawdown, and loss-erasure ratios from confirmed outcomes
only. Return `NO_EVIDENCE` on insufficient samples or missing evidence.

- [ ] **Step 4: Run replay, turnover, and Book Brain evidence tests**

Run: `..\.venv\Scripts\python.exe -m pytest tests\test_firehose_runtime_replay.py tests\test_firehose_basket_replay.py tests\test_firehose_turnover.py tests\test_firehose_basket_evidence.py -q`

Expected: pass; existing incomplete journal remains honestly unavailable.

- [ ] **Step 5: Commit Task 4**

```powershell
git add bot/aegis/research/firehose_basket_replay.py bot/aegis/intel/firehose_turnover.py bot/tests/test_firehose_runtime_replay.py
```

### Task 5: Preserve Existing Decisions And Provide Diagnostic Exit Trace

**Files:**
- Modify: `bot/aegis/intel/fast_exit_runner.py`
- Modify: `bot/scripts/run_broker_paper.py`
- Create: `bot/tests/test_firehose_exit_diagnostics.py`

**Interfaces:**
- Consumes Task 1 policy decision result and existing FastExit result.
- Produces a structured diagnostic trace; absent validated artifact does not alter existing terminal action selection.

- [ ] **Step 1: Write failing regression tests**

```python
def test_no_evidence_policy_trace_does_not_replace_existing_hold():
    outcome = combine_existing_exit_with_policy(existing_action="HOLD", policy_action="NO_EVIDENCE")
    assert outcome["action"] == "HOLD"
    assert outcome["policy_reason"] == "missing_validated_policy_artifact"


def test_exit_trace_uses_bid_for_buy_and_ask_for_sell(buy_snapshot, sell_snapshot):
    assert render_exit_trace(buy_snapshot)["liquidation_mark_side"] == "BID"
    assert render_exit_trace(sell_snapshot)["liquidation_mark_side"] == "ASK"


def test_trace_has_no_hardcoded_usd_harvest_threshold(observed_snapshot):
    assert "quick_harvest_threshold_usd" not in render_exit_trace(snapshot)
```

- [ ] **Step 2: Run focused tests and confirm no diagnostic adapter exists**

Run: `..\.venv\Scripts\python.exe -m pytest tests\test_firehose_exit_diagnostics.py tests\test_fast_exit_runner.py -q`

Expected: failure because the diagnostic functions are absent.

- [ ] **Step 3: Implement diagnostic-only composition**

Implement a helper that preserves existing `FastExit` and Profit Manager terminal
actions. It may add trace fields and a policy `NO_EVIDENCE` reason, but must not
close, lock, extend, scratch, or add clips on its own. Print or persist the
structured trace only through the existing report/turnover pathways.

- [ ] **Step 4: Run focused safety tests**

Run: `..\.venv\Scripts\python.exe -m pytest tests\test_firehose_exit_diagnostics.py tests\test_fast_exit_runner.py tests\test_run_broker_paper_helpers.py tests\test_paper_control.py -q`

Expected: pass with `allow_live` and risk assertions unchanged.

- [ ] **Step 5: Commit Task 5**

```powershell
git add bot/aegis/intel/fast_exit_runner.py bot/scripts/run_broker_paper.py bot/tests/test_firehose_exit_diagnostics.py
```

### Task 6: Verify Safety, Existing Systems, And Honest Data Availability

**Files:**
- Modify: `docs/superpowers/specs/2026-08-24-firehose-runtime-turnover-design.md` only if verification reveals a design correction.
- Create: `.superpowers/sdd/2026-08-24-firehose-runtime-turnover/task-6-report.md`

**Interfaces:**
- Consumes all completed runtime evidence/trace paths.
- Produces a verification report only; no runner launch and no policy activation.

- [ ] **Step 1: Run Firehose focused suites**

Run: `..\.venv\Scripts\python.exe -m pytest tests\test_firehose_runtime_evidence.py tests\test_firehose_basket.py tests\test_firehose_basket_runtime.py tests\test_firehose_runtime_replay.py tests\test_firehose_basket_replay.py tests\test_firehose_turnover.py tests\test_firehose_exit_diagnostics.py -q`

Expected: pass.

- [ ] **Step 2: Run Book Brain, Factory, Council, and full suite**

Run: `..\.venv\Scripts\python.exe -m pytest tests\test_firehose_basket_evidence.py tests\test_research_factory.py tests\test_council_cycle.py -q`

Run: `..\.venv\Scripts\python.exe -m pytest -q`

Expected: pass with only pre-existing warnings documented.

- [ ] **Step 3: Verify local journal and safety values read-only**

Run the existing harvest analyzer against local journal data. Record
`NO_EVIDENCE` if confirmed lifecycle/cost/OOS rows remain absent. Inspect the
DEMO YAML and assert `allow_live: false` and risk `$0.15`; do not modify it.

- [ ] **Step 4: Verify imports without starting a runner**

Run: `..\.venv\Scripts\python.exe -B -c "import aegis.research_factory.main, ai_council.cycle; print('IMPORTS_OK')"`

Expected: `IMPORTS_OK`; do not invoke continuous modes, MT5, or broker runners.

- [ ] **Step 5: Commit verification report only if requested**

The report is ignored plan workspace evidence by default. Do not commit, push,
merge, or start MT5 DEMO unless separately requested and approved.
