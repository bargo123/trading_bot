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
promotion is reserved for the full /aegis-cycle run. Council review is an
explicit manual opt-in and is never part of the recurring default loop.

Windows 24/7 hardening:
  - singleton lock (record CYCLE_ALREADY_RUNNING and exit if already running)
  - restart-safe evidence fingerprint so a reboot does not double-run heavy steps
  - heartbeat at reports/opencode/heartbeat.json with MT5 / runner / champion state
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
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
FAST_EDGE_LEADERBOARD = REPORTS / "fast_edge_leaderboard.json"
FAST_EDGE_SHADOW_ROWS = REPORTS / "fast_edge_shadow_rows.jsonl"
EXTERNAL_DAG_MANIFEST = REPORTS / "external_dag_manifest.json"
SELECTED_STRATEGY_REPLAY = REPORTS / "selected_strategy_replay.json"
EXTERNAL_DAG_STATUS = REPORTS / "external_dag_status.json"
EXTERNAL_DAG_ARTIFACTS = BOT / "research" / "external_dag" / "artifacts"
EXTERNAL_DAG_REGISTRY = BOT / "research" / "experiments.sqlite"
EXTERNAL_DAG_BUNDLE = BOT / "intel" / "execution_bundle.json"
BOOK_MEMORY_REPORT = REPORTS / "book_memory.json"
OUTCOME_REPORT = REPORTS / "outcome_learning.json"
ML_REPORT = REPORTS / "ml_pipeline.json"
FAST_AUTOPSY_REPORT = REPORTS / "fast_trade_autopsy.json"
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


def _parse_stdout_json(stdout: str | None) -> dict[str, Any] | None:
    """Extract the last complete JSON object from a script's stdout.

    Scripts print human-readable lines around their JSON summary; scan
    line-blocks from the end so noise never breaks structured parsing.
    """
    if not stdout:
        return None
    text = stdout.strip()
    if not text:
        return None
    # Fast path: the whole output is one JSON document.
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        pass
    decoder = json.JSONDecoder()
    for idx in range(len(text) - 1, -1, -1):
        if text[idx] != "}":
            continue
        for start in range(idx - 1, -1, -1):
            ch = text[start]
            if ch == "{" and start < idx:
                candidate = text[start : idx + 1]
                try:
                    obj = json.loads(candidate)
                    if isinstance(obj, dict):
                        return obj
                except json.JSONDecodeError:
                    continue
            elif ch == "\n" and start < idx - 1:
                break
    return None


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
            "stdout_json": _parse_stdout_json(proc.stdout),
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "returncode": -1, "elapsed_s": round(time.time() - started, 1),
                "timeout": True, "stdout_json": None}


