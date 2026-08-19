#!/usr/bin/env python3
"""20-minute fast watcher for the AEGIS research cycle.

Polls the live artifacts (heartbeat, risk state, journal, deals, outcome log)
and keeps the research loop moving with bounded scope:
  - recompute outcome learning on any new realized outcomes
  - rebuild book memory when source notes changed
  - re-run strategy selection + ML model on the measured index (no MT5)
  - fetch M1 (read-only) and re-run exit-horizon research on a slow cadence
  - record experiments in the registry
  - write cycle status markdown + opencode heartbeat
  - fast-exit with NO_NEW_EVIDENCE when nothing meaningful changed

It never places orders, never touches live YAML, and never promotes a champion;
promotion is reserved for the full /aegis-cycle run.

Windows 24/7 hardening:
  - singleton lock (record CYCLE_ALREADY_RUNNING and exit if already running)
  - restart-safe evidence fingerprint so a reboot does not double-run heavy steps
  - heartbeat at reports/opencode/heartbeat.json with MT5 / runner / champion state
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

BOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BOT))

from aegis.paper_control import ProcessLock  # noqa: E402

CYCLE_INTERVAL_S = 20 * 60
EXIT_RESEARCH_EVERY_N = 6  # ~every 2h

REPORTS = BOT / "reports" / "research"
CYCLE_STATUS = REPORTS / "aegis_cycle_status.md"
BOOK_MEMORY_REPORT = REPORTS / "book_memory.json"
OUTCOME_REPORT = REPORTS / "outcome_learning.json"
ML_REPORT = REPORTS / "ml_pipeline.json"
NOTES_DIR = BOT / "research" / "source_notes"
STATE_DIR = BOT / "research" / "fast_watcher_state"
OPENCODE_DIR = BOT / "reports" / "opencode"
HEARTBEAT = OPENCODE_DIR / "heartbeat.json"
WATCHER_LOCK = STATE_DIR / "watcher.lock"
EVIDENCE_STATE = STATE_DIR / "evidence.json"
OUTCOME_LOG = BOT / "intel" / "outcome_log.jsonl"
ANALOGUE_INDEX = BOT / "intel" / "analogue_index.json"
RUNNER_LOCK = BOT / "reports" / "run_broker_paper.lock"
CHAMPION_ARTIFACT = BOT / "intel" / "intelligent_champion.json"
FIREHOSE_JOURNAL = BOT / "reports" / "mt5_demo_firehose_hw_journal.jsonl"
MT5_PATH = r"C:\Program Files\MetaTrader 5\terminal64.exe"


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


def _evidence_fingerprint() -> str:
    """Deterministic fingerprint of the live evidence sources the cycle consumes."""
    parts = []
    for path in (OUTCOME_LOG, ANALOGUE_INDEX, FIREHOSE_JOURNAL):
        try:
            stat = path.stat()
            parts.append(f"{path.name}:{stat.st_size}:{int(stat.st_mtime)}")
        except OSError:
            parts.append(f"{path.name}:missing")
    for note in sorted(NOTES_DIR.glob("*.json")):
        try:
            parts.append(f"{note.name}:{int(note.stat().st_mtime)}")
        except OSError:
            parts.append(f"{note.name}:missing")
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _evidence_changed() -> tuple[bool, int]:
    """Return (changed, new_outcome_lines_since_last_cycle)."""
    fingerprint = _evidence_fingerprint()
    previous: dict[str, Any] = {}
    if EVIDENCE_STATE.exists():
        try:
            previous = json.loads(EVIDENCE_STATE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            previous = {}
    changed = fingerprint != previous.get("fingerprint")
    last_lines = int(previous.get("outcome_lines", 0) or 0)
    try:
        current_lines = sum(1 for _ in OUTCOME_LOG.open(encoding="utf-8"))
    except OSError:
        current_lines = last_lines
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    EVIDENCE_STATE.write_text(
        json.dumps({"fingerprint": fingerprint, "outcome_lines": current_lines}, sort_keys=True),
        encoding="utf-8",
    )
    return changed, max(0, current_lines - last_lines)


def _mt5_status() -> dict[str, Any]:
    """Lightweight read-only MT5 connection probe for the heartbeat."""
    info: dict[str, Any] = {"process_running": False, "connected": False,
                            "login": None, "server": None, "trade_mode": None}
    try:
        proc = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq terminal64.exe", "/NH"],
            capture_output=True, text=True, timeout=10,
        )
        info["process_running"] = "terminal64.exe" in proc.stdout
    except (OSError, subprocess.SubprocessError):
        pass
    if not info["process_running"]:
        return info
    try:
        import MetaTrader5 as mt5
        if not mt5.initialize(path=MT5_PATH, timeout=10_000):
            info["error"] = str(mt5.last_error())
            return info
        try:
            account = mt5.account_info()
            if account is not None:
                info["connected"] = True
                info["login"] = account.login
                info["server"] = account.server
                info["trade_mode"] = int(account.trade_mode)
        finally:
            mt5.shutdown()
    except Exception as exc:  # heartbeat must never crash the watcher
        info["error"] = str(exc)
    return info


def _runner_pid() -> int | None:
    try:
        return int(RUNNER_LOCK.read_text(encoding="utf-8").strip().splitlines()[0])
    except (OSError, ValueError, IndexError):
        return None


def _runner_process_alive() -> bool:
    pid = _runner_pid()
    if pid is None:
        return False
    try:
        proc = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                              capture_output=True, text=True, timeout=10)
        return str(pid) in proc.stdout
    except (OSError, subprocess.SubprocessError):
        return False


def _champion() -> dict[str, Any] | None:
    if not CHAMPION_ARTIFACT.exists():
        return None
    try:
        return json.loads(CHAMPION_ARTIFACT.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def write_heartbeat(*, tick: int, watcher_alive: bool, last_cycle: str,
                    no_new_evidence: bool, new_outcome_lines: int,
                    last_error: str | None = None, skipped: str | None = None) -> Path:
    mt5 = _mt5_status()
    champion = _champion() or {}
    payload = {
        "timestamp": _now(),
        "watcher_alive": watcher_alive,
        "last_cycle": last_cycle,
        "tick": tick,
        "no_new_evidence": no_new_evidence,
        "new_outcome_lines": new_outcome_lines,
        "next_expected_cycle": (datetime.now(timezone.utc) + timedelta(seconds=CYCLE_INTERVAL_S)).isoformat(),
        "mt5": mt5,
        "runner": {
            "pid": _runner_pid(),
            "alive": _runner_process_alive(),
            "lock": str(RUNNER_LOCK),
        },
        "champion": champion.get("champion") or champion.get("id") or None,
        "skipped": skipped,
        "last_error": last_error,
    }
    OPENCODE_DIR.mkdir(parents=True, exist_ok=True)
    HEARTBEAT.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return HEARTBEAT


def write_status(
    *,
    tick: int,
    outcome: dict[str, Any],
    book: dict[str, Any],
    ml: dict[str, Any],
    exit_run: bool,
    notes_changed: bool,
    no_new_evidence: bool = False,
    new_outcome_lines: int = 0,
    skipped: str | None = None,
) -> Path:
    lines = [
        "# AEGIS cycle status (fast watcher)",
        "",
        f"Tick: {tick}  |  UTC: {_now()}",
        "",
        "> Research-only watcher. No orders placed, no live YAML promoted. Champion",
        "> promotion is reserved for the full `/aegis-cycle` run.",
        "",
    ]
    if no_new_evidence:
        lines += [
            "## Fast exit",
            "",
            "- NO_NEW_EVIDENCE: nothing meaningful changed since the last cycle;",
            f"- new outcome lines since last cycle: {new_outcome_lines}",
            f"- skipped: {skipped}",
            "",
        ]
    else:
        lines += [
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
    evidence_changed, new_outcome_lines = _evidence_changed()
    notes_changed = _notes_changed()

    # Fast exit: no new evidence, no notes change, and not a fetch cadence tick.
    if not evidence_changed and not notes_changed and not fetch_exit:
        status = write_status(
            tick=tick,
            outcome={},
            book={"ok": True, "skipped": True},
            ml={},
            exit_run=False,
            notes_changed=False,
            no_new_evidence=True,
            new_outcome_lines=new_outcome_lines,
            skipped="outcome_learning,book_memory,ml_pipeline",
        )
        heartbeat = write_heartbeat(
            tick=tick, watcher_alive=True, last_cycle=_now(),
            no_new_evidence=True, new_outcome_lines=new_outcome_lines,
            skipped="outcome_learning,book_memory,ml_pipeline",
        )
        return {
            "tick": tick,
            "utc": _now(),
            "no_new_evidence": True,
            "status": str(status),
            "heartbeat": str(heartbeat),
            "placed_orders": False,
            "promoted_live_yaml": False,
            "mt5_touched": False,
        }

    outcome = _run_script("research_outcome_learning.py")
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
    heartbeat = write_heartbeat(
        tick=tick, watcher_alive=True, last_cycle=_now(),
        no_new_evidence=False, new_outcome_lines=new_outcome_lines,
    )
    return {
        "tick": tick,
        "utc": _now(),
        "no_new_evidence": False,
        "status": str(status),
        "heartbeat": str(heartbeat),
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

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    lock = ProcessLock(WATCHER_LOCK)
    if not lock.try_acquire():
        # Another watcher owns the loop. Record CYCLE_ALREADY_RUNNING and exit.
        OPENCODE_DIR.mkdir(parents=True, exist_ok=True)
        heartbeat = {
            "timestamp": _now(),
            "watcher_alive": True,
            "cycle_already_running": True,
            "last_error": "CYCLE_ALREADY_RUNNING: another watcher holds the singleton lock",
            "lock": str(WATCHER_LOCK),
        }
        HEARTBEAT.write_text(json.dumps(heartbeat, indent=2, sort_keys=True), encoding="utf-8")
        print(json.dumps(heartbeat, indent=2, default=str), flush=True)
        return 0

    try:
        while True:
            tick = _tick_count()
            fetch_exit = bool(args.fetch_exit) or (tick % EXIT_RESEARCH_EVERY_N == 0)
            try:
                result = run_cycle(tick, fetch_exit=fetch_exit)
            except Exception as exc:  # keep the watcher alive across transient failures
                result = {"tick": tick, "utc": _now(), "error": str(exc)}
                write_heartbeat(tick=tick, watcher_alive=True, last_cycle=_now(),
                                no_new_evidence=False, new_outcome_lines=0,
                                last_error=str(exc))
            print(json.dumps(result, indent=2, default=str), flush=True)
            if args.once:
                return 0
            time.sleep(int(args.interval))
    finally:
        lock.release()


if __name__ == "__main__":
    raise SystemExit(main())