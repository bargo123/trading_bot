# Research Factory Replay And Promotion Integrity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Compile provenance-bearing hypotheses into validated rules, replay them with broker-native costs, persist every outcome, and use the sealed holdout once per frozen candidate.

**Architecture:** New focused `rules.py` and `replay.py` modules replace ad hoc parsing and replay inside `core.py`. Existing `ExperimentRegistry`, `SealedHoldoutStore`, and governed promotion modules remain the persistence and promotion authorities. The factory orchestrates statuses but never writes champion state directly.

**Tech Stack:** Python 3.12, pandas, NumPy, pytest, existing AEGIS research and broker-math modules.

**Spec:** `docs/superpowers/specs/2026-08-23-research-factory-integrity-design.md`

## Global Constraints

- Never place orders, edit live YAML, or write champion state outside governed promotion code.
- Never invent hypothesis direction, prices, geometry, costs, trades, or metrics.
- Unknown, incomplete, or unsupported rules return `NOT_EXECUTABLE`.
- Missing broker specification or observed costs returns `NO_EVIDENCE`.
- Costs are charged exactly once using broker-native tick size and tick value.
- Every attempted hypothesis is appended to `ExperimentRegistry`.
- Sealed data is evaluated once per frozen candidate and holdout fingerprint and never used for tuning.
- Do not commit or push unless the user explicitly authorizes it.

---

### Task 1: Consolidate The Structured Hypothesis Schema

**Files:**
- Modify: `bot/aegis/research_factory/hypothesis.py`
- Modify: `bot/aegis/research_factory/core.py` to import this schema instead of defining another one
- Create: `bot/aegis/research_factory/rules.py`
- Create: `bot/tests/test_research_factory_rules.py`

**Interfaces:**
- Produces: one `Hypothesis` dataclass with dictionary `entry_rule` and `exit_rule`, explicit `side`, optional `invalidation_price`, `target_price`, and `max_hold_s`.
- Produces: `compile_hypothesis(hypothesis, available_columns) -> CompileResult`.
- `CompileResult.status` is `EXECUTABLE` or `NOT_EXECUTABLE`; executable results contain normalized rules and required columns.

- [ ] **Step 1: Write schema round-trip and enum tests**

Create a complete hypothesis with a breakout entry and regime-change exit, serialize and deserialize it, and assert equality of origin, status, side, and both rule dictionaries. Assert `Hypothesis.from_dict` constructs `HypothesisOrigin(value)` and `HypothesisRegistry.update_status` stores `HypothesisStatus(value)`.

- [ ] **Step 2: Run schema tests and verify RED**

Run: `..\.venv\Scripts\python.exe -m pytest tests\test_research_factory_rules.py -k "round_trip or status" -q`

Expected: origin is assigned the enum class or rule types do not round-trip.

- [ ] **Step 3: Implement one schema and remove the duplicate core dataclass**

Do not provide defaults for side, expected effect, dates, stop, or target. Optional fields remain `None`. Keep provenance collections explicit. Update existing imports and constructors to the canonical schema.

- [ ] **Step 4: Write compiler rejection tests**

```python
@pytest.mark.parametrize("entry_rule,reason", [
    ({"type": "unknown"}, "unknown entry rule"),
    ({"type": "breakout", "direction": "long"}, "missing columns"),
    ({"type": "breakout", "direction": "long", "window": 0}, "window"),
])
def test_invalid_rules_are_not_executable(entry_rule, reason):
    hypothesis = complete_hypothesis(entry_rule=entry_rule)
    result = compile_hypothesis(hypothesis, {"time", "close"})
    assert result.status == "NOT_EXECUTABLE"
    assert reason in result.reason
```

Also reject buy stops at or above entry, buy targets at or below entry, inverse sell geometry, missing side, and exit types whose behavior is not implemented.

- [ ] **Step 5: Run compiler tests and verify RED**

Run: `..\.venv\Scripts\python.exe -m pytest tests\test_research_factory_rules.py -k executable -q`

Expected: unsupported rules silently produce false signals.

- [ ] **Step 6: Implement the minimal rule compiler**

Support only rules with deterministic existing semantics: breakout, mean reversion, regime/structure alignment, regime change, explicit stop/target, and elapsed-time exit. Normalize direction to the hypothesis side. Return required columns and validated parameters; do not retain branches containing `pass`.

- [ ] **Step 7: Verify Task 1**

Run: `..\.venv\Scripts\python.exe -m pytest tests\test_research_factory_rules.py tests\test_research_factory.py -q`

Expected: all rule and existing factory tests pass.

- [ ] **Step 8: Commit checkpoint only if authorized**

```powershell
git add bot/aegis/research_factory/hypothesis.py bot/aegis/research_factory/rules.py bot/aegis/research_factory/core.py bot/tests/test_research_factory_rules.py
git commit -m "fix: compile only executable research hypotheses"
```

---

### Task 2: Replay With Broker-Native Geometry And Costs

