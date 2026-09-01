"""Narang's run-frequency tradeoff replay diagnostic (Inside the Black Box, ch. 3)."""
from __future__ import annotations

from collections.abc import Sequence

from ._common import absent, base, explicitly_observed, first, number, values


ALGORITHM_ID = "narang_run_frequency_tradeoff"
SOURCES = ("Rishi K Narang — Inside the Black Box",)
KEYS = (
    "narang_run_frequency_grid_s",
    "narang_run_frequency_gross_returns",
    "narang_run_frequency_transaction_costs",
    "narang_run_frequency_noise_penalties",
    "narang_run_frequency_data_provenance",
)


def _series(value):
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return None
    result = [number(item) for item in value]
    return result if len(result) >= 2 and all(item is not None for item in result) else None


def evaluate(state):
    found = values(state, *KEYS)
    provenance = first(state, "narang_run_frequency_data_provenance")
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(
        provenance,
        accepted=("observed", "measured", "historical", "replay"),
    ):
        missing.append("narang_run_frequency_data_provenance")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    grid = _series(first(state, "narang_run_frequency_grid_s"))
    gross = _series(first(state, "narang_run_frequency_gross_returns"))
    transaction_costs = _series(first(state, "narang_run_frequency_transaction_costs"))
    noise_penalties = _series(first(state, "narang_run_frequency_noise_penalties"))
    if any(item is None for item in (grid, gross, transaction_costs, noise_penalties)):
        result["narang_run_frequency_action"] = "INVALID_FREQUENCY_REPLAY"
        result["reasons"] = [
            "frequency replay needs four equally sized finite series with at least two observations"
        ]
        return result
    if not (len(grid) == len(gross) == len(transaction_costs) == len(noise_penalties)):
        result["narang_run_frequency_action"] = "INVALID_FREQUENCY_REPLAY"
        result["reasons"] = [
            "frequency, gross-return, transaction-cost, and noise-penalty grids must be equally sized"
        ]
        return result
    if any(frequency <= 0 for frequency in grid) or any(
        later <= earlier for earlier, later in zip(grid, grid[1:])
    ):
        result["narang_run_frequency_action"] = "INVALID_FREQUENCY_REPLAY"
        result["reasons"] = ["run-frequency grid must be strictly increasing and positive"]
        return result
    if any(cost < 0 for cost in transaction_costs) or any(penalty < 0 for penalty in noise_penalties):
        result["narang_run_frequency_action"] = "INVALID_FREQUENCY_REPLAY"
        result["reasons"] = ["transaction costs and noise penalties cannot be negative"]
        return result

    net_returns = [
        gross_return - transaction_cost - noise_penalty
        for gross_return, transaction_cost, noise_penalty in zip(
            gross, transaction_costs, noise_penalties
        )
    ]
    ranking = sorted(
        zip(grid, net_returns, gross, transaction_costs, noise_penalties),
        key=lambda item: item[1],
        reverse=True,
    )
    best_frequency, best_net, _, _, _ = ranking[0]
    tied = len(ranking) > 1 and best_net == ranking[1][1]
    result.update(
        {
            "narang_run_frequency_net_returns": net_returns,
            "narang_run_frequency_ranking": ranking,
            "narang_selected_run_frequency_s": best_frequency,
            "narang_selected_run_frequency_net_return": best_net,
            "narang_run_frequency_observation_n": len(grid),
            "directional_claim": False,
        }
    )
    if tied:
        result["narang_run_frequency_action"] = "NO_CLEAR_FREQUENCY_LEADER"
        result["reasons"] = ["the best cost-adjusted replay frequencies are tied"]
        return result
    best_index = net_returns.index(best_net)
    if best_index == 0:
        action = "PREFER_MORE_FREQUENT"
    elif best_index == len(net_returns) - 1:
        action = "PREFER_LESS_FREQUENT"
    else:
        action = "PREFER_INTERMEDIATE_FREQUENCY"
    result["narang_run_frequency_action"] = action
    result["reasons"] = [
        "the selected run frequency maximizes the supplied replay return after transaction and noise costs"
    ]
    result["warnings"] = [
        "run-frequency ranking is a replay diagnostic; it does not prove future profitability or choose a trade direction"
    ]
    return result
