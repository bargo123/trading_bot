"""The 10XROI source's high-R parabolic/weekly-level warning."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, number, values, volman_truth

ALGORITHM_ID = "thomas_parabolic_exhaustion_exit"
SOURCES = ("The 10XROI Trading System",)
KEYS = (
    "thomas_trade_in_profit",
    "thomas_r_multiple",
    "thomas_parabolic_move",
    "thomas_weekly_level_near",
    "thomas_parabolic_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(first(state, "thomas_parabolic_data_provenance"), accepted=("observed", "measured", "timestamped")):
        missing.append("thomas_parabolic_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    result["directional_claim"] = False
    r_multiple = number(first(state, "thomas_r_multiple"))
    if r_multiple is None or r_multiple < 0:
        result["thomas_parabolic_action"] = "WAIT_INVALID_R"
        result["reasons"] = ["the observed R multiple must be finite and non-negative"]
        return result
    if not volman_truth(first(state, "thomas_trade_in_profit")):
        result["thomas_parabolic_action"] = "WAIT_NOT_IN_PROFIT"
        result["reasons"] = ["the source warning applies only to a profitable high-R position"]
        return result
    if r_multiple < 8.0 or not volman_truth(first(state, "thomas_parabolic_move")) or not volman_truth(first(state, "thomas_weekly_level_near")):
        result["thomas_parabolic_action"] = "CONTINUE_SOURCE_TARGET"
        result["reasons"] = ["the 8R threshold, parabolic move, and nearby weekly level are not all observed"]
        return result
    result["thomas_parabolic_action"] = "EXIT_END_OF_PARABOLIC_RUN"
    result["thomas_management_action"] = "RESEARCH_EXIT_WARNING"
    result["reasons"] = ["the source warns against allowing a high-R parabolic run into major weekly support/resistance to reverse"]
    return result
