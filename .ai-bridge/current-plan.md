# AEGIS bounded verification, broker-only governed activation, one-survivor OOS

Updated: 2026-08-26T09:55Z
Workspace: C:\Users\Zaid barghouthi\Desktop\trading_bot
Target agent: Codex

## Non-negotiable safety
- MT5 DEMO ONLY. Keep `bot/config_mt5_demo_firehose_hw.yaml` `mode: mt5_demo`, `allow_live: false`, `paper_trading_enabled: true`.
- Do not increase risk or sizing. Current order quantity is 0.01 and existing risk gates remain unchanged.
- Never bypass `artifact_shadow_only`, chronological OOS, EV, spread, evidence, tail-loss, calibration, LCB95, or execution-owner gates just to create activity.
- Never force/randomize trades. Never start a duplicate `run_broker_paper.py` owner.
- Keep healthy Watcher/Factory/Council processes running; activation in this batch is broker-owner-only.

## Fresh verified evidence
- Full native Windows repo suite is GREEN: **1306 passed, 1 warning in 120.91s**, return code 0. This is fresh evidence from `.ai-bridge/verification-result.json`.
- The same run's read-only MT5 probe: `trade_mode=0`, `server=MetaQuotes-Demo`, `positions=0`.
- Current heartbeat: PID 7788, `status=running`, `open=0`, `risk_halted=false`, `circuit_ok=true`, fixed quantity 0.01.
- Firehose at ~09:53:46Z: 30,963 scans, 11,893 micro-candidates, 13,949 raw signals, 0 ML-eligible, 0 fires, 0 submissions, 0 fills. Dominant blocker remains `artifact_shadow_only` (26,276 rejects); spread rejects 4,687.
- Short-horizon runtime remains `SHADOW_ONLY_NO_POSITIVE_OOS`, `authorized_symbols=[]`, captured OOS expectancy `-4.406381507775209e-06`, PF `0.6801316153093229`, TEST N 25,598, SEALED N 25,204.
- Watcher tick 413 at 09:44:24Z is healthy and now reports 43 shortlisted -> 42 validated -> **1 unique survivor**. `ml_pipeline.json` explicitly reports `n_survive=1`, `n_survive_rows=2`.
- The two validation rows are hierarchy duplicates of ONE opportunity: **GBPUSD BUY / Asia / trend / structure=none**, measured p75 executable cost **1.2 pips**. Do not count Level A and Level B separately.
- Council latest remains conservative: `defer_validation`. Factory handoff says `execution_authority=NONE` and asks for longer independent replay, calibration, and tail-loss work.
- Exact repair semantics are present in source and covered by the green suite: `min_scratch_loss_frac` rapid-loss scratch; calibrated/non-abstaining support revocation only replaces a non-profitable default HOLD; geometry-scaled remaining EV is tagged `PROXY`; open FAST tickets refresh `ShortHorizonPredictor`; survivor counting distinguishes unique opportunities from hierarchy evidence rows.

## Safety cleanup performed by reviewer
- Removed the temporary watcher auto-execution block that ran `bot/scripts/_temp_finish_governed.py` on watcher startup. That helper directly killed/re-Popened both watcher and broker and violated the broker-only governed activation requirement.
- Do NOT recreate direct subprocess/taskkill/Popen activation plumbing. Treat `_temp_finish_governed.py` and `_temp_finish_governed.ps1` as temporary junk to remove when safe; do not preserve them as governed evidence.

## Priority 1 — broker-only governed activation, only if owner identity is certain
1. Enumerate `run_broker_paper.py` processes using native Windows process inspection. Require exactly ONE incumbent owner and verify its command line includes this repo/config and `--video-style`. Confirm heartbeat PID matches that exact owner and `open=0` immediately before restart.
2. Reconfirm MT5 read-only state is MetaQuotes DEMO (`trade_mode=0`) and positions=0, and `allow_live=false` in config.
3. If and only if those checks are certain, stop ONLY that exact incumbent broker PID. Do not stop/restart the research watcher.
4. Invoke the repository's governed `bot/scripts/supervisor_keepalive.ps1` once so it starts the broker owner with `--video-style`. Do not direct-Popen the broker yourself.
5. Verify a fresh heartbeat from a NEW PID, `status=running`, `open=0`, and exactly one `run_broker_paper.py` owner after activation. If any identity check is uncertain, STOP with `BLOCKED_SAFE_RESTART`; do not improvise.

## Priority 2 — strict evaluation of the ONE GBPUSD survivor
6. Evaluate exactly **GBPUSD BUY / Asia / trend / structure=none** through chronological executable TEST + SEALED OOS using measured cost 1.2 pips and current real execution geometry.
7. Produce one explicit verdict containing TEST N/expectancy/PF/tails and SEALED N/expectancy/PF/tails, cost source, calibration/evidence/LCB95 status, and whether every execution-authority gate clears.
8. If it fails, permit at most ONE materially different mechanism targeted at the measured failure cause, then STOP/IDLE. Do not create more generic strategy families or hierarchy duplicates.

## Codex bounded-work rule
- Session metadata shows repeated short-lived Codex fan-out. STOP spawning secondary sessions. Use one main Codex session only.
- Hard stop after the unique survivor verdict, 3 materially different full validations, or 75 minutes, whichever comes first.

## Repo hygiene
- Do not broad-commit the dirty tree.
- Preserve governed research/Council/model/lifecycle evidence.
- Remove only clearly temporary untracked mutation helpers (`fix_*.py`, `add_*.py`, `_temp_check.py`) after confirming no imports/references, plus the two `_temp_finish_governed.*` helpers after they are no longer needed.
- Record commands/results and final activation/OOS verdict in `Desktop/trading_bot/.ai-bridge/agent-status.md`.
