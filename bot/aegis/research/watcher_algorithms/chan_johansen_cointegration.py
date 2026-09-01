"""Chan's Johansen rank/eigenvector cointegration diagnostic."""
from __future__ import annotations

from collections.abc import Sequence

from ._common import absent, base, explicitly_observed, first, number, values

ALGORITHM_ID = "chan_johansen_cointegration"
SOURCES = ("Ernest P. Chan — Algorithmic Trading: Winning Strategies and Their Rationale",)
KEYS = (
    "chan_johansen_statistic",
    "chan_johansen_critical_value",
    "chan_johansen_rank",
    "chan_johansen_series_n",
    "chan_johansen_best_eigenvalue",
    "chan_johansen_eigenvector",
    "chan_johansen_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    statistic = number(first(state, "chan_johansen_statistic"))
    critical = number(first(state, "chan_johansen_critical_value"))
    rank = number(first(state, "chan_johansen_rank"))
    series_n = number(first(state, "chan_johansen_series_n"))
    eigenvalue = number(first(state, "chan_johansen_best_eigenvalue"))
    eigenvector = first(state, "chan_johansen_eigenvector")
    missing = [
        key for key, value in (
            ("chan_johansen_statistic", statistic),
            ("chan_johansen_critical_value", critical),
            ("chan_johansen_rank", rank),
            ("chan_johansen_series_n", series_n),
            ("chan_johansen_best_eigenvalue", eigenvalue),
            ("chan_johansen_eigenvector", eigenvector),
        ) if value is None
    ]
    if not explicitly_observed(first(state, "chan_johansen_data_provenance"), accepted=("observed", "measured", "replay")):
        missing.append("chan_johansen_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    result["directional_claim"] = False
    if any(value != int(value) for value in (rank, series_n)) or series_n < 2 or rank < 0 or rank > series_n - 1:
        result["view"] = "MISSING_DATA"
        result["reasons"] = ["Johansen rank and series count are inconsistent"]
        return result
    if eigenvalue <= 0 or not isinstance(eigenvector, Sequence) or isinstance(eigenvector, (str, bytes, bytearray)) or len(eigenvector) != int(series_n):
        result["view"] = "MISSING_DATA"
        result["reasons"] = ["the strongest Johansen eigenvalue/eigenvector geometry is incomplete"]
        return result
    if any(number(item) is None for item in eigenvector):
        result["view"] = "MISSING_DATA"
        result["reasons"] = ["Johansen eigenvector contains a non-numeric component"]
        return result
    result["chan_johansen_rank"] = int(rank)
    result["chan_johansen_best_eigenvalue"] = eigenvalue
    result["chan_johansen_eigenvector"] = list(eigenvector)
    if rank > 0 and statistic > critical:
        result["chan_johansen_assessment"] = "COINTEGRATION_SUPPORTED"
        result["reasons"] = ["a positive cointegration rank and strongest eigenvector pass the Johansen statistic test"]
    else:
        result["chan_johansen_assessment"] = "COINTEGRATION_NOT_REJECTED"
        result["reasons"] = ["the Johansen statistic or rank does not support a cointegrating relation"]
    return result

