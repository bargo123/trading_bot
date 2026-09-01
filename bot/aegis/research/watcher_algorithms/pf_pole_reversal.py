"""Jeremy du Plessis' Point-and-Figure high/low pole reversal perspective."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "pf_pole_reversal"
SOURCES = ("Jeremy du Plessis — The Definitive Guide to Point and Figure",)
SOURCE_PAGES = "pp. 155-164"
KEYS = (
    "pf_box_reversal",
    "pf_pole_type",
    "pf_initial_column_boxes",
    "pf_reversal_column_boxes",
    "pf_reversal_percent",
    "pf_reversal_confirmed",
    "pf_data_provenance",
)


def _truthy(value):
    return value is True or normalized_status(value) in {"true", "yes", "confirmed", "observed", "valid"}


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    provenance = normalized_status(first(state, "pf_data_provenance"))
    if not provenance or any(token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")):
        missing.append("pf_data_provenance")
    missing = list(dict.fromkeys(missing))
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    if normalized_status(first(state, "pf_box_reversal")) != "3 box":
        result["view"] = "WAIT"
        result["reasons"] = ["the documented pole strategy uses the three-box chart"]
        return result
    pole = normalized_status(first(state, "pf_pole_type"))
    if pole not in {"high", "low"}:
        result["view"] = "WAIT"
        result["reasons"] = ["pole type must be an observed high pole or low pole"]
        return result
    initial = number(first(state, "pf_initial_column_boxes"))
    reversal = number(first(state, "pf_reversal_column_boxes"))
    reported_percent = number(first(state, "pf_reversal_percent"))
    if initial is None or initial <= 0 or reversal is None or reversal <= 0 or reported_percent is None:
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["finite_positive_pole_columns_and_retracement"]
        result["reasons"] = ["pole completion requires measured initial and reversal columns"]
        return result
    measured_percent = reversal / initial * 100.0
    if abs(measured_percent - reported_percent) > 1.0:
        result["view"] = "WAIT"
        result["reasons"] = ["reported pole retracement does not match the observed box columns"]
        return result
    if reported_percent < 50.0:
        result["view"] = "WAIT"
        result["reasons"] = ["the documented early pole signal requires at least a fifty-percent retracement"]
        return result
    if not _truthy(first(state, "pf_reversal_confirmed")):
        result["view"] = "WAIT"
        result["reasons"] = ["the pole reversal column is not confirmed"]
        return result
    signal = "SELL" if pole == "high" else "BUY"
    result["pf_reversal_percent"] = reported_percent
    result["pf_pole_geometry"] = {
        "initial_column_boxes": initial,
        "reversal_column_boxes": reversal,
    }
    return with_direction(result, state, signal, "confirmed Point-and-Figure pole reversal")
