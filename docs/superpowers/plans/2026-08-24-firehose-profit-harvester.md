# Firehose Profit Harvester Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an evidence-gated, ticket-scoped fast profit harvester that improves Firehose turnover without weakening DEMO safety or changing Research Factory or AI Council architecture.

**Architecture:** A read-only analyzer turns complete ticket lifecycle records into honest bucket and policy-comparison reports. A pure `ProfitHarvester` receives normalized ticket economics and microstructure evidence from `evaluate_fast_exit`; it returns explained close/lock/hold/scratch decisions without creating orders. `run_broker_paper.py` continues to own broker execution, close confirmation, metadata release, journal events, and re-entry gating.

**Tech Stack:** Python 3, dataclasses, pytest, JSONL journals, existing broker-native `BrokerSymbolSpec` math, existing `QuoteBuffer`, MT5 DEMO runner.

**Spec:** `docs/superpowers/specs/2026-08-24-firehose-profit-harvester-design.md`

## Global Constraints

- Do not delete, disable, replace, or couple Research Factory, AI Council, Book Brain, replay, ML training, or champion/challenger governance to the runtime.
- Do not modify `bot/config*.yaml`, `allow_live`, risk limits, entry-quality gates, or make live orders.
- Preserve `engine=mt5`, `mode=mt5_demo`, `allow_live=false`, `paper_trading_enabled=true`, and `exploration_max_risk_per_trade_usd=0.15`.
- Use exact ticket metadata and BUY=BID/SELL=ASK liquidation marks; missing broker/cost/ticket/microstructure evidence fails closed.
- No fixed USD take-profit threshold. Runtime policy parameters are normalized R/cost/age/momentum values and activate only with explicit evidence.
- Preserve unrelated dirty worktree files. Selectively stage only files named in each task.
- Never claim profitability without forward DEMO evidence. Repository `AGENTS.md` prohibits order placement, so do not start an MT5 order runner.

---

### Task 1: Honest Firehose Lifecycle Analysis

**Files:**
- Create: `bot/aegis/intel/firehose_harvest_research.py`
- Create: `bot/scripts/analyze_firehose_harvest.py`
- Create: `bot/tests/test_firehose_harvest_research.py`

**Interfaces:**
- Produces: `analyze_ticket_lifecycles(events: Iterable[Mapping[str, Any]]) -> dict[str, Any]`.
- Produces: `write_harvest_report(report: Mapping[str, Any], json_path: Path, markdown_path: Path) -> None`.
- Consumes complete `firehose_open`, `firehose_exit_trace`, and confirmed `pm_exit`/deal lifecycle events keyed by ticket.

- [ ] **Step 1: Write failing lifecycle-analysis tests**

```python
def test_incomplete_ticket_is_reported_not_inferred():
    report = analyze_ticket_lifecycles([{"event": "firehose_open", "ticket": "T1"}])
    assert report["completed_tickets"] == 0
    assert report["incomplete_tickets"] == ["T1"]
    assert report["buckets"]["0.70_usd"]["count"] == 0

def test_complete_ticket_reports_peak_capture_and_hold_metrics():
    report = analyze_ticket_lifecycles(COMPLETE_TICKET_EVENTS)
    bucket = report["buckets"]["0.70_usd"]
    assert bucket["count"] == 1
    assert bucket["realized_net_usd"] == pytest.approx(0.55)
    assert bucket["peak_unrealized_usd"] == pytest.approx(0.80)
    assert bucket["profit_capture_ratio"] == pytest.approx(0.6875)
```

- [ ] **Step 2: Run tests to verify RED**

Run: `..\.venv\Scripts\python.exe -m pytest tests\test_firehose_harvest_research.py -q`

Expected: FAIL because the module and analyzer do not exist.

- [ ] **Step 3: Implement strict lifecycle reconstruction**

```python
USD_BUCKETS = (0.30, 0.50, 0.70, 0.80, 1.00)

def analyze_ticket_lifecycles(events):
    # Match exact tickets; only confirmed exits and observed MFE are complete.
    # Never fill absent peak/cost/close-time fields with zero.
    tickets = index_events_by_ticket(events)
    return summarize_complete_tickets(tickets, USD_BUCKETS)
```

