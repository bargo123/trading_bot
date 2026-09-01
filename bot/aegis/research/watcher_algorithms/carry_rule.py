"""Systematic Trading carry rule using explicit net carry inputs."""
from __future__ import annotations

from ._common import absent, base, explicitly_validated, first, number, strings, values, with_direction

ALGORITHM_ID = "carry_rule"
SOURCES = (
    "Robert Carver — Systematic Trading",
    "Kathy Lien — Day Trading and Swing Trading the Currency Market",
    "Roy E. Bailey — The Economics of Financial Markets",
)
KEYS = ("carry_return_pct", "carry_funding_cost_pct", "carry_signal", "carry_data_provenance")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("verified_net_carry",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    carry = number(first(state, "carry_return_pct"))
    funding = number(first(state, "carry_funding_cost_pct"))
    signal = str(first(state, "carry_signal") or "").strip().upper()
    provenance = strings(state, "carry_data_provenance")
    if None in {carry, funding} or signal not in {"BUY", "SELL"} or not explicitly_validated(provenance, accepted=("verified", "validated")):
        result["view"] = "WAIT"
        result["reasons"] = ["carry requires verified return, funding cost, and directional pair mapping"]
        return result
    net = carry - funding
    result["net_carry_pct"] = net
    if net <= 0:
        result["view"] = "WAIT"
        result["reasons"] = ["verified net carry is not positive"]
        return result
    return with_direction(result, state, signal, "verified positive net carry supports the recorded direction")
