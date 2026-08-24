# Canonical State Semantics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make runtime and research derive identical completed M5/M15/H1 bars and Firehose state signature fields from the same completed MT5 M1 input.

**Architecture:** A new neutral pandas-only `aegis.completed_bars` module owns timestamp normalization, complete-window resampling, and session labels. A neutral `aegis.state_semantics` module owns pure state fields used by both research and runtime. Research retains its richer `MarketState` wrapper and runtime retains its compact response shape, but both consume the same frame and semantic primitives.

**Tech Stack:** Python 3.12, pandas, pytest.

**Spec:** `docs/superpowers/specs/2026-08-24-zero-trade-starvation-design.md`

## Global Constraints

- MT5 M1 timestamps are bar-open timestamps; the caller provides completed M1 bars only.
- No runtime import may depend on `aegis.research`, broker code, filesystems, configuration, or order APIs.
- Do not change config, authorization, risk limits, spread policy, or order submission in this plan.
- Do not fabricate missing M1 bars. A larger bucket is complete only when its final expected M1 open timestamp exists.
- Preserve `allow_live=false` and all existing fail-closed execution controls.

---

### Task 1: Lock Down Exact Completed-Bar Parity

**Files:**
- Create: `bot/tests/test_completed_bars.py`
- Modify: `bot/tests/test_research_pipeline.py:44-48`
- Modify: `bot/tests/test_intel_firehose_brain.py:323-332`

**Interfaces:** Defines the expected API `resample_completed(m1: pd.DataFrame, tf: str) -> pd.DataFrame` and proves it emits period-start-labelled, fully completed OHLCV bars.

- [ ] **Step 1: Write failing M5, M15, and H1 exact-bar tests**

```python
@pytest.mark.parametrize("tf, minutes", [("M5", 5), ("M15", 15), ("H1", 60)])
def test_runtime_and_research_completed_bars_match(tf, minutes):
    m1 = numbered_m1(minutes * 2 + 1)
    research = resample_completed(m1, tf)
    runtime = runtime_resample_completed(m1, minutes)
    pd.testing.assert_frame_equal(runtime.reset_index(drop=True), research["time open high low close volume".split()].reset_index(drop=True))
    assert research["time"].tolist() == [m1["time"].iloc[0], m1["time"].iloc[minutes]]
    assert research["close"].tolist() == [minutes - 1, minutes * 2 - 1]
```

Use a fixture whose M1 `open`, `high`, `low`, `close`, and `volume` encode each minute index so a shifted window cannot pass through matching totals.

- [ ] **Step 2: Run the targeted tests and observe the current mismatch**

Run: `..\.venv\Scripts\python.exe -m pytest tests\test_completed_bars.py tests\test_research_pipeline.py -q`

Expected: M5/M15/H1 runtime comparisons fail because runtime uses right-closed, right-labelled resampling and removes the actual latest complete bucket.

- [ ] **Step 3: Add completion-boundary and missing-minute tests**

```python
def test_resample_excludes_partial_and_gapped_bucket():
    m1 = numbered_m1(11).drop(index=4)
    assert resample_completed(m1, "M5").empty
```

Add a second case with twelve contiguous M1 bars proving exactly two M5 rows are retained and the final two source M1 bars are not treated as an output M5 candle.

- [ ] **Step 4: Commit the red test-only change**

```powershell
git add bot/tests/test_completed_bars.py bot/tests/test_research_pipeline.py bot/tests/test_intel_firehose_brain.py
```

### Task 2: Extract Neutral Completed-Bar and State Primitives

**Files:**
- Create: `bot/aegis/completed_bars.py`
- Create: `bot/aegis/state_semantics.py`
- Modify: `bot/aegis/research/dataplane.py:13-23,38-44,67-82,161-162,183-195`
- Modify: `bot/aegis/intel/state_runtime.py:9-101,141-203`

**Interfaces:**
- Produces `TF_MINUTES: Mapping[str, int]` and `resample_completed(m1, tf)` from `aegis.completed_bars`.
- Produces `session_label(ts)`, `direction(frame)`, `volatility(m1)`, `structure(frame)`, `regime(m1)`, and `signature_fields(state, side, setup)` from `aegis.state_semantics`.
- `aegis.research.dataplane` continues to re-export `TF_MINUTES`, `resample_completed`, and `session_label` for current callers.

- [ ] **Step 1: Implement normalized completed-bar resampling**

```python
def resample_completed(m1: pd.DataFrame, tf: str) -> pd.DataFrame:
    minutes = TF_MINUTES[tf]
    frame = normalize_completed_m1(m1)
    if minutes == 1:
        return frame
    grouped = frame.set_index("time").resample(
        f"{minutes}min", label="left", closed="left"
    ).agg(OHLCV_AGGREGATIONS).dropna(subset=["close"])
    required_last_open = grouped.index + pd.Timedelta(minutes=minutes - 1)
    return grouped.loc[required_last_open.isin(frame["time"])].reset_index()
```

`normalize_completed_m1` must validate required OHLCV columns, convert time to UTC, sort ascending, reject duplicate timestamps, and never synthesize a missing minute. The M1 output must preserve the normalized source frame.