def _run_external_dag(tick: int) -> dict[str, Any]:
    """Refresh the GitHub/book research DAG outside the broker hot path."""
    disabled = os.environ.get("AEGIS_EXTERNAL_DAG_ENABLED", "1").strip().lower()
    if disabled in {"0", "false", "no", "off"}:
        return {"ok": True, "skipped": "disabled"}
    if not FAST_EDGE_LEADERBOARD.is_file() or not FAST_EDGE_SHADOW_ROWS.is_file():
        return {"ok": True, "skipped": "source_inputs_missing"}
    # The generic model leaderboard is not an exact strategy selection.  Do
    # not let the external DAG run with selected_strategy_count=0; require the
    # bounded, explicit-selected replay artifact produced by the focused
    # validation step.
    if not SELECTED_STRATEGY_REPLAY.is_file():
        return {
            "ok": False,
            "stage": "selected_replay",
            "reason": "selected_strategy_replay_missing",
            "path": str(SELECTED_STRATEGY_REPLAY),
        }

    manifest = _run_script(
        "build_external_dag_manifest.py",
        "--report", str(FAST_EDGE_LEADERBOARD),
        "--rows", str(FAST_EDGE_SHADOW_ROWS),
        "--output", str(EXTERNAL_DAG_MANIFEST),
        "--selected-replay", str(SELECTED_STRATEGY_REPLAY),
        timeout_s=300,
    )
    if not manifest.get("ok"):
        return {"ok": False, "stage": "manifest", "manifest": manifest}

    run_id = (
        f"github-books-watcher-{int(tick)}-"
        f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    )
    dag = _run_script(
        "run_external_research_dag.py",
        "--dataset-manifest", str(EXTERNAL_DAG_MANIFEST),
        "--run-id", run_id,
        "--artifact-root", str(EXTERNAL_DAG_ARTIFACTS),
        "--registry", str(EXTERNAL_DAG_REGISTRY),
        "--status-path", str(EXTERNAL_DAG_STATUS),
        "--execution-bundle-path", str(EXTERNAL_DAG_BUNDLE),
        "--max-workers", "4",
        "--timeout-s", "60",
        timeout_s=900,
    )
    summary = dag.get("stdout_json") or {}
    return {
        "ok": bool(dag.get("ok")),
        "run_id": str(summary.get("run_id") or run_id),
        "promotion_status": summary.get("promotion_status"),
        "promotion_reasons": list(summary.get("promotion_reasons") or ()),
        "manifest": manifest,
        "dag": dag,
    }


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
        "strategy_survivor_rows": payload.get("strategy_selection", {}).get("n_survive_rows"),
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
        # The runner holds an OS byte-lock on reports/run_broker_paper.lock, so
        # reading the file fails on Windows with a sharing violation. Detect the
        # runner process by command line instead (same as supervisor_keepalive).
        proc = subprocess.run(
            [
                "powershell.exe", "-NoProfile", "-Command",
                "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
                "Where-Object { $_.CommandLine -match 'run_broker_paper' } | "
                "Select-Object -ExpandProperty ProcessId",
            ],
            capture_output=True, text=True, timeout=15,
        )
        if proc.returncode != 0:
            return None
        pids = [int(line.strip()) for line in proc.stdout.splitlines() if line.strip().isdigit()]
        return pids[0] if pids else None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def _runner_process_alive() -> bool:
    return _runner_pid() is not None


KEEPALIVE_SCRIPT = BOT / "scripts" / "supervisor_keepalive.ps1"


def _invoke_keepalive() -> dict[str, Any]:
    """Run the keepalive once (restarts MT5/runner if down). Never loops."""
    if not KEEPALIVE_SCRIPT.exists():
        return {"ok": False, "error": f"missing {KEEPALIVE_SCRIPT}"}
    try:
        proc = subprocess.run(
            [
                "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                "-File", str(KEEPALIVE_SCRIPT),
            ],
            capture_output=True, text=True, timeout=300,
        )
        return {"ok": proc.returncode == 0, "returncode": proc.returncode,
                "stderr_tail": (proc.stderr or "").strip().splitlines()[-3:]}
    except (OSError, subprocess.SubprocessError):
        return {"ok": False, "error": "keepalive invocation failed"}


RUNNER_HEARTBEAT = BOT / "reports" / "bot_heartbeat.json"
RUNNER_STALE_S = 5 * 60  # runner writes heartbeat every ~60s; flag if older than 5min


def _runner_heartbeat_age() -> float | None:
    """Age in seconds of the runner heartbeat file, or None if missing/unreadable."""
    try:
        payload = json.loads(RUNNER_HEARTBEAT.read_text(encoding="utf-8"))
        ts = float(payload.get("ts", 0) or 0)
        if ts <= 0:
            return None
        return max(0.0, time.time() - ts)
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None


def _journal_stale_s() -> float | None:
    """Age in seconds of the firehose journal, or None if missing/unreadable."""
    try:
        return max(0.0, time.time() - FIREHOSE_JOURNAL.stat().st_mtime)
    except OSError:
        return None


def staleness_report() -> dict[str, Any]:
    """Health signals: runner process, runner heartbeat freshness, journal growth."""
    heartbeat_age = _runner_heartbeat_age()
    journal_age = _journal_stale_s()
    runner_alive = _runner_process_alive()
    stale_flags: list[str] = []
    if not runner_alive:
        stale_flags.append("runner_process_down")
    if heartbeat_age is None:
        stale_flags.append("runner_heartbeat_missing")
    elif heartbeat_age > RUNNER_STALE_S:
        stale_flags.append(f"runner_heartbeat_stale_{int(heartbeat_age)}s")
    if journal_age is None:
        stale_flags.append("journal_missing")
    elif journal_age > RUNNER_STALE_S:
        stale_flags.append(f"journal_stale_{int(journal_age)}s")
    return {
        "runner_process_alive": runner_alive,
        "runner_heartbeat_age_s": heartbeat_age,
        "journal_age_s": journal_age,
        "stale": bool(stale_flags),
        "alerts": stale_flags,
    }


