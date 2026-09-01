"""Van Tharp expectancy per initial-risk unit (R) perspective."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, number, values

ALGORITHM_ID = "tharp_r_multiple_expectancy"
SOURCES = ("Van K. Tharp — Trade Your Way to Financial Freedom",)
KEYS = (
    "tharp_win_probability",
    "tharp_average_win_r",
    "tharp_average_loss_r",
    "tharp_cost_r",
    "tharp_expectancy_sample_n",
    "tharp_expectancy_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("net_expectancy_per_r",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    result["directional_claim"] = False
    provenance = first(state, "tharp_expectancy_data_provenance")
    p_win = number(first(state, "tharp_win_probability"))
    avg_win = number(first(state, "tharp_average_win_r"))
    avg_loss = number(first(state, "tharp_average_loss_r"))
    cost = number(first(state, "tharp_cost_r"))
    sample_n = number(first(state, "tharp_expectancy_sample_n"))
    if not explicitly_observed(provenance, accepted=("observed", "measured", "timestamped", "journal")):
        result["tharp_expectancy_assessment"] = "PROVENANCE_MISSING"
        result["warnings"] = ["expectancy is not supported by observed chronological net outcomes"]
        return result
    if (
        p_win is None or not 0 <= p_win <= 1
        or avg_win is None or avg_win <= 0
        or avg_loss is None or avg_loss <= 0
        or cost is None or cost < 0
        or sample_n is None or sample_n <= 0
    ):
        result["tharp_expectancy_assessment"] = "INVALID_EXPECTANCY_INPUTS"
        result["reasons"] = ["probability, win/loss R multiples, cost, and sample size are invalid"]
        return result
    expectancy = p_win * avg_win - (1.0 - p_win) * avg_loss - cost
    result["tharp_expectancy_per_r"] = expectancy
    result["tharp_expectancy_sample_n"] = int(sample_n)
    result["tharp_expectancy_assessment"] = "POSITIVE_EXPECTANCY" if expectancy > 0 else "NON_POSITIVE_EXPECTANCY"
    result["reasons"] = ["expectancy is calculated as win probability times average win R minus loss probability times average loss R and measured cost R"]
    return result
