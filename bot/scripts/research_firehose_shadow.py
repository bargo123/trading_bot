#!/usr/bin/env python3
"""Observe the same completed bars as CORE firehose. Never places orders.

This process is separate from run_broker_paper.py. It reads config for the
symbol list and bar convention only. It does not mutate YAML, restart the
runner, send MT5 orders, or shut down the terminal.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

BOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BOT))

from aegis.config import configured_symbols, load_config  # noqa: E402
from aegis.intel.paths import INTEL_DIR  # noqa: E402
from aegis.paper_control import ProcessLock  # noqa: E402
from aegis.research.analogues import load_analogue_index  # noqa: E402
from aegis.research.intelligent_champion import (  # noqa: E402
    load_intelligent_champion,
    strategy_from_champion,
)
from aegis.research.knowledge import load_knowledge_table  # noqa: E402
from aegis.research.market_state import MarketStateCache  # noqa: E402
from aegis.research.shadow_firehose import aligned_shadow_rows, scoreboard_markdown  # noqa: E402
from aegis.research.shadow_observe import ShadowBook, scan_symbol  # noqa: E402

SHADOW_LOCK = BOT / "reports" / "research_firehose_shadow.lock"
SHADOW_JSONL = BOT / "reports" / "research" / "shadow_decisions.jsonl"
SHADOW_MD = BOT / "reports" / "research" / "firehose_vs_firehose.md"
SHADOW_HEARTBEAT = BOT / "reports" / "research" / "shadow_heartbeat.json"


def write_scoreboard(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(scoreboard_markdown(rows), encoding="utf-8")
    jsonl = path.with_suffix(".jsonl")
    jsonl.write_text("".join(json.dumps(row, default=str) + "\n" for row in rows), encoding="utf-8")


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, default=str) + "\n")


def write_heartbeat(payload: dict[str, Any]) -> None:
    SHADOW_HEARTBEAT.parent.mkdir(parents=True, exist_ok=True)
    SHADOW_HEARTBEAT.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def run_live(cfg: dict[str, Any], *, once: bool, poll: float, jsonl_path: Path, md_path: Path) -> int:
    from aegis.engines import create_engine

    lock = ProcessLock(SHADOW_LOCK)
    if not lock.try_acquire():
        raise SystemExit(f"another shadow observer holds {SHADOW_LOCK}")
    engine = create_engine({**cfg, "allow_live": False})
    if not hasattr(engine, "connect_readonly"):
        lock.release()
        raise SystemExit("engine lacks read-only attach")
    engine.connect_readonly()
    symbols = configured_symbols(cfg)
    knowledge = load_knowledge_table(INTEL_DIR / "knowledge_table.json")
    strategy = strategy_from_champion(load_intelligent_champion())
    analogue_path = Path(str(cfg.get("analogue_index_path") or (INTEL_DIR / "analogue_index.json")))
    analogue_records = load_analogue_index(analogue_path)
    book = ShadowBook()
    cache = MarketStateCache()
    last_bar_time: dict[str, pd.Timestamp] = {}
    existing = load_jsonl(jsonl_path)
    for row in existing:
        symbol = str(row.get("symbol") or "")
        bar_time = row.get("bar_time")
        if not symbol or not bar_time:
            continue
        ts = pd.Timestamp(bar_time)
        prev = last_bar_time.get(symbol)
        if prev is None or ts > prev:
            last_bar_time[symbol] = ts
    session_rows: list[dict[str, Any]] = list(existing)
    new_this_process = 0
    try:
        while True:
            cycle_n = 0
            for symbol in symbols:
                try:
                    row = scan_symbol(
                        engine=engine,
                        symbol=symbol,
                        cfg=cfg,
                        last_bar_time=last_bar_time.get(symbol),
                        knowledge_rows=knowledge,
                        strategy=strategy,
                        book=book,
                        cache=cache,
                        analogue_records=analogue_records,
                    )
                except Exception as exc:
                    write_heartbeat(
                        {
                            "status": "symbol_error",
                            "symbol": symbol,
                            "error": str(exc),
                            "placed_orders": False,
                            "pid": __import__("os").getpid(),
                            "ts_utc": datetime.now(timezone.utc).isoformat(),
                        }
                    )
                    continue
                if row is None:
                    continue
                if row.get("placed_orders"):
                    raise SystemExit("shadow observer refused a row with placed_orders true")
                last_bar_time[symbol] = pd.Timestamp(row["bar_time"])
                append_jsonl(jsonl_path, row)
                session_rows.append(row)
                new_this_process += 1
                cycle_n += 1
            md_path.parent.mkdir(parents=True, exist_ok=True)
            md_path.write_text(scoreboard_markdown(session_rows[-10_000:]), encoding="utf-8")
            write_heartbeat(
                {
                    "status": "observing",
                    "pid": __import__("os").getpid(),
                    "ts_utc": datetime.now(timezone.utc).isoformat(),
                    "symbols": symbols,
                    "bars_this_process": new_this_process,
                    "bars_on_disk": len(session_rows),
                    "bars_this_cycle": cycle_n,
                    "placed_orders": False,
                    "allow_live": False,
                    "inherited_strategy": None if strategy is None else strategy.strategy_id,
                    "knowledge_rows": len(knowledge),
                }
            )
            if once:
                break
            time.sleep(poll)
    finally:
        try:
            lock.release()
        except Exception:
            pass
        write_heartbeat(
            {
                "status": "stopped",
                "pid": __import__("os").getpid(),
                "ts_utc": datetime.now(timezone.utc).isoformat(),
                "placed_orders": False,
            }
        )
        # Readonly attach: never disconnect/shutdown. That can kill the live paper runner.
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Shadow intelligent firehose (no orders)")
    parser.add_argument("--config", required=True)
    parser.add_argument("--old-jsonl", type=Path)
    parser.add_argument("--new-jsonl", type=Path)
    parser.add_argument("--out", type=Path, default=SHADOW_MD)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll", type=float)
    parser.add_argument("--jsonl", type=Path, default=SHADOW_JSONL)
    args = parser.parse_args()
    cfg = load_config(args.config)
    if args.live:
        poll = float(args.poll) if args.poll is not None else float(cfg.get("poll_seconds", 1) or 1)
        return run_live(cfg, once=args.once, poll=poll, jsonl_path=args.jsonl, md_path=args.out)
    if args.old_jsonl is None or args.new_jsonl is None:
        raise SystemExit("offline mode requires --old-jsonl and --new-jsonl (or pass --live)")
    symbols = set(configured_symbols(cfg))
    old_rows = load_jsonl(args.old_jsonl)
    new_rows = load_jsonl(args.new_jsonl)
    if any(str(row.get("symbol")) not in symbols for row in old_rows + new_rows):
        raise SystemExit("shadow rows contain a symbol not in the firehose config")
    rows = aligned_shadow_rows(old_rows, new_rows)
    if any(row["placed_orders"] for row in rows):
        raise SystemExit("shadow comparison must keep placed_orders false")
    write_scoreboard(rows, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
