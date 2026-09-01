# Book Strategy Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the local trading-book corpus into provenance-linked, truthfully classified strategy records and expose exact after-cost evidence in the read-only Watcher.

**Architecture:** A source-ingestion module reads PDF/DJVU inputs page by page, hashes and deduplicates them, and emits conservative strategy records. A deterministic rule compiler evaluates only explicit rules; a point-in-time context/replay layer calculates executable outcomes; the Watcher consumes normalized registry/evaluation/outcome records and keeps proxy or untestable material visibly separate from exact evidence.

**Tech Stack:** Python 3.11+, standard library, existing `pypdf` runtime dependency, JSONL/JSON reports, pytest, existing Watcher scripts and `WatcherKnowledgeEngine`.

**Spec:** `docs/superpowers/specs/2026-08-28-watcher-strategy-evidence-design.md`

## Global Constraints

- Keep Watcher, Book Brain, Factory, Council, and research processes read-only with respect to MT5 positions.
- Only `bot/scripts/run_broker_paper.py` may submit governed MT5 DEMO orders.
- Preserve `engine: mt5`, `mode: mt5_demo`, `allow_live: false`, and `paper_trading_enabled: true`.
- Do not fabricate probabilities, fill missing features, or turn generic/M1 proxy evidence into horizon-specific captured-win probability.
- Use executable BUY `ASK -> BID` and SELL `BID -> ASK` pricing; apply spread, commission, and measurable slippage once.
- Preserve existing dirty runtime/generated files; stage only the source, test, and deliberately generated report files belonging to this work.
- Every experiment or replay run must use the existing `ExperimentRegistry` when it creates a research experiment record.

---

### Task 1: Build the canonical book-source registry

**Files:**
- Create: `bot/aegis/research/book_strategy_extraction.py`
- Create: `bot/scripts/extract_book_strategies.py`
- Create: `bot/tests/test_book_strategy_extraction.py`
- Modify: `bot/requirements.txt` only if the existing runtime does not already provide `pypdf`

**Interfaces:**
- `discover_book_sources(downloads_dir: Path) -> list[Path]` returns supported `.pdf` and `.djvu` files while excluding unrelated files and unfinished downloads.
- `extract_source_pages(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]` returns page records with `page`, `text`, and extraction metadata; failures are returned as an explicit status, not raised into fabricated content.
- `canonical_strategy_id(source_sha256: str, passage_hash: str) -> str` is stable across reruns.
- `classify_passage(text: str) -> dict[str, Any]` returns one of `CODED_EXACT`, `FAMILY_PROXY`, `UNTESTABLE_SOURCE`, or `COMPILE_ERROR` plus explicit fields and reasons.
- `build_strategy_registry(downloads_dir: Path, output_path: Path) -> dict[str, Any]` writes one JSONL record per canonical passage and returns counts, duplicate links, extraction failures, and source hashes.

- [ ] **Step 1: Write failing tests for source discovery, hashing, and conservative classification.**

```python
def test_discovery_excludes_duplicates_and_non_books(tmp_path):
    (tmp_path / "book.pdf").write_bytes(b"pdf")
    (tmp_path / "book-copy.pdf").write_bytes(b"pdf")
    (tmp_path / "partial.crdownload").write_bytes(b"partial")
    (tmp_path / "photo.mp4").write_bytes(b"video")
    paths = discover_book_sources(tmp_path)
    assert [path.name for path in paths] == ["book-copy.pdf", "book.pdf"]

def test_classification_never_calls_generic_advice_exact():
    result = classify_passage("There are no shortcuts to success.")
    assert result["status"] == "UNTESTABLE_SOURCE"
    assert result["reason"] == "missing_explicit_entry_exit_rule"

def test_explicit_rule_is_measurable_but_not_validated():
    result = classify_passage(
        "Buy when close crosses above the 20-period high. Stop at 1 ATR and exit after 10 seconds."
    )
    assert result["status"] == "CODED_EXACT"
    assert result["validation_status"] == "UNVALIDATED_RESEARCH"

def test_same_source_passage_has_stable_strategy_id():
    assert canonical_strategy_id("a" * 64, "b" * 64) == canonical_strategy_id("a" * 64, "b" * 64)
```

- [ ] **Step 2: Run the focused tests and confirm they fail because the extractor module is absent.**

Run: `..\.venv\Scripts\python.exe -m pytest -q bot/tests/test_book_strategy_extraction.py`

Expected: collection failure or missing-function failures.

- [ ] **Step 3: Implement source discovery and page extraction.**

