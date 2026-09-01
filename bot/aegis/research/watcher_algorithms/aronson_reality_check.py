"""Aronson family-wise post-selection significance perspective."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, number, values, with_direction
from ._deprado_common import finite_series, provenance_ok

ALGORITHM_ID = "aronson_reality_check"
SOURCES = ("David Aronson — Evidence-Based Technical Analysis",)
KEYS = (
    "aronson_rule_direction",
    "aronson_observed_net_return",
    "aronson_null_net_returns",
    "aronson_rule_universe_n",
    "aronson_significance_level",
    "aronson_data_provenance",
)


def evaluate(state):
    observed = number(first(state, "aronson_observed_net_return"))
    null_returns = finite_series(state, "aronson_null_net_returns")
    universe_n = number(first(state, "aronson_rule_universe_n"))
    alpha = number(first(state, "aronson_significance_level"))
    direction = str(first(state, "aronson_rule_direction") or "").strip().upper()
    found = values(state, *KEYS)
    missing = []
    if observed is None:
        missing.append("aronson_observed_net_return")
    if null_returns is None or len(null_returns) < 20:
        missing.append("aronson_null_net_returns")
    if universe_n is None or universe_n < 1:
        missing.append("aronson_rule_universe_n")
    if alpha is None or not 0 < alpha < 1:
        missing.append("aronson_significance_level")
    if direction not in {"BUY", "SELL"}:
        missing.append("aronson_rule_direction")
    provenance = first(state, "aronson_data_provenance")
    if not explicitly_observed(provenance, accepted=("observed", "measured", "replay")) or not provenance_ok(provenance):
        missing.append("aronson_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))

    p_value = (1.0 + sum(value >= observed for value in null_returns)) / (len(null_returns) + 1.0)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    result["analysis_stage"] = "familywise_post_selection_validation"
    result["directional_claim"] = False
    result["aronson_reality_check_p_value"] = p_value
    result["aronson_null_sample_n"] = len(null_returns)
    result["aronson_rule_universe_n"] = universe_n
    result["aronson_significance_level"] = alpha
    result["aronson_observed_net_return"] = observed
    supported = observed > 0 and p_value <= alpha
    result["aronson_reality_check_assessment"] = "FAMILYWISE_SUPPORT" if supported else "FAMILYWISE_NOT_SUPPORTED"
    result["warnings"] = ["family-wise significance corrects selection bias; it is not a standalone live-entry gate"]
    if supported:
        result["directional_claim"] = True
        return with_direction(result, state, direction, "observed net return survives the supplied family null distribution")
    result["reasons"] = ["the selected rule does not beat the family null at the supplied significance level"]
    return result
