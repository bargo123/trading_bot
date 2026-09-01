"""Fail-closed compiler for structured research hypotheses."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, FrozenSet, Iterable, Mapping, Optional

from aegis.research_factory.hypothesis import Hypothesis


_ENTRY_RULE_KEYS = {
    "breakout": frozenset({"type", "direction", "window"}),
    "mean_reversion": frozenset({"type", "direction", "z_threshold"}),
    "regime_structure_alignment": frozenset(
        {"type", "direction", "required_regimes", "required_structure"}
    ),
}
_EXIT_RULE_KEYS = {
    "regime_change": frozenset({"type"}),
    "stop_target": frozenset({"type"}),
    "stop_loss": frozenset({"type"}),
    "target_hit": frozenset({"type"}),
    "elapsed_time": frozenset({"type"}),
    "time_exit": frozenset({"type"}),
}


@dataclass(frozen=True)
class CompileResult:
    """A normalized executable hypothesis or an explicit rejection."""

    status: str
    reason: str
    entry_rule: Optional[Dict[str, Any]] = None
    exit_rule: Optional[Dict[str, Any]] = None
    required_columns: FrozenSet[str] = frozenset()
    side: Optional[str] = None
    invalidation_price: Optional[float] = None
    target_price: Optional[float] = None
    max_hold_s: Optional[int] = None


def _rejected(reason: str) -> CompileResult:
    return CompileResult(status="NOT_EXECUTABLE", reason=reason)


def _positive_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _positive_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and float(value) > 0
    )


def _price(value: Any) -> Optional[float]:
    if value is None:
        return None
    if not _positive_number(value):
        raise ValueError
    return float(value)


def _missing_columns(required: set[str], available: set[str]) -> Optional[str]:
    missing = sorted(required - available)
    if missing:
        return f"missing columns: {', '.join(missing)}"
    return None


def _unexpected_keys(
    rule: Mapping[str, Any], allowed: FrozenSet[str], rule_kind: str
) -> Optional[str]:
    unexpected = set(rule) - allowed
    if unexpected:
        names = ", ".join(sorted(str(key) for key in unexpected))
        return f"unexpected {rule_kind} rule keys: {names}"
    return None


def compile_hypothesis(
    hypothesis: Hypothesis, available_columns: Iterable[str]
) -> CompileResult:
    """Validate and normalize only rules whose behavior is fully defined."""

    side = hypothesis.side
    if side is None or side == "":
        return _rejected("missing side")
    if side not in {"buy", "sell"}:
        return _rejected(f"invalid side: {side}")

    if not isinstance(hypothesis.book_evidence, list) or not all(
        isinstance(item, dict) for item in hypothesis.book_evidence
    ):
        return _rejected("book_evidence must be a list of dictionaries")
    if not isinstance(hypothesis.ml_evidence, dict):
        return _rejected("ml_evidence must be a dictionary")
    if not isinstance(hypothesis.loss_autopsy_evidence, list) or not all(
        isinstance(item, dict) for item in hypothesis.loss_autopsy_evidence
    ):
        return _rejected("loss_autopsy_evidence must be a list of dictionaries")
    if not (
        hypothesis.book_evidence
        or hypothesis.ml_evidence
        or hypothesis.loss_autopsy_evidence
    ):
        return _rejected("missing source evidence")

    if not isinstance(hypothesis.features_required, list) or not all(
        isinstance(column, str) and column for column in hypothesis.features_required
    ):
        return _rejected("invalid features_required")

    try:
        available = set(available_columns)
    except TypeError:
        return _rejected("invalid available columns")

    if not isinstance(hypothesis.entry_rule, Mapping):
        return _rejected("entry rule must be a dictionary")
    entry_type = hypothesis.entry_rule.get("type")
    entry_columns: set[str]
    if entry_type == "breakout":
        entry_columns = {"high", "low", "close"}
    elif entry_type == "mean_reversion":
        entry_columns = {"close", "sma_20"}
    elif entry_type == "regime_structure_alignment":
        entry_columns = {"regime", "structure"}
    else:
        return _rejected(f"unknown entry rule: {entry_type or '<missing>'}")

    unexpected_reason = _unexpected_keys(
        hypothesis.entry_rule, _ENTRY_RULE_KEYS[entry_type], "entry"
    )
    if unexpected_reason:
        return _rejected(unexpected_reason)

    required_columns = set(hypothesis.features_required) | entry_columns
    missing_reason = _missing_columns(required_columns, available)
    if missing_reason:
        return _rejected(missing_reason)

    direction = "long" if side == "buy" else "short"
    normalized_entry = {"type": entry_type, "direction": direction}
    if entry_type == "breakout":
        if not _positive_integer(hypothesis.entry_rule.get("window")):
            return _rejected("window must be a positive integer")
        normalized_entry["window"] = hypothesis.entry_rule["window"]
    elif entry_type == "mean_reversion":
        threshold = hypothesis.entry_rule.get("z_threshold")
        if not _positive_number(threshold):
            return _rejected("z_threshold must be positive")
        normalized_entry["z_threshold"] = float(threshold)
    else:
        regimes = hypothesis.entry_rule.get("required_regimes")
        if (
            not isinstance(regimes, list)
            or not regimes
            or not all(isinstance(regime, str) and regime for regime in regimes)
        ):
            return _rejected("required_regimes must be a non-empty list")
        if hypothesis.entry_rule.get("required_structure") is not True:
            return _rejected("required_structure must be true")
        normalized_entry["required_regimes"] = list(regimes)
        normalized_entry["required_structure"] = True

    if not isinstance(hypothesis.exit_rule, Mapping):
        return _rejected("exit rule must be a dictionary")
    exit_type = hypothesis.exit_rule.get("type")
    if exit_type == "regime_change":
        exit_columns = {"regime"}
    elif exit_type == "stop_target":
        exit_columns = {"high", "low"}
    elif exit_type == "stop_loss":
        exit_columns = {"high", "low"}
    elif exit_type == "target_hit":
        exit_columns = {"high", "low"}
    elif exit_type in {"elapsed_time", "time_exit"}:
        exit_columns = {"time"}
    else:
        return _rejected(f"unknown exit rule: {exit_type or '<missing>'}")

    unexpected_reason = _unexpected_keys(
        hypothesis.exit_rule, _EXIT_RULE_KEYS[exit_type], "exit"
    )
    if unexpected_reason:
        return _rejected(unexpected_reason)
    normalized_exit = {
        "type": "elapsed_time" if exit_type == "time_exit" else exit_type
    }

    if (
        exit_type == "stop_target"
        and hypothesis.invalidation_price is None
        and hypothesis.target_price is None
    ):
        return _rejected("stop_target requires an invalidation or target price")
    if exit_type == "stop_loss" and hypothesis.invalidation_price is None:
        return _rejected("stop_loss requires an invalidation price")
    if exit_type == "target_hit" and hypothesis.target_price is None:
        return _rejected("target_hit requires a target price")
    if exit_type in {"elapsed_time", "time_exit"} and not _positive_integer(
        hypothesis.max_hold_s
    ):
        return _rejected("max_hold_s must be a positive integer")

    if hypothesis.max_hold_s is not None:
        if not _positive_integer(hypothesis.max_hold_s):
            return _rejected("max_hold_s must be a positive integer")
        exit_columns.add("time")

    if hypothesis.invalidation_price is not None or hypothesis.target_price is not None:
        exit_columns.update({"high", "low"})

    required_columns.update(exit_columns)
    missing_reason = _missing_columns(required_columns, available)
    if missing_reason:
        return _rejected(missing_reason)

    try:
        entry_price = _price(hypothesis.entry_price)
        invalidation_price = _price(hypothesis.invalidation_price)
        target_price = _price(hypothesis.target_price)
    except ValueError:
        return _rejected("prices must be finite and positive")

    if (invalidation_price is not None or target_price is not None) and entry_price is None:
        return _rejected("entry price is required for stop/target geometry")
    if side == "buy":
        if invalidation_price is not None and invalidation_price >= entry_price:
            return _rejected("buy invalidation price must be below entry price")
        if target_price is not None and target_price <= entry_price:
            return _rejected("buy target price must be above entry price")
    else:
        if invalidation_price is not None and invalidation_price <= entry_price:
            return _rejected("sell invalidation price must be above entry price")
        if target_price is not None and target_price >= entry_price:
            return _rejected("sell target price must be below entry price")

    return CompileResult(
        status="EXECUTABLE",
        reason="",
        entry_rule=normalized_entry,
        exit_rule=normalized_exit,
        required_columns=frozenset(required_columns),
        side=side,
        invalidation_price=invalidation_price,
        target_price=target_price,
        max_hold_s=hypothesis.max_hold_s,
    )
