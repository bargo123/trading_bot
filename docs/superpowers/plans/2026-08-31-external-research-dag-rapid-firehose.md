# External Research DAG and Rapid Firehose Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect all 14 installed GitHub systems and the complete implemented book-algorithm registry through a versioned, auditable research DAG that produces compact governed artifacts for a non-blocking rapid MT5 DEMO Firehose.

**Architecture:** A separate research orchestrator executes role-specific adapters against immutable inputs, stores content-addressed results, registers terminal outcomes, and assembles a deterministic `ResearchBundle`. The Firehose never invokes external tools; it atomically loads only a validated `ExecutionBundle` and keeps all tick-to-order work local.

**Tech Stack:** Python 3.12, dataclasses, pathlib, subprocess, concurrent.futures, hashlib, JSON, SQLite `ExperimentRegistry`, pytest, PowerShell installer, isolated `.external` environments.

**Spec:** `docs/superpowers/specs/2026-08-31-external-research-dag-rapid-firehose-design.md`

**Prediction scope:** Pinned GitHub systems and the complete book-algorithm
registry are the only external research inputs. AEGIS Council and Research
Factory remain outside this prediction path and cannot vote, set probability,
or grant execution authority.

## Global Constraints

- Preserve the existing dirty worktree; never reset, clean, stash, or overwrite unrelated files.
- `bot/scripts/run_broker_paper.py` remains the only broker-execution owner.
- `engine=mt5`, `mode=mt5_demo`, `allow_live=false`, `paper_trading_enabled=true`, and `dry_run=false` remain unchanged.
- External tools, Watcher algorithms, Book Brain and research workflows remain broker-read-only.
- The configured per-trade risk ceiling remains `$0.15`; no martingale, forced trade, or loss-based risk escalation.
- `ALGORITHM_MODULES` is the authoritative book-algorithm set; no hand-maintained subset is allowed.
- No external process executes in the Firehose hot path.
- Missing, failed, synthetic-only or unvalidated evidence cannot authorize execution.
- Do not commit or push unless the operator explicitly requests it.

## File Structure

- Create `bot/aegis/research/external_dag/contracts.py`: immutable public contracts and canonical hashing.
- Create `bot/aegis/research/external_dag/store.py`: atomic content-addressed artifact storage.
- Create `bot/aegis/research/external_dag/catalog.py`: exactly 14 installed tool specifications and role metadata.
- Create `bot/aegis/research/external_dag/adapters.py`: adapter protocol, process runner, book adapter and reference adapters.
- Create `bot/aegis/research/external_dag/scheduler.py`: dependency validation, concurrent execution, timeout, resume and deterministic assembly.
- Create `bot/aegis/research/external_dag/bundles.py`: research/execution bundle validation and promotion boundary.
- Create `bot/aegis/research/external_dag/status.py`: atomic read-only status projection for monitoring.
- Create `bot/aegis/research/external_dag/__init__.py`: stable package exports.
- Create `bot/scripts/run_external_research_dag.py`: CLI entry point; no broker imports.
- Create `bot/aegis/intel/execution_bundle.py`: fast immutable runtime loader.
- Modify `bot/aegis/intel/firehose_brain.py`: attach validated in-memory bundle context without granting book/external authority.
- Modify `bot/scripts/run_broker_paper.py`: periodic non-blocking bundle refresh and telemetry only.
- Create focused tests under `bot/tests/test_external_dag_*.py` and `bot/tests/test_execution_bundle.py`.

---

### Task 1: Immutable contracts and artifact store

**Files:**
- Create: `bot/aegis/research/external_dag/contracts.py`
- Create: `bot/aegis/research/external_dag/store.py`
- Create: `bot/aegis/research/external_dag/__init__.py`
- Test: `bot/tests/test_external_dag_contracts.py`

**Interfaces:**
- Produces: `canonical_json(value) -> str`, `content_hash(value) -> str`, `ExternalToolSpec`, `WorkflowNodeSpec`, `WorkflowSpec`, `ExternalTaskRequest`, `ExternalTaskResult`, `ArtifactEnvelope`, `ResearchBundle`, `ExecutionBundle`, `ArtifactStore.put()`, `ArtifactStore.get()`.
- Depends on: Python standard library only.

- [ ] **Step 1: Write failing canonical-hash and mutation tests**

