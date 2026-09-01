"""MAE comparison between a live state and observed winning trades."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, number, values

ALGORITHM_ID = "tharp_mae_winner_band"
SOURCES = ("Van K. Tharp — Trade Your Way to Financial Freedom",)
KEYS = (
    "tharp_current_mae_r",
    "tharp_winner_mae_p95_r",
    "tharp_initial_stop_r",
    "tharp_mae_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("observed_mae_distribution",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    result["directional_claim"] = False
    provenance = first(state, "tharp_mae_data_provenance")
    current = number(first(state, "tharp_current_mae_r"))
    winner_band = number(first(state, "tharp_winner_mae_p95_r"))
    initial_stop = number(first(state, "tharp_initial_stop_r"))
    if not explicitly_observed(provenance, accepted=("observed", "measured", "timestamped", "journal")):
        result["tharp_mae_assessment"] = "PROVENANCE_MISSING"
        result["warnings"] = ["MAE comparison is not supported by observed winner and loser outcomes"]
        return result
    if current is None or winner_band is None or initial_stop is None or min(current, winner_band) < 0 or initial_stop <= 0:
        result["tharp_mae_assessment"] = "INVALID_MAE_INPUTS"
        result["reasons"] = ["MAE and initial stop values must be finite, non-negative, and positive where required"]
        return result
    result["tharp_mae_distance_to_winner_band_r"] = winner_band - current
    if current <= winner_band:
        result["tharp_mae_assessment"] = "WITHIN_WINNER_BAND"
        result["reasons"] = ["current adverse excursion remains within the observed upper band of winning trades"]
    else:
        result["tharp_mae_assessment"] = "EXCEEDS_WINNER_BAND"
        result["warnings"] = ["current adverse excursion exceeds the observed winner band and warrants stop/entry review"]
        result["reasons"] = ["winning trades historically did not usually tolerate this much adverse excursion"]
    return result
