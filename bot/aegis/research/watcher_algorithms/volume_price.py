"""Volume-price effort/result algorithm."""
from __future__ import annotations
from ._common import base, direction, explicitly_observed, strings, values, with_direction

ALGORITHM_ID = "volume_price"
SOURCES = ("Anna Coulling — A Complete Guide to Volume Price Analysis", "Alexander Elder — The New Trading for a Living", "Jean-Philippe Bouchaud — Trades, Quotes and Prices")
KEYS = ("volume", "volume_ratio", "relative_volume", "tick_volume", "bar_range", "price_change", "effort_result")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return base(ALGORITHM_ID, state, SOURCES, KEYS, applicability="MISSING_DATA", view="MISSING_DATA", missing_inputs=("volume_and_price_result",))
    text = " ".join(str(value).lower() for _, value in found)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    volume_context = state.get("volume_context")
    volume_source = volume_context.get("source") if isinstance(volume_context, dict) else None
    if not explicitly_observed(volume_source, accepted=("real", "volume", "traded")):
        result["warnings"] = ["tick_activity_proxy is not traded volume; volume conclusions are provisional"]
        result["view"] = "WAIT"
        result["reasons"] = ["volume-price direction requires real traded-volume provenance"]
        return result
    if any(token in text for token in ("absorption", "narrow spread", "effort without result")):
        result["view"] = "WAIT"
        result["reasons"] = ["volume effort is not producing a commensurate price result"]
        return result
    signal = direction(strings(state, "price_change", "effort_result"))
    if signal:
        return with_direction(result, state, signal, "volume and price-result direction agree")
    result["view"] = "WAIT"
    result["reasons"] = ["volume exists but its directional price result is not explicit"]
    return result