```python
def test_artifact_hash_is_canonical_and_detects_mutation(tmp_path):
    store = ArtifactStore(tmp_path)
    first = store.put(producer="qlib", schema="qlib.v1", payload={"b": 2, "a": 1})
    second = store.put(producer="qlib", schema="qlib.v1", payload={"a": 1, "b": 2})
    assert first.content_hash == second.content_hash
    path = store.path_for(first.content_hash)
    path.write_text(path.read_text().replace('"b":2', '"b":3'), encoding="utf-8")
    with pytest.raises(ArtifactIntegrityError):
        store.get(first.content_hash)
```

- [ ] **Step 2: Run the test and verify missing-package failure**

Run: `..\.venv\Scripts\python.exe -m pytest -q tests/test_external_dag_contracts.py`

Expected: FAIL importing `aegis.research.external_dag`.

- [ ] **Step 3: Implement frozen contracts and canonical serialization**

Use frozen dataclasses with `schema_version`, stable IDs and tuple dependencies. Reject blank IDs, duplicate dependencies, negative timeouts and non-finite numeric payload values. Serialize with sorted keys, compact separators and UTF-8.

- [ ] **Step 4: Implement atomic content-addressed storage**

`ArtifactStore.put()` writes `<hash>.json.tmp`, flushes and atomically replaces `<hash>.json`. `get()` recalculates the hash and raises `ArtifactIntegrityError` on mismatch. Existing matching content is reused.

- [ ] **Step 5: Run focused tests**

Run: `..\.venv\Scripts\python.exe -m pytest -q tests/test_external_dag_contracts.py`

Expected: PASS.

- [ ] **Step 6: Record checkpoint without committing**

Run: `git diff --check -- bot/aegis/research/external_dag bot/tests/test_external_dag_contracts.py`

---

### Task 2: Complete external catalog and book-algorithm adapter

**Files:**
- Create: `bot/aegis/research/external_dag/catalog.py`
- Create: `bot/aegis/research/external_dag/adapters.py`
- Test: `bot/tests/test_external_dag_catalog.py`
- Test: `bot/tests/test_external_dag_book_adapter.py`

**Interfaces:**
- Consumes: `ExternalToolSpec`, `ExternalTaskRequest`, `ExternalTaskResult`, `ArtifactStore`.
- Produces: `load_external_catalog(project_root) -> tuple[ExternalToolSpec, ...]`, `ResearchAdapter.run(request, store) -> ExternalTaskResult`, `BookAlgorithmAdapter`.

- [ ] **Step 1: Write failing catalog completeness test**

```python
EXPECTED = {
    "OpenAlice", "awesome-systematic-trading", "qlib", "ordersim",
    "hftbacktest", "oos-lab", "Keystone",
    "algorithmic-trading-research-framework", "samvid-trading-core",
    "Vibe-Trading", "metatrader5-mcp-server", "nautilus_trader",
    "Lean", "abides",
}

def test_catalog_matches_every_installed_repository(project_root):
    catalog = load_external_catalog(project_root)
    assert {tool.tool_id for tool in catalog} == EXPECTED
    assert all(tool.repository_sha and tool.role and tool.environment for tool in catalog)
    assert all(tool.broker_authority is False for tool in catalog)
```

- [ ] **Step 2: Write failing exact book coverage test**

```python
def test_book_adapter_evaluates_exact_authoritative_registry(tmp_path, watcher_state):
    result = BookAlgorithmAdapter().run(request_for(watcher_state), ArtifactStore(tmp_path))
    rows = result.payload["algorithms"]
    assert len(rows) == len(ALGORITHM_MODULES)
    assert {row["algorithm_id"] for row in rows} == set(ALGORITHM_MODULES)
    assert all(row["execution_authority"] is False for row in rows)
```

- [ ] **Step 3: Implement catalog from the generated manifest**

Load `bot/reports/research/external_dependency_manifest.json`, require all 14 names, normalize absolute paths beneath `.external`, preserve SHA/license/version and attach one of `CONTROL_PLANE`, `SOURCE_CATALOG`, `MODEL`, `REPLAY`, `VALIDATION`, `RECOVERY`, `PREFLIGHT`, `PARITY`, or `STRESS` capabilities.

- [ ] **Step 4: Implement book adapter using the real registry**

