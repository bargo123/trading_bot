# Safe Firehose Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the DEMO Firehose auditable and capable of safely executing only exact-family, real-evidence validated opportunities while retaining a bounded exploration lane.

**Architecture:** The runtime emits a correlated, terminal funnel record for every scan and maintains separate intent, submission, and fill counts. Research produces family-scoped artifacts from executable trade facts and exact runtime matching; missing historical execution evidence remains fail-closed. Existing FastExit and watcher/factory/council services remain separate from broker submission.

**Tech Stack:** Python 3.12, pandas, pytest, MT5 DEMO adapter, JSON/JSONL artifacts, existing ResearchFactory replay and walk-forward modules.

**Spec:** `docs/superpowers/specs/2026-08-24-safe-firehose-expansion-design.md`

## Global Constraints

- Preserve MT5 DEMO mode and `allow_live: false`.
- Keep all exploration limits exactly as configured.
- Do not force a trade or relax fresh quote, measured spread, economics, geometry, portfolio, sizing, or self-hedge gates.
- Treat missing executable historical cost evidence as `NO_EVIDENCE`.
- `FIRES` means broker submission and `FILLS` means broker-confirmed execution.

---

### Task 1: Diagnose Micro Families Without Changing Decisions

**Files:**
- Modify: `bot/aegis/intel/fast_firehose.py`
- Modify: `bot/aegis/intel/firehose_brain.py`
- Test: `bot/tests/test_fast_firehose.py`
- Test: `bot/tests/test_exploration_firehose.py`

**Interfaces:**
- Produces `diagnose_micro_candidates(ctx: FastMarketContext) -> tuple[list[MicroCandidate], dict[str, str]]`.
- Produces `ExplorationAttempt` journal data with `micro_candidate_count` and per-family diagnostics.

- [ ] **Step 1: Write failing diagnostics tests**

```python
def test_micro_diagnostics_identify_missing_return_without_candidate():
    candidates, reasons = diagnose_micro_candidates(context_without_returns())
    assert candidates == []
    assert reasons["micro_momentum_burst"] == "missing_return_30s"

def test_exploration_journal_records_micro_rejection_reason():
    decision = brain.evaluate(**undercovered_state_without_m15_range())
    assert decision.journal["exploration_skip"] == "no_micro_candidate_matched"
    assert decision.journal["micro_diagnostics"]["fair_value_snapback"] == "missing_m15_range"
```

- [ ] **Step 2: Run the focused tests and confirm they fail**

Run: `..\\.venv\\Scripts\\python.exe -m pytest tests\\test_fast_firehose.py tests\\test_exploration_firehose.py -q`

Expected: failures because the diagnostics API and journal fields do not exist.

- [ ] **Step 3: Implement fail-closed diagnostics**

Implement family-local diagnostic predicates that return the same candidate as
the existing generator or a precise reason. Preserve the current candidate
logic and exception fail-closed behavior. Replace the single opaque
`no_micro_candidate_matched` result with structured journal metadata only.

- [ ] **Step 4: Run focused tests**

Run: `..\\.venv\\Scripts\\python.exe -m pytest tests\\test_fast_firehose.py tests\\test_exploration_firehose.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add bot/aegis/intel/fast_firehose.py bot/aegis/intel/firehose_brain.py bot/tests/test_fast_firehose.py bot/tests/test_exploration_firehose.py
```

### Task 2: Make the Runtime Funnel Truthful

**Files:**
- Modify: `bot/aegis/intel/firehose_brain.py`
- Modify: `bot/scripts/run_broker_paper.py`
- Modify: `bot/scripts/firehose_throughput.py`
- Test: `bot/tests/test_exploration_firehose.py`
- Test: `bot/tests/test_firehose_repair.py`
- Test: `bot/tests/test_execution_audit.py`

**Interfaces:**
- Produces append-only `firehose_funnel.v1` journal rows keyed by `scan_id`.
- Produces heartbeat and report counts for all 13 specified stages.

- [ ] **Step 1: Write failing funnel tests**

```python
def test_brain_intent_does_not_count_as_broker_fire():
    report = aggregate_funnel([{"event": "intel_brain_fire", "submitted": False}])
    assert report["FIRES"] == 0

def test_margin_rejection_is_a_risk_terminal_outcome():
    report = aggregate_funnel([{"event": "margin_precheck_skip"}])
    assert report["RISK_REJECT"] == 1
    assert report["FIRES"] == 0
```

- [ ] **Step 2: Run the focused tests and confirm they fail**

Run: `..\\.venv\\Scripts\\python.exe -m pytest tests\\test_firehose_repair.py tests\\test_execution_audit.py -q`

Expected: failures because funnel rows and stage counts do not exist.

- [ ] **Step 3: Implement one terminal outcome per scan**

Create a stable scan identifier at runner evaluation. Map stale, measured
spread, economics, geometry, risk, and other failures to exactly one terminal
bucket. Record `brain_intent`, `submitted`, and `filled` separately. Increment
`FIRES` immediately before the sole `place_order` call and `FILLS` only after
confirmed broker status.

