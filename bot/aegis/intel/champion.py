"""Champion / challenger records. Never overwrite champion on a failed test."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aegis.intel.paths import INTEL_DIR, ensure_intel_dirs


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def load_champion() -> dict[str, Any] | None:
    p = INTEL_DIR / "champion.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def save_champion(payload: dict[str, Any]) -> Path:
    ensure_intel_dirs()
    path = INTEL_DIR / "champion.json"
    payload = dict(payload)
    payload["role"] = "CHAMPION"
    payload["updated_utc"] = datetime.now(timezone.utc).isoformat()
    _write(path, payload)
    return path


def save_challenger(payload: dict[str, Any]) -> Path:
    ensure_intel_dirs()
    path = INTEL_DIR / "challenger.json"
    payload = dict(payload)
    payload["role"] = "CHALLENGER"
    payload["updated_utc"] = datetime.now(timezone.utc).isoformat()
    _write(path, payload)
    return path


def append_experiment(row: dict[str, Any]) -> Path:
    ensure_intel_dirs()
    path = INTEL_DIR / "experiments.jsonl"
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, default=str) + "\n")
    return path
