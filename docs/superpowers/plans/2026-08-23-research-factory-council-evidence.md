# Research Factory Council And Evidence Integrity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reuse one streaming AI Council adapter, enforce the exhausted Codex budget, and attach hashed supporting and contradictory Book Brain evidence without fabricated fallbacks.

**Architecture:** `ai_council/agents.py` becomes the sole process adapter and `ai_council/live.py` adds budget-aware research orchestration. `research_factory/evidence.py` adapts existing book indexes and thesis evidence into explicit support/contradiction sets. `ResearchFactory` consumes these interfaces and contains no local Claude/Codex client or simulated response.

**Tech Stack:** Python 3.12, subprocess `Popen`, JSON, existing AEGIS BookIndex/knowledge/thesis modules, pytest.

**Spec:** `docs/superpowers/specs/2026-08-23-research-factory-integrity-design.md`

## Global Constraints

- Never invoke a paid API or place an order.
- Claude and Codex asks stream retained output with `[CLAUDE]` and `[CODEX]` prefixes.
- Ask paths use `Popen`, not `subprocess.run(capture_output=True)`.
- AI failures never create simulated text or hypotheses.
- The sole Codex call is already consumed; no Codex probe or ask occurs without an explicit new human budget.
- Unknown book queries return no evidence, not unrelated fallback evidence.
- Supporting and contradictory evidence retain source location, hash, polarity, and executable status.
- Do not commit or push unless the user explicitly authorizes it.

---

### Task 1: Stream Shared Agent Output Through Popen

**Files:**
- Modify: `bot/ai_council/agents.py:244-347`
- Modify: `bot/tests/test_council_cycle.py`

**Interfaces:**
- `ask_agent(name, prompt, *, timeout_s=240, cwd=None, line_sink=None) -> dict`.
- `line_sink` receives complete prefixed lines while the returned `output` retains unprefixed parseable content.
- Existing status vocabulary and JSON parsing remain stable.

- [ ] **Step 1: Write a FakePopen streaming test**

Create a fake process with iterable stdout lines `['first\n', '{"answer": 1}\n']`, empty stderr, `returncode=0`, and `wait/poll/kill` behavior. Patch `subprocess.Popen` and call `ask_agent('claude', ..., line_sink=seen.append)`. Assert:

```python
assert seen == ["[CLAUDE] first", '[CLAUDE] {"answer": 1}']
assert result["output"] == 'first\n{"answer": 1}\n'
assert result["parsed"] == {"answer": 1}
```

Add an equivalent Codex prefix case and timeout case.

- [ ] **Step 2: Run streaming tests and verify RED**

Run: `..\.venv\Scripts\python.exe -m pytest tests\test_council_cycle.py -k stream -q`

Expected: `_run_ask` uses `subprocess.run` and emits no lines.

- [ ] **Step 3: Implement concurrent stdout/stderr draining with Popen**

Use text-mode `Popen` with pipes. Drain both streams without deadlock, preserve line order within each stream, emit stdout and stderr lines through `line_sink` using the uppercase agent prefix, enforce the timeout, and terminate then kill if needed. Retain bounded output/tails and existing auth/quota/error classification.

Do not change `detect_status` unless required by tests; CLI `--help` detection may remain non-streaming because it does not consume model quota.

- [ ] **Step 4: Verify Task 1**

Run: `..\.venv\Scripts\python.exe -m pytest tests\test_council_cycle.py -q`

Expected: all existing Council behavior and new streaming tests pass.

- [ ] **Step 5: Commit checkpoint only if authorized**

```powershell
git add bot/ai_council/agents.py bot/tests/test_council_cycle.py
git commit -m "feat: stream AI Council CLI output"
```

---

### Task 2: Persist Agent Budgets And Exhaust Codex

**Files:**
- Create: `bot/ai_council/live.py`
- Create: `bot/tests/test_council_live.py`
- Modify: `bot/aegis/research_factory/core.py:82-260, 1276-1300`

**Interfaces:**
- Produces: `AgentBudgetLedger(path: Path)` with `remaining(agent)`, `consume(agent)`, and atomic JSON persistence.
- Produces: `ask_research_agent(agent, prompt, *, ledger, line_sink, cwd) -> dict`.
- Initial Codex state is persisted as `used=1`, `limit=1`, `remaining=0`.

