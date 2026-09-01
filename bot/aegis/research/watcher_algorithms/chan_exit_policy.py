"""Chan's strategy-family-specific exit-policy diagnostic."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, normalized_status, values

ALGORITHM_ID = "chan_exit_policy"
SOURCES = ("Ernest P. Chan — Quantitative Trading",)
KEYS = (
    "side",
    "chan_strategy_type",
    "chan_exit_style",
    "chan_exit_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(
        first(state, "chan_exit_data_provenance"),
        accepted=("observed", "measured", "historical", "timestamped"),
    ):
        missing.append("chan_exit_data_provenance")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    strategy = normalized_status(first(state, "chan_strategy_type")).replace(" ", "_")
    exit_style = normalized_status(first(state, "chan_exit_style")).replace(" ", "_")
    result["directional_claim"] = False
    if strategy not in {"mean_reversion", "momentum"} or exit_style not in {
        "fixed_holding_period", "profit_cap", "latest_signal", "stop_loss"
    }:
        result["chan_exit_assessment"] = "INVALID_EXIT_POLICY"
        result["reasons"] = ["the exit diagnostic needs a supported mean-reversion/momentum family and explicit exit style"]
        return result

    result.update({"chan_strategy_type": strategy, "chan_exit_style": exit_style})
    if strategy == "mean_reversion" and exit_style == "stop_loss":
        result["chan_exit_assessment"] = "MEAN_REVERSION_STOP_LOSS_WARNING"
        result["reasons"] = ["the source cautions that a stop loss can exit a reversal trade at the worst time"]
        return result

    result["chan_exit_assessment"] = f"{strategy.upper()}_EXIT_ALIGNED"
    result["reasons"] = ["the observed exit style is compatible with the source strategy family"]
    return result
