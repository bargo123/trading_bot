"""Read-only research observation. Never places orders or starts a runner."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aegis.research.champion import ChampionStore
from aegis.research.registry import ExperimentRegistry


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def observe_cycle(
    *,
    heartbeat: dict[str, Any] | None,
    champion: dict[str, Any] | None,
    registry: ExperimentRegistry | None = None,
) -> dict[str, Any]:
    rows = registry.all_rows() if registry is not None else []
    rejects = [r for r in rows if str(r.get("status")) == "rejected"][-8:]
    hb = heartbeat or {}
    return {
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "equity": hb.get("equity"),
        "open": hb.get("open", hb.get("positions", 0)),
        "halt": hb.get("halt") or hb.get("risk_halt"),
        "champion_id": None if champion is None else champion.get("id"),
        "recent_rejects": [r.get("id") for r in rejects],
        "placed_orders": False,
        "allow_live": False,
        "mt5_touched": False,
    }


def observe_from_paths(
    *,
    heartbeat_path: Path | None,
    db_path: Path,
) -> dict[str, Any]:
    hb = read_json(heartbeat_path) if heartbeat_path and Path(heartbeat_path).is_file() else {}
    store = ChampionStore(db_path)
    return observe_cycle(heartbeat=hb, champion=store.current(), registry=store.registry)
