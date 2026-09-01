"""Narang's observable relationship-shift warning (Inside the Black Box, ch. 10)."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, number, values

ALGORITHM_ID = "narang_regime_change_warning"
SOURCES = ("Rishi K. Narang — Inside the Black Box",)
KEYS = (
    "side",
    "narang_relationship_current",
    "narang_relationship_baseline",
    "narang_relationship_shift_limit",
    "narang_regime_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(
        first(state, "narang_regime_data_provenance"),
        accepted=("observed", "measured", "historical", "replay"),
    ):
        missing.append("narang_regime_data_provenance")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    current = number(first(state, "narang_relationship_current"))
    baseline = number(first(state, "narang_relationship_baseline"))
    limit = number(first(state, "narang_relationship_shift_limit"))
    if current is None or baseline is None or limit is None or limit < 0.0:
        result["narang_regime_action"] = "INVALID_REGIME_INPUT"
        result["reasons"] = ["current and baseline relationship metrics must be finite with a nonnegative shift limit"]
        return result

    shift = current - baseline
    result.update({
        "narang_relationship_shift": shift,
        "narang_relationship_current": current,
        "narang_relationship_baseline": baseline,
        "narang_relationship_shift_limit": limit,
        "directional_claim": False,
    })
    if abs(shift) > limit:
        result["narang_regime_action"] = "REGIME_CHANGE_ALERT"
        result["reasons"] = ["the observed relationship moved beyond its explicit baseline limit"]
    else:
        result["narang_regime_action"] = "REGIME_WITHIN_BASELINE"
        result["reasons"] = ["the observed relationship remains within its explicit baseline limit"]
    return result
