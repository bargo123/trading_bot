"""Research-system paths. Isolated from the paper-runner lock."""
from __future__ import annotations

from pathlib import Path

BOT_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BOT_ROOT.parent
RESEARCH_DIR = BOT_ROOT / "research"
DEFAULT_REGISTRY = RESEARCH_DIR / "experiments.sqlite"
DEFAULT_BOOKS_INDEX = RESEARCH_DIR / "books_index.sqlite"


def ensure_research_dirs() -> None:
    RESEARCH_DIR.mkdir(parents=True, exist_ok=True)
