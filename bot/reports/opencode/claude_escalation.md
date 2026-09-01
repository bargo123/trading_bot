# OpenCode escalation path (for Claude / human)

This file exists so that a future agent (e.g. Claude) can determine whether a
human is needed. The recurring 20-minute OpenCode research watcher is fully
autonomous and free (local deterministic Python + OpenCode); it never needs a
Claude/Anthropic credential.

## When to escalate to a human

Only escalate after TWO consecutive failed cycles, or immediately for these:

1. **MT5 demo terminal down** AND `supervisor_keepalive.ps1` failed to restart
   it twice (heartbeat `mt5.connected == false` across 2 cycles).
2. **Execution runner down** (heartbeat `runner.alive == false`) AND the
   keepalive task is not running.
3. **Watcher not producing heartbeats** - `bot/reports/opencode/heartbeat.json`
   is older than 30 minutes. That means the 20-min watcher loop is dead.
4. **Data corruption** in `bot/intel/outcome_log.jsonl`, `experiments.sqlite`,
   or `sealed_holdouts.jsonl` that blocks outcome learning / registry writes.
5. **AC-power loss recovery failure** after a wall-power outage: machine stays
   off or MT5/terminal does not come back (see `BIOS_POWER_RECOVERY.md`).

## How to escalate

Append a short entry to `bot/reports/opencode/escalations.jsonl`:

```json
{"ts": "2026-08-19T00:00:00+00:00", "reason": "...", "evidence": "...", "required": "human"}
```

Do not page a human for normal research results, rejected promotions, or
negative findings. Those are expected outcomes and belong in the registry/status,
not escalation.

## Autonomous limits (never cross)

- Never place live orders. Demo/paper runner only.
- Never write live YAML or set `allow_live: true`.
- Never promote a champion outside the governed path
  (`research_promote_champion.py` / `research_asia_sell_strategy.py`).
- Never create a second execution runner or a second watcher process.
- Never use an Anthropic/Claude credential for the recurring cycle.