- [ ] **Step 4: Update throughput aggregation and heartbeat snapshot**

Consume the versioned funnel rows; retain legacy totals only as legacy fields.
Expose the required funnel names verbatim and the dominant terminal reason.

- [ ] **Step 5: Run focused tests**

Run: `..\\.venv\\Scripts\\python.exe -m pytest tests\\test_exploration_firehose.py tests\\test_firehose_repair.py tests\\test_execution_audit.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add bot/aegis/intel/firehose_brain.py bot/scripts/run_broker_paper.py bot/scripts/firehose_throughput.py bot/tests/test_exploration_firehose.py bot/tests/test_firehose_repair.py bot/tests/test_execution_audit.py
```

### Task 3: Enforce Exact Strategy-Family Authorization

**Files:**
- Modify: `bot/scripts/research_ml_pipeline.py`
- Modify: `bot/aegis/intel/firehose_brain.py`
- Test: `bot/tests/test_audit_fixes.py`
- Test: `bot/tests/test_intel_firehose_brain.py`

**Interfaces:**
- Produces `validated_opportunities.v2` records with strategy/rule identity,
  dataset/config/code/index hashes, exact scope, measured cost source, and
  acceptance reason.
- Runtime lookup key is `symbol|strategy_family|regime|structure|session|side`.

- [ ] **Step 1: Write failing family-isolation tests**

```python
def test_validated_family_cannot_authorize_different_runtime_family(tmp_path):
    brain = gated_brain_with_family_artifact(tmp_path, family="failed_breakout_fade")
    decision = evaluate_setup(brain, setup="micro_momentum_burst")
    assert decision.reason == "state_not_in_validated_set"

def test_session_cost_provenance_is_required_for_v2_permission(tmp_path):
    artifact = write_v2_artifact_without_measured_session_cost(tmp_path)
    assert load_validated_opportunities(artifact) == {}
```

- [ ] **Step 2: Run the focused tests and confirm they fail**

Run: `..\\.venv\\Scripts\\python.exe -m pytest tests\\test_audit_fixes.py tests\\test_intel_firehose_brain.py -q`

Expected: family collisions are currently possible because the loader omits the
family key.

- [ ] **Step 3: Implement v2 artifact identity and fail-closed loader**

Preserve all v1 data while generating v2 only from exact family records.
Include measured session cost provenance and index hash. Reject malformed,
family-mismatched, stale, or missing-evidence v2 records. Do not authorize a
pooled record without exact per-symbol/family evidence.

- [ ] **Step 4: Run focused tests**

Run: `..\\.venv\\Scripts\\python.exe -m pytest tests\\test_audit_fixes.py tests\\test_intel_firehose_brain.py tests\\test_intel_spread_policy.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add bot/scripts/research_ml_pipeline.py bot/aegis/intel/firehose_brain.py bot/tests/test_audit_fixes.py bot/tests/test_intel_firehose_brain.py
```

### Task 4: Add Pre-Registered Book Mechanism Studies

**Files:**
- Create: `bot/aegis/research/firehose_mechanisms.py`
- Modify: `bot/aegis/research_factory/replay.py`
- Modify: `bot/scripts/research_ml_pipeline.py`
- Test: `bot/tests/test_firehose_mechanism_research.py`
- Test: `bot/tests/test_research_factory_replay.py`

**Interfaces:**
- Produces `FirehoseMechanismSpec` containing source classification, passage
  hashes, rule fingerprint, entry/exit rules, and falsification conditions.
- Produces executable replay facts including geometry, itemized costs, MFE,
  MAE, holding time, and exit reason.

- [ ] **Step 1: Write failing mechanism-contract tests**

```python
def test_ponsi_failed_breakout_spec_has_source_and_falsification():
    spec = built_in_mechanisms()["failed_breakout_fade_v1"]
    assert spec.source_kind == "BOOK_DERIVED"
    assert spec.passage_hashes
    assert spec.falsification

def test_replay_trade_preserves_cost_and_loss_geometry():
    trade = replay_one_pre_registered_trade(real_bar_fixture(), measured_cost_fixture())
    assert trade.net_pnl_usd == trade.gross_pnl_usd - trade.cost_usd
    assert trade.mae_r is not None and trade.mfe_r is not None
```

- [ ] **Step 2: Run the focused tests and confirm they fail**

Run: `..\\.venv\\Scripts\\python.exe -m pytest tests\\test_firehose_mechanism_research.py tests\\test_research_factory_replay.py -q`

Expected: failures because no immutable mechanism specifications or replay
geometry fields exist.

- [ ] **Step 3: Implement only traceable mechanisms**

Add Ponsi failed-breakout fade and Chan Bollinger midpoint reversion as separate
versioned specifications. Label existing unsourced mechanisms `DATA_DERIVED`
or `BOOK_COVERAGE=INSUFFICIENT`; do not promote them as book-derived. Reuse
existing replay cost evidence and preserve same-bar stop-first conservatism.

