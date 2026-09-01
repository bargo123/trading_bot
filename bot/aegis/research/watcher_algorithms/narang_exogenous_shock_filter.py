"""Narang's exogenous-shock warning for unexplained market moves."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, number, normalized_status, values

ALGORITHM_ID = "narang_exogenous_shock_filter"
SOURCES = ("Rishi K. Narang — Inside the Black Box",)
KEYS = (
    "side",
    "narang_observed_move",
    "narang_model_expected_move",
    "narang_unexplained_move_limit",
    "narang_external_event_flag",
    "narang_shock_data_provenance",
)


def _boolean(value):
    if isinstance(value, bool):
        return value
    normalized = normalized_status(value)
    if normalized in {"true", "yes", "1", "present", "confirmed"}:
        return True
    if normalized in {"false", "no", "0", "absent", "clear"}:
        return False
    return None


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(
        first(state, "narang_shock_data_provenance"),
        accepted=("observed", "measured", "historical", "replay"),
    ):
        missing.append("narang_shock_data_provenance")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    observed = number(first(state, "narang_observed_move"))
    expected = number(first(state, "narang_model_expected_move"))
    limit = number(first(state, "narang_unexplained_move_limit"))
    event = _boolean(first(state, "narang_external_event_flag"))
    if observed is None or expected is None or limit is None or limit < 0.0 or event is None:
        result["narang_shock_action"] = "INVALID_SHOCK_INPUT"
        result["reasons"] = ["shock filtering needs finite moves, a nonnegative limit, and an explicit event flag"]
        return result

    unexplained = abs(observed - expected)
    result.update({
        "narang_unexplained_move": unexplained,
        "narang_external_event_flag": event,
        "directional_claim": False,
    })
    if event or unexplained > limit:
        result["narang_shock_action"] = "SHOCK_ABSTAIN"
        result["reasons"] = ["an external event or an unexplained move beyond the explicit limit is present"]
    else:
        result["narang_shock_action"] = "SHOCK_CLEAR"
        result["reasons"] = ["no external event and no unexplained move beyond the explicit limit is present"]
    return result
