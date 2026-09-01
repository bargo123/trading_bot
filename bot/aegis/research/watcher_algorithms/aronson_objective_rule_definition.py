"""Aronson objective-rule and causal-timing perspective."""
from __future__ import annotations

from collections.abc import Sequence

from ._common import absent, base, explicitly_observed, first, values
from ._deprado_common import provenance_ok

ALGORITHM_ID = "aronson_objective_rule_definition"
SOURCES = ("David Aronson — Evidence-Based Technical Analysis",)
KEYS = (
    "aronson_rule_inputs",
    "aronson_rule_operators",
    "aronson_signal_timing",
    "aronson_no_lookahead",
    "aronson_data_provenance",
)


def _nonempty_sequence(value):
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)) and bool(value)


def evaluate(state):
    found = values(state, *KEYS)
    missing = []
    inputs = first(state, "aronson_rule_inputs")
    operators = first(state, "aronson_rule_operators")
    timing = first(state, "aronson_signal_timing")
    if not _nonempty_sequence(inputs):
        missing.append("aronson_rule_inputs")
    if not _nonempty_sequence(operators):
        missing.append("aronson_rule_operators")
    if not isinstance(timing, str) or not timing.strip():
        missing.append("aronson_signal_timing")
    if first(state, "aronson_no_lookahead") is None:
        missing.append("aronson_no_lookahead")
    provenance = first(state, "aronson_data_provenance")
    if not explicitly_observed(provenance, accepted=("observed", "measured", "replay")) or not provenance_ok(provenance):
        missing.append("aronson_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    result["directional_claim"] = False
    result["analysis_stage"] = "causal_rule_specification"
    result["aronson_rule_input_count"] = len(inputs)
    result["aronson_rule_operator_count"] = len(operators)
    result["aronson_signal_timing"] = timing.strip()
    result["aronson_objectivity_assessment"] = (
        "OBJECTIVE_CAUSAL_RULE" if first(state, "aronson_no_lookahead") is True else "LOOKAHEAD_RISK"
    )
    result["warnings"] = ["an objectively specified rule is still research evidence, not execution authority"]
    if first(state, "aronson_no_lookahead") is not True:
        result["reasons"] = ["rule timing is not explicitly marked no-lookahead"]
    else:
        result["reasons"] = ["inputs, operators, and executable timing are explicitly specified"]
    return result
