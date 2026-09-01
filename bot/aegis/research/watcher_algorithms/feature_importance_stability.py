"""Feature-importance stability diagnostic for model research."""
from __future__ import annotations

from ._common import absent, base, explicitly_validated, first, number, values

ALGORITHM_ID = "feature_importance_stability"
SOURCES = ("Marcos López de Prado — Advances in Financial Machine Learning", "Stefan Jansen — Machine Learning for Algorithmic Trading")
KEYS = ("feature_importance_stability", "feature_importance_oos_status", "feature_importance_observation_n")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("stable_oos_feature_importance",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    stability = number(first(state, "feature_importance_stability"))
    observations = number(first(state, "feature_importance_observation_n"))
    oos = first(state, "feature_importance_oos_status")
    if stability is None or observations is None or not 0 <= stability <= 1 or observations < 50 or not explicitly_validated(oos, accepted=("walk forward", "sealed oos", "validated")):
        result["view"] = "WAIT"
        result["reasons"] = ["feature importance is not stable on a sufficient chronological OOS sample"]
        return result
    result["stability_assessment"] = "STABLE" if stability >= 0.5 else "UNSTABLE"
    result["view"] = "WAIT"
    result["reasons"] = ["feature-importance stability is a model diagnostic, not a directional signal"]
    return result
