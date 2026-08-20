#!/usr/bin/env python3
"""Interactive AEGIS council console.

Commands:
  status            - agent availability + runner health + corpus stats
  cases             - list recent council cases
  case <id>         - show one case record
  ask <agent> <q>   - ask one agent a question (read-only)
  ask-all <q>       - ask every AVAILABLE agent (read-only)
  round <question>  - run a REAL council round (invokes every AVAILABLE agent)
  round --dry-run <question>
                    - simulated round (tagged DRY_RUN, never counts as research)
  verify            - harmless real invocation of every AVAILABLE agent
  force-cycle       - trigger the watcher once (--once) and report
  watch             - render the live watch terminal
  quit / exit
"""
from __future__ import annotations

import json
import shlex
import subprocess
import sys
from pathlib import Path

BOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BOT))

from ai_council import agents as agent_cli  # noqa: E402
from ai_council import cases as case_store  # noqa: E402
from ai_council.cycle import run_council_cycle  # noqa: E402
from ai_council.knowledge.corpus import corpus_stats, retrieve  # noqa: E402


def _cmd_status() -> None:
    print(json.dumps(agent_cli.all_statuses(), indent=2, default=str))
    cache = agent_cli._load_probe_cache()
    if cache:
        print("last REAL probes (cached):")
        for name, entry in sorted(cache.items()):
            print(
                f"  {name}: {entry.get('status')} model={entry.get('model')} "
                f"probed={entry.get('probed_utc')}"
            )
    stats = corpus_stats()
    print(f"corpus: {stats['n_real']} real books, {stats['total_words']:,} words")


def _cmd_cases() -> None:
    for case in case_store.list_cases()[:10]:
        print(f"{case['id']}  {case['phase']}  {case['status']}  {case['question']}")


def _cmd_case(case_id: str) -> None:
    try:
        case = case_store.load_case(case_id)
    except FileNotFoundError as exc:
        print(exc)
        return
    print(json.dumps(case, indent=2, default=str))


def _cmd_ask(agent: str, question: str) -> None:
    result = agent_cli.ask_agent(agent, question)
    print(f"{agent}: {result.get('status')}")
    if result.get("ok"):
        print(result.get("stdout_tail") or "(no output)")
    else:
        print(result.get("error") or "no output")


def _cmd_ask_all(question: str) -> None:
    for name in agent_cli.load_agents_config():
        probe = agent_cli.probe_agent(name)
        if probe.get("status") != "AVAILABLE":
            print(f"{name}: {probe.get('status')} - skipped")
            continue
        print(f"--- {name} ---")
        _cmd_ask(name, question)


def _cmd_round(args: list[str]) -> None:
    dry_run = "--dry-run" in args
    args = [a for a in args if a != "--dry-run"]
    question = " ".join(args).strip()
    if not question:
        print("usage: round [--dry-run] <question>")
        return
    mode = "DRY_RUN" if dry_run else "REAL"
    print(f"running council round in {mode} mode: {question}")
    result = run_council_cycle(question, dry_run=dry_run)
    print(json.dumps(result, indent=2, default=str))
    case = case_store.load_case(result["id"])
    from ai_council.cycle import dump_live

    print("live:", dump_live(result, case=case))


def _cmd_verify() -> None:
    """Harmless REAL probe of every agent (fresh, bypasses cache)."""
    for name in agent_cli.load_agents_config():
        result = agent_cli.probe_agent(name, force=True)
        print(
            f"{name}: status={result.get('status')} model={result.get('model')} "
            f"cli={result.get('cli')} duration={result.get('duration_s')}s "
            f"rc={result.get('returncode')}"
        )
        if result.get("status") == "AVAILABLE":
            print("  reply: OK")
        elif result.get("error"):
            print(f"  error: {result.get('error')}")


def _cmd_force_cycle() -> None:
    try:
        proc = subprocess.run(
            [sys.executable, str(BOT / "scripts" / "research_fast_watcher.py"), "--once"],
            capture_output=True, text=True, timeout=1500,
        )
        print(f"returncode={proc.returncode}")
        print((proc.stdout or "").strip().splitlines()[-12:])
        if proc.stderr:
            print((proc.stderr or "").strip().splitlines()[-6:])
    except subprocess.TimeoutExpired:
        print("watcher cycle exceeded 1500s; it continues in the background task")


def _cmd_watch() -> None:
    from scripts.aegis_council_watch import render

    print(render())


_COMMANDS = {
    "status": lambda args: _cmd_status(),
    "cases": lambda args: _cmd_cases(),
    "case": lambda args: _cmd_case(args[0] if args else ""),
    "ask": lambda args: _cmd_ask(args[0] if args else "", " ".join(args[1:])),
    "ask-all": lambda args: _cmd_ask_all(" ".join(args)),
    "round": _cmd_round,
    "verify": lambda args: _cmd_verify(),
    "force-cycle": lambda args: _cmd_force_cycle(),
    "watch": lambda args: _cmd_watch(),
}


def main() -> int:
    if len(sys.argv) > 1:  # one-shot: execute the given command and exit
        parts = shlex.split(" ".join(sys.argv[1:]))
        cmd = parts[0].lower()
        handler = _COMMANDS.get(cmd)
        if handler is None:
            print(f"unknown command: {cmd}")
            return 1
        try:
            handler(parts[1:])
        except Exception as exc:
            print(f"error: {exc}")
        return 0
    print("AEGIS council console. Commands:", ", ".join(sorted(_COMMANDS)))
    while True:
        try:
            line = input("council> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not line:
            continue
        parts = shlex.split(line)
        cmd = parts[0].lower()
        if cmd in {"quit", "exit", "q"}:
            return 0
        if cmd in {"help", "h"}:
            print(__doc__)
            continue
        handler = _COMMANDS.get(cmd)
        if handler is None:
            print(f"unknown command: {cmd}")
            continue
        try:
            handler(parts[1:])
        except Exception as exc:  # console never crashes on one bad command
            print(f"error: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())