Implement bucket metrics, winner/loser distribution, average/median/p95/p99/max loss, `wins_erased_by_*`, hold-time percentiles, round-trips/hour, time between close and subsequent entry, slot utilization, profit capture, and cost per round trip. Report `NO_COMPLETE_LIFECYCLE_EVIDENCE` when any requested metric lacks required observations.

- [ ] **Step 4: Add deterministic policy-comparison tests**

```python
def test_policy_comparison_rejects_missing_cost_or_quote_evidence():
    result = compare_exit_policies(INCOMPLETE_REPLAY_ROWS)
    assert result["status"] == "NO_EVIDENCE"

def test_policy_comparison_ranks_by_oos_expectancy_not_win_rate():
    result = compare_exit_policies(COSTED_OOS_ROWS)
    assert result["selection_metric"] == "oos_expectancy_after_cost"
    assert result["winner"] != "highest_win_rate_policy"
```

- [ ] **Step 5: Implement policy comparison and CLI**

Implement `compare_exit_policies(rows)` for original structural, quick harvest, extension, MFE floor, remaining-EV, and combination policies. Require costed OOS rows. The CLI accepts explicit `--journal`, `--json-out`, and `--markdown-out` paths and writes only reports, never config or runtime state.

- [ ] **Step 6: Run focused tests to verify GREEN**

Run: `..\.venv\Scripts\python.exe -m pytest tests\test_firehose_harvest_research.py -q`

Expected: PASS.

- [ ] **Step 7: Commit Task 1**

```powershell
git add bot/aegis/intel/firehose_harvest_research.py bot/scripts/analyze_firehose_harvest.py bot/tests/test_firehose_harvest_research.py
git commit -m "feat: analyze firehose harvest evidence"
```

### Task 2: Pure Profit Harvester Policy

**Files:**
- Create: `bot/aegis/intel/profit_harvester.py`
- Modify: `bot/aegis/intel/fast_firehose.py:27-35,428-524`
- Create: `bot/tests/test_profit_harvester.py`
- Modify: `bot/tests/test_fast_firehose.py:143-205`

**Interfaces:**
- Produces: `HarvestInput` dataclass with ticket, side, net_pnl_r, mfe_r, age_s, return_5s_r, return_15s_r, return_30s_r, remaining_ev, remaining_ev_status, spread_normal, and observed-cost fields.
- Produces: `ProfitHarvester.evaluate(input: HarvestInput) -> HarvestDecision` where `action` is `QUICK_TAKE`, `PROFIT_LOCK`, `MOMENTUM_HOLD`, `SCRATCH`, `ABORT`, or `UNAVAILABLE`.
- Consumes: evidence-backed `HarvestPolicy` supplied through runtime config/state, never a USD profit threshold.

- [ ] **Step 1: Write failing policy tests**

```python
def test_cost_adjusted_profitable_stall_quick_takes():
    decision = harvester.evaluate(stalled_winner(net_pnl_r=0.7, mfe_r=0.8))
    assert decision.action == "QUICK_TAKE"
    assert decision.reason == "momentum_stall_profit_harvest"

def test_accelerating_winner_gets_bounded_momentum_hold():
    decision = harvester.evaluate(accelerating_winner())
    assert decision.action == "MOMENTUM_HOLD"

def test_floor_breach_takes_before_normal_loss():
    decision = harvester.evaluate(armed_winner(mfe_r=1.0, net_pnl_r=0.45))
    assert decision.action == "QUICK_TAKE"
    assert decision.reason == "profit_floor_breach"
```

- [ ] **Step 2: Run tests to verify RED**

Run: `..\.venv\Scripts\python.exe -m pytest tests\test_profit_harvester.py -q`

Expected: FAIL because `profit_harvester` does not exist.

- [ ] **Step 3: Implement normalized, fail-closed policy**

