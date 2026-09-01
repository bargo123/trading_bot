"""Read-only effort/result perspective requiring real traded-volume evidence."""
from __future__ import annotations

from collections.abc import Mapping

from ._common import base, explicitly_confirmed, explicitly_observed, first, normalized_status, values, with_direction

ALGORITHM_ID = "volume_effort_result"
SOURCES = (
    "Anna Coulling — A Complete Guide to Volume Price Analysis",
    "Alexander Elder — The New Trading for a Living",
    "Barry Johnson — Algorithmic Trading and DMA",
)
KEYS = ("volume_context", "volume_data_provenance", "effort_result_direction", "vsa_signal", "volume_confirmation", "vsa_confirmation")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return base(ALGORITHM_ID, state, SOURCES, KEYS, applicability="MISSING_DATA", view="MISSING_DATA", missing_inputs=("volume_context", "effort_result"))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    volume_context = first(state, "volume_context")
    provenance = first(state, "volume_data_provenance", "volume_provenance")
    real_volume = isinstance(volume_context, Mapping) and volume_context.get("is_real_volume") is True
    real_volume = real_volume and explicitly_observed(
        provenance,
        accepted=("real traded volume", "exchange volume", "actual volume", "traded volume"),
    )
    if not real_volume:
        result["view"] = "WAIT"
        result["warnings"] = ["real_traded_volume_required"]
        result["reasons"] = ["tick activity or proxy volume cannot establish effort/result"]
        return result
    signal = normalized_status(first(state, "effort_result_direction", "vsa_signal"))
    confirmation = first(state, "volume_confirmation", "vsa_confirmation")
    if signal not in {"buy", "sell"} or not explicitly_confirmed(confirmation):
        result["view"] = "WAIT"
        result["reasons"] = ["real volume, directional effort/result, and explicit confirmation are required"]
        return result
    return with_direction(result, state, signal.upper(), "confirmed effort/result direction is supported by real traded volume")

