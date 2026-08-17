# Autonomous MT5 optimizer (Aegis)

Educational/systems work only. No profit guarantees. The optimizer **does not rewrite** the live paper stack. It reads journals, heartbeat, and (optionally) MT5 history, then proposes **YAML** patches under `bot/optimizer/`.

## Components

| Piece | Path |
| --- | --- |
| Live paper runner | `bot/scripts/run_broker_paper.py` (lock: `bot/reports/run_broker_paper.lock`) |
| Optimizer cycle | `bot/scripts/run_optimizer_cycle.py` (lock: `bot/optimizer/optimizer.lock`) |
| Snapshot | `bot/scripts/optimizer_snapshot.py` |
| Status | `bot/scripts/optimizer_status.py` |
| Promote-when-flat | `bot/scripts/optimizer_promote.py` |
| Supervisor | `bot/scripts/supervisor_optimizer.ps1` |
| Logon task | `bot/scripts/register_optimizer_task.ps1` |
| Memory | `bot/optimizer/optimizer_state.md`, `current_best.json`, `experiments.jsonl` |
| Accepted / candidate YAML | `bot/optimizer/accepted.yaml`, `bot/optimizer/candidate.yaml` |
| Metrics | `bot/optimizer/metrics/` |
| Checkpoints | `bot/optimizer/checkpoints/<exp_id>/` |

Two locks on purpose: research can run while the demo trades. The optimizer never calls `mt5.shutdown()`.

## Start / stop / status

The venv and scripts live in `C:\Users\Raqam\trading_bot\bot`, not your user home. From **any** prompt:

```bat
cd /d C:\Users\Raqam\trading_bot
optimizer_status.bat
run_optimizer_cycle.bat --no-mt5
```

Or by hand:

```bat
cd /d C:\Users\Raqam\trading_bot\bot
.venv\Scripts\python.exe scripts\optimizer_status.py
.venv\Scripts\python.exe scripts\run_optimizer_cycle.py --dry-run --no-mt5 --skip-pytest
.venv\Scripts\python.exe scripts\run_optimizer_cycle.py --no-mt5
```

Windows supervisor (20 minute default interval):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File bot\scripts\supervisor_optimizer.ps1
```

Register a **current-user logon** scheduled task (not an admin service):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File bot\scripts\register_optimizer_task.ps1
```

If `schtasks` is denied, the script prints the exact command to run once.

Stop the supervisor with Ctrl+C (or end the scheduled task). That does **not** stop the live paper runner.

## Code edits stay off

`bot/optimizer/config.yaml` has `allow_code_edit: false`. Cycles only patch declared YAML keys (TP, spread gate, symbol list, `max_positions`, `scratch_losers`). Python strategy files are not modified.

## Promote-when-flat

Accepted candidates are copied to `bot/optimizer/accepted.yaml`. They are copied onto the live `--config` path **only** when `bot/reports/bot_heartbeat.json` shows `open: 0`. If the bot is in a trade, `pending_promote.json` is written and the live YAML is left alone. Each supervisor cycle retries that copy (and `optimizer_promote.py` can do the same). A restart of `run_broker_paper.py` happens only after a successful copy. It does not flatten positions.

## Recover from reboot / closed console

The 3% daily-loss halt is stored in `bot/reports/risk_state.json`. Restarting the paper runner **does not** start a fresh loss budget for that UTC day.

A **laptop shutdown** kills Python. After the next Windows logon, keep-alive should start MT5, the paper runner, and the optimizer. Daily-loss halt stays on disk; leftover positions are adopted, not flattened.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File bot\scripts\install_startup.ps1
```

That writes a Startup folder shortcut and a current-user Run key (no admin). Optional Task Scheduler (may be denied):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File bot\scripts\register_keepalive_tasks.ps1
```

After a reboot:

1. Start MetaTrader 5, log into the demo, keep **Algo Trading** green.
2. Wait up to 20 minutes for the keep-alive task, or run `bot\scripts\supervisor_keepalive.ps1`.
3. History is on disk under `bot/optimizer/` (metrics JSONL, checkpoints, experiment logs). Nothing in that runtime tree is required from git besides `config.yaml` and `AGENT_PROMPT.md`.

## Cursor CLI (optional)

## Cursor fine-tuning

This chat can keep reviewing the optimizer on a timer (20 minutes). That is **this Cursor agent**, not the live order path.

The standalone **Cursor agent CLI** (`agent`, not `cursor.exe`) is optional. If you install and auth it, set `with_cursor: true` in `bot/optimizer/config.yaml`. Python still validates the YAML patch and backtests it. Cursor never places orders.

```powershell
irm 'https://cursor.com/install' | iex
agent login
```

The cycle's pytest subset skips `test_ib_paper_config_defaults_to_observation_only` because the checked-in IB yaml no longer matches that observation-only assertion. Optimizer and MT5 engine tests still run.

## Accept gate

Out-of-sample `expectancy_r` must beat the baseline **and** the stored `current_best` expectancy, max drawdown may not worsen by more than `dd_tolerance_pct`, `total_trades >= min_trades`, and a win-rate increase with an expectancy drop is rejected (Tharp). There is no 100% WR target.

## Laptop heat (does not change trading)

`bot\scripts\cool_machine.ps1` caps Intel turbo (processor max 99%), turns the screen off after 10 minutes, and keeps sleep/hibernate **Never**. The optimizer cycle runs BelowNormal with two BLAS threads. Live paper, MT5, firehose YAML, and poll interval are unchanged.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File bot\scripts\cool_machine.ps1
```
