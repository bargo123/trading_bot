"""Chan's augmented Dickey-Fuller mean-reversion diagnostic.

The ADF result is a statistical prerequisite for a mean-reversion study, not
an entry signal.  It requires an explicitly observed chronological series and
keeps a non-rejected null separate from evidence supporting mean reversion.
"""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, number, values

ALGORITHM_ID = "chan_adf_mean_reversion"
SOURCES = ("Ernest P. Chan — Algorithmic Trading: Winning Strategies and Their Rationale",)
KEYS = (
    "chan_adf_t_statistic",
    "chan_adf_critical_value",
    "chan_adf_coefficient",
    "chan_adf_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    statistic = number(first(state, "chan_adf_t_statistic"))
    critical = number(first(state, "chan_adf_critical_value"))
    coefficient = number(first(state, "chan_adf_coefficient"))
    missing = [
        key for key, value in (
            ("chan_adf_t_statistic", statistic),
            ("chan_adf_critical_value", critical),
            ("chan_adf_coefficient", coefficient),
        ) if value is None
    ]
    if not explicitly_observed(first(state, "chan_adf_data_provenance"), accepted=("observed", "measured", "replay")):
        missing.append("chan_adf_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    result["directional_claim"] = False
    if critical >= 0:
        result["view"] = "MISSING_DATA"
        result["reasons"] = ["ADF critical values for this test must be negative"]
        return result
    if coefficient >= 0:
        result["chan_adf_assessment"] = "NON_MEAN_REVERTING"
        result["reasons"] = ["the estimated level coefficient is not negative"]
    elif statistic < critical:
        result["chan_adf_assessment"] = "MEAN_REVERSION_SUPPORTED"
        result["reasons"] = ["the negative ADF statistic exceeds the negative critical threshold"]
    else:
        result["chan_adf_assessment"] = "NEGATIVE_BUT_NOT_REJECTED"
        result["reasons"] = ["the coefficient is negative but the unit-root null was not rejected"]
    result["chan_adf_t_statistic"] = statistic
    result["chan_adf_critical_value"] = critical
    result["chan_adf_coefficient"] = coefficient
    return result

