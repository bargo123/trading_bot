# Research Factory Data And ML Integrity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce one provenance-bearing, point-in-time canonical dataframe and train real models on purged chronological splits.

**Architecture:** `research_factory/data.py` owns discovery, feature/label construction, fingerprints, and chronological partitioning. `research_factory/ml_pipeline.py` owns one fitted sklearn pipeline per model and explicit validation failures. `ResearchFactory` delegates to these components and records an honest terminal status when data or training is unavailable.

**Tech Stack:** Python 3.12, pandas, NumPy, scikit-learn, pytest.

**Spec:** `docs/superpowers/specs/2026-08-23-research-factory-integrity-design.md`

## Global Constraints

- Never place orders, access a live account, or edit live YAML.
- Never synthesize source rows, labels, targets, metrics, or successful status.
- Group every rolling or forward operation by both `symbol` and `timeframe`.
- Features use current or earlier observations only; future observations are permitted only for matured labels.
- Unknown label tails are excluded, and each split boundary purges the full label horizon.
- Rows sharing one timestamp belong to one partition.
- Missing targets and training errors fail explicitly.
- Do not commit or push unless the user explicitly authorizes it.

---

### Task 1: Discover Real Sources With Provenance

**Files:**
- Modify: `bot/aegis/research_factory/data.py:18-112`
- Create: `bot/tests/test_research_factory_data_integrity.py`

**Interfaces:**
- Produces: `DataSource(path, symbol, timeframe, source_kind, quality, metadata_path)`.
- Produces: `discover_csv_sources(roots: Sequence[Path]) -> list[DataSource]`.
- Produces: `DataPipeline.load_sources(sources: Sequence[DataSource]) -> pd.DataFrame` with `source_file`, `source_kind`, `source_quality`, `symbol`, and `timeframe` columns.

- [ ] **Step 1: Write failing discovery and provenance tests**

```python
def test_discovery_uses_snapshot_metadata_and_keeps_timeframes_separate(tmp_path):
    csv = tmp_path / "EURUSD_X_1m_7d.csv"
    pd.DataFrame({
        "time": ["2026-01-01T00:00:00Z"],
        "open": [1.1], "high": [1.2], "low": [1.0], "close": [1.15],
    }).to_csv(csv, index=False)
    csv.with_suffix(".json").write_text(json.dumps({
        "symbol": "EURUSD", "timeframe": "1m", "source": "yahoo_snapshot",
        "quality": "proxy_no_bid_ask",
    }))

    sources = discover_csv_sources([tmp_path])
    frame = DataPipeline(min_train_size=1).load_sources(sources)

    assert [(s.symbol, s.timeframe) for s in sources] == [("EURUSD", "1m")]
    assert frame.loc[0, "source_kind"] == "yahoo_snapshot"
    assert frame.loc[0, "source_quality"] == "proxy_no_bid_ask"
```

Also add `test_discovery_is_recursive_and_returns_empty_without_fallback` and assert an empty root returns `[]` and an empty dataframe.

- [ ] **Step 2: Run the tests and verify RED**

Run: `..\.venv\Scripts\python.exe -m pytest tests\test_research_factory_data_integrity.py -q`

Expected: import failure for `DataSource` or `discover_csv_sources`.

- [ ] **Step 3: Implement deterministic discovery and loading**

Add immutable `DataSource`. Read adjacent JSON metadata when present; otherwise parse known names by locating a timeframe token matching `1m|5m|15m|30m|1h|4h|1d`, never by assuming the second underscore token. Skip unreadable files with a warning and never generate rows. Normalize timestamps to UTC, retain provenance columns, and sort by `symbol`, `timeframe`, then `time`.

- [ ] **Step 4: Replace partial dataset hashing with full-content hashing**

Canonicalize column order, row order, datetimes, and nulls, then hash every row with `pd.util.hash_pandas_object(..., index=False)` plus column names and dtypes. Add a test where only row 101 changes and assert the fingerprint changes.

- [ ] **Step 5: Verify Task 1**

Run: `..\.venv\Scripts\python.exe -m pytest tests\test_research_factory_data_integrity.py -q`

Expected: all Task 1 tests pass.

- [ ] **Step 6: Commit checkpoint only if authorized**

```powershell
git add bot/aegis/research_factory/data.py bot/tests/test_research_factory_data_integrity.py
git commit -m "fix: discover research data with provenance"
```

---

### Task 2: Build Mature Labels And Purged Timestamp Splits

**Files:**
- Modify: `bot/aegis/research_factory/data.py:18-35, 114-198, 201-441`
- Modify: `bot/tests/test_research_factory_data_integrity.py`
- Modify: `bot/tests/test_research_factory.py:43-130`

**Interfaces:**
- Produces: `FeatureSet.canonical: pd.DataFrame` containing metadata, features, and labels exactly once.
- `FeatureEngineer.engineer` requires explicit positive `profit_barrier_pct` and `loss_barrier_pct`; it has no fabricated defaults.
- Produces: `DataPipeline.create_splits(df, *, label_horizon: int) -> DatasetSplit`.
- `DatasetSplit.split_info` includes `label_horizon`, timestamp bounds, and purged row counts.