Use `hashlib.sha256` for file and passage hashes. Use `pypdf.PdfReader(..., strict=False)` for PDFs and return `EXTRACTION_FAILED` with the exception type for unreadable files. For DJVU files without a supported decoder, return `UNSUPPORTED_FORMAT` and preserve the file hash. Do not replace empty text with OCR guesses. Deduplicate exact file hashes and retain `duplicate_of`.

- [ ] **Step 4: Implement conservative passage windows and classification.**

Build windows from pages containing explicit trading-rule markers. Mark `CODED_EXACT` only when the same window contains an explicit directional trigger plus an entry/action verb and an explicit exit/invalidation/stop/target or time rule. Mark passages with a named mechanism but missing executable parameters `FAMILY_PROXY`; mark generic advice or unsupported prose `UNTESTABLE_SOURCE`. Persist only a bounded excerpt, page range, source hashes, extraction metadata, and structured fields; never store a guessed rule.

- [ ] **Step 5: Implement the CLI and registry report.**

`extract_book_strategies.py` accepts `--downloads`, `--output`, and `--summary`. It writes JSONL records plus a JSON summary containing `sources_seen`, `sources_unique`, `pages_read`, `records_by_status`, `duplicate_count`, `unsupported_count`, and `source_hashes`. Its default output is under `bot/reports/research/` and it does not change MT5 or Watcher runtime state.

- [ ] **Step 6: Run the focused tests and commit the source-registry task.**

Run: `..\.venv\Scripts\python.exe -m pytest -q bot/tests/test_book_strategy_extraction.py`

Expected: all tests pass. Commit only the new extractor, CLI, tests, and any dependency line actually required: `git add bot/aegis/research/book_strategy_extraction.py bot/scripts/extract_book_strategies.py bot/tests/test_book_strategy_extraction.py bot/requirements.txt && git commit -m "feat: index book strategy sources"`.

### Task 2: Add deterministic rule evaluation and point-in-time context

**Files:**
- Create: `bot/aegis/research/book_strategy_evidence.py`
- Create: `bot/tests/test_book_strategy_evidence.py`
- Modify: `bot/scripts/watcher_knowledge_engine.py:285-361`

**Interfaces:**
- `compact_context_event(event: Mapping[str, Any]) -> dict[str, Any]` returns an immutable context snapshot and `context_hash`.
- `evaluate_compiled_strategy(strategy: Mapping[str, Any], context: Mapping[str, Any]) -> dict[str, Any]` returns `MATCH`, `NO_MATCH`, `MISSING_INPUT`, `INVALID_INPUT`, or `EVALUATION_ERROR` with failed predicates.
- `evaluate_strategy_evidence(record: Mapping[str, Any], state: Mapping[str, Any]) -> dict[str, Any]` preserves legacy fixture compatibility while using exact predicates only for `CODED_EXACT` records.

- [ ] **Step 1: Write failing tests for context hashes and explicit predicate outcomes.**

```python
def test_context_snapshot_is_point_in_time_and_hashed():
    snapshot = compact_context_event({"timestamp": 10, "symbol": "EURUSD", "bid": 1.1, "ask": 1.1001, "future_quote": 9})
    assert snapshot["symbol"] == "EURUSD"
    assert "future_quote" not in snapshot
    assert len(snapshot["context_hash"]) == 64

def test_buy_rule_requires_explicit_inputs():
    strategy = {"status": "CODED_EXACT", "side_rule": "BUY", "entry_rule": {"return_1s_gte": 0.0001}}
    result = evaluate_compiled_strategy(strategy, {"side": "BUY"})
    assert result["status"] == "MISSING_INPUT"
    assert "return_1s" in result["missing"]

def test_proxy_strategy_cannot_emit_exact_match():
    result = evaluate_strategy_evidence({"status": "FAMILY_PROXY", "strategy_family": "momentum"}, {"side": "BUY"})
    assert result["evidence_status"] == "FAMILY_PROXY"
    assert result["evaluation_status"] == "CONTEXT_ONLY"
```

- [ ] **Step 2: Run the focused tests and confirm failure.**

Run: `..\.venv\Scripts\python.exe -m pytest -q bot/tests/test_book_strategy_evidence.py`

- [ ] **Step 3: Implement the context snapshot.**

Allow only named point-in-time fields: timestamp, symbol, side, mechanism, horizon, session, regime, executable bid/ask/spread/quote age, short returns, tick dynamics, volatility, M1/M5/M15 summaries, structure, and provenance/schema versions. Copy nested mappings defensively, normalize finite numbers, omit unknown/future fields, and hash canonical JSON with sorted keys.

- [ ] **Step 4: Implement the allow-listed evaluator.**