Call `evaluate_all(state)` once, require exact algorithm ID-set equality with `ALGORITHM_MODULES`, preserve source books/applicability/view/missing inputs/warnings, hash the point-in-time input state, and stamp every row `research_only=true`, `execution_authority=false`, `order_intent=false`.

- [ ] **Step 5: Run focused tests**

Run: `..\.venv\Scripts\python.exe -m pytest -q tests/test_external_dag_catalog.py tests/test_external_dag_book_adapter.py`

Expected: PASS and exact current registry coverage.

---

### Task 3: Bounded process adapters and deterministic DAG scheduler

**Files:**
- Modify: `bot/aegis/research/external_dag/adapters.py`
- Create: `bot/aegis/research/external_dag/scheduler.py`
- Test: `bot/tests/test_external_dag_scheduler.py`

**Interfaces:**
- Consumes: `WorkflowSpec`, `WorkflowNodeSpec`, adapter mapping, `ArtifactStore`.
- Produces: `ExternalDagRunner.run(workflow, inputs) -> ResearchBundle` and `ExternalDagRunner.resume(run_id) -> ResearchBundle`.

- [ ] **Step 1: Write failing dependency/concurrency/order test**

Use fake adapters `source`, `book`, `model`, and `validate`; make source/book sleep concurrently, require model after source and validate after model+book, then assert elapsed time proves independent-node overlap while bundle node order equals topological order.

- [ ] **Step 2: Write failing timeout, cleanup and resume test**

The timeout adapter launches a child process. Assert terminal status `TIMEOUT`, child process termination, preserved bounded stderr, and resume reuses successful node hashes while rerunning only the failed node.

- [ ] **Step 3: Implement dependency validation and scheduler**

Reject unknown dependencies and cycles before starting. Submit ready nodes through `ThreadPoolExecutor`, track monotonic timing, never publish a node before all dependencies have terminal results, and serialize bundle nodes by deterministic topological index.

- [ ] **Step 4: Implement bounded subprocess execution**

Use `subprocess.Popen` with explicit argument arrays, environment allowlist, working directory validation, stdout/stderr limits, timeout, Windows process-group cleanup and no shell. Record `SUCCESS`, `FAILED`, `TIMEOUT`, `UNAVAILABLE`, or `NOT_APPLICABLE`.

- [ ] **Step 5: Implement idempotent resume**

Derive request ID from workflow hash, node spec hash and input hashes. Reuse only verified successful artifacts with identical identities. Failed, timed-out and mutated artifacts rerun.

- [ ] **Step 6: Run focused tests**

Run: `..\.venv\Scripts\python.exe -m pytest -q tests/test_external_dag_scheduler.py`

Expected: PASS with no surviving child processes.

---

### Task 4: Role-specific integration for all 14 installed tools

**Files:**
- Modify: `bot/aegis/research/external_dag/catalog.py`
- Modify: `bot/aegis/research/external_dag/adapters.py`
- Create: `bot/tests/test_external_dag_real_adapters.py`

**Interfaces:**
- Consumes: installed manifest, frozen dataset manifest, replay request, validation request.
- Produces: one `ArtifactEnvelope` per catalog tool with role-specific payload and honest terminal status.

- [ ] **Step 1: Write failing adapter registry test**

```python
def test_every_catalog_tool_has_role_specific_adapter(project_root):
    catalog = load_external_catalog(project_root)
    adapters = build_adapter_registry(project_root)
    assert set(adapters) == {tool.tool_id for tool in catalog}
    assert len({type(adapter).__name__ for adapter in adapters.values()}) >= 8
```

- [ ] **Step 2: Implement compute adapters**

Qlib consumes the frozen feature dataset and emits model/feature metadata;
ordersim and hftbacktest consume executable quote/order fixtures and emit fill,
cost and latency metrics; OOS-Lab consumes chronological predictions/outcomes;
NautilusTrader and LEAN consume the same normalized replay manifest and emit
parity metrics; ABIDES emits deterministic latency/disconnection stress.

Each worker runs in its catalog environment through explicit argv and returns
its native version, input hash, output hash and role metrics. Unsupported input
is `NOT_APPLICABLE`, never success.

- [ ] **Step 3: Implement reference/control adapters**

Awesome Systematic Trading emits a pinned source inventory; Keystone and the
research framework emit methodology/integrity checks; Samvid emits recovery and
reconciliation contract checks; Vibe-Trading emits pinned MT5-preflight contract
evidence; MT5-MCP emits read-only terminal/account/symbol diagnostics; OpenAlice
consumes the final status projection and emits a read-only control-plane health
acknowledgement.

