"""AI Council report paths (live terminal + latest summary)."""
from __future__ import annotations

from pathlib import Path

REPORTS = Path(__file__).resolve().parents[1] / "reports" / "council"
LIVE_JSONL = REPORTS / "live.jsonl"
LATEST_MD = REPORTS / "latest.md"