Support exact comparisons, numeric ranges, directional side, named short-return thresholds, spread limits, and explicit required-context fields. Reject unsupported expression forms with `COMPILE_ERROR`/`EVALUATION_ERROR`. Return all missing fields and the first failed predicate. Keep `execution_authority=False` for every result.

- [ ] **Step 5: Integrate the evaluator into Watcher analysis without breaking old fixtures.**

When a record has the new `status`/compiled-rule fields, route it through `evaluate_strategy_evidence`; otherwise retain the current legacy applicability result and mark it `LEGACY_UNCOMPILED`. Add `context_hash`, `evidence_status`, and `evaluation_status` to compact opinions. Do not add any broker import or order surface.

- [ ] **Step 6: Run focused regression tests and commit.**

Run: `..\.venv\Scripts\python.exe -m pytest -q bot/tests/test_book_strategy_evidence.py bot/tests/test_watcher_knowledge_engine.py`

Expected: all focused tests pass. Commit: `git add bot/aegis/research/book_strategy_evidence.py bot/scripts/watcher_knowledge_engine.py bot/tests/test_book_strategy_evidence.py bot/tests/test_watcher_knowledge_engine.py && git commit -m "feat: evaluate book rules from point-in-time context"`.

### Task 3: Add executable replay and truthful evidence metrics

**Files:**
- Create: `bot/aegis/research/book_strategy_replay.py`
- Create: `bot/tests/test_book_strategy_replay.py`
- Modify: `bot/scripts/watcher_knowledge_engine.py:620-824`

**Interfaces:**
- `replay_executable_outcome(quotes: Sequence[Mapping[str, Any]], *, side: str, horizon_s: int, entry_cost_usd: float = 0.0, commission_usd: float = 0.0, slippage_usd: float = 0.0) -> dict[str, Any]` returns the exact net outcome labels.
- `summarize_strategy_evidence(outcomes: Iterable[Mapping[str, Any]]) -> dict[str, Any]` returns sample size, wins, losses, win rate, expectancy, PF when defined, loss quantiles, and calibration fields when probabilities are present.
- `replay_strategy_matches(strategy, contexts, quote_history) -> list[dict[str, Any]]` returns only chronological, point-in-time matches.

- [ ] **Step 1: Write failing tests for BUY/SELL price orientation, costs, and horizon identity.**

```python
def test_buy_uses_ask_entry_and_bid_exit():
    result = replay_executable_outcome(
        [{"timestamp": 0, "bid": 100.0, "ask": 100.2}, {"timestamp": 3, "bid": 100.5, "ask": 100.7}],
        side="BUY", horizon_s=3,
    )
    assert result["gross_pnl"] == 0.3
    assert result["p_captured_win"] == 1.0

def test_costs_are_applied_once_and_horizons_are_distinct():
    quotes = [{"timestamp": 0, "bid": 100.0, "ask": 100.2}, {"timestamp": 3, "bid": 100.25, "ask": 100.45}, {"timestamp": 10, "bid": 99.9, "ask": 100.1}]
    short = replay_executable_outcome(quotes, side="BUY", horizon_s=3, commission_usd=0.01)
    long = replay_executable_outcome(quotes, side="BUY", horizon_s=10, commission_usd=0.01)
    assert short["net_pnl"] != long["net_pnl"]
    assert short["costs_usd"] == 0.01
```

- [ ] **Step 2: Run the replay tests and confirm failure.**

Run: `..\.venv\Scripts\python.exe -m pytest -q bot/tests/test_book_strategy_replay.py`

- [ ] **Step 3: Implement sequential executable replay.**

Select the first quote at or after entry and the first quote at or after the requested horizon; use ASK for BUY entry/BID liquidation and BID for SELL entry/ASK liquidation. Record MFE/MAE from the same executable orientation, first net-green time, peak time, never-green, green-then-loser, spread, commission, slippage, tail loss, and missing-quote reasons. Apply each cost exactly once and never read quotes before entry for labels.

- [ ] **Step 4: Implement evidence aggregation.**

Compute `p_captured_win` from positive `net_pnl`, not directional price movement. Keep evidence keys by `(strategy_id, symbol, side, mechanism, horizon_s, dataset_partition)`. Return `None` for undefined PF/calibration instead of zero. Calculate ECE only from recorded probabilities and labels with a minimum sample guard; retain synthetic/proxy provenance separately.

- [ ] **Step 5: Integrate replay summaries into Watcher strategy observations.**