- [ ] **Step 4: Prove no broker authority**

Scan adapter modules and subprocess commands for `order_send`, `place_order`,
`close_ticket`, pending mutation and live-mode flags. The MT5-MCP adapter must
use diagnostics-only commands and reject any mutation capability.

- [ ] **Step 5: Run real bounded adapter test**

Run: `..\.venv\Scripts\python.exe -m pytest -q tests/test_external_dag_real_adapters.py -m external`

Expected: every tool emits `SUCCESS`, `NOT_APPLICABLE`, or an exact honest
`FAILED/UNAVAILABLE` result; no catalog entry is missing and no broker mutation occurs.

---

### Task 5: ResearchBundle, ExperimentRegistry and promotion boundary

**Files:**
- Create: `bot/aegis/research/external_dag/bundles.py`
- Modify: `bot/aegis/research/registry.py`
- Test: `bot/tests/test_external_dag_bundles.py`

**Interfaces:**
- Consumes: terminal DAG node results and governed validation metrics.
- Produces: `assemble_research_bundle(...)`, `build_execution_bundle(...)`, registry run/node outcome records.

- [ ] **Step 1: Write failing incomplete/shadow rejection tests**

Assert a missing required node, negative chronological OOS, negative sealed OOS, PF <= 1, hash mismatch, missing book coverage, or parity disagreement yields `SHADOW_ONLY` and cannot create an `ExecutionBundle`.

- [ ] **Step 2: Write valid fixture promotion test**

Use a synthetic fixture explicitly marked test-only with positive metrics and all required hashes; assert the produced bundle contains only authorized symbols/horizons and no raw external commands or book consensus probability.

- [ ] **Step 3: Implement deterministic assembly and registry writes**

Sort node results by workflow order, calculate bundle hash, register workflow/dataset/node/bundle identities, and persist terminal success/failure in one transaction. Duplicate immutable runs return the existing run identity.

- [ ] **Step 4: Implement strict execution-bundle builder**

Require positive chronological and sealed executable expectancy, PF > 1,
minimum observation/loss counts, calibration and tail-loss fields, stable
perturbation status, explicit symbols/horizons, complete book coverage and valid
hashes. Missing fields reject rather than default.

- [ ] **Step 5: Run focused tests**

Run: `..\.venv\Scripts\python.exe -m pytest -q tests/test_external_dag_bundles.py tests/test_research_registry.py`

Expected: PASS.

---

### Task 6: Atomic non-blocking Firehose execution-bundle consumer

**Files:**
- Create: `bot/aegis/intel/execution_bundle.py`
- Modify: `bot/aegis/intel/firehose_brain.py`
- Modify: `bot/scripts/run_broker_paper.py`
- Test: `bot/tests/test_execution_bundle.py`
- Modify: `bot/tests/test_exploration_firehose.py`
- Modify: `bot/tests/test_run_broker_paper_helpers.py`

**Interfaces:**
- Consumes: immutable `ExecutionBundle` JSON.
- Produces: `ExecutionBundleLoader.refresh_if_changed()`, `ExecutionContext.snapshot()`, decision-journal bundle metadata.

- [ ] **Step 1: Write failing atomic loader tests**

Assert valid bundles load once, unchanged hashes do no work, partial writes are ignored, mutation fails closed, expiry and unauthorized symbols abstain, and concurrent readers see either the old complete snapshot or the new complete snapshot.

- [ ] **Step 2: Write failing hot-path isolation test**

Patch `subprocess.Popen`, external adapters and filesystem globbing to raise if
called during `brain.decide()`. Supply an already-loaded in-memory context and
assert the decision uses bundle metadata without external/file calls.

- [ ] **Step 3: Implement loader and in-memory context**

Refresh on a low-frequency runner checkpoint, verify schema/hash/validation
identity, then replace one immutable context reference under a short lock. Keep
last-known valid context when a new file is partial/corrupt and journal the
refresh failure.

- [ ] **Step 4: Attach context without authority inflation**

The brain may use validated horizon probability/model evidence and book context
already present in the bundle. Book support never becomes probability. Missing
validated evidence remains candidate-level abstention; never invoke the retired
forced-order lane.

- [ ] **Step 5: Run focused tests and benchmark**

