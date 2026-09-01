"""Shared causal evaluator for the four Bulkowski head-and-shoulders variants."""
from __future__ import annotations

from ._common import first, normalized_status, number
from .bulkowski_pattern_common import direction, finish, observed_bool, start

KEYS = (
    "bulkowski_hs_type", "bulkowski_hs_prior_trend", "bulkowski_hs_left_shoulder",
    "bulkowski_hs_head", "bulkowski_hs_right_shoulder", "bulkowski_hs_shoulder_symmetry_pct",
    "bulkowski_hs_neckline_price", "bulkowski_hs_breakout_direction",
    "bulkowski_hs_breakout_close_confirmed", "bulkowski_hs_breakout_price",
    "bulkowski_hs_extra_shoulders", "bulkowski_hs_extra_heads", "bulkowski_data_provenance",
)


def evaluate_hs(state, algorithm_id: str, *, bottom: bool, complex_pattern: bool, source_pages: str):
    result = start(algorithm_id, state, KEYS)
    if result["view"] == "MISSING_DATA":
        return result
    if normalized_status(first(state, "bulkowski_hs_type")) != ("complex" if complex_pattern else "normal"):
        result["reasons"] = ["the supplied head-and-shoulders type does not match this perspective"]
        return result
    expected_trend = "down" if bottom else "up"
    if normalized_status(first(state, "bulkowski_hs_prior_trend")) != expected_trend:
        result["reasons"] = [f"a head-and-shoulders {'bottom' if bottom else 'top'} requires the corresponding prior trend"]
        return result
    left = number(first(state, "bulkowski_hs_left_shoulder"))
    head = number(first(state, "bulkowski_hs_head"))
    right = number(first(state, "bulkowski_hs_right_shoulder"))
    symmetry = number(first(state, "bulkowski_hs_shoulder_symmetry_pct"))
    neckline = number(first(state, "bulkowski_hs_neckline_price"))
    price = number(first(state, "bulkowski_hs_breakout_price"))
    extra_shoulders = number(first(state, "bulkowski_hs_extra_shoulders"))
    extra_heads = number(first(state, "bulkowski_hs_extra_heads"))
    breakout = direction(state, "bulkowski_hs_breakout_direction")
    if None in (left, head, right, symmetry, neckline, price, extra_shoulders, extra_heads) or breakout is None:
        result["reasons"] = ["head-and-shoulders geometry, symmetry, and breakout must be finite observations"]
        return result
    if symmetry > 20 or extra_shoulders < 0 or extra_heads < 0 or (complex_pattern and extra_shoulders + extra_heads < 1) or (not complex_pattern and extra_shoulders + extra_heads != 0):
        result["reasons"] = ["shoulder symmetry or normal/complex structure classification failed"]
        return result
    if bottom:
        shaped = head < min(left, right)
        valid_break = breakout == "UP" and price > neckline
        signal = "BUY"
        target = price + (neckline - head)
    else:
        shaped = head > max(left, right)
        valid_break = breakout == "DOWN" and price < neckline
        signal = "SELL"
        target = price - (head - neckline)
    if not shaped:
        result["reasons"] = ["the center head is not distinct from both shoulders"]
        return result
    if not valid_break or not observed_bool(first(state, "bulkowski_hs_breakout_close_confirmed")):
        result["reasons"] = ["the head-and-shoulders neckline breakout is not confirmed"]
        return result
    result.update({"source_pages": source_pages, "bulkowski_measure_target": target, "bulkowski_neckline_height": abs(neckline - head)})
    return finish(result, state, signal, "a symmetric head-and-shoulders structure confirmed through its neckline")
