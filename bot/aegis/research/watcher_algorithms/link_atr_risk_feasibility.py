"""Link's ATR-based loss-feasibility check (High Probability Trading, ch. 9)."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, number, values


ALGORITHM_ID = "link_atr_risk_feasibility"
SOURCES = ("Marcel Link — High Probability Trading",)
KEYS = (
    "link_atr_value",
    "link_stop_distance",
    "link_max_atr_risk_fraction",
    "link_atr_risk_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    provenance = first(state, "link_atr_risk_data_provenance")
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(provenance, accepted=("observed", "measured", "historical", "replay")):
        missing.append("link_atr_risk_data_provenance")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    atr = number(first(state, "link_atr_value"))
    stop_distance = number(first(state, "link_stop_distance"))
    fraction = number(first(state, "link_max_atr_risk_fraction"))
    if atr is None or stop_distance is None or fraction is None or atr <= 0.0 or stop_distance <= 0.0 or not 0.0 < fraction <= 1.0:
        result["link_atr_risk_assessment"] = "INVALID_ATR_RISK_INPUT"
        result["reasons"] = ["ATR, structural stop distance, and the maximum ATR risk fraction must be positive finite observations"]
        return result

    maximum = atr * fraction
    result.update({
        "link_atr_value": atr,
        "link_stop_distance": stop_distance,
        "link_max_atr_risk_fraction": fraction,
        "link_max_stop_distance": maximum,
        "directional_claim": False,
    })
    if stop_distance > maximum:
        result["link_atr_risk_assessment"] = "STOP_TOO_FAR_SKIP"
        result["reasons"] = ["the technically correct stop exceeds the supplied risk fraction of ATR, so the setup is skipped"]
    else:
        result["link_atr_risk_assessment"] = "RISK_FEASIBLE"
        result["reasons"] = ["the structural stop fits within the supplied ATR-based loss budget"]
    return result
