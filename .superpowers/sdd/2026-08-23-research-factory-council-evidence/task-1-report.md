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

## Review Fix Round 1

The original Popen implementation could block forever when a descendant kept a
pipe open and retained unbounded output. The adapter now creates an isolated
process tree (`CREATE_NEW_PROCESS_GROUP` on Windows and `start_new_session` on
POSIX), sends tree termination then force-kill on timeout, closes parent pipes,
and joins drains only for bounded intervals. A drain that still cannot finish
returns the explicit `OUTPUT_DRAIN_TIMEOUT` error; timeout always returns
`TIMEOUT` deterministically.

Stdout and stderr now retain bounded tails. Every complete line still reaches
`line_sink`; sink exceptions are ignored so draining continues. Oversized
stdout returns `ERROR` with `OUTPUT_TOO_LARGE`, empty `output`, and the ASCII
`[OUTPUT TRUNCATED]` marker in `stdout_tail`, preventing a partial response
from being treated as parseable evidence.

### Review TDD Evidence

Before the fix, the new controlled FakePopen tests produced:

```text
3 failed, 4 passed, 15 deselected, 1 warning
```

The failures demonstrated an available oversized response, missing tree
cleanup helper, and a timeout blocked by inherited pipes.

### Review Verification

```text
..\\.venv\\Scripts\\python.exe -m pytest tests\\test_council_cycle.py -q
24 passed in 2.93s

..\\.venv\\Scripts\\python.exe -m pytest -q
971 passed, 1 warning in 84.44s
```

## Review Fix Round 2

Pipes now run in binary mode. Drain threads read fixed 4096-byte chunks, own
their stream close, incrementally decode and frame prefixed sink output, and
cap unterminated sink records with `[LINE TRUNCATED]`. Control threads never
close a live pipe and return after bounded joins. New controlled tests cover a
blocking close/reader and a generated huge unterminated byte stream.

```text
tests\test_council_cycle.py: 26 passed in 3.07s
full suite: 973 passed, 1 warning in 94.29s
```