Store exact evidence fields under `strategy_observations[record_id]` and retain the existing broker-confirmed net-PnL truth. Mark legacy shadow results as `FAMILY_PROXY` unless they carry an exact compiled strategy ID and executable quote replay. Keep the per-trade execution owner unchanged.

- [ ] **Step 6: Run focused tests and commit.**

Run: `..\.venv\Scripts\python.exe -m pytest -q bot/tests/test_book_strategy_replay.py bot/tests/test_watcher_knowledge_engine.py`

Expected: all pass. Commit: `git add bot/aegis/research/book_strategy_replay.py bot/scripts/watcher_knowledge_engine.py bot/tests/test_book_strategy_replay.py bot/tests/test_watcher_knowledge_engine.py && git commit -m "feat: replay executable book strategy outcomes"`.

### Task 4: Link decision context to broker-confirmed learning

**Files:**
- Create: `bot/tests/test_watcher_strategy_attribution.py`
- Modify: `bot/scripts/watcher_knowledge_engine.py:770-1071`
- Modify: `bot/scripts/watch_firehose_live.py` only if the existing event flattener drops strategy/context fields

**Interfaces:**
- `_strategy_ids(state: Mapping[str, Any]) -> list[str]` remains the sole source of strategy attribution.
- `_process_open(event: Mapping[str, Any])` freezes strategy IDs and the pre-entry `context_hash`.
- `_process_close(event: Mapping[str, Any])` emits `broker_confirmed`, `realized_net_usd`, frozen strategy IDs, classification labels, and `UNATTRIBUTED` when no correlation exists.

- [ ] **Step 1: Write failing tests for frozen pre-entry attribution and missing correlation.**

```python
def test_close_uses_frozen_strategy_ids_not_post_entry_state(tmp_path):
    engine = _engine(tmp_path)
    engine.process_event({"event": "firehose_open", "ticket": "T1", "symbol": "EURUSD", "side": "BUY", "mechanism": "x", "horizon_s": 3, "strategy_ids": ["s1"], "entry_state": {"context_hash": "h1"}})
    outputs = engine.process_event({"event": "confirmed_close_finalization", "ticket": "T1", "status": "BROKER_CONFIRMED", "broker_facts": {"realized_net_usd": 0.2}, "strategy_ids": ["s2"]})
    outcome = next(row for row in outputs if row["record_type"] == "production_outcome")
    assert outcome["features"]["strategy_ids"] == ["s1"]
    assert outcome["features"]["context_hash"] == "h1"

def test_confirmed_close_without_correlation_is_unattributed(tmp_path):
    engine = _engine(tmp_path)
    outputs = engine.process_event({"event": "confirmed_close_finalization", "ticket": "T1", "status": "BROKER_CONFIRMED", "broker_facts": {"realized_net_usd": -0.1}})
    outcome = next(row for row in outputs if row["record_type"] == "production_outcome")
    assert outcome["attribution_status"] == "UNATTRIBUTED"
```

- [ ] **Step 2: Run the attribution tests and confirm failure.**

Run: `..\.venv\Scripts\python.exe -m pytest -q bot/tests/test_watcher_strategy_attribution.py`

- [ ] **Step 3: Freeze open-state metadata and carry it through close.**

Persist strategy IDs, context snapshot/hash, symbol, side, mechanism, horizon, entry quote, costs, and entry evidence in the existing in-memory open record and state file. Ignore any strategy IDs supplied on later close events. Preserve broker-confirmed net PnL as the outcome truth.

- [ ] **Step 4: Add explicit attribution and lifecycle labels.**

Emit `BAD_ENTRY`, `GOOD_ENTRY_BAD_EXIT`, `GOOD_ENTRY_GOOD_EXIT`, or `AMBIGUOUS` only when the recorded lifecycle evidence supports it; otherwise use `AMBIGUOUS`. Add `FAST_WINNER`, `FAST_LOSER`, `NEVER_GREEN`, and `GREEN_THEN_LOSER` only from recorded executable observations. Missing strategy IDs become `UNATTRIBUTED` and do not update any strategy’s exact win rate.

- [ ] **Step 5: Run the existing and new Watcher tests and commit.**

Run: `..\.venv\Scripts\python.exe -m pytest -q bot/tests/test_watcher_strategy_attribution.py bot/tests/test_watcher_knowledge_engine.py bot/tests/test_show_watcher_strategy_report.py`

Expected: all pass. Commit: `git add bot/scripts/watcher_knowledge_engine.py bot/scripts/watch_firehose_live.py bot/tests/test_watcher_strategy_attribution.py bot/tests/test_watcher_knowledge_engine.py bot/tests/test_show_watcher_strategy_report.py && git commit -m "feat: attribute confirmed outcomes to frozen strategies"`.

