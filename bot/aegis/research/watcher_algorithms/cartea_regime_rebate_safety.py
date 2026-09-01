"""Regime-conditioned rebate safety study from Cartea and Jaimungal."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values

ALGORITHM_ID = "cartea_regime_rebate_safety"
SOURCES = ("Modelling Asset Prices for Algorithmic and High-Frequency Trading",)
KEYS = (
    "cartea_regime_persistence",
    "cartea_zero_revision_probability",
    "cartea_revision_volatility",
    "cartea_rebate_net_edge",
    "cartea_rebate_safety_status",
    "cartea_regime_data_provenance",
)


def _provenance_ok(value) -> bool:
    provenance = normalized_status(value)
    return bool(provenance) and not any(
        token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")
    )


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    if not _provenance_ok(first(state, "cartea_regime_data_provenance")):
        missing.append("cartea_regime_data_provenance")
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    result.update({"directional_claim": False, "cartea_rebate_eligible": False})
    persistence = number(first(state, "cartea_regime_persistence"))
    zero_revision = number(first(state, "cartea_zero_revision_probability"))
    volatility = number(first(state, "cartea_revision_volatility"))
    net_edge = number(first(state, "cartea_rebate_net_edge"))
    status = normalized_status(first(state, "cartea_rebate_safety_status"))
    if (
        None in {persistence, zero_revision, volatility, net_edge}
        or not 0.0 <= persistence <= 1.0
        or not 0.0 <= zero_revision <= 1.0
        or volatility < 0.0
        or net_edge <= 0.0
        or status not in {"safe", "eligible", "low risk"}
    ):
        result["reasons"] = ["rebate safety needs observed regime persistence, revision risk, volatility, and positive net edge"]
        return result
    result.update(
        {
            "cartea_rebate_eligible": True,
            "cartea_regime_persistence": persistence,
            "cartea_zero_revision_probability": zero_revision,
            "cartea_revision_volatility": volatility,
            "cartea_rebate_net_edge": net_edge,
        }
    )
    result["reasons"] = ["the observed regime is marked safe and its measured rebate economics are positive"]
    return result