```python
@dataclass(frozen=True)
class HarvestPolicy:
    min_net_r: float
    min_mfe_r: float
    protected_mfe_fraction: float
    max_extension_s: float
    scratch_age_s: float
    scratch_loss_r: float

def evaluate(self, input: HarvestInput) -> HarvestDecision:
    if not input.has_required_evidence:
        return HarvestDecision("UNAVAILABLE", "harvest_evidence_unavailable")
    return self._evaluate_observed_state(input)
```

Order decisions: invalid/negative estimated EV -> `ABORT`; armed floor breach -> `QUICK_TAKE`; meaningful profit plus stalled/weakening momentum -> `QUICK_TAKE`; only strong favorable momentum, positive EV, normal spread, no giveback, and age inside extension -> `MOMENTUM_HOLD`; no-progress adverse early trade -> `SCRATCH`; otherwise `UNAVAILABLE`/existing FastExit behavior. Do not mutate stops or submit orders.

- [ ] **Step 4: Add loss and safety regressions**

```python
def test_negative_remaining_ev_aborts():
    assert harvester.evaluate(observed_state(remaining_ev=-0.01)).action == "ABORT"

def test_no_progress_loser_scratches_before_protective_stop():
    assert harvester.evaluate(no_progress_loser()).action == "SCRATCH"

def test_missing_cost_or_momentum_evidence_is_unavailable():
    assert harvester.evaluate(observed_state(return_5s_r=None)).action == "UNAVAILABLE"

def test_fast_exit_legacy_target_take_behavior_is_unchanged():
    assert legacy_machine.evaluate(**AT_TARGET).action == "TAKE"
```

- [ ] **Step 5: Integrate the policy behind FastExit**

Extend `ExitAction` with `QUICK_TAKE` and `MOMENTUM_HOLD`. Let `FastExitStateMachine.evaluate()` consume an optional harvest decision only after existing liquidation geometry and before default HOLD; preserve target, regime-loss, time, giveback, and EV protections. Map `PROFIT_LOCK` to the existing `LOCK` execution path and `QUICK_TAKE` to a close action.

- [ ] **Step 6: Run focused tests to verify GREEN**

Run: `..\.venv\Scripts\python.exe -m pytest tests\test_profit_harvester.py tests\test_fast_firehose.py -q`

Expected: PASS.

- [ ] **Step 7: Commit Task 2**

```powershell
git add bot/aegis/intel/profit_harvester.py bot/aegis/intel/fast_firehose.py bot/tests/test_profit_harvester.py bot/tests/test_fast_firehose.py
git commit -m "feat: add normalized firehose profit harvester"
```


### Task 3: Production Adapter, Trace, And Clean Re-entry

**Files:**
- Modify: `bot/aegis/intel/fast_exit_runner.py:16-154`
- Modify: `bot/aegis/intel/ticket_metadata.py:33-155`
- Create: `bot/aegis/intel/firehose_turnover.py`
- Modify: `bot/scripts/run_broker_paper.py:1598-1900`
- Modify: `bot/tests/test_fast_exit_production.py`
- Create: `bot/tests/test_firehose_turnover.py`

- Produces: `build_harvest_input(ctx: FastExitContext) -> HarvestInput | None` using broker-native USD/R conversion, `QuoteBuffer`, exact ticket metadata, and estimated remaining EV.
- Produces: `FirehoseReentryGuard.record_close(ticket, thesis_key, quote_fingerprint, closed_at)` and `allows(thesis_key, quote_fingerprint, now) -> tuple[bool, str]`.
- Produces: `firehose_exit_trace(ctx, verdict) -> dict[str, Any]` with all required observed fields.

- [ ] **Step 1: Write failing production adapter tests**