- [ ] **Step 1: Write hand-calculated label tests**

Use one symbol/timeframe with closes `[100, 100, 100]`, highs `[101, 104, 101]`, lows `[99, 99, 95]`, `horizon=2`, `profit_barrier_pct=0.02`, and `loss_barrier_pct=0.02`. Assert the first row records the profit barrier at offset 1, exact MFE/MAE, `time_to_target == 1`, and that the final two rows retain null labels rather than zeros. Add a separate test asserting omitted or non-positive barrier percentages raise `ValueError`.

Add the same timestamps for a second symbol with extreme prices and assert neither symbol changes the other symbol's features or labels.

- [ ] **Step 2: Run the label tests and verify RED**

Run: `..\.venv\Scripts\python.exe -m pytest tests\test_research_factory_data_integrity.py -k "label or symbol" -q`

Expected: fabricated `time_to_target`, zero-filled tails, or cross-group calculations fail assertions.

- [ ] **Step 3: Implement grouped point-in-time features and matured labels**

Use grouping keys `['symbol', 'timeframe']`. Sort each group by time before rolling. Build future windows per group without crossing boundaries. Leave labels nullable until the full horizon exists. Require explicit positive `profit_barrier_pct` and `loss_barrier_pct`; derive each row's barrier prices from its decision-time close. Compute barrier order by scanning offsets `1..horizon`; no barrier produces a null `profit_barrier_first` and null `time_to_target`.

Return a `FeatureSet` whose `canonical` frame contains metadata columns, feature columns, and label columns with unique names. Do not fill feature warm-up NaNs globally; supervised consumers drop rows missing required features or target.

- [ ] **Step 4: Write strict timestamp and purge tests**

Create 100 timestamps with two symbols per timestamp and `label_horizon=3`. Assert:

```python
assert split.train.time.max() < split.validation.time.min()
assert split.validation.time.max() < split.test.time.min()
assert split.test.time.max() < split.sealed_holdout.time.min()
for timestamp in frame.time.unique():
    memberships = sum(timestamp in set(part.time) for part in (
        split.train, split.validation, split.test, split.sealed_holdout,
    ))
    assert memberships <= 1
assert split.split_info["label_horizon"] == 3
assert split.split_info["purged_rows"] > 0
```

- [ ] **Step 5: Run split tests and verify RED**

Run: `..\.venv\Scripts\python.exe -m pytest tests\test_research_factory_data_integrity.py -k "split or purge" -q`

Expected: row-count splitting divides equal timestamps or fails to purge boundaries.

- [ ] **Step 6: Implement unique-timestamp partitioning and horizon purge**

Choose boundaries from sorted unique timestamps using configured ratios. Assign complete timestamps to each partition. For train, validation, and test, remove the last `label_horizon` rows per symbol/timeframe before the next partition. Drop supervised rows whose target remains null. The sealed frame remains inaccessible to consumers outside `DatasetSplit.sealed_holdout`.

- [ ] **Step 7: Verify Task 2**

Run: `..\.venv\Scripts\python.exe -m pytest tests\test_research_factory_data_integrity.py tests\test_research_factory.py -q`

Expected: all data and existing factory tests pass after updating old row-count expectations to timestamp-safe expectations.

- [ ] **Step 8: Commit checkpoint only if authorized**

```powershell
git add bot/aegis/research_factory/data.py bot/tests/test_research_factory_data_integrity.py bot/tests/test_research_factory.py
git commit -m "fix: build purged point-in-time research splits"
```

---

### Task 3: Train And Infer Through One Real Sklearn Pipeline

**Files:**
- Modify: `bot/aegis/research_factory/ml_pipeline.py:35-288`
- Create: `bot/tests/test_research_factory_ml_integrity.py`

**Interfaces:**
- Produces: `MLPipeline.train(train_df, val_df=None) -> list[TrainedModel]`.
- `TrainedModel.model` is the sole fitted sklearn pipeline and `predict_proba` invokes it exactly once.
- Missing target, no numeric features, feature mismatch, and single-class targets raise `ValueError` with an explicit reason.

- [ ] **Step 1: Write failing target and leakage tests**

```python
def test_prepare_features_requires_target_and_excludes_all_labels():
    pipeline = MLPipeline(configs=[small_logistic_config()])
    with pytest.raises(ValueError, match="profit_barrier_first"):
        pipeline.train(pd.DataFrame({"feature": [0.0, 1.0]}))

    frame = labeled_frame(80)
    pipeline.train(frame.iloc[:60], frame.iloc[60:])
    assert pipeline.feature_names == ["signal"]
```

The fixture includes `target_direction`, `direction`, `return_horizon`, `mfe`, `mae`, and provenance fields so leakage is observable.

- [ ] **Step 2: Run target tests and verify RED**