**Files:**
- Create: `bot/aegis/research_factory/replay.py`
- Modify: `bot/aegis/intel/broker_math.py:17-41`
- Create: `bot/tests/test_research_factory_replay.py`
- Modify: `bot/tests/test_intel_broker_math.py` if present, otherwise add broker-spec tests to the new replay test file

**Interfaces:**
- Produces: `ReplayCostEvidence(symbol_spec, lots, spread_price, commission_usd, slippage_price)`.
- Produces: `ReplayResult(status, trades, metrics, reason)`.
- Produces: `replay_hypothesis(data, compiled, costs) -> ReplayResult`.
- `BrokerSymbolSpec.from_mapping` raises `ValueError` for absent or non-positive tick evidence.

- [ ] **Step 1: Write fail-closed broker evidence tests**

Assert `BrokerSymbolSpec.from_mapping(None)` and zero tick-size/value mappings raise `ValueError`. Assert replay without `ReplayCostEvidence` returns `NO_EVIDENCE` and no trades or metrics.

- [ ] **Step 2: Run evidence tests and verify RED**

Run: `..\.venv\Scripts\python.exe -m pytest tests\test_research_factory_replay.py -k evidence -q`

Expected: broker math fabricates FX defaults.

- [ ] **Step 3: Implement strict broker specification validation**

Require positive `trade_tick_value`, `trade_tick_size`, and `volume_min`. Preserve `trade_contract_size` only as broker-provided metadata; replay PnL uses tick conversion.

- [ ] **Step 4: Write hand-calculated buy/sell and currency-cross tests**

Use a EURUSD spec where one tick is `$1` per lot and a USDJPY spec where one tick is `$0.67` per lot. For mirrored buy and sell paths with the same favorable ticks and identical costs, assert equal net USD PnL. Derive expected values literally:

```python
expected_gross = favorable_ticks * tick_value * lots
expected_cost = spread_ticks * tick_value * lots + commission_usd + slippage_ticks * tick_value * lots
assert trade.net_pnl_usd == pytest.approx(expected_gross - expected_cost)
```

- [ ] **Step 5: Run geometry tests and verify RED**

Run: `..\.venv\Scripts\python.exe -m pytest tests\test_research_factory_replay.py -k "buy or sell or jpy" -q`

Expected: sell PnL is negated or defaults ignore tick value.

- [ ] **Step 6: Implement chronological replay**

Use bid/ask columns when available; otherwise require explicit spread evidence and derive executable bid/ask from the recorded mid without charging spread twice. Apply slippage once at fills. Convert price movement to USD through `BrokerSymbolSpec.price_units_to_usd`. Track elapsed UTC timestamps for `max_hold_s`.

Resolve same-bar stop/target collisions at the adverse stop. Fill targets at the target, never a more favorable price. Close an open final position at the final observable executable price with `exit_reason='end_of_data'`, or return it in `unresolved_positions`; test and document the selected conservative behavior.

- [ ] **Step 7: Add irregular-time, collision, and end-of-data tests**

Use timestamps at `00:00`, `00:01`, and `00:05` with `max_hold_s=120`; assert exit at `00:05`. Create a bar touching both stop and target and assert stop. Create an entry on the final tradable interval and assert it is not silently omitted.

- [ ] **Step 8: Verify Task 2**

Run: `..\.venv\Scripts\python.exe -m pytest tests\test_research_factory_replay.py tests\test_intel_trade_economics.py -q`

Expected: all replay and broker-economics tests pass. Update legacy target-synthesis expectations to fail closed where they conflict with the approved spec.

- [ ] **Step 9: Commit checkpoint only if authorized**

```powershell
git add bot/aegis/research_factory/replay.py bot/aegis/intel/broker_math.py bot/tests/test_research_factory_replay.py bot/tests/test_intel_trade_economics.py
git commit -m "fix: replay hypotheses with broker-native costs"
```

---

### Task 3: Persist Every Outcome And Protect The Sealed Gate

**Files:**
- Create: `bot/aegis/research_factory/evaluation.py`
- Modify: `bot/aegis/research/promote.py:30-138`
- Modify: `bot/aegis/research_factory/core.py:608-700`
- Create: `bot/tests/test_research_factory_evaluation.py`
- Modify: `bot/tests/test_research_promote.py`

**Interfaces:**
- Produces: `record_outcome(registry, hypothesis, dataset_fingerprint, status, reason, metrics=None) -> str`.
- Produces: `evaluate_candidate_once(candidate, sealed_store, holdout_fingerprint, evaluate) -> dict`.
- Factory terminal statuses are `NO_DATA`, `NO_EVIDENCE`, `NOT_EXECUTABLE`, `FAILED`, `REJECTED`, or `CHALLENGER`.

- [ ] **Step 1: Write registry coverage tests**

Parameterize every terminal status. Use a temporary `ExperimentRegistry`, call `record_outcome`, then assert one row exists with exact status, reason, fingerprints, provenance, and metrics. Ensure no failure status gains zero-valued performance metrics unless those values were observed.

