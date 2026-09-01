"""PCA/eigenportfolio risk-factor context."""
from __future__ import annotations

from ._common import absent, base, explicitly_validated, first, number, values

ALGORITHM_ID = "pca_eigenportfolio"
SOURCES = ("Stefan Jansen — Machine Learning for Algorithmic Trading", "Richard Grinold and Ronald Kahn — Active Portfolio Management")
KEYS = ("pca_status", "pca_explained_variance", "pca_loading", "pca_portfolio_name")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("validated_pca_factor_context",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    status = first(state, "pca_status")
    variance = number(first(state, "pca_explained_variance"))
    loading = number(first(state, "pca_loading"))
    name = first(state, "pca_portfolio_name")
    if not explicitly_validated(status) or variance is None or loading is None or not name or not 0 <= variance <= 1:
        result["view"] = "WAIT"
        result["reasons"] = ["PCA factor context is incomplete or unvalidated"]
        return result
    result["factor_assessment"] = "OBSERVED"
    result["view"] = "WAIT"
    result["reasons"] = ["PCA/eigenportfolio is a risk-factor context and does not select a side"]
    return result