Run: `..\.venv\Scripts\python.exe -m pytest tests\test_research_factory_ml_integrity.py -k "target or excludes" -q`

Expected: missing targets silently become zeros or label columns enter features.

- [ ] **Step 3: Implement explicit frame preparation**

Define one `LABEL_COLUMNS` constant. `_prepare_features` returns a dataframe, target series, and ordered feature names. Validate target presence, nulls, two classes, numeric features, and exact validation feature compatibility. Reset `self.models` and `self.feature_names` at the start of every `train` call.

- [ ] **Step 4: Write a no-double-preprocessing fit/predict test**

Train a small logistic config with `feature_selector=False` and `calibrate=False`, call `TrainedModel.predict_proba(frame)`, and assert finite probabilities of matching length. Monkeypatch the fitted pipeline's `predict_proba` with a counting wrapper and assert one invocation.

- [ ] **Step 5: Run inference test and verify RED**

Run: `..\.venv\Scripts\python.exe -m pytest tests\test_research_factory_ml_integrity.py -k "preprocessing or predict" -q`

Expected: scaler/selector is applied twice or dimensionality fails.

- [ ] **Step 6: Store only the fitted pipeline and use tuned thresholds**

`TrainedModel.predict_proba` selects `feature_names`, normalizes infinities/nulls, and calls `self.model.predict_proba` once. Remove separately executed scaler/selector fields or retain them only as metadata without invoking them. Validation metrics use `(probability >= tuned_threshold)`, not `pipeline.predict()`.

For calibration, use a sklearn-supported fitted-pipeline calibration flow that never fits a raw estimator on preprocessed validation dimensions. If validation has fewer than the minimum samples required for isotonic calibration, skip calibration and record `calibration_status` in metrics.

- [ ] **Step 7: Add repeated-training and real-model coverage**

Use reduced deterministic configs for logistic and random forest. Assert both fit and predict, and assert calling `train` twice returns exactly two models rather than four. Add safe metric handling for one-class validation folds without fabricating ROC AUC.

- [ ] **Step 8: Verify Task 3**

Run: `..\.venv\Scripts\python.exe -m pytest tests\test_research_factory_ml_integrity.py -q`

Expected: all ML integrity tests pass.

- [ ] **Step 9: Commit checkpoint only if authorized**

```powershell
git add bot/aegis/research_factory/ml_pipeline.py bot/tests/test_research_factory_ml_integrity.py
git commit -m "fix: train research models without leakage"
```

---

### Task 4: Route One Canonical Frame Through The Factory

**Files:**
- Modify: `bot/aegis/research_factory/core.py:608-735`
- Modify: `bot/tests/test_research_factory.py`
- Modify: `bot/tests/test_research_factory_data_integrity.py`

**Interfaces:**
- `ResearchFactory._run_generation()` delegates discovery, engineering, splitting, and training to `DataPipeline`, `FeatureEngineer`, and `MLPipeline`.
- Produces explicit generation status `NO_DATA` or `FAILED` when appropriate.
- `ResearchState.last_generation_status` and `last_generation_reason` persist the terminal generation outcome.
- Does not inspect `sealed_holdout` in this plan; Plan 2 owns its one-shot use.

- [ ] **Step 1: Write a canonical-frame identity test**

Construct `ResearchFactory` with `object.__new__`, install small fake collaborators that capture object identities, and invoke `_run_generation`. Assert the frame passed into `create_splits` is `feature_set.canonical`, and the returned train/validation frames are exactly those passed into `MLPipeline.train`. Assert no sealed frame reaches training.

- [ ] **Step 2: Run the orchestration test and verify RED**

Run: `..\.venv\Scripts\python.exe -m pytest tests\test_research_factory_data_integrity.py -k canonical -q`

Expected: core splits `labeled_data` and bypasses `research_df`.

- [ ] **Step 3: Replace duplicate core data methods with delegation**

Remove or stop calling `_load_dataset`, `_engineer_features`, `_create_labels`, `_split_data`, and `_train_models` implementations in `core.py`. Inject or initialize the canonical collaborators once. Update `state.dataset_fingerprint` from the full canonical frame. Return before hypothesis work on `NO_DATA` or training failure and record the reason in state/events.

- [ ] **Step 4: Add a no-data regression**

Assert an empty source catalog produces `NO_DATA`, zero model calls, zero hypotheses, zero experiments claiming metrics, and no factory exception.

- [ ] **Step 5: Verify Plan 1**

Run: `..\.venv\Scripts\python.exe -m pytest tests\test_research_factory.py tests\test_research_factory_data_integrity.py tests\test_research_factory_ml_integrity.py -q`

Expected: all focused tests pass.

Run: `..\.venv\Scripts\python.exe -m pytest -q`

Expected: complete baseline passes; record the exact count.

- [ ] **Step 6: Commit checkpoint only if authorized**

```powershell
git add bot/aegis/research_factory/core.py bot/tests/test_research_factory.py bot/tests/test_research_factory_data_integrity.py
git commit -m "fix: route canonical data through research factory"
```
