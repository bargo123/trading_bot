"""Aronson position-bias and market-drift-adjusted return perspective."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, values
from ._deprado_common import finite_series, provenance_ok

ALGORITHM_ID = "aronson_detrended_rule_return"
SOURCES = ("David Aronson — Evidence-Based Technical Analysis",)
KEYS = (
    "aronson_rule_returns",
    "aronson_market_returns",
    "aronson_position_series",
    "aronson_data_provenance",
)


def evaluate(state):
    rule_returns = finite_series(state, "aronson_rule_returns")
    market_returns = finite_series(state, "aronson_market_returns")
    positions = finite_series(state, "aronson_position_series")
    found = values(state, *KEYS)
    missing = []
    if rule_returns is None or len(rule_returns) < 3:
        missing.append("aronson_rule_returns")
    if market_returns is None or len(market_returns) < 3:
        missing.append("aronson_market_returns")
    if positions is None or len(positions) < 3:
        missing.append("aronson_position_series")
    provenance = first(state, "aronson_data_provenance")
    if not explicitly_observed(provenance, accepted=("observed", "measured", "replay")) or not provenance_ok(provenance):
        missing.append("aronson_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))
    if not (len(rule_returns) == len(market_returns) == len(positions)) or any(position not in {-1.0, 1.0} for position in positions):
        result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="MISSING_DATA")
        result["reasons"] = ["aligned binary rule returns, market returns, and long/short positions are required"]
        return result

    market_mean = sum(market_returns) / len(market_returns)
    detrended = [rule_return - position * market_mean for rule_return, position in zip(rule_returns, positions)]
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    result["directional_claim"] = False
    result["analysis_stage"] = "position_bias_adjusted_outcome_diagnostic"
    result["aronson_market_mean_return"] = market_mean
    result["aronson_raw_mean_return"] = sum(rule_returns) / len(rule_returns)
    result["aronson_detrended_mean_return"] = sum(detrended) / len(detrended)
    result["aronson_detrended_returns"] = detrended
    result["aronson_position_long_fraction"] = sum(position == 1.0 for position in positions) / len(positions)
    result["warnings"] = ["detrending removes market drift and position bias for research comparison; it does not change executable PnL"]
    result["reasons"] = ["aligned observed returns were adjusted by the contemporaneous sample market drift"]
    return result