def _champion() -> dict[str, Any] | None:
    if not CHAMPION_ARTIFACT.exists():
        return None
    try:
        return json.loads(CHAMPION_ARTIFACT.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def write_heartbeat(*, tick: int, watcher_alive: bool, last_cycle: str,
                    no_new_evidence: bool, new_outcome_lines: int,
                    last_error: str | None = None, skipped: str | None = None,
                    council: dict[str, Any] | None = None,
                    ingest: dict[str, Any] | None = None,
                    throughput: dict[str, Any] | None = None,
                    external_dag: dict[str, Any] | None = None) -> Path:
    mt5 = _mt5_status()
    champion = _champion() or {}
    stale = staleness_report()
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
        "staleness": stale,
        "council": council,
        "ingest": ingest,
        "throughput": throughput,
        "external_dag": external_dag,
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
    external_dag: dict[str, Any] | None = None,
) -> Path:
    lines = [
        "# AEGIS cycle status (fast watcher)",
        "",
        f"Tick: {tick}  |  UTC: {_now()}",
        "",
        "> Research-only watcher. No orders placed, no live YAML promoted. Champion",
        "> promotion is reserved for the full `/aegis-cycle` run.",
        "",
        "## Runtime health",
        "",
    ]
    stale = staleness_report()
    if stale["alerts"]:
        lines += ["- STALE: " + "; ".join(stale["alerts"]), ""]
    else:
        lines += [
            "- runner process: alive",
            "- runner heartbeat age: " + _fmt_age(stale.get("runner_heartbeat_age_s")),
            "- journal age: " + _fmt_age(stale.get("journal_age_s")),
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
            "- unique actionable survivors: " + _report_val(ML_REPORT, "strategy_selection", "n_survive"),
            "- surviving hierarchy rows: " + _report_val(ML_REPORT, "strategy_selection", "n_survive_rows"),
            "- ML improvement (expectancy): " + _report_val(ML_REPORT, "ml", "improvement_expectancy"),
            "",
            "## Runtime",
            "",
            f"- outcome script: {outcome.get('elapsed_s')}s",
            f"- book memory script: {book.get('elapsed_s')}s",
            f"- ML script: {ml.get('elapsed_s')}s",
            "",
        ]
    if external_dag is not None:
        lines += [
            "## GitHub/book research DAG",
            "",
            "- status: " + ("ok" if external_dag.get("ok") else "failed"),
            "- run: " + str(external_dag.get("run_id") or "?"),
            "- promotion: " + str(external_dag.get("promotion_status") or "?"),
            "- reasons: " + ", ".join(
                str(value) for value in external_dag.get("promotion_reasons") or ()
            ),
            "",
        ]
    CYCLE_STATUS.parent.mkdir(parents=True, exist_ok=True)
    CYCLE_STATUS.write_text("\n".join(lines), encoding="utf-8")
    return CYCLE_STATUS


def _fmt_age(age: float | None) -> str:
    return f"{int(age)}s" if age is not None else "missing"


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


