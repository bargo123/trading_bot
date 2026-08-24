# Task 1 Report: Stream Shared Agent Output Through Popen

## Status

Completed. `ai_council.agents.ask_agent` now accepts an optional `line_sink`
and uses `subprocess.Popen` for model asks. Stdout and stderr are drained
concurrently; each complete line is delivered with the uppercase agent prefix.
Returned `output` remains the unprefixed stdout text used for JSON parsing.
Timeouts terminate, then kill if necessary, and return `TIMEOUT` without a
fabricated response.

## TDD Evidence

The new FakePopen streaming tests were run before implementation:

```text
2 failed, 16 deselected
TypeError: ask_agent() got an unexpected keyword argument 'line_sink'
```

They passed after the Popen implementation:

```text
3 passed, 15 deselected
```

## Verification

```text
..\\.venv\\Scripts\\python.exe -m pytest tests\\test_council_cycle.py -q
18 passed in 2.73s

..\\.venv\\Scripts\\python.exe -m pytest -q
965 passed, 1 warning in 91.60s
```

The full-suite warning is an existing `eventkit` deprecation warning about no
current event loop in `test_ibkr_order_hygiene.py`.

## Scope And Safety

- Tests replace `subprocess.Popen`; no external CLI, MT5, YAML, order, or
  factory operation is invoked.
- The exhausted durable Codex budget belongs to Plan 3 Task 2 and was not
  probed or consumed by this Task 1 implementation.
- Existing unstaged `research_factory/core.py` Claude/fallback cleanup remains
  unmodified and unstaged.
