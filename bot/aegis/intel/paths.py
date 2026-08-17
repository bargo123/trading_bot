"""Paths for the intel research loop. Separate from the live paper lock."""
from __future__ import annotations

from pathlib import Path

BOT_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BOT_ROOT.parent
INTEL_DIR = BOT_ROOT / "intel"
FROZEN_V1 = Path(__file__).resolve().parent / "frozen_v1.json"


def ensure_intel_dirs() -> Path:
    INTEL_DIR.mkdir(parents=True, exist_ok=True)
    (INTEL_DIR / "loss_db").mkdir(parents=True, exist_ok=True)
    (INTEL_DIR / "win_db").mkdir(parents=True, exist_ok=True)
    return INTEL_DIR