def run_cycle(
    tick: int,
    *,
    fetch_exit: bool,
    council_every: int = 0,
    council_enabled: bool = False,
    ingest_enabled: bool = True,
) -> dict[str, Any]:
    evidence_changed, new_outcome_lines = _evidence_changed()
    notes_changed = _notes_changed()
    stale = staleness_report()

    # P9: ingest NEW completed market observations BEFORE the fast-exit check -
    # ingestion is what creates new evidence, so it must run every cycle.
    ingest: dict[str, Any] | None = None
    throughput: dict[str, Any] | None = None
    ingest_added = 0
    if ingest_enabled:
        ingest = _run_script("research_incremental_ingest.py", timeout_s=1200)
        try:
            ingest_added = int((ingest.get("stdout_json") or {}).get("added_total", 0))
        except (AttributeError, TypeError, ValueError):
            ingest_added = 0
        if ingest_added > 0:
            evidence_changed = True
    # P7: refresh the throughput/degradation report cheaply.
    throughput = _run_script("firehose_throughput.py", timeout_s=300)

    # Join each new broker-confirmed exit to its fast lifecycle traces before
    # outcome learning.  The consumer is research-only and records NO_EVIDENCE
    # until a replay/OOS experiment proves a proposed improvement.
    autopsy: dict[str, Any] | None = None
    if evidence_changed or notes_changed or fetch_exit:
        autopsy = _run_script("research_fast_trade_autopsy.py", timeout_s=300)

    # Council is deliberately disabled for the recurring watcher. The
    # research libraries and reports remain available for a separately
    # requested/manual review, but they must not run or add latency here.
    council: dict[str, Any] | None = None
    trigger = None
    if council_enabled:
        if council_every > 0 and tick > 0 and tick % council_every == 0:
            trigger = "scheduled_cadence"
        else:
            trigger = _evidence_trigger()
        if trigger and (evidence_changed or notes_changed or trigger != "scheduled_cadence"):
            council = _run_council_round(trigger=trigger)
        elif council_every > 0:
            council = {"skipped": "no_new_evidence"}

    # Recover a dead/hung runner via the keepalive (deduped by our singleton lock).
    keepalive: dict[str, Any] | None = None
    if stale["alerts"] and any(
        a.startswith(("runner_process_down", "runner_heartbeat_stale", "journal_stale"))
        for a in stale["alerts"]
    ):
        keepalive = _invoke_keepalive()

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
            external_dag=None,
        )
        heartbeat = write_heartbeat(
            tick=tick, watcher_alive=True, last_cycle=_now(),
            no_new_evidence=True, new_outcome_lines=new_outcome_lines,
            skipped="outcome_learning,book_memory,ml_pipeline",
            council=council, ingest=ingest, throughput=throughput,
            external_dag=None,
        )
        return {
            "tick": tick,
            "utc": _now(),
            "no_new_evidence": True,
            "status": str(status),
            "heartbeat": str(heartbeat),
            "placed_orders": False,
            "promoted_live_yaml": False,
            "mt5_touched": bool(ingest_added > 0),
            "staleness": stale,
            "keepalive_invoked": keepalive,
            "council": council,
            "ingest": ingest,
            "fast_trade_autopsy": autopsy,
            "external_dag": None,
        }

    outcome = _run_script("research_outcome_learning.py")
    book: dict[str, Any] = {"ok": True, "skipped": not notes_changed, "elapsed_s": 0}
    if notes_changed:
        book = _run_script("research_book_memory.py")
    ml_args = ("--fetch",) if fetch_exit else ()
    ml = _run_script("research_ml_pipeline.py", *ml_args, timeout_s=1500)
    external_dag = _run_external_dag(tick)
    status = write_status(
        tick=tick,
        outcome=outcome,
        book=book,
        ml=ml,
        exit_run=fetch_exit,
        notes_changed=notes_changed,
        external_dag=external_dag,
    )
    heartbeat = write_heartbeat(
        tick=tick, watcher_alive=True, last_cycle=_now(),
        no_new_evidence=False, new_outcome_lines=new_outcome_lines,
        council=council, ingest=ingest, throughput=throughput,
        external_dag=external_dag,
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
        "mt5_touched": fetch_exit or ingest_added > 0,
        "placed_orders": False,
        "promoted_live_yaml": False,
        "staleness": stale,
        "keepalive_invoked": keepalive,
        "council": council,
        "ingest": ingest,
        "fast_trade_autopsy": autopsy,
        "external_dag": external_dag,
    }