- [ ] **Step 1: Write exhausted-budget tests**

Create a temporary ledger initialized with Codex `used=1`, `limit=1`. Patch both `probe_agent` and `ask_agent` to raise if called. Assert `ask_research_agent('codex', ...)` returns `BUDGET_EXHAUSTED`, invokes neither function, and remains exhausted after reconstructing the ledger.

- [ ] **Step 2: Run budget tests and verify RED**

Run: `..\.venv\Scripts\python.exe -m pytest tests\test_council_live.py -q`

Expected: module or ledger does not exist.

- [ ] **Step 3: Implement atomic budget persistence**

Write JSON to a sibling temporary file and replace the ledger path. Consume budget immediately before a real ask so process failure still counts. An explicit human-supplied ledger update is the only mechanism for increasing a limit. Do not infer refreshed quota from CLI presence.

- [ ] **Step 4: Remove local factory agent clients and simulation**

Delete `CodexClient`, `ClaudeClient`, `_simulate_claude_response`, and local subprocess handling from `research_factory/core.py`. `_ask_claude_for_new_direction` calls `ask_research_agent('claude', ...)`; unavailable, malformed, or failed output is logged and recorded as failure without registering a hypothesis. No factory path calls Codex while exhausted.

- [ ] **Step 5: Add no-fallback factory tests**

Return an agent error and malformed text from the shared adapter. Assert hypothesis registry size does not change and the failure is auditable. Assert the local client classes are no longer imported by public factory construction through behavior: constructing a factory with an unavailable shared adapter succeeds without invoking a CLI.

- [ ] **Step 6: Verify Task 2**

Run: `..\.venv\Scripts\python.exe -m pytest tests\test_council_live.py tests\test_research_factory.py -q`

Expected: budget and no-fallback tests pass.

- [ ] **Step 7: Commit checkpoint only if authorized**

```powershell
git add bot/ai_council/live.py bot/ai_council/agents.py bot/aegis/research_factory/core.py bot/tests/test_council_live.py bot/tests/test_research_factory.py
git commit -m "fix: enforce shared agent budgets in research"
```

---

### Task 3: Retrieve Hashed Supporting And Contradictory Evidence

**Files:**
- Create: `bot/aegis/research_factory/evidence.py`
- Modify: `bot/aegis/research/intelligence.py:13-106` only if the existing evidence contract lacks polarity/location fields
- Create: `bot/tests/test_research_factory_evidence.py`

**Interfaces:**
- Produces: `BookEvidence(source, location, passage_hash, polarity, executable, detail)`.
- Produces: `EvidenceBundle(supporting, contradicting, unavailable)`.
- Produces: `retrieve_hypothesis_evidence(index, query, *, required_data, proposed_polarity) -> EvidenceBundle`.

- [ ] **Step 1: Write support/contradiction provenance tests**

Use a fake `BookIndex.search` returning two hashed records for the same conflict topic with `continuation` and `fade` polarity. Query with proposed polarity `continuation`. Assert the continuation record is supporting, fade is contradicting, and both retain filename, source location, passage hash, executable flag, and detail.

- [ ] **Step 2: Write unavailable and unknown-query tests**

Assert no search rows produces three empty tuples. Assert a record requiring unavailable L2 data is in `unavailable`, not `supporting`. Assert an unhashed or non-executable record cannot support an executable hypothesis.

- [ ] **Step 3: Run evidence tests and verify RED**

Run: `..\.venv\Scripts\python.exe -m pytest tests\test_research_factory_evidence.py -q`

Expected: no factory evidence adapter exists or unknown lookup falls back to another concept.

- [ ] **Step 4: Implement evidence adaptation over existing indexes**

Use full-book search and compiled knowledge records; never call `aegis.intel.books.lookup` for an unknown loss class. Classify opposite non-empty polarity as contradiction. Preserve unavailable data and non-executable records separately. Do not merge authors or convert book consensus into trade authorization.

- [ ] **Step 5: Integrate evidence into hypothesis generation**

`ResearchFactory` stores `book_evidence` from `EvidenceBundle` with explicit support/contradiction categories. If no executable evidence and no real data-derived mechanism exists, record `NO_EVIDENCE`; do not generate generic default buy hypotheses or “reduce losses by 50%” claims.

- [ ] **Step 6: Verify Task 3**

