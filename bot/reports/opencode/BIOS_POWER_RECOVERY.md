# BIOS AC-power-loss recovery (Windows)

Purpose: survive a wall-power outage on a 24/7 unattended AEGIS research + demo
trading machine so the system comes back up without a manual button press.

## Current Windows-level protection (already configured)

These are set in the active High-performance power plan and require no admin:

- Sleep after (AC/DC): `never` (0 s)
- Hibernate after (AC/DC): `never` (0 s)
- Allow wake timers (AC/DC): `enabled`

So the OS will not sleep or hibernate on AC, and the scheduled research watcher
can wake the machine (WakeToRun) when it is in a low-power state.

## BIOS-level protection (manual, hardware-dependent)

Windows cannot set BIOS options. If the PC loses wall power entirely and is not
configured to auto-restore, it stays off until someone presses the power button.

Recommended setting, if your motherboard supports it (often under
`Power Management` / `AC Power` / `Restore on AC Power Loss`):

- `Restore on AC Power Loss` = **Power On** (always return to on state after AC returns)

If the option does not exist, the machine requires manual power-on after an
outage. Check your motherboard/vendor documentation:

- Dell: `BIOS Setup -> Power Management -> AC Recovery` (Power On)
- HP: `Advanced -> Power Management Options -> After Power Loss`
- Lenovo: `Power -> After Power Loss`
- ASUS: `APM -> Restore AC Power Loss` (Power On)
- MSI: `Settings -> Advanced -> Power Management Setup -> Restore after AC Power Loss`

## After any reboot (watcher self-heals)

On boot/logon the `AegisResearchWatcher` scheduled task starts the 20-min
research watcher. The watcher is restart-safe:

- singleton lock: if an instance is already running, the new one records
  `CYCLE_ALREADY_RUNNING` and exits (no duplicate watchers)
- evidence fingerprint: heavy steps (outcome learning, book memory, ML) only
  re-run when live evidence actually changed; a reboot does not re-run them
- heartbeat: `bot/reports/opencode/heartbeat.json` is rewritten each cycle

The execution stack (MT5 demo paper runner) is supervised by the existing
`supervisor_keepalive.ps1` task, which starts MT5 and the paper runner after a
logon/shutdown and reconciles positions/cursor on start. No immediate trading is
forced on recovery; the runner reconciles MT5 positions + cursor first.

## If MT5 does not reconnect after an outage

1. Confirm the terminal is running (`terminal64.exe`).
2. The keepalive task restarts it on logon.
3. Manually: `Start-Process "C:\Program Files\MetaTrader 5\terminal64.exe"`.
4. Check `bot/reports/opencode/heartbeat.json` -> `mt5.connected` and
   `bot/reports/bot_heartbeat.json`.

## When to escalate

Follow `bot/reports/opencode/claude_escalation.md` if a recovery cycle fails and
the watcher or runner stays down across two consecutive 20-minute cycles.