```python
def test_buy_harvest_uses_bid_and_sell_harvest_uses_ask():
    assert build_harvest_input(BUY_CONTEXT).liquidation_mark == BUY_CONTEXT.current_bid
    assert build_harvest_input(SELL_CONTEXT).liquidation_mark == SELL_CONTEXT.current_ask

def test_exact_ticket_metadata_supplies_stop_target_and_opened_time():
    assert build_harvest_input(CONTEXT_WITH_META).opened_ts == CONTEXT_WITH_META.ticket_meta.opened_ts

def test_missing_quote_history_keeps_existing_safety_hold():
    assert evaluate_fast_exit(CONTEXT_WITHOUT_QUOTES)["action"] == "HOLD"

def test_trace_contains_pnl_r_mfe_floor_momentum_ev_and_reason():
    assert {"pnl_r", "mfe_r", "profit_floor_r", "return_5s_r", "remaining_ev", "reason"} <= firehose_exit_trace(CONTEXT, VERDICT).keys()
```

- [ ] **Step 2: Run tests to verify RED**

Run: `..\.venv\Scripts\python.exe -m pytest tests\test_fast_exit_production.py -q`

Expected: FAIL because adapter trace/harvest input fields do not exist.

- [ ] **Step 3: Extend FastExitContext and adapter**

Add optional quote-buffer, estimated remaining EV/status, and current cost/spread evidence fields. Use `BrokerSymbolSpec` for USD-to-pips/R conversion. Read side-specific 5/15/30 second returns from `QuoteBuffer`; unavailable observations yield no harvest input and preserve safety behavior. Return trace fields with `None` for unavailable observed values, never zero defaults.

- [ ] **Step 4: Write failing lifecycle/re-entry tests**

```python
def test_successful_close_releases_metadata_and_slot():
    assert close_confirmed("T1", ok=True).metadata_removed is True

def test_same_thesis_same_quote_cannot_reenter_immediately():
    guard.record_close("T1", "thesis", "quote-a", 100.0)
    assert guard.allows("thesis", "quote-a", 101.0) == (False, "stale_reentry")

def test_new_quote_fingerprint_allows_valid_fast_reentry():
    guard.record_close("T1", "thesis", "quote-a", 100.0)
    assert guard.allows("thesis", "quote-b", 101.0)[0] is True

def test_quick_take_is_closed_through_existing_close_ticket_path():
    assert run_exit_action("QUICK_TAKE", "T1").close_ticket_called is True
```

- [ ] **Step 5: Implement runner-only lifecycle integration**

Record continuous quotes before evaluation; pass exact metadata, quote buffer, costs, and current remaining EV to `FastExitContext`. Emit `[FIREHOSE EXIT TRACE]` journal/log payloads. Treat `QUICK_TAKE`, `SCRATCH`, and `ABORT` as existing close execution requests. Remove ticket metadata and update turnover/re-entry state only after `close_ticket()` confirms success. Do not change order sizing, risk, entry gates, or YAML.

- [ ] **Step 6: Run focused tests to verify GREEN**

Run: `..\.venv\Scripts\python.exe -m pytest tests\test_fast_exit_production.py tests\test_firehose_turnover.py -q`

Expected: PASS.

- [ ] **Step 7: Commit Task 3**

```powershell
git add bot/aegis/intel/fast_exit_runner.py bot/aegis/intel/ticket_metadata.py bot/aegis/intel/firehose_turnover.py bot/scripts/run_broker_paper.py bot/tests/test_fast_exit_production.py bot/tests/test_firehose_turnover.py
git commit -m "feat: trace firehose exits and clean reentry"
```


### Task 4: Runtime Metrics, Evidence Reports, And Integration Verification

**Files:**
- Modify: `bot/aegis/intel/firehose_turnover.py`
- Modify: `bot/scripts/run_broker_paper.py`
- Modify: `bot/aegis/intel/firehose_harvest_research.py`
- Create: `bot/tests/test_firehose_harvest_integration.py`

- Produces: `TurnoverMetrics.snapshot(now) -> Mapping[str, float | None]` containing median/p90 hold, round trips/hour, close-to-entry interval, slot utilization, capture ratio, gross/net per hour, and cost per round trip.
- Produces: append-only `firehose_open`, `firehose_exit_trace`, and confirmed `firehose_close` journal records.

- [ ] **Step 1: Write failing end-to-end metric tests**