### Task 5: Expose every strategy’s truthful evidence and run the corpus

**Files:**
- Modify: `bot/scripts/show_watcher_strategy_report.py:51-320`
- Create: `bot/tests/test_watcher_strategy_report_evidence.py`
- Modify: `bot/scripts/watcher_dashboard.py` only where it renders strategy status/metrics
- Generate: `bot/reports/research/book_strategy_registry.jsonl`
- Generate: `bot/reports/research/book_strategy_registry_summary.json`

**Interfaces:**
- `_empty_strategy(record)` includes `evidence_status`, `evidence_source`, `exact_sample_size`, `exact_win_rate`, `proxy_sample_size`, `proxy_win_rate`, and `unattributed_outcomes`.
- `build_strategy_report(report_dir: Path) -> dict[str, Any]` preserves `None` for unavailable percentages and includes status counts.
- `render_strategy_report(report, limit=None)` visibly separates exact measured, proxy, and untestable rows.

- [ ] **Step 1: Write failing tests for visible status separation.**

```python
def test_report_does_not_show_proxy_as_exact_win_rate(tmp_path):
    report = build_strategy_report(_fixture_report_dir(tmp_path))
    row = next(item for item in report["strategies"] if item["evidence_status"] == "FAMILY_PROXY")
    assert row["exact_win_rate"] is None
    assert row["proxy_win_rate"] == 0.6

def test_unobserved_strategy_has_explicit_state_not_blank_percent(tmp_path):
    report = build_strategy_report(_fixture_report_dir(tmp_path))
    row = next(item for item in report["strategies"] if item["evidence_status"] == "UNTESTABLE_SOURCE")
    assert row["evidence_status"] == "UNTESTABLE_SOURCE"
    assert row["exact_win_rate"] is None
```

- [ ] **Step 2: Run the report tests and confirm failure.**

Run: `..\.venv\Scripts\python.exe -m pytest -q bot/tests/test_watcher_strategy_report_evidence.py`

- [ ] **Step 3: Update the report model and dashboard labels.**

Render explicit labels: `EXACT_MEASURED`, `FAMILY_PROXY`, `UNTESTABLE_SOURCE`, `NO_SAMPLES`, or `UNATTRIBUTED`. Show wins/losses/sample size, net expectancy, PF, and provenance. Never convert `None` to `0%`, and never combine proxy and exact counts in one rate.

- [ ] **Step 4: Run the extractor against the Downloads corpus.**

Run: `..\.venv\Scripts\python.exe bot/scripts/extract_book_strategies.py --downloads "C:\Users\Zaid barghouthi\Downloads" --output bot/reports/research/book_strategy_registry.jsonl --summary bot/reports/research/book_strategy_registry_summary.json`

Expected: the summary reports exact source hashes, duplicate/unsupported files, pages read, and status counts. Any unreadable source remains explicitly listed; no unsupported record is promoted to exact.

- [ ] **Step 5: Run focused tests and inspect the generated summary.**

Run: `..\.venv\Scripts\python.exe -m pytest -q bot/tests/test_watcher_strategy_report_evidence.py bot/tests/test_watcher_dashboard.py bot/tests/test_show_watcher_strategy_report.py bot/tests/test_watcher_knowledge_engine.py`

Check the summary for `sources_seen`, `sources_unique`, `pages_read`, `records_by_status`, `duplicate_count`, `unsupported_count`, and non-empty source hashes.

- [ ] **Step 6: Run the full suite once and inspect scope.**

Run: `..\.venv\Scripts\python.exe -m pytest -q`

Then run the existing Firehose verifier without restarting MT5, inspect `git diff --stat` and `git status --short`, verify `allow_live=false` and the configured DEMO risk ceiling, and report any pre-existing dirty files separately.

- [ ] **Step 7: Commit only coherent source/tests and the intended summary report.**

Stage explicit paths only. Do not stage runtime logs, raw traces, databases, watcher archives, or unrelated dirty files. Commit: `git commit -m "feat: expose truthful book strategy evidence"`. Push only if the user explicitly requests the push in a follow-up.

## Plan self-review

- The source registry, exact evaluator, replay metrics, broker attribution, and dashboard requirements from the approved spec each have an implementation task.
- Unsupported, duplicate, proxy, and untestable source states remain explicit; no step assigns a fabricated percentage.
- All interfaces use the same names and preserve the existing Watcher fallback for old fixtures.
- No task changes the MT5 execution owner or trading configuration.
- The plan contains no unresolved placeholders or deferred design decisions.
