#!/usr/bin/env python3
"""20-minute fast watcher for the AEGIS research cycle.

Polls the live artifacts (heartbeat, risk state, journal, deals, outcome log)
and keeps the research loop moving with bounded scope:
  - recompute outcome learning on any new realized outcomes
  - rebuild book memory when source notes changed
  - re-run strategy selection + ML model on the measured index (no MT5)
  - fetch M1 (read-only) and re-run exit-horizon research on a slow cadence
  - record experiments in the registry
  - write cycle status markdown

It never places orders, never touches live YAML, and never promotes a champion;
promotion is reserved for the full /aegis-cycle run.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

BOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BOT))

CYCLE_INTERVAL_S = 20 * 60
EXIT_RESEARCH_EVERY_N = 6  # ~every 2h

REPORTS = BOT / "reports" / "research"
CYCLE_STATUS = REPORTS / "aegis_cycle_status.md"
BOOK_MEMORY_REPORT = REPORTS / "book_memory.json"
OUTCOME_REPORT = REPORTS / "outcome_learning.json"
ML_REPORT = REPORTS / "ml_pipeline.json"
NOTES_DIR = BOT / "research" / "source_notes"
STATE_DIR = BOT / "research" / "fast_watcher_state"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_script(name: str, *extra: str, timeout_s: int = 900) -> dict[str, Any]:
    cmd = [sys.executable, str(BOT / "scripts" / name), *extra]
    started = time.time()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
        ok = proc.returncode == 0
        tail = (proc.stdout or "").strip().splitlines()[-8:]
        return {
            "ok": ok,
            "returncode": proc.returncode,
            "elapsed_s": round(time.time() - started, 1),
            "stdout_tail": tail,
            "stderr_tail": (proc.stderr or "").strip().splitlines()[-4:],
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "returncode": -1, "elapsed_s": round(time.time() - started, 1), "timeout": True}


def _notes_changed() -> bool:
    state = STATE_DIR / "notes_mtime.json"
    current = {}
    for note in NOTES_DIR.glob("*.json"):
        current[note.name] = round(note.stat().st_mtime, 3)
    if not state.exists():
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        state.write_text(json.dumps(current), encoding="utf-8")
        return True
    previous = json.loads(state.read_text(encoding="utf-8"))
    state.write_text(json.dumps(current), encoding="utf-8")
    return current != previous


def _tick_count() -> int:
    state = STATE_DIR / "tick.json"
    if not state.exists():
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        state.write_text(json.dumps({"ticks": 0}), encoding="utf-8")
        return 0
    ticks = int(json.loads(state.read_text(encoding="utf-8")).get("ticks", 0))
    state.write_text(json.dumps({"ticks": ticks + 1}), encoding="utf-8")
    return ticks


def _summarize_ml(report: Path) -> dict[str, Any]:
    if not report.exists():
        return {}
    payload = json.loads(report.read_text(encoding="utf-8"))
    return {
        "exit_recommended": payload.get("exit_research", {}).get("recommended"),
        "exit_summary": payload.get("exit_research", {}).get("summary"),
        "strategies_shortlisted": payload.get("strategy_selection", {}).get("n_shortlisted"),
        "strategies_survive": payload.get("strategy_selection", {}).get("n_survive"),
        "ml_improvement": payload.get("ml", {}).get("improvement_expectancy"),
    }


def write_status(
    *,
    tick: int,
    outcome: dict[str, Any],
    book: dict[str, Any],
    ml: dict[str, Any],
    exit_run: bool,
    notes_changed: bool,
) -> Path:
    lines = [
        "# AEGIS cycle status (fast watcher)",
        "",
        f"Tick: {tick}  |  UTC: {_now()}",
        "",
        "> Research-only watcher. No orders placed, no live YAML promoted. Champion",
        "> promotion is reserved for the full `/aegis-cycle` run.",
        "",
        "## Outcome learning",
        "",
        "- status: " + ("ok" if outcome.get("ok") else "failed"),
        "- rows/exits: "
        + _report_count(OUTCOME_REPORT, "n_exits")
        + f" (report: {OUTCOME_REPORT.name})",
        "",
        "## Book memory",
        "",
        "- status: " + ("ok" if book.get("ok") else "failed"),
        "- notes changed: " + str(notes_changed),
        "- records: " + _report_count(BOOK_MEMORY_REPORT, "records"),
        "",
        "## Strategy selection + ML",
        "",
        "- status: " + ("ok" if ml.get("ok") else "failed"),
        "- exit research ran: " + str(exit_run),
        "- strategies shortlisted: " + _report_val(ML_REPORT, "strategy_selection", "n_shortlisted"),
        "- strategies survived validation: " + _report_val(ML_REPORT, "strategy_selection", "n_survive"),
        "- ML improvement (expectancy): " + _report_val(ML_REPORT, "ml", "improvement_expectancy"),
        "",
        "## Runtime",
        "",
        f"- outcome script: {outcome.get('elapsed_s')}s",
        f"- book memory script: {book.get('elapsed_s')}s",
        f"- ML script: {ml.get('elapsed_s')}s",
        "",
    ]
    CYCLE_STATUS.parent.mkdir(parents=True, exist_ok=True)
    CYCLE_STATUS.write_text("\n".join(lines), encoding="utf-8")
    return CYCLE_STATUS


def _report_count(report: Path, key: str) -> str:
    try:
        payload = json.loads(report.read_text(encoding="utf-8"))
        value = payload.get(key)
        if isinstance(value, dict):
            value = value.get("n")
        return str(value) if value is not None else "?"
    except (OSError, json.JSONDecodeError):
        return "?"


def _report_val(report: Path, group: str, key: str) -> str:
    try:
        payload = json.loads(report.read_text(encoding="utf-8"))
        value = payload.get(group, {}).get(key)
        if value is None:
            return "?"
        if isinstance(value, (int, float)):
            return str(round(float(value), 4))
        return str(value)
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return "?"


def run_cycle(tick: int, *, fetch_exit: bool) -> dict[str, Any]:
    outcome = _run_script("research_outcome_learning.py")
    notes_changed = _notes_changed()
    book: dict[str, Any] = {"ok": True, "skipped": not notes_changed, "elapsed_s": 0}
    if notes_changed:
        book = _run_script("research_book_memory.py")
    ml_args = ("--fetch",) if fetch_exit else ()
    ml = _run_script("research_ml_pipeline.py", *ml_args, timeout_s=1500)
    status = write_status(
        tick=tick,
        outcome=outcome,
        book=book,
        ml=ml,
        exit_run=fetch_exit,
        notes_changed=notes_changed,
    )
    return {
        "tick": tick,
        "utc": _now(),
        "status": str(status),
        "outcome": outcome,
        "book_memory": book,
        "ml": ml,
        "mt5_touched": fetch_exit,
        "placed_orders": False,
        "promoted_live_yaml": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="AEGIS 20-min research fast watcher")
    parser.add_argument("--once", action="store_true", help="run a single cycle and exit")
    parser.add_argument("--interval", type=int, default=CYCLE_INTERVAL_S, help="seconds between cycles")
    parser.add_argument("--fetch-exit", action="store_true", help="force M1 fetch for exit research every cycle")
    args = parser.parse_args()

    while True:
        tick = _tick_count()
        fetch_exit = bool(args.fetch_exit) or (tick % EXIT_RESEARCH_EVERY_N == 0)
        try:
            result = run_cycle(tick, fetch_exit=fetch_exit)
        except Exception as exc:  # keep the watcher alive across transient failures
            result = {"tick": tick, "utc": _now(), "error": str(exc)}
        print(json.dumps(result, indent=2, default=str), flush=True)
        if args.once:
            return 0
        time.sleep(int(args.interval))


if __name__ == "__main__":
    raise SystemExit(main())