- [ ] **Step 4: Add chronological validation adapter**

Generate family-specific trade facts from real source data. Require bid/ask or
explicit measured cost evidence. If the current source cannot satisfy the
contract, write an auditable `NO_EVIDENCE` result rather than a permission.

- [ ] **Step 5: Run focused tests**

Run: `..\\.venv\\Scripts\\python.exe -m pytest tests\\test_firehose_mechanism_research.py tests\\test_research_factory_replay.py tests\\test_research_factory_walk_forward.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add bot/aegis/research/firehose_mechanisms.py bot/aegis/research_factory/replay.py bot/scripts/research_ml_pipeline.py bot/tests/test_firehose_mechanism_research.py bot/tests/test_research_factory_replay.py
```

### Task 5: Close Research and Lifecycle Evidence Gaps

**Files:**
- Modify: `bot/scripts/research_incremental_ingest.py`
- Modify: `bot/scripts/research_fast_watcher.py`
- Modify: `bot/scripts/run_broker_paper.py`
- Modify: `bot/aegis/intel/fast_exit_runner.py`
- Test: `bot/tests/test_watcher_audit.py`
- Test: `bot/tests/test_firehose_harvest_integration.py`

**Interfaces:**
- Watcher output has explicit per-symbol ingest success/failure and artifact
  provenance.
- Confirmed close records carry numeric realized net PnL, costs, MFE, MAE,
  ticket identity, and exit reason.

- [ ] **Step 1: Write failing service/lifecycle tests**

```python
def test_incremental_ingest_rejects_bad_row_with_symbol_reason(tmp_path):
    result = ingest_rows(["invalid"], symbol="EURUSD")
    assert result["status"] == "FAILED"
    assert "mapping" in result["reason"]

def test_confirmed_close_journal_has_numeric_cost_and_net_pnl():
    event = confirmed_close_event(closed_ticket_fixture())
    assert isinstance(event["cost_usd"], float)
    assert isinstance(event["realized_net_usd"], float)
```

- [ ] **Step 2: Run the focused tests and confirm they fail**

Run: `..\\.venv\\Scripts\\python.exe -m pytest tests\\test_watcher_audit.py tests\\test_firehose_harvest_integration.py -q`

Expected: failures because the all-symbol ingest exception and incomplete close
facts remain possible.

- [ ] **Step 3: Fix the watcher ingest type boundary and lifecycle facts**

Validate row mappings at ingestion boundaries, preserve a per-symbol failure
without reporting success, and make close facts use broker-confirmed numeric
values. Do not activate profit harvesting without a validated OOS policy.

- [ ] **Step 4: Run focused tests**

Run: `..\\.venv\\Scripts\\python.exe -m pytest tests\\test_watcher_audit.py tests\\test_firehose_harvest_integration.py tests\\test_fast_exit_production.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add bot/scripts/research_incremental_ingest.py bot/scripts/research_fast_watcher.py bot/scripts/run_broker_paper.py bot/aegis/intel/fast_exit_runner.py bot/tests/test_watcher_audit.py bot/tests/test_firehose_harvest_integration.py
```

### Task 6: Regenerate, Verify, Deploy, and Report

**Files:**
- Modify only generated measured artifacts: `bot/intel/validated_opportunities.json`, `bot/intel/validated_states.json`, `bot/intel/demo_canary.json`
- Modify: `bot/reports/research/firehose_throughput.json` only as generated output

- [ ] **Step 1: Regenerate artifacts without order submission**

Run the research pipeline against its real measured data. Confirm each new
permission has exact strategy-family identity, real evidence, and measured
session-cost provenance. Preserve an empty permission list when data is
insufficient.

- [ ] **Step 2: Run focused verification**

Run: `..\\.venv\\Scripts\\python.exe -m pytest tests\\test_fast_firehose.py tests\\test_exploration_firehose.py tests\\test_intel_firehose_brain.py tests\\test_audit_fixes.py tests\\test_watcher_audit.py tests\\test_firehose_harvest_integration.py -q`

Expected: PASS.

- [ ] **Step 3: Run the full suite**

Run: `..\\.venv\\Scripts\\python.exe -m pytest -q`

Expected: PASS with only known third-party warnings.

- [ ] **Step 4: Review staged changes and commit measured artifacts**

```powershell
git diff --cached --check
```

- [ ] **Step 5: Push and restart DEMO runner only after verification**

Push the reviewed branch, restart the runner pair, retain the singleton watcher,
and confirm `MetaQuotes-Demo`, `allow_live=false`, and all configured
exploration caps from the new heartbeat.

- [ ] **Step 6: Confirm the live funnel**

Verify heartbeat and throughput expose every required count. If no order is
eligible, report the dominant terminal blocker from the new funnel; do not
weaken a threshold merely to create a fill.