Run: `..\.venv\Scripts\python.exe -m pytest -q tests/test_execution_bundle.py tests/test_exploration_firehose.py tests/test_run_broker_paper_helpers.py tests/test_rapid_benchmark.py`

Expected: PASS and local p95 <= 50 ms at 250 ms, 50 ms and 10 ms event intervals.

---

### Task 7: CLI, status projection and end-to-end workflow

**Files:**
- Create: `bot/aegis/research/external_dag/status.py`
- Create: `bot/scripts/run_external_research_dag.py`
- Test: `bot/tests/test_external_dag_cli.py`
- Create: `bot/reports/research/external_dag_status.json` at runtime only.

**Interfaces:**
- Consumes: workflow name, dataset manifest, project root and bounded runtime options.
- Produces: run directory, ExperimentRegistry entries, `ResearchBundle`, optional governed `ExecutionBundle`, atomic status JSON and exit code.

- [ ] **Step 1: Write failing CLI dry-run test**

Assert `--dry-run` resolves all 14 adapters, the book node, dependencies,
commands, environments and output paths without starting subprocesses.

- [ ] **Step 2: Write failing fake end-to-end test**

Run the full workflow with deterministic fake adapters. Assert all nodes execute,
the book node returns exact registry coverage, the registry contains every
terminal node, OpenAlice receives status only after bundle assembly, and no
execution bundle is created from shadow metrics.

- [ ] **Step 3: Implement CLI and cooperative cancellation**

Support `--workflow full_research_validation.v1`, `--dataset-manifest`,
`--run-id`, `--resume`, `--dry-run`, `--max-workers` and `--timeout-s`. Ctrl+C
stops child process trees, marks unfinished nodes interrupted and leaves
completed artifacts reusable.

- [ ] **Step 4: Implement atomic status projection**

Expose workflow/run status, node states, durations, hashes, book coverage,
promotion state, bundle identity and exact failures. Exclude secrets and broker
mutation controls.

- [ ] **Step 5: Run focused tests**

Run: `..\.venv\Scripts\python.exe -m pytest -q tests/test_external_dag_cli.py`

Expected: PASS.

---

### Task 8: Final verification and controlled DEMO proof

**Files:**
- Update generated reports under `bot/reports/research/` only from verified output.

**Interfaces:**
- Consumes: completed implementation and current runtime.
- Produces: exact test/runtime report; no commit or push.

- [ ] **Step 1: Run all focused DAG and Firehose tests**

Run: `..\.venv\Scripts\python.exe -m pytest -q tests/test_external_dag_contracts.py tests/test_external_dag_catalog.py tests/test_external_dag_book_adapter.py tests/test_external_dag_scheduler.py tests/test_external_dag_real_adapters.py tests/test_external_dag_bundles.py tests/test_execution_bundle.py tests/test_external_dag_cli.py tests/test_exploration_firehose.py tests/test_run_broker_paper_helpers.py tests/test_rapid_benchmark.py`

- [ ] **Step 2: Run static execution-authority audit**

Require direct `mt5.order_send()` hits only in `bot/aegis/engines/mt5.py`, zero
research mutation hits and exactly one logical `run_broker_paper.py` process.

- [ ] **Step 3: Run one full pytest**

Run from `bot`: `..\.venv\Scripts\python.exe -m pytest -q`

Record exact pass/warning count and duration.

- [ ] **Step 4: Run Firehose verifier**

Run: `..\.venv\Scripts\python.exe scripts\verify_master_spec.py --runtime`

Expected: all merge-blocking requirements verified.

- [ ] **Step 5: Run one bounded real external workflow**

Use a frozen research dataset, bounded timeouts and no broker mutation. Record
one terminal artifact for every catalog tool, exact failures, book registry
coverage, bundle hash and promotion status.

- [ ] **Step 6: Controlled MT5 DEMO restart only if source changed**

Confirm zero open positions, DEMO account, `allow_live=false`, permissions and
one execution owner. Stop the old runner cooperatively, start one new runner,
verify healthy feed, accepted causal events, active scans, bundle hash telemetry
and `$0.15` risk ceiling. Do not force a trade.

- [ ] **Step 7: Completion audit**

Check every spec acceptance item against direct files, registry rows, test
output, process state and runtime telemetry. Any missing or indirect evidence
remains incomplete; do not claim profitability or full completion.
