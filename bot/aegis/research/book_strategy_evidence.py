"""Truthful, deterministic evaluation of book-derived strategy evidence."""
from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any, Mapping

_DIRECT_KEYS = frozenset({
    "timestamp", "symbol", "side", "mechanism", "horizon_s", "session", "regime",
    "structure", "bid", "ask", "spread", "spread_pips", "quote_age_s", "volatility",
    "volatility_context", "short_returns", "tick_velocity", "tick_direction",
    "m1_context", "m5_context", "m15_context", "provenance", "schema_version",
})
_NESTED_KEYS = frozenset({"context", "entry_state", "decision_snapshot", "candidate_details"})
_NUMERIC_OPS = {"gte": ">=", "gt": ">", "lte": "<=", "lt": "<", "eq": "=="}
_SUFFIX_RE = re.compile(r"^(?P<field>[a-z0-9_]+)_(?P<op>gte|gt|lte|lt|eq)$")


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _clean(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _clean(item) for key, item in value.items() if str(key) not in {"future_quote", "quotes", "counterfactual_quotes"}}
    if isinstance(value, (list, tuple)):
        return [_clean(item) for item in value]
    number = _finite(value)
    if isinstance(value, (int, float)) and number is not None:
        return number
    return value


def compact_context_event(event: Mapping[str, Any]) -> dict[str, Any]:
    """Keep only pre-entry fields and hash their canonical representation."""
    source: dict[str, Any] = {}
    for key, value in event.items():
        if key in _DIRECT_KEYS:
            source[key] = value
        elif key in _NESTED_KEYS and isinstance(value, Mapping):
            for nested_key, nested_value in value.items():
                if nested_key in _DIRECT_KEYS or nested_key.startswith("return_") or nested_key.startswith("tick_"):
                    source.setdefault(nested_key, nested_value)
    if "spread" not in source and "spread_pips" in source:
        source["spread"] = source["spread_pips"]
    snapshot = _clean(source)
    if not isinstance(snapshot, dict):  # defensive; source is always a dict
        snapshot = {}
    encoded = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    snapshot["context_hash"] = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return snapshot


def _lookup(context: Mapping[str, Any], field: str) -> Any:
    if field in context:
        return context[field]
    for key in ("m1_context", "m5_context", "m15_context", "short_returns", "volatility_context"):
        nested = context.get(key)
        if isinstance(nested, Mapping) and field in nested:
            return nested[field]
    return None


def _split_rule(key: str, value: Any) -> tuple[str, str, Any]:
    match = _SUFFIX_RE.match(key)
    if match:
        return match.group("field"), match.group("op"), value
    if key.endswith("_max"):
        return key[:-4], "lte", value
    if key.endswith("_min"):
        return key[:-4], "gte", value
    if key.endswith("_in"):
        return key[:-3], "in", value
    return key, "eq", value


def _comparison(actual: Any, op: str, expected: Any) -> tuple[bool, str | None]:
    if op in _NUMERIC_OPS:
        left = _finite(actual)
        right = _finite(expected)
        if left is None or right is None:
            return False, "non_numeric_value"
        if op == "gte":
            return left >= right, None
        if op == "gt":
            return left > right, None
        if op == "lte":
            return left <= right, None
        if op == "lt":
            return left < right, None
        return left == right, None
    if op == "in":
        expected_values = expected if isinstance(expected, (list, tuple, set, frozenset)) else [expected]
        return str(actual).lower() in {str(item).lower() for item in expected_values}, None
    if isinstance(actual, str) or isinstance(expected, str):
        return str(actual).lower() == str(expected).lower(), None
    return actual == expected, None


def evaluate_compiled_strategy(strategy: Mapping[str, Any], context: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate an allow-listed compiled rule without execution authority."""
    status = str(strategy.get("status") or "").upper()
    result: dict[str, Any] = {
        "evidence_status": status or "UNCLASSIFIED",
        "execution_authority": False,
        "uses_future_data": False,
        "failed_predicates": [],
        "missing": [],
    }
    if status != "CODED_EXACT":
        result.update({"status": "CONTEXT_ONLY", "evaluation_status": "CONTEXT_ONLY", "reason": "non_exact_strategy"})
        return result
    side_rule = str(strategy.get("side_rule") or "").upper()
    current_side = str(_lookup(context, "side") or "").upper()
    if side_rule and current_side and side_rule != current_side:
        result["failed_predicates"].append("side_rule")
    elif side_rule and not current_side:
        result["missing"].append("side")
    compiled = strategy.get("compiled_rule")
    if not isinstance(compiled, Mapping):
        result.update({"status": "EVALUATION_ERROR", "evaluation_status": "COMPILE_ERROR", "reason": "missing_compiled_rule"})
        return result
    for key, expected in compiled.items():
        field, op, target = _split_rule(str(key), expected)
        actual = _lookup(context, field)
        if actual is None or actual == "":
            result["missing"].append(field)
            continue
        passed, error = _comparison(actual, op, target)
        if error:
            result["failed_predicates"].append(f"{key}:{error}")
        elif not passed:
            result["failed_predicates"].append(key)
    result["missing"] = list(dict.fromkeys(result["missing"]))
    if result["missing"]:
        result.update({"status": "MISSING_INPUT", "evaluation_status": "MISSING_INPUT", "reason": "missing_required_input"})
    elif result["failed_predicates"]:
        result.update({"status": "NO_MATCH", "evaluation_status": "NO_MATCH", "reason": "predicate_failed"})
    else:
        result.update({"status": "MATCH", "evaluation_status": "MATCH", "reason": "all_predicates_satisfied"})
    return result


def evaluate_strategy_evidence(record: Mapping[str, Any], state: Mapping[str, Any]) -> dict[str, Any]:
    snapshot = compact_context_event(state)
    strategy_status = str(record.get("status") or record.get("validation_status") or "UNCLASSIFIED").upper()
    if strategy_status != "CODED_EXACT":
        return {
            "evaluation_status": "CONTEXT_ONLY",
            "evidence_status": strategy_status,
            "reason": "non_exact_strategy",
            "context_hash": snapshot["context_hash"],
            "execution_authority": False,
            "uses_future_data": False,
        }
    result = evaluate_compiled_strategy(record, snapshot)
    result["context_hash"] = snapshot["context_hash"]
    return result


__all__ = ["compact_context_event", "evaluate_compiled_strategy", "evaluate_strategy_evidence"]
