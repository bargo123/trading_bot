from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_yaml(path: Path) -> dict[str, Any]:
    import yaml

    with Path(path).open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def ensure_dirs(root: Path | None = None) -> Path:
    root = root or project_root()
    for rel in [
        "books",
        "extracted",
        "cleaned",
        "docs/trading/books",
        "reports",
        "tests",
    ]:
        (root / rel).mkdir(parents=True, exist_ok=True)
    return root


def save_json(path: Path, data: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")