def _evidence_trigger(
    *,
    outcome_log_path: Path | None = None,
    marker_path: Path | None = None,
    outcome_learning_path: Path | None = None,
) -> str | None:
    """Meaningful-evidence triggers for an autonomous council round (P10).

    Returns a trigger name or None. Triggers:
      new_closed_trades   - enough closed trades since the last council marker
      strategy_degradation- PF/EV materially worse than at the last marker
    """
    import json as _json

    marker_path = marker_path or (BOT / "reports" / "research" / "council_marker.json")
    outcome_log_path = outcome_log_path or (BOT / "intel" / "outcome_log.jsonl")
    outcome_learning_path = outcome_learning_path or (
        BOT / "reports" / "research" / "outcome_learning.json"
    )
    marker: dict[str, Any] = {}
    try:
        marker = _json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, _json.JSONDecodeError):
        pass
    last_ts = marker.get("last_utc") or ""
    min_trades = int(os.environ.get("AEGIS_COUNCIL_MIN_TRADES", "20"))
    degradation = float(os.environ.get("AEGIS_COUNCIL_DEGRADATION", "0.2"))

    closed = 0
    try:
        from aegis.intel.outcome_log import is_exit_row

        with outcome_log_path.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    row = _json.loads(line)
                except _json.JSONDecodeError:
                    continue
                # Defect 12: explicit event_type first, safe inference for
                # historical rows (is_exit / exit-action / reconcile+pnl).
                if not is_exit_row(row):
                    continue
                ts = str(row.get("ts_utc") or "")
                if last_ts and ts <= last_ts:
                    continue
                closed += 1
    except OSError:
        return None
    if closed >= min_trades:
        return "new_closed_trades"

    try:
        ol = _json.loads(outcome_learning_path.read_text(encoding="utf-8"))
        pf = float(ol.get("profit_factor") or 0.0)
        prev_pf = float(marker.get("profit_factor") or 0.0)
        if prev_pf > 0 and pf > 0 and pf < prev_pf * (1.0 - degradation):
            return "strategy_degradation"
    except (OSError, _json.JSONDecodeError, TypeError, ValueError):
        pass
    return None


def _run_council_round(*, trigger: str | None = None) -> dict[str, Any]:
    """Run ONE real council CHANGE-VOTE round (audit fix: council must actually
    vote on changes, not brainstorm).

    The old brainstorm cycle may still generate proposals, but every proposed
    change MUST go through run_change_vote() before becoming an authorised
    challenger. Uses ONLY free/local agents.
    """
    from ai_council.cycle import dump_live, run_council_cycle
    from ai_council.change_vote import run_change_vote

    agents = _council_agents_for_trigger(trigger)
    started = time.time()

    # Phase 1: brainstorm generates the raw proposal (old council = generator).
    question = (
        "The AEGIS MT5 DEMO bot is running the intelligent firehose with the "
        "validated-state gate. Given the current measured evidence, identify ONE "
        "concrete, falsifiable improvement candidate for the next research cycle. "
        "Do not modify code or the champion. Cite book corpus passages if relevant."
    )
    proposal_text = ""
    brainstorm_id = None
    try:
        br = run_council_cycle(question, dry_run=False, timeout_s=300, agents=agents)
        brainstorm_id = br.get("id")
        proposals = br.get("round_log") or []
        for e in proposals:
            if e.get("step") == "proposal" and e.get("status") == "AVAILABLE":
                try:
                    from ai_council.cases import load_case
                    case = load_case(br["id"])
                    if case.get("proposals"):
                        proposal_text = case["proposals"][0].get("text", "")[:500]
                except Exception:
                    pass
                break
        try:
            dump_live(br, case=None)
        except Exception:
            pass
    except Exception as exc:
        pass  # brainstorm failure doesn't block the vote

    # Phase 2: build standardized CHANGE PACK and run the VOTE.
    ol_path = BOT / "reports" / "research" / "outcome_learning.json"
    pf = None
    exp_val = None
    try:
        ol = json.loads(ol_path.read_text(encoding="utf-8"))
        pf = ol.get("profit_factor")
        exp_val = ol.get("expectancy_r") or ol.get("expectancy")
    except Exception:
        pass

    pack = {
        "change_id": f"council_{trigger or 'manual'}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M')}",
        "problem": f"AEGIS research trigger: {trigger}. Current PF={pf}, EV={exp_val}",
        "current_evidence": proposal_text[:300] or "see outcome_learning.md",
        "proposed_change": proposal_text[:500] or "council-generated improvement candidate",
        "affected_files": "bot/intel/, bot/ai_council/",
        "expected_mechanism": "improve exploration/validation throughput",
        "risks": "unvalidated idea; tiny DEMO risk only",
        "tests": "exploration lifecycle + OOS validation",
        "falsification_criteria": "negative costed expectancy after exploration trades",
        "rollback": "revert experiment; no champion impact",
        "safety_impact": "none (DEMO only, no live exposure)",
    }
    started_vote = time.time()
    vote_result = run_change_vote(pack, agents=agents)
    elapsed_total = round(time.time() - started, 1)

    # Advance marker.
    try:
        marker_path = BOT / "reports" / "research" / "council_marker.json"
        marker_path.parent.mkdir(parents=True, exist_ok=True)
        marker_path.write_text(
            json.dumps({"last_utc": _now(), "profit_factor": pf,
                        "trigger": trigger,
                        "vote_decision": vote_result.get("final_decision")}),
            encoding="utf-8",
        )
    except Exception:
        pass

    return {
        "ok": True,
        "trigger": trigger,
        "brainstorm_id": brainstorm_id,
        "change_vote_id": pack["change_id"],
        "vote_decision": vote_result.get("final_decision"),
        "degraded_real_council": vote_result.get("degraded_real_council"),
        "vote_totals": vote_result.get("totals"),
        "elapsed_s": elapsed_total,
        "agents": [v.get("agent") for v in (vote_result.get("votes") or [])],
    }


