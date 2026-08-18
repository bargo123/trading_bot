"""Append-only outcome memory for Intelligent Firehose. Never places orders."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

DEFAULT_OUTCOME_PATH = Path(__file__).resolve().parents[2] / "intel" / "outcome_log.jsonl"


def append_outcome(row: Mapping[str, Any], path: Path | None = None) -> None:
    target = Path(path) if path is not None else DEFAULT_OUTCOME_PATH
    payload = dict(row)
    payload.setdefault("ts_utc", datetime.now(timezone.utc).isoformat())
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, default=str) + "\n")