- [ ] **Step 2: Move pure common state calculations into `state_semantics.py`**

Implement `direction`, volatility phase, ATR/compression, confirmed-pivot structure, session label, and regime from the canonical M5/M15/H1 frames. Return the existing Firehose field vocabulary (`trend`, `range`, `noise`, `no_trade`, `unavailable`) consistently; do not retain different runtime and research implementations for the fields that form an authorization signature.

- [ ] **Step 3: Switch research and runtime to the neutral APIs**

`dataplane.annotate_bars` adds the neutral `session_label`; it must not resample locally. `state_runtime.build_runtime_state` calls the neutral resampler and semantic functions. It must preserve its public `runtime_state.v1` mapping keys and only add fields where needed for parity.

`research.market_state.build_market_state` must use the neutral frames and semantic functions for M5/M15/H1 direction, regime, M15/M5 structure, volatility, and session while retaining research-only execution, portfolio, provenance, and cost fields.

- [ ] **Step 4: Run bar-level tests and commit the implementation**

Run: `..\.venv\Scripts\python.exe -m pytest tests\test_completed_bars.py tests\test_research_pipeline.py tests\test_intel_firehose_brain.py -q`

Expected: all completed-bar tests pass, including the original partial-bucket test.

```powershell
git add bot/aegis/completed_bars.py bot/aegis/state_semantics.py bot/aegis/research/dataplane.py bot/aegis/research/market_state.py bot/aegis/intel/state_runtime.py
```

### Task 3: Prove Research/Runtime State and Signature Parity

**Files:**
- Modify: `bot/tests/test_completed_bars.py`
- Modify: `bot/tests/test_intel_firehose_brain.py`
- Create: `bot/tests/test_research_market_state.py`
- Modify: `bot/scripts/run_broker_paper.py:930-1103`

**Interfaces:** The tests compare `build_runtime_state(symbol, m1)` to `build_market_state(symbol, m1).as_dict()` and compare `runtime_signature` with the neutral signature builder for the same `side` and `setup`.

- [ ] **Step 1: Write a failing full-parity regression test**

```python
def test_research_and_runtime_state_signature_match_for_completed_m1():
    m1 = realistic_completed_m1(600)
    runtime = build_runtime_state(symbol="EURUSD", m1=m1)
    research = build_market_state(symbol="EURUSD", m1=m1).as_dict()
    assert runtime["regime"] == research["regime"]
    assert runtime["structure"]["M15"] == signature_structure(research["structure"]["M15"])
    assert runtime["structure"]["M5"] == signature_structure(research["structure"]["M5"])
    assert runtime["multi_timeframe"] == research["multi_timeframe"]
    assert runtime["session"] == research["session"]
    assert runtime_signature(runtime, side="buy", setup="scan") == state_signature(research, side="buy", setup="scan")
```

The fixture must include both trend and range transitions plus enough bars for H1 and confirmed pivots. Test a flat final candle too, proving neither path silently maps it to opposite directions.

- [ ] **Step 2: Run only the new parity test and correct semantic drift**

Run: `..\.venv\Scripts\python.exe -m pytest tests\test_completed_bars.py::test_research_and_runtime_state_signature_match_for_completed_m1 -q`

Expected before final implementation: failure on regime or structure differences. Correct the neutral primitive, not a test expectation or one consumer.

- [ ] **Step 3: Add the non-M1 fail-closed test at the runtime ingestion boundary**

```python
def test_intelligent_runner_rejects_non_m1_timeframe():
    with pytest.raises(ValueError, match="completed M1"):
        validate_intelligent_timeframe({"timeframe": "5m", "intelligent_firehose": True})
```

Add `validate_intelligent_timeframe(cfg)` in the runner and call it before `eng.bars`. It accepts only the configured M1 spelling already supported by the engine adapter. Do not resample configurable higher-timeframe input as though it were M1.

- [ ] **Step 4: Run focused verification and commit**

Run: `..\.venv\Scripts\python.exe -m pytest tests\test_completed_bars.py tests\test_research_pipeline.py tests\test_research_market_state.py tests\test_intel_firehose_brain.py tests\test_exploration_firehose.py -q`

```powershell
git add bot/tests/test_completed_bars.py bot/tests/test_intel_firehose_brain.py bot/tests/test_research_market_state.py bot/scripts/run_broker_paper.py
```

### Task 4: Verify the Complete State-Semantics Change

- [ ] Run `..\.venv\Scripts\python.exe -m pytest tests\test_completed_bars.py tests\test_research_pipeline.py tests\test_research_market_state.py tests\test_intel_firehose_brain.py tests\test_exploration_firehose.py tests\test_run_broker_paper_helpers.py -q`.
- [ ] Run `..\.venv\Scripts\python.exe -m pytest -q`.
- [ ] Run the repository's existing validation verifier after locating its documented command with `rg -n "verif(y|ier)" README.md docs bot/scripts`.
- [ ] Run `git diff --check`, inspect `git status --short`, and confirm that no generated artifact, runtime report, config safety value, or process launcher was included accidentally.
- [ ] Commit only reviewed source/tests/docs, then proceed to the separate authorization-lane and evidence-regeneration plan.