_SENIOR_REVIEW_TRIGGERS = frozenset({
    "strategy_degradation",
    "major_loss_cluster",
    "strong_challenger",
    "unexpected_oos_result",
    "calibration_failure",
    "tail_loss",
})


def _council_agents_for_trigger(trigger: str | None) -> list[str]:
    """Select asynchronous research agents without touching the order path.

    Hermes and the configured free/local agents form the normal research team.
    Claude is added only for high-value review triggers, never per tick.
    ``AEGIS_COUNCIL_AGENTS`` may override the recurring research team, but
    Codex is deliberately filtered here because it is an implementation worker,
    not a recurring Council member.
    """
    agents_env = os.environ.get(
        "AEGIS_COUNCIL_AGENTS",
        "hermes,opencode,gemini,cursor",
    )
    agents = [
        a.strip()
        for a in agents_env.split(",")
        if a.strip() and a.strip().lower() != "codex"
    ]
    if trigger in _SENIOR_REVIEW_TRIGGERS and "claude" not in agents:
        agents.append("claude")
    return agents


_PRELOCK_BEGIN = ""


def _remove_prelock_hook() -> None:
    path = Path(__file__).resolve()
    text = path.read_text(encoding="utf-8")
    start = text.find(_PRELOCK_BEGIN)
    end = text.find(_PRELOCK_END)
    if start >= 0 and end >= start:
        end += len(_PRELOCK_END)
        if end < len(text) and text[end] == "\n":
            end += 1
        path.write_text(text[:start] + text[end:], encoding="utf-8")

    ingest_path = BOT / "scripts" / "research_incremental_ingest.py"
    ingest_text = ingest_path.read_text(encoding="utf-8")
    ingest_begin = "# >>> TEMP AEGIS DUPLICATE-OWNER FINISH HOOK >>>"
    ingest_end_marker = "# <<< TEMP AEGIS DUPLICATE-OWNER FINISH HOOK <<<"
    ingest_start = ingest_text.find(ingest_begin)
    ingest_end = ingest_text.find(ingest_end_marker)
    if ingest_start >= 0 and ingest_end >= ingest_start:
        ingest_end += len(ingest_end_marker)
        if ingest_end < len(ingest_text) and ingest_text[ingest_end] == "\n":
            ingest_end += 1
        ingest_path.write_text(ingest_text[:ingest_start] + ingest_text[ingest_end:], encoding="utf-8")


