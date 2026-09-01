"""Paths for the intel research loop. Separate from the live paper lock."""
from __future__ import annotations

from pathlib import Path

BOT_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BOT_ROOT.parent
INTEL_DIR = BOT_ROOT / "intel"
FROZEN_V1 = Path(__file__).resolve().parent / "frozen_v1.json"


def resolve_bot_path(value: str | Path | None, default: Path) -> Path:
    """Resolve a configured path against the bot directory, never the CWD.

    Demo configs carry relative paths such as ``intel/analogue_index.json``. Taken
    literally those resolve against the current working directory, so launching the
    runner from the repository root pointed the brain at a nonexistent file and it
    loaded zero analogues and zero book knowledge without complaint - every decision
    was then made on no evidence at all. Anchoring to ``BOT_ROOT`` makes the
    configured paths mean what they look like they mean.
    """
    if value is None or str(value).strip() == "":
        return default
    path = Path(str(value)).expanduser()
    if path.is_absolute():
        return path
    return (BOT_ROOT / path).resolve()


def ensure_intel_dirs() -> Path:
    INTEL_DIR.mkdir(parents=True, exist_ok=True)
    (INTEL_DIR / "loss_db").mkdir(parents=True, exist_ok=True)
    (INTEL_DIR / "win_db").mkdir(parents=True, exist_ok=True)
    return INTEL_DIR