- [ ] **Step 2: Run registry tests and verify RED**

Run: `..\.venv\Scripts\python.exe -m pytest tests\test_research_factory_evaluation.py -k record -q`

Expected: factory state lists are used instead of the governed registry.

- [ ] **Step 3: Implement the registry adapter**

Build stable experiment rows from the canonical hypothesis and `ExperimentRegistry.record`. Normalize factory uppercase statuses to the registry vocabulary without losing the original status in provenance. Duplicate and equivalent experiment errors become explicit failed outcomes; they are not swallowed.

- [ ] **Step 4: Write persistent sealed-use tests**

Freeze one candidate, evaluate it through `evaluate_candidate_once`, reconstruct `SealedHoldoutStore` from the same path, and assert the second call raises `SealedHoldoutError` before invoking the callback. Capture callback inputs and assert no sealed dataframe is available before the call.

- [ ] **Step 5: Run sealed tests and verify RED**

Run: `..\.venv\Scripts\python.exe -m pytest tests\test_research_factory_evaluation.py -k sealed -q`

Expected: core resets an in-memory boolean each generation or trains on sealed data.

- [ ] **Step 6: Implement callback-owned sealed evaluation**

The candidate is frozen before the callback. `SealedHoldoutStore.evaluate_once` owns invocation and persistence. Modify governed promotion with a new callback-based entry point; keep the existing direct-metrics entry point only for current external scripts, clearly separate from the factory path. The factory never calls `MLPipeline.train` on sealed data and never reads sealed length or distribution for fold configuration.

- [ ] **Step 7: Verify Task 3**

Run: `..\.venv\Scripts\python.exe -m pytest tests\test_research_factory_evaluation.py tests\test_research_registry.py tests\test_research_promote.py tests\test_research_shadow_firehose.py -q`

Expected: all registry, sealed, and promotion tests pass.

- [ ] **Step 8: Commit checkpoint only if authorized**

```powershell
git add bot/aegis/research_factory/evaluation.py bot/aegis/research_factory/core.py bot/aegis/research/promote.py bot/tests/test_research_factory_evaluation.py bot/tests/test_research_promote.py
git commit -m "fix: govern research outcomes and sealed evaluation"
```

---

### Task 4: Integrate Cost-Aware Expanding Walk-Forward Evaluation

**Files:**
- Create: `bot/aegis/research_factory/walk_forward.py`
- Modify: `bot/aegis/research_factory/core.py`
- Create: `bot/tests/test_research_factory_walk_forward.py`

**Interfaces:**
- Produces: `walk_forward_evaluate(frame, *, pipeline_factory, compiled, costs, min_train_timestamps, validation_timestamps, step_timestamps) -> WalkForwardResult`.
- Each fold reports train/validation timestamp bounds, sample counts, trade count, gross PnL, costs, net PnL, expectancy, drawdown, and status.

- [ ] **Step 1: Write expanding-window and cost-decision tests**

Use deterministic timestamps and a pipeline spy. Assert every fold trains only on timestamps earlier than validation, the training end expands, and no sealed timestamp appears. Run the same predictions with zero observed costs and higher observed costs; assert the higher-cost result has lower net PnL and can change `CHALLENGER` to `REJECTED`.

- [ ] **Step 2: Run walk-forward tests and verify RED**

Run: `..\.venv\Scripts\python.exe -m pytest tests\test_research_factory_walk_forward.py -q`

Expected: current `_walk_forward_validation` returns `None` or ignores replay results.

- [ ] **Step 3: Implement fold retraining and replay aggregation**

Build folds from unique timestamps. Instantiate a fresh `MLPipeline` per fold, train on the expanding prefix, predict the next validation window, convert predictions to the compiled entry rule, and call `replay_hypothesis`. Aggregate only observed fold metrics. Any failed fold remains in the result with its status and reason.

- [ ] **Step 4: Remove the incomplete core walk-forward and replay implementations**

Delegate from `ResearchFactory` to `walk_forward_evaluate`; delete the `pass` path, fabricated default costs, duplicate entry assignments, sell double-negation, and seconds-versus-bars logic from `core.py`.

- [ ] **Step 5: Verify Plan 2**

Run: `..\.venv\Scripts\python.exe -m pytest tests\test_research_factory_rules.py tests\test_research_factory_replay.py tests\test_research_factory_evaluation.py tests\test_research_factory_walk_forward.py -q`

Expected: all focused tests pass.

Run: `..\.venv\Scripts\python.exe -m pytest -q`

Expected: complete baseline passes; record the exact count.

- [ ] **Step 6: Commit checkpoint only if authorized**

```powershell
git add bot/aegis/research_factory/walk_forward.py bot/aegis/research_factory/core.py bot/tests/test_research_factory_walk_forward.py
git commit -m "fix: run cost-aware walk-forward research"
```
