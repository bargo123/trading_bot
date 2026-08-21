"""Append-only outcome memory for Intelligent Firehose. Never places orders."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

DEFAULT_OUTCOME_PATH = Path(__file__).resolve().parents[2] / "intel" / "outcome_log.jsonl"

EVENT_TYPE_EXIT = "position_exit"


def is_exit_row(row: Mapping[str, Any]) -> bool:
    """Defect 12: explicit schema first, safe backward-compatible inference.

    New rows carry ``event_type: "position_exit"``. Historical rows are an exit
    when they say so explicitly (``is_exit``) or when the action/reason proves a
    close (action in {exit, reduce} or a reconcile/mt5_deal row with a pnl).
    """
    if str(row.get("event_type") or "") == EVENT_TYPE_EXIT:
        return True
    if "is_exit" in row:
        return bool(row.get("is_exit"))
    action = str(row.get("action") or "").lower()
    if action in {"exit", "reduce"}:
        return True
    source = str(row.get("source") or "")
    if source in {"reconcile", "mt5_deal"} and row.get("pnl") is not None:
        return True
    return False


def append_outcome(row: Mapping[str, Any], path: Path | None = None) -> None:
    target = Path(path) if path is not None else DEFAULT_OUTCOME_PATH
    payload = dict(row)
    payload.setdefault("ts_utc", datetime.now(timezone.utc).isoformat())
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, default=str) + "\n")
