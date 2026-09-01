"""Noise/chop context perspective for the read-only Watcher.

Trading literature treats noisy conditions as a filter on setup quality and
execution, not as a direction. This evaluator requires an explicitly
classified, point-in-time observation and never fabricates a threshold from a
bare numeric feature. It is research context only.
"""
from __future__ import annotations

import re

from ._common import absent, base, first, normalized_status, number, values

ALGORITHM_ID = "noise_filter"
SOURCES = (
    "Mark Douglas — The Disciplined Trader",
    "Irene Aldridge — High-Frequency Trading",
    "Adam Grimes — The Art and Science of Technical Analysis",
    "Bob Volman — Forex Price Action Scalping",
    "David Aronson — Evidence-Based Technical Analysis",
)
KEYS = (
    "noise_state",
    "noise_ratio",
    "signal_to_noise",
    "chop_index",
    "directional_efficiency",
    "noise_provenance",
    "quote_fresh",
    "quote_age_s",
    "regime",
)


def _has_token(value: str, token: str) -> bool:
    return bool(re.search(r"(?<![a-z])" + re.escape(token) + r"(?![a-z])", value))


def _provenance_is_observed(value) -> bool:
    label = normalized_status(value)
    if not label or any(
        _has_token(label, marker)
        for marker in ("unknown", "missing", "unavailable", "synthetic", "proxy", "unverified", "not observed", "not real")
    ):
        return False
    return any(
        _has_token(label, marker)
        for marker in ("point in time", "quote history", "observed", "measured", "tick history")
    )


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("noise_state_or_measurement",))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    result["directional_claim"] = False
    state_label = normalized_status(first(state, "noise_state"))
    numeric_keys = ("noise_ratio", "signal_to_noise", "chop_index", "directional_efficiency")
    numeric_values = {key: number(first(state, key)) for key in numeric_keys}
    if any(value is not None and value < 0 for value in numeric_values.values()):
        result["noise_assessment"] = "UNKNOWN"
        result["reasons"] = ["noise measurement contains an invalid negative value"]
        return result
    efficiency = numeric_values["directional_efficiency"]
    if efficiency is not None and not 0.0 <= efficiency <= 1.0:
        result["noise_assessment"] = "UNKNOWN"
        result["reasons"] = ["directional efficiency is outside the [0, 1] range"]
        return result
    if not state_label:
        result["noise_assessment"] = "UNKNOWN"
        result["reasons"] = ["numeric noise features require an explicit classification threshold"]
        return result
    if not _provenance_is_observed(first(state, "noise_provenance")):
        result["noise_assessment"] = "UNKNOWN"
        result["warnings"] = ["noise provenance is missing, synthetic, proxy, or unverified"]
        result["reasons"] = ["noise classification is not supported by point-in-time observed data"]
        return result
    quote_age = number(first(state, "quote_age_s"))
    if first(state, "quote_fresh") is not True or quote_age is None or quote_age > 5:
        result["noise_assessment"] = "UNKNOWN"
        result["warnings"] = ["quote freshness is insufficient to classify current noise"]
        result["reasons"] = ["current quote is stale or explicitly not fresh"]
        return result

    high = any(_has_token(state_label, marker) for marker in ("high", "noisy", "choppy", "random", "unstable"))
    low = any(_has_token(state_label, marker) for marker in ("low", "clean", "directional", "persistent"))
    if high and not low:
        result["noise_assessment"] = "HIGH"
        result["warnings"] = ["observed noise/chop is elevated for short-horizon hypotheses"]
        result["reasons"] = ["point-in-time quote history classifies the current state as noisy"]
    elif low and not high:
        result["noise_assessment"] = "LOW"
        result["reasons"] = ["point-in-time quote history classifies the current state as relatively directional"]
    else:
        result["noise_assessment"] = "UNKNOWN"
        result["reasons"] = ["noise labels are absent or conflicting"]
    return result
