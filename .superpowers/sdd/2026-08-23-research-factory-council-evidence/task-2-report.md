# Task 2 Report: Persist Agent Budgets And Exhaust Codex

## Status

Completed. `AgentBudgetLedger` atomically persists a fail-closed Codex budget
of `used=1`, `limit=1`. `ask_research_agent` returns `BUDGET_EXHAUSTED`
without probing or asking when no budget remains, and consumes a configured
budget before the shared adapter makes an ask.

`ResearchFactory` no longer defines local Claude/Codex process clients. It
creates the durable ledger under its report directory and routes Claude through
the shared adapter. Adapter errors and non-serialized hypotheses are recorded
as `FAILED`; neither creates a hypothesis.

## TDD Evidence

The new ledger test was run before `ai_council.live` existed:

```text
ModuleNotFoundError: No module named 'ai_council.live'
```

After implementation and the legacy client-construction expectation update:

```text
..\\.venv\\Scripts\\python.exe -m pytest tests\\test_council_live.py tests\\test_research_factory.py -q
22 passed in 4.58s
```

## Verification

```text
..\\.venv\\Scripts\\python.exe -m pytest -q
978 passed, 1 warning in 77.28s

git diff --check
exit 0
```

The full-suite warning is the existing `eventkit` deprecation warning about no
current event loop in `test_ibkr_order_hygiene.py`.

## Scope And Safety

- Tests forbid adapter/process use for exhausted Codex and construction.
- No Codex probe or ask was made; no external CLI, MT5, YAML, orders, factory,
  or subagents were started.
- The unrelated `label_horizon` worktree hunk remains unstaged.
- The pre-existing fallback cleanup overlaps the Task 2 replacement of
  `_ask_claude_for_new_direction`; the staged implementation removes the local
  fallback as required by this task while preserving its no-fabrication result.
