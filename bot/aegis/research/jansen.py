"""Jansen-style ML track. Disabled until a point-in-time model exists."""
from __future__ import annotations

from typing import Any

from aegis.research.capabilities import require_capability


def jansen_ml_predict(_features: dict[str, Any]) -> None:
    """Genuine ML inference is unavailable. Local `jansen_score` is a heuristic, not this."""
    require_capability("jansen_ml")
