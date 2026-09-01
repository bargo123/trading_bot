"""Chan's Hurst-exponent stationarity diagnostic."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, normalized_status, number, values

ALGORITHM_ID = "chan_hurst_stationarity"
SOURCES = ("Ernest P. Chan — Algorithmic Trading: Winning Strategies and Their Rationale",)
KEYS = ("chan_hurst_exponent", "chan_hurst_null_rejected", "chan_hurst_data_provenance")


def _boolean(value):
    if isinstance(value, bool):
        return value
    label = normalized_status(value)
    if label in {"true", "yes", "rejected", "reject", "significant"}:
        return True
    if label in {"false", "no", "not rejected", "not significant"}:
        return False
    return None


def evaluate(state):
    found = values(state, *KEYS)
    hurst = number(first(state, "chan_hurst_exponent"))
    rejected = _boolean(first(state, "chan_hurst_null_rejected"))
    missing = [
        key for key, value in (
            ("chan_hurst_exponent", hurst),
            ("chan_hurst_null_rejected", rejected),
        ) if value is None
    ]
    if not explicitly_observed(first(state, "chan_hurst_data_provenance"), accepted=("observed", "measured", "replay")):
        missing.append("chan_hurst_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    result["directional_claim"] = False
    if not 0.0 <= hurst <= 1.0:
        result["view"] = "MISSING_DATA"
        result["reasons"] = ["Hurst exponent must be within [0, 1]"]
        return result
    if not rejected or abs(hurst - 0.5) < 1e-9:
        assessment = "RANDOM_WALK_NOT_REJECTED"
        reason = "the random-walk null was not rejected or the exponent is approximately 0.5"
    elif hurst < 0.5:
        assessment = "MEAN_REVERSION_SUPPORTED"
        reason = "a significant Hurst exponent below 0.5 indicates slower-than-random diffusion"
    else:
        assessment = "TRENDING_SUPPORTED"
        reason = "a significant Hurst exponent above 0.5 indicates persistent diffusion"
    result["chan_hurst_assessment"] = assessment
    result["chan_hurst_exponent"] = hurst
    result["reasons"] = [reason]
    return result