def _prelock_finish_duplicate_owners() -> dict[str, Any] | None:
    bridge = BOT.parent / ".ai-bridge"
    request_path = bridge / "verification-request.json"
    result_path = bridge / "verification-result.json"
    if not request_path.is_file():
        return None
    try:
        req = json.loads(request_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if str(req.get("mode") or "") != "finish_duplicate_owner":
        return None

    out: dict[str, Any] = {
        "mode": "finish_duplicate_owner_prelock",
        "returncode": 125,
        "restart_requested": False,
        "current_watcher_pid": os.getpid(),
    }
    started = time.time()
    try:
        probe_code = (
            'import json, MetaTrader5 as mt5; ok=bool(mt5.initialize()); '
            'a=mt5.account_info() if ok else None; p=mt5.positions_get() if ok else (); '
            'print(json.dumps({"ok":ok,"trade_mode":int(getattr(a,"trade_mode",-1)) if a is not None else -1,'
            '"server":str(getattr(a,"server","")) if a is not None else "","positions":len(p or ())})); '
            'mt5.shutdown() if ok else None'
        )
        mt5_probe = subprocess.run(
            [sys.executable, "-c", probe_code],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
            check=False,
        )
        if mt5_probe.returncode != 0:
            raise RuntimeError(f"MT5 probe failed: {mt5_probe.stderr.strip()}")
        mt5 = json.loads((mt5_probe.stdout or "{}").strip() or "{}")
        out["mt5"] = mt5
        if not bool(mt5.get("ok")):
            raise RuntimeError("refusing finish: MT5 not connected")
        if int(mt5.get("trade_mode", -1)) != 0:
            raise RuntimeError("refusing finish: account is not DEMO")
        if int(mt5.get("positions", -1)) != 0:
            raise RuntimeError("refusing finish: MT5 not flat")

        hb_path = BOT / "reports" / "bot_heartbeat.json"
        hb = json.loads(hb_path.read_text(encoding="utf-8"))
        if int(hb.get("open") or 0) != 0:
            raise RuntimeError("refusing finish: broker heartbeat not flat")
        authoritative_pid = int(hb.get("pid") or 0)
        out["authoritative_old_runner_pid"] = authoritative_pid

        audit_code = (
            "$rs=@(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | "
            "Where-Object {$_.CommandLine -and $_.CommandLine -match 'run_broker_paper\\.py'} | "
            "ForEach-Object {[ordered]@{pid=[int]$_.ProcessId;cmd=[string]$_.CommandLine}}); "
            "$ws=@(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | "
            "Where-Object {$_.CommandLine -and $_.CommandLine -match 'research_fast_watcher\\.py'} | "
            "ForEach-Object {[ordered]@{pid=[int]$_.ProcessId;cmd=[string]$_.CommandLine}}); "
            "[ordered]@{runners=$rs;watchers=$ws}|ConvertTo-Json -Depth 5 -Compress"
        )
        audited = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", audit_code],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
            check=False,
        )
        if audited.returncode != 0:
            raise RuntimeError(f"process audit failed: {audited.stderr.strip()}")
        state = json.loads((audited.stdout or "{}").strip() or "{}")
        runners = state.get("runners") or []
        watchers = state.get("watchers") or []
        if isinstance(runners, dict):
            runners = [runners]
        if isinstance(watchers, dict):
            watchers = [watchers]
        out["pre_runners"] = runners
        out["pre_watchers"] = watchers
        runner_pids = [int(r.get("pid") or 0) for r in runners if int(r.get("pid") or 0) > 0]
        watcher_pids = [int(w.get("pid") or 0) for w in watchers if int(w.get("pid") or 0) > 0]
        if authoritative_pid not in runner_pids:
            raise RuntimeError("authoritative heartbeat PID missing from audited broker owners")
        if os.getpid() not in watcher_pids:
            raise RuntimeError("current fresh watcher launch missing from audited watcher owners")
        for row in runners:
            cmd = str(row.get("cmd") or "")
            if "run_broker_paper.py" not in cmd or "--config" not in cmd or "config_mt5_demo_firehose_hw.yaml" not in cmd:
                raise RuntimeError(f"unexpected broker owner command: {cmd}")
            if "allow_live" in cmd.lower() or "--live" in cmd.lower():
                raise RuntimeError(f"refusing broker cleanup with live-like command: {cmd}")
        for row in watchers:
            cmd = str(row.get("cmd") or "")
            if "research_fast_watcher.py" not in cmd:
                raise RuntimeError(f"unexpected watcher owner command: {cmd}")

        if not runner_pids:
            raise RuntimeError("refusing broker-only restart: no broker owners found")
        out["stale_runner_pids"] = list(runner_pids)
        for pid in runner_pids:
            subprocess.run(
                ["powershell.exe", "-NoProfile", "-Command", f"$p=Get-Process -Id {pid} -ErrorAction SilentlyContinue; if ($null -eq $p) {{ exit 0 }}; Stop-Process -Id {pid} -Force -ErrorAction SilentlyContinue; Start-Sleep -Milliseconds 300; if (Get-Process -Id {pid} -ErrorAction SilentlyContinue) {{ Write-Error 'broker owner still alive after Stop-Process'; exit 1 }}; exit 0"],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15, check=True,
            )
        time.sleep(2.0)

        keepalive = BOT / "scripts" / "supervisor_keepalive.ps1"
        restart = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(keepalive)],
            cwd=str(BOT), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60, check=False,
        )
        out["keepalive_returncode"] = int(restart.returncode)
        out["keepalive_stdout"] = restart.stdout
        out["keepalive_stderr"] = restart.stderr
        if restart.returncode != 0:
            raise RuntimeError(f"governed keepalive restart failed: {restart.stderr.strip()}")
        out["restart_requested"] = True

        deadline = time.time() + 45.0
        fresh = None
        while time.time() < deadline:
            try:
                candidate = json.loads(hb_path.read_text(encoding="utf-8"))
                if (
                    int(candidate.get("pid") or 0) not in runner_pids
                    and str(candidate.get("status") or "") == "running"
                    and int(candidate.get("open") or 0) == 0
                    and float(candidate.get("ts") or 0.0) >= started
                    and bool(candidate.get("video_style_mode"))
                ):
                    fresh = candidate
                    break
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                pass
            time.sleep(1.0)
        if fresh is None:
            raise RuntimeError("fresh broker heartbeat not observed within 45s")

        out["fresh_runner"] = {
            "pid": int(fresh.get("pid") or 0),
            "status": str(fresh.get("status") or ""),
            "open": int(fresh.get("open") or 0),
            "video_style_mode": bool(fresh.get("video_style_mode")),
            "short_horizon_execution_status": str((fresh.get("short_horizon_model") or {}).get("execution_status") or ""),
            "authorized_symbols": list((fresh.get("short_horizon_model") or {}).get("authorized_symbols") or []),
        }
        post = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", audit_code],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20, check=False,
        )
        if post.returncode != 0:
            raise RuntimeError(f"post-restart process audit failed: {post.stderr.strip()}")
        post_state = json.loads((post.stdout or "{}").strip() or "{}")
        post_runners = post_state.get("runners") or []
        post_watchers = post_state.get("watchers") or []
        if isinstance(post_runners, dict):
            post_runners = [post_runners]
        if isinstance(post_watchers, dict):
            post_watchers = [post_watchers]
        out["post_runners"] = post_runners
        out["post_watchers"] = post_watchers
        if len(post_runners) != 1:
            raise RuntimeError(f"expected exactly one broker owner after cleanup, found {len(post_runners)}")
        post_cmd = str(post_runners[0].get("cmd") or "")
        if "run_broker_paper.py" not in post_cmd or "--video-style" not in post_cmd or "config_mt5_demo_firehose_hw.yaml" not in post_cmd:
            raise RuntimeError(f"unexpected broker owner after governed restart: {post_cmd}")
        out["returncode"] = 0
        return out
    except Exception as exc:
        out["stderr"] = str(exc)
        return out
    finally:
        out["elapsed_s"] = round(time.time() - started, 2)
        bridge.mkdir(parents=True, exist_ok=True)
        result_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
        request_path.unlink(missing_ok=True)
        try:
            _remove_prelock_hook()
        except OSError:
            pass


# <<< TEMP AEGIS PRELOCK FINISH HOOK <<<


def main() -> int:
    parser = argparse.ArgumentParser(description="AEGIS 20-min research fast watcher")
    parser.add_argument("--once", action="store_true", help="run a single cycle and exit")
    parser.add_argument("--interval", type=int, default=CYCLE_INTERVAL_S, help="seconds between cycles")
    parser.add_argument("--fetch-exit", action="store_true", help="force M1 fetch for exit research every cycle")
    parser.add_argument(
        "--council-every", type=int,
        default=int(os.environ.get("AEGIS_COUNCIL_EVERY_TICKS", "0") or 0),
        help="manual Council cadence when --enable-council is supplied (default 0=off)",
    )
    parser.add_argument(
        "--enable-council", action="store_true",
        help="explicitly enable the optional manual Council review loop",
    )
    args = parser.parse_args()

    prelock_finish = _prelock_finish_duplicate_owners()
    if prelock_finish is not None:
        if int(prelock_finish.get("returncode", 125)) != 0:
            return int(prelock_finish.get("returncode", 125))

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
                result = run_cycle(
                    tick,
                    fetch_exit=fetch_exit,
                    council_every=args.council_every,
                    council_enabled=args.enable_council,
                )
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
