"""Named data capabilities. Missing feeds are never fabricated."""
from __future__ import annotations

from typing import Any

# Feeds we do not have. Values must stay False so require_capability() fails closed.
UNAVAILABLE = {
    "mt5_l2": False,
    "news_calendar": False,
    "news_headline_sentiment": False,
    "cot": False,
    "futures_oi": False,
    "jansen_ml": False,
    "partial_fill_state": False,
    "cross_asset": False,
    "queue_position": False,
    "exchange_volume": False,
    "johnson_dma": False,
}

# Coded research proxies. Not full-book systems; not live YAML.
RESEARCH_PROXY = {
    "gann_cycles": True,
    "prado_purged_cv": True,
    "prado_meta_label": True,
    "six_book_stack": True,
    "johnson_spread_gate": True,
}


class CapabilityUnavailable(RuntimeError):
    """Requested feed or model is not present in this environment."""


def capabilities_snapshot() -> dict[str, Any]:
    return {**UNAVAILABLE, **RESEARCH_PROXY}


def require_capability(name: str) -> None:
    cap = capabilities_snapshot()
    if not cap.get(name):
        raise CapabilityUnavailable(f"{name} is unavailable; not fabricated")