Run: `..\.venv\Scripts\python.exe -m pytest tests\test_research_factory_evidence.py tests\test_research_intelligence.py tests\test_book_knowledge.py -q`

Expected: all evidence, intelligence, and book tests pass.

- [ ] **Step 7: Commit checkpoint only if authorized**

```powershell
git add bot/aegis/research_factory/evidence.py bot/aegis/research_factory/core.py bot/aegis/research/intelligence.py bot/tests/test_research_factory_evidence.py
git commit -m "fix: preserve contradictory research evidence"
```

---

### Task 4: Stabilize The Public CLI And Verify No-Fabrication Smoke

**Files:**
- Modify: `bot/aegis/research_factory/core.py`
- Modify: `bot/aegis/research_factory/__init__.py`
- Modify: `bot/aegis/research_factory/main.py`
- Modify: `bot/tests/test_research_factory.py`
- Delete after review: `_temp_check.py`, `bot/add_calculate_metrics.py`, `bot/add_calculate_metrics2.py`, `bot/add_method.py`, `bot/add_research_cycle.py`, `bot/add_test_method.py`, and untracked `bot/fix_*.py` helper scripts created during this repair

**Interfaces:**
- `python -m aegis.research_factory.main --mode weekend --max-generations 1` remains the supported entry point.
- `aegis.research_factory` exports only symbols that exist.
- One generation terminates with an auditable status and never starts trading.

- [ ] **Step 1: Write construction and one-generation integration tests**

Use temporary source, registry, sealed, ledger, and report paths. Inject deterministic local collaborators and no external CLI. Assert all methods called by `run()` exist, `save_report()` succeeds, no order API is imported or called, and terminal status is one of the approved status vocabulary.

- [ ] **Step 2: Run integration tests and verify RED**

Run: `..\.venv\Scripts\python.exe -m pytest tests\test_research_factory.py -k "generation or public" -q`

Expected: missing `_check_plateau`, `_promote_challenger`, `_log_learning`, nested helpers, duplicate initialization, or invalid exports fail.

- [ ] **Step 3: Reduce core to orchestration and repair public exports**

Remove duplicate initializers, orphaned helper classes, nested functions after `main`, incomplete methods, and local domain implementations replaced by Plans 1-3. Add minimal `_check_plateau` and learning/report behavior based only on persisted experiments. Keep the CLI research-only and dependency-injectable.

- [ ] **Step 4: Remove repair helper scripts without touching runtime/user artifacts**

Delete only the named temporary Python scripts after confirming they are untracked repair helpers. Do not delete AI Council cases, reports, databases, logs, or other runtime artifacts unless the user explicitly requests cleanup.

- [ ] **Step 5: Run focused verification**

Run: `..\.venv\Scripts\python.exe -m pytest tests\test_research_factory*.py tests\test_council_cycle.py tests\test_council_live.py tests\test_research_intelligence.py tests\test_book_knowledge.py -q`

Expected: all focused tests pass.

- [ ] **Step 6: Run complete verification**

Run: `..\.venv\Scripts\python.exe -m pytest -q`

Expected: complete baseline passes; record exact pass/fail/skip counts.

Run: `git diff --check`

Expected: no whitespace errors.

- [ ] **Step 7: Run one foreground no-fabrication smoke only after tests pass**

Run from `bot` with external agents disabled and one generation. Capture the complete output. Accept `NO_DATA`, `NO_EVIDENCE`, `NOT_EXECUTABLE`, `FAILED`, `REJECTED`, or a genuinely evidenced `CHALLENGER`. Reject any output containing simulated response, fallback hypothesis, default broker cost, fabricated metric, order placement, or live YAML mutation.

- [ ] **Step 8: Commit checkpoint only if authorized**

```powershell
git add bot/aegis/research_factory/core.py bot/aegis/research_factory/__init__.py bot/aegis/research_factory/main.py bot/tests/test_research_factory.py docs/superpowers/specs/2026-08-23-research-factory-integrity-design.md docs/superpowers/plans/2026-08-23-research-factory-data-ml.md docs/superpowers/plans/2026-08-23-research-factory-replay-promotion.md docs/superpowers/plans/2026-08-23-research-factory-council-evidence.md
git status --short
git commit -m "fix: make research factory evidence-driven"
```

Stage only intended source, tests, spec, and plans. Exclude runtime artifacts, databases, logs, generated Council cases, and secrets.
