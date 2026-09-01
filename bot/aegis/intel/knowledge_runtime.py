"""Load compiled book hypotheses at runtime. No research imports."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

DEFAULT_KNOWLEDGE_PATH = Path(__file__).resolve().parents[2] / "intel" / "knowledge_table.json"


def load_knowledge_rows(path: Path | None = None) -> list[dict[str, Any]]:
    target = Path(path) if path is not None else DEFAULT_KNOWLEDGE_PATH
    if not target.is_file():
        return []
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    rows = payload.get("rows") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def match_knowledge(
    rows: Sequence[Mapping[str, Any]],
    *,
    regime: str,
    structure: str,
    limit: int = 6,
) -> list[dict[str, Any]]:
    tags = {str(regime).lower(), str(structure).lower()}
    tags.discard("")
    tags.discard("unknown")
    tags.discard("none")
    scored: list[tuple[int, dict[str, Any]]] = []
    for row in rows:
        blob = " ".join(
            [
                str(row.get("strategy_family") or ""),
                " ".join(str(item) for item in (row.get("concepts") or [])),
                str(row.get("setup") or ""),
            ]
        ).lower()
        overlap = sum(1 for tag in tags if tag in blob)
        if overlap:
            scored.append((overlap, dict(row)))
    scored.sort(key=lambda item: (-item[0], str(item[1].get("filename") or "")))
    return [row for _, row in scored[:limit]]
