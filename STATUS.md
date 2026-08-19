# OpenCode STATUS — AEGIS Intelligent Firehose research lab

Branch: `opencode/aegis-infra` | Baseline: 527 tests passing (trusted handoff
`9a3cfcc`); current suite: **567 passing**.

## Completed

- **Reconcile cursor persistence** — `bot/aegis/intel/lifecycle.py`
  (`load_cursor`/`save_cursor`), wired into `bot/scripts/run_broker_paper.py`;
  survives restart, corrupt/missing → fresh. Tests green.
- **MAE tracking** — `update_mae`/`load_excursion`/`save_excursion` in
  `bot/aegis/exits.py`, wired into the paper runner (all close paths pop the
  excursion record).
- **Outcome learning** — `bot/aegis/research/outcome_learning.py` +
  `research_outcome_learning.py`. Latest: 3117 rows, 2347 exits, expectancy
  −0.0097, PF 0.777. SL exits destructive (−0.503 avg).
- **Champion promotion (governed)** — `bot/aegis/research/promote.py` +
  `research_promote_champion.py`; validation → freeze → one-shot sealed
  holdout → bootstrap/tail/stress → strategy-model readiness.
- **Book memory** — `bot/aegis/research/book_memory.py`; semantic quality
  gates; 108 records → `bot/research/book_memory/knowledge_records.jsonl`
  (versioned) + SQLite (ignored).
- **Asia-session sell edges** — deep-dive on mt5_m1 index (6-day sample,
  Aug 14–19 2026): range/asia/sell exp 1.39 / PF 1.59 / bootstrap p05 0.92,
  survives all exclusions + 0.8-pip costs. Trend variant weaker (p05 0.33,
  Tuesday −0.89).
- **Governed promotion of `asia_sell_range` → REJECTED.** Validation-window
  bootstrap p05 ≤ 0; no champion artifact written (correct governance).
- **ML pipeline** — `bot/aegis/research/{exit_research,ml_pipeline}.py` +
  `research_ml_pipeline.py`. Exit research: every fixed-TP horizon (1/2/5/10
  pips vs 30-pip SL) is **net-negative after costs** (1-pip: WR 88.7% but
  PF 0.71) — the high-win-rate shape is a cost mirage. Strategy selection
  (60/40): 10 shortlisted, 5 validate. Ridge model: no OOS improvement.
- **20-min fast watcher** — `bot/scripts/research_fast_watcher.py`
  (`--once` for single cycle). Writes `aegis_cycle_status.md`.
- **opencode config** — `.opencode/command/aegis-cycle.md`, `opencode.json`
  (permissions), `AGENTS.md` safety rules.

## Status / next

- `/aegis-cycle` command + `opencode.json` + `AGENTS.md` are new — restart
  opencode to load them.
- No champion in `intel/intelligent_champion.json` (intentionally absent).

## Invariants

- `mt5_touched` / `placed_orders` / `promoted_live_yaml` are `false` in every
  experiment record unless a governed promotion legitimately accepted.
- Live YAML is never edited; MT5 access is read-only.