```python
def test_two_confirmed_round_trips_report_turnover_and_capture():
    metrics = metrics_from_confirmed_lifecycle_events(EVENTS)
    assert metrics["round_trips_per_hour"] == pytest.approx(2.0)
    assert metrics["profit_capture_ratio"] == pytest.approx(0.75)

def test_failed_close_does_not_release_slot_or_count_round_trip():
    assert metrics_after_failed_close().snapshot(120.0)["round_trips_per_hour"] == 0.0

def test_metrics_do_not_train_or_promote_research_artifacts():
    assert run_metrics_snapshot().research_or_council_calls == []
```

- [ ] **Step 2: Run tests to verify RED**

Run: `..\.venv\Scripts\python.exe -m pytest tests\test_firehose_harvest_integration.py -q`

Expected: FAIL because lifecycle metrics do not exist.

- [ ] **Step 3: Implement append-only metrics and report integration**

Persist observed metrics in the Firehose journal/report path only. Include terminal health snapshots in heartbeat/report payloads, but do not import Research Factory or AI Council into the runtime. Ensure analyzer consumes these metrics read-only.

- [ ] **Step 4: Run Firehose and protected-system verification**

Run:

```powershell
..\.venv\Scripts\python.exe -m pytest tests\test_fast_firehose.py tests\test_fast_exit_production.py tests\test_fast_exit_integration.py tests\test_profit_harvester.py tests\test_firehose_turnover.py tests\test_firehose_harvest_research.py tests\test_firehose_harvest_integration.py -q
..\.venv\Scripts\python.exe -m pytest tests\test_research_factory.py tests\test_council_cycle.py tests\test_council_live.py -q
..\.venv\Scripts\python.exe -c "from aegis.research_factory.core import ResearchFactory; from ai_council.agents import ask_agent; print('imports-ok')"
..\.venv\Scripts\python.exe -m pytest -q
```

Expected: all pass; full-suite count must be recorded exactly. Verify safety by reading the configured DEMO values without editing YAML and assert `allow_live is False` and risk is `0.15`.

- [ ] **Step 5: Run the analyzer against existing history**

Run:

```powershell
..\.venv\Scripts\python.exe scripts\analyze_firehose_harvest.py --journal reports\mt5_demo_firehose_hw_journal.jsonl --json-out reports\research\firehose_profit_harvest.json --markdown-out reports\research\firehose_profit_harvest.md
```

Expected: either complete observed metrics or an explicit no-evidence/incomplete-lifecycle result; never a fabricated policy selection.

- [ ] **Step 6: Commit Task 4**

```powershell
git add bot/aegis/intel/firehose_turnover.py bot/aegis/intel/firehose_harvest_research.py bot/scripts/run_broker_paper.py bot/tests/test_firehose_harvest_integration.py bot/reports/research/firehose_profit_harvest.json bot/reports/research/firehose_profit_harvest.md
git commit -m "feat: report firehose turnover evidence"
```

### Task 5: Final Review, Safety Verification, And Delivery

**Files:**
- Modify: `docs/superpowers/specs/2026-08-24-firehose-profit-harvester-design.md` only if implementation evidence requires a factual correction.

- [ ] **Step 1: Inspect safety-sensitive diff**

Run:

```powershell
git diff --check HEAD~4..HEAD
git diff HEAD~4..HEAD -- bot/config*.yaml bot/aegis/research bot/ai_council
git status --short
```

Expected: no config safety change; no deletion/disablement of Research Factory or Council; unrelated worktree changes remain unstaged.

- [ ] **Step 2: Verify Research Factory command startup without running a persistent worker**

Run the existing help/import-safe entry point identified in `bot/aegis/research_factory/main.py` with `--help` or equivalent, then run its focused tests. Do not start a persistent process or invoke an external AI CLI.

- [ ] **Step 3: Push without merging**

```powershell
git status --short --branch
git push origin opencode/exploration-firehose
```

Expected: branch pushes successfully; no merge command is run.

- [ ] **Step 4: Report evidence honestly**

State the historical analysis result, test commands/results, safety checks, pushed commit range, and that no live/Demo order runner was started because repository policy forbids order placement. Do not claim improved profitability until forward DEMO evidence exists.
