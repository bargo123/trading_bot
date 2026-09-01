#!/usr/bin/env python3
"""AEGIS council live terminal.

Default behavior is LIVE FOLLOW mode: it prints one compact status snapshot,
then streams only NEW council activity until Ctrl+C.

  python bot/scripts/aegis_council_watch.py            # follow (Ctrl+C to exit)
  python bot/scripts/aegis_council_watch.py --once     # single snapshot, exit
  python bot/scripts/aegis_council_watch.py --interval 2

Event sources:
  bot/reports/council/live.jsonl   canonical council round stream (tailed)
  bot/intel/challenger.json        challenger created/updated
  bot/intel/champion.json          champion promoted/updated
  bot/reports/bot_heartbeat.json   runner/watcher health changes

Read-only; never mutates council state.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

BOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BOT))

try:  # Windows consoles default to cp1252; agent output may contain unicode
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass

from ai_council.agents import all_statuses, _load_probe_cache  # noqa: E402
from ai_council import paths as council_paths  # noqa: E402
from ai_council.cases import list_cases  # noqa: E402
from ai_council.knowledge.corpus import corpus_stats  # noqa: E402

LIVE_JSONL = council_paths.LIVE_JSONL
CHALLENGER_JSON = BOT / "intel" / "challenger.json"
CHAMPION_JSON = BOT / "intel" / "champion.json"
HEARTBEAT_JSON = BOT / "reports" / "bot_heartbeat.json"

POLL_INTERVAL_S = 2.0


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _runner_heartbeat() -> dict:
    return _read_json(HEARTBEAT_JSON)


def render() -> str:
    """Compact status snapshot (agents, runner, corpus, latest rounds)."""
    utc = datetime.now(timezone.utc).isoformat(timespec="seconds")
    statuses = all_statuses().get("agents", {})
    probes = _load_probe_cache()
    cases = list_cases()
    stats = corpus_stats()
    hb = _runner_heartbeat()
    lines = [
        "# AEGIS council watch - status snapshot",
        f"UTC {utc}   (follow mode: streaming new events; Ctrl+C to exit)",
        "",
        "## Agents (CLI detection + last REAL probe)",
        "",
    ]
    for name, info in sorted(statuses.items()):
        probe = probes.get(name) or {}
        probe_status = probe.get("status") or "never-probed"
        model = probe.get("model") or "-"
        probed_at = (probe.get("probed_utc") or "")[:19]
        lines.append(
            f"- {name}: cli={info.get('status')} real={probe_status} "
            f"model={model} probed={probed_at}"
        )
    lines += ["", "## Recent cases", ""]
    if not cases:
        lines.append("- (no cases yet)")
    for case in cases[:6]:
        decision = (case.get("decision") or {}).get("decision") if isinstance(
            case.get("decision"), dict
        ) else case.get("decision")
        reason = ""
        if isinstance(case.get("decision"), dict):
            reason = case["decision"].get("evidence", {}).get("reason") or ""
        lines.append(
            f"- {case.get('id')} [{case.get('mode')}] {case.get('phase')} "
            f"{decision or '-'} {reason} - {(case.get('question') or '')[:60]}"
        )
    lines += [
        "",
        "## Runner",
        "",
        f"- pid: {hb.get('pid')}  status: {hb.get('status')}",
        f"- validated_states: {hb.get('validated_states')}  gate: {hb.get('gate_validated_states')}",
        f"- equity: {hb.get('equity')}  open: {hb.get('open')}",
        "",
        "## Knowledge corpus",
        "",
        f"- books: {stats.get('n_books')} ({stats.get('n_real')} real)  words: {stats.get('total_words'):,}",
        "",
        "## Latest rounds",
        "",
    ]
    if LIVE_JSONL.exists():
        try:
            feed = LIVE_JSONL.read_text(encoding="utf-8").strip().splitlines()[-5:]
        except OSError:
            feed = []
        for line in feed:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            lines.append(
                f"- {item.get('finished_utc','')[:19]} {item.get('id')} "
                f"[{item.get('mode')}] {item.get('decision')}"
            )
    else:
        lines.append("- (no council rounds yet)")
    return "\n".join(lines)


def _fmt_dur(duration: object) -> str:
    try:
        return f"{float(duration):.1f}s"
    except (TypeError, ValueError):
        return "-"


def _round_events(record: dict) -> list[str]:
    """Human-readable event lines for one appended live.jsonl record."""
    out: list[str] = []
    cid = record.get("id")
    for act in record.get("activity") or []:
        step = act.get("step")
        agent = str(act.get("agent") or "?").upper()
        status = act.get("status")
        dur = _fmt_dur(act.get("duration_s"))
        if step == "proposal":
            line = f"[PROPOSAL] {agent} {status} ({dur})"
        elif step == "critique":
            line = f"[CRITIQUE] {agent} -> {str(act.get('target') or '?').upper()} {status} ({dur})"
        elif step == "revision":
            line = f"[REVISION] {agent} {status} ({dur})"
        else:
            line = f"[{str(step or 'EVENT').upper()}] {agent} {status} ({dur})"
        if act.get("error"):
            line += f" :: {act['error']}"
        out.append(line)
    decision = record.get("decision")
    if isinstance(decision, dict):
        reason = decision.get("evidence", {}).get("reason") or ""
        challenger = decision.get("evidence", {}).get("challenger_id") or ""
        out.append(f"[COUNCIL DECISION] {cid} -> {decision.get('decision')} ({reason})")
        if challenger:
            out.append(f"[CHALLENGER CREATED] {challenger}")
    elif decision:
        out.append(f"[COUNCIL DECISION] {cid} -> {decision}")
    return out


def _tail_new_lines(path: Path, offset: int) -> tuple[list[str], int]:
    """Return (new complete lines, new offset); safe on rotation/truncation."""
    try:
        size = path.stat().st_size
    except OSError:
        return [], offset
    if size < offset:  # truncated or rotated: skip replaying old content
        return [], size
    if size == offset:
        return [], offset
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            fh.seek(offset)
            data = fh.read()
            offset = fh.tell()
    except OSError:
        return [], offset
    lines = data.splitlines()
    if data and not data.endswith("\n") and lines:
        # last line may be partially written; rewind to its start
        partial = lines.pop()
        offset -= len(partial.encode("utf-8", errors="replace")) + 1
    return [ln for ln in lines if ln.strip()], offset


def follow(interval: float = POLL_INTERVAL_S) -> None:
    print(render())
    print("")
    print("--- following council events (Ctrl+C to exit) ---")
    print("", flush=True)

    offset = LIVE_JSONL.stat().st_size if LIVE_JSONL.exists() else 0
    last_challenger = (_read_json(CHALLENGER_JSON).get("updated_utc"),)
    last_champion = (_read_json(CHAMPION_JSON).get("updated_utc"),)
    last_hb_key: tuple | None = None

    try:
        while True:
            new_lines, offset = _tail_new_lines(LIVE_JSONL, offset)
            for line in new_lines:
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                stamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
                for event in _round_events(record):
                    print(f"{stamp} {event}", flush=True)

            challenger = _read_json(CHALLENGER_JSON)
            champion = _read_json(CHAMPION_JSON)
            if challenger.get("updated_utc") != last_challenger[0]:
                if last_challenger[0] is not None or challenger:
                    stamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
                    print(
                        f"{stamp} [CHALLENGER UPDATED] {challenger.get('id')} "
                        f"decision={challenger.get('decision')}",
                        flush=True,
                    )
                last_challenger = (challenger.get("updated_utc"),)
            if champion.get("updated_utc") != last_champion[0]:
                if last_champion[0] is not None or champion:
                    stamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
                    print(
                        f"{stamp} [CHAMPION UPDATED] {champion.get('id')} "
                        f"role={champion.get('role')}",
                        flush=True,
                    )
                last_champion = (champion.get("updated_utc"),)

            hb = _runner_heartbeat()
            hb_key = (
                hb.get("pid"),
                hb.get("status"),
                hb.get("equity"),
                hb.get("open"),
                hb.get("fire"),
                hb.get("skip"),
                hb.get("quote_stale"),
                hb.get("validated_states"),
            )
            if last_hb_key is None:
                last_hb_key = hb_key
            elif hb_key != last_hb_key:
                stamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
                changed = [
                    f"{name}: {old} -> {new}"
                    for name, old, new in zip(
                        ("pid", "status", "equity", "open", "fire", "skip",
                         "quote_stale", "validated_states"),
                        last_hb_key,
                        hb_key,
                    )
                    if old != new
                ]
                print(f"{stamp} [RUNNER] {' '.join(changed)}", flush=True)
                last_hb_key = hb_key

            time.sleep(interval)
    except KeyboardInterrupt:
        print("")
        print("watch stopped (Ctrl+C).")
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="AEGIS council live terminal")
    parser.add_argument(
        "--once", action="store_true",
        help="print one status snapshot and exit (default: follow until Ctrl+C)",
    )
    parser.add_argument(
        "--interval", type=float, default=POLL_INTERVAL_S,
        help="poll interval seconds in follow mode (default 2)",
    )
    args = parser.parse_args()
    if args.once:
        print(render())
        return 0
    follow(interval=max(0.5, float(args.interval)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
