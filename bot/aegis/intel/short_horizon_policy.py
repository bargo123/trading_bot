"""Runtime-safe promotion thresholds shared with the offline builder."""
from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

MIN_CAPTURED_EXIT_LOSSES = 5
MIN_CAPTURED_EXIT_WIN_LCB95 = 0.95

FEATURE_PROVENANCE_SCHEMA = "point_in_time_feature_provenance.v1"
FEATURE_AVAILABILITY = "at_or_before_decision"

_QUOTE_HISTORY_FEATURES = frozenset(
    {
        "bid", "ask", "mid", "spread", "spread_change", "tick_velocity",
        "price_acceleration", "quote_age_s", "spread_percentile",
        "micro_volatility", "realized_vol_60s", "spread_to_micro_vol",
        "spread_to_realized_vol", "spread_acceleration", "micro_reversal",
        "momentum_persistence", "momentum_decay", "distance_to_micro_high",
        "distance_to_micro_low", "volatility_expansion", "cost_to_movement",
        "entry_price", "entry_bid", "entry_ask", "entry_spread_price",
    }
)
_DECISION_CONTEXT_FEATURES = frozenset(
    {
        "hour_utc", "dow_utc", "session_asia_or_off", "session_london",
        "session_new_york", "session_overlap", "side_buy", "horizon_s",
        "assumed_commission_round_trip_usd", "commission", "slippage",
        "expected_initial_friction_price",
    }
)
_FUTURE_FEATURE_PREFIXES = (
    "pnl_", "green_", "captured_", "exit_", "future_", "time_to_",
    "terminal_", "label_",
)
_FUTURE_FEATURE_NAMES = frozenset(
    {
        "first_green", "first_profitable_executable_close",
        "first_profitable_close_net_pnl", "immediate_adverse_move",
        "winner_giveback", "never_green", "time_in_red_s",
        "future_path_observed_n", "exit_policy", "exit_time_s",
    }
)


def _feature_source(name: str) -> str:
    lowered = str(name).strip().lower()
    if lowered in _FUTURE_FEATURE_NAMES or lowered.startswith(_FUTURE_FEATURE_PREFIXES):
        raise ValueError(f"future outcome alias: {name}")
    if lowered in _QUOTE_HISTORY_FEATURES:
        return "quote_history_at_or_before_decision"
    if lowered in _DECISION_CONTEXT_FEATURES:
        return "decision_context_or_config"
    if re.fullmatch(r"return_[1-9][0-9]*s", lowered):
        return "quote_history_at_or_before_decision"
    for prefix, limit in (("symbol_bucket_", 32), ("mechanism_bucket_", 32)):
        if lowered.startswith(prefix):
            suffix = lowered[len(prefix):]
            if suffix.isdigit() and 0 <= int(suffix) < limit and len(suffix) == 2:
                return "deterministic_identity_at_decision"
    raise ValueError(f"unknown point-in-time feature: {name}")


def build_feature_provenance(feature_names: Sequence[Any]) -> dict[str, Any]:
    """Build an explicit source/availability attestation for runtime features."""
    names = [str(value).strip() for value in feature_names]
    if not names or any(not value for value in names) or len(set(names)) != len(names):
        raise ValueError("feature names must be non-empty and unique")
    return {
        "schema": FEATURE_PROVENANCE_SCHEMA,
        "decision_time": "entry_quote_timestamp",
        "label_time_boundary": "strictly_after_decision",
        "all_features_available_at_or_before_decision": True,
        "features": {
            name: {
                "source": _feature_source(name),
                "availability": FEATURE_AVAILABILITY,
            }
            for name in names
        },
    }


def validate_feature_provenance(
    provenance: Mapping[str, Any] | None,
    feature_names: Sequence[Any],
) -> None:
    """Validate a complete point-in-time feature attestation."""
    if not isinstance(provenance, Mapping):
        raise ValueError("feature provenance missing")
    if provenance.get("schema") != FEATURE_PROVENANCE_SCHEMA:
        raise ValueError("feature provenance schema mismatch")
    if provenance.get("decision_time") != "entry_quote_timestamp":
        raise ValueError("feature provenance decision time mismatch")
    if provenance.get("label_time_boundary") != "strictly_after_decision":
        raise ValueError("feature provenance label boundary mismatch")
    if provenance.get("all_features_available_at_or_before_decision") is not True:
        raise ValueError("feature provenance does not prove decision-time availability")
    names = [str(value).strip() for value in feature_names]
    rows = provenance.get("features")
    if not isinstance(rows, Mapping) or set(rows) != set(names):
        raise ValueError("feature provenance feature rows do not match runtime features")
    for name in names:
        row = rows.get(name)
        if not isinstance(row, Mapping):
            raise ValueError(f"feature provenance row missing: {name}")
        expected_source = _feature_source(name)
        if row.get("availability") != FEATURE_AVAILABILITY:
            raise ValueError(f"feature availability is not point-in-time: {name}")
        if row.get("source") != expected_source:
            raise ValueError(f"feature provenance source mismatch: {name}")


__all__ = [
    "MIN_CAPTURED_EXIT_LOSSES", "MIN_CAPTURED_EXIT_WIN_LCB95",
    "FEATURE_PROVENANCE_SCHEMA", "FEATURE_AVAILABILITY",
    "build_feature_provenance", "validate_feature_provenance",
]
