# Agent Status

Updated: 2026-08-26T16:01Z

## Current broker symptom
- Broker heartbeat PID: 17048
- Status: running, MT5 DEMO evidence remains fail-closed for live money
- Equity: 74.65 USD
- Open positions: 0
- Current session at 16:01:01Z: SCANS=7176, RAW_SIGNALS=0, MICRO_CANDIDATES=0, ML_ELIGIBLE=0, FIRES=0, SUBMITTED=0, FILLS=0
- Rejects: artifact_shadow_only=5779, spread_above_measured_session_limit=1397
- Current short-horizon artifact remains SHADOW_ONLY_NO_POSITIVE_OOS with authorized_symbols=[]; no authorization gate was weakened.

## Root-cause evidence
1. The ML/OOS artifact is not the cause of RAW_SIGNALS=0. In current source, raw signal and micro-candidate telemetry are created before the short-horizon authorization veto.
2. Repository bridge evidence at 2026-08-26 ~09:53:46Z recorded working runtime PID 7788 with 30,963 scans, 13,949 raw signals and 11,893 micro-candidates. The signal path therefore worked earlier today.
3. A later broker activation reset the session and the current PID 17048 now produces zero raw signals/candidates.
4. Current source writes `video_style_mode` into every broker heartbeat. PID 17048's fresh heartbeat does not contain that field, proving the live process has stale `run_broker_paper.py` code loaded relative to the current workspace.
5. Current `supervisor_keepalive.ps1` starts `run_broker_paper.py` with `--video-style`, and `test_supervisor_keepalive.py` statically requires that flag.
6. Owner identity is inconsistent: the watcher heartbeat at 2026-08-26T15:42:43Z reported `runner.pid=3044`, while the broker heartbeat at the same period reported PID 17048. A later duplicate watcher invocation hit the singleton lock and overwrote the watcher heartbeat with CYCLE_ALREADY_RUNNING.
7. `run_broker_paper.lock` is actively locked (read returned EBUSY), so a broker owner holds the singleton execution lock.

## Safe-restart status
BLOCKED_SAFE_RESTART.

Do not kill PID 17048 or PID 3044 until native Windows process inspection proves which exact process owns the broker lock and confirms exactly one intended `run_broker_paper.py` command line from this repo/config with `--video-style`.

CodexPro command execution is currently unavailable: its self-test fails only the bash policy with `spawn bash ENOENT`; server config has bashMode=full but the Windows implementation tries to spawn `bash`. This is infrastructure/tooling failure, not a bot test failure.

## Verification evidence available
- Previous repository-native full-suite evidence exists in `.ai-bridge/verification-result.json`: 1306 passed, 1 warning, return code 0. This is historical evidence only, not a fresh test run for this status update.
- No fresh pytest command could be run in this session because CodexPro's local command bridge cannot spawn a shell. Therefore no new test-passing claim is made.

## Next safe action
Once native command execution is available, perform read-only process enumeration first. If and only if heartbeat PID, process command line, DEMO/flat MT5 state, and singleton owner identity all agree, stop only that exact broker PID and invoke `bot/scripts/supervisor_keepalive.ps1` once. Then require a new PID heartbeat containing `video_style_mode: true` and verify RAW_SIGNALS/MICRO_CANDIDATES resume before evaluating the remaining negative OOS authorization blocker.
