"""Intel research helpers around CORE_STRATEGY_V1.

Keep the package boundary light.  Transport-only contracts, replay, and
broker-lifecycle imports must not eagerly load the pandas-backed decision
engine just because they live under ``aegis.intel``.
"""
from __future__ import annotations

from typing import Any


def intel_allows(*args: Any, **kwargs: Any) -> Any:
    from aegis.intel.decide import intel_allows as _intel_allows

    return _intel_allows(*args, **kwargs)


def intel_decision(*args: Any, **kwargs: Any) -> Any:
    from aegis.intel.decide import intel_decision as _intel_decision

    return _intel_decision(*args, **kwargs)


def last_intel(*args: Any, **kwargs: Any) -> Any:
    from aegis.intel.decide import last_intel as _last_intel

    return _last_intel(*args, **kwargs)


def quality_score(*args: Any, **kwargs: Any) -> Any:
    from aegis.intel.score import quality_score as _quality_score

    return _quality_score(*args, **kwargs)


__all__ = ["intel_allows", "intel_decision", "last_intel", "quality_score"]
