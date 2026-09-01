"""MT5 depth. Retail depth is not exchange queue position and is unavailable here."""
from __future__ import annotations

from aegis.research.capabilities import require_capability


def load_l2() -> None:
    require_capability("mt5_l2")
