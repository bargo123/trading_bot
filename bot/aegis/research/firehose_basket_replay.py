"""Chronological, research-only validation for Firehose basket policies."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from math import isfinite
from typing import Any


_POLICIES = (
    "structural",
    "harvest",
    "extension",
    "floor",
    "ev",
    "scratch",
    "combined",
)
_PARTITION_ORDER = {"TRAIN": 0, "VALIDATION": 1, "OOS": 2, "SEALED": 2}
_PARAMETER_KEYS = frozenset({"r_multiple", "cost_r", "momentum_threshold"})


def evaluate_basket_policies(rows: Sequence[Mapping[str, Any]], policy_packets: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate evidenced policies without allowing OOS outcomes to select a winner."""
    packets = _validated_packets(policy_packets)
    if packets is None:
        return _no_evidence("missing_policy_evidence")

    prepared = _prepare_rows(rows)
    if prepared is None:
        return _no_evidence("non_chronological_rows")
    if prepared == "missing_cost":
        return _no_evidence("missing_cost_evidence")

    partitions = [row["partition"] for row in prepared]
    if not {"TRAIN", "VALIDATION"}.issubset(partitions) or not any(
        partition in {"OOS", "SEALED"} for partition in partitions
    ):
        return _no_evidence("incomplete_oos_evidence")

    train_rows = [row for row in prepared if row["partition"] == "TRAIN"]
    validation_rows = [row for row in prepared if row["partition"] == "VALIDATION"]
    oos_rows = [row for row in prepared if row["partition"] in {"OOS", "SEALED"}]
    if not _has_policy_outcomes(train_rows + validation_rows, _POLICIES):
        return _no_evidence("incomplete_policy_outcomes")

    walk_forward = _walk_forward(train_rows, validation_rows)
    validation_by_policy = {
        policy: _metrics(validation_rows, policy) for policy in _POLICIES
    }
    winner = _winner(validation_by_policy)
    if winner is None or not _has_policy_outcomes(oos_rows, (winner,)):
        return _no_evidence("incomplete_oos_evidence")

    return {
        "status": "VALIDATED",
        "winner": winner,
        "train_metrics": _metrics(train_rows, winner),
        "validation_metrics": validation_by_policy[winner],
        "walk_forward": walk_forward,
        "oos_metrics": _metrics(oos_rows, winner),
        "artifact": {
            "validated": True,
            "complete": True,
            "policy": winner,
            "normalized_parameters": dict(packets[winner]),
        },
    }


def _validated_packets(policy_packets: Any) -> dict[str, Mapping[str, float]] | None:
    if not isinstance(policy_packets, Mapping) or set(policy_packets) != set(_POLICIES):
        return None
    parameters: dict[str, Mapping[str, float]] = {}
    for policy in _POLICIES:
        packet = policy_packets[policy]
        if not isinstance(packet, Mapping):
            return None
        if not isinstance(packet.get("hypothesis_id"), str) or not packet["hypothesis_id"].strip():
            return None
        if not isinstance(packet.get("data_observation"), Mapping) or not packet.get("falsification"):
            return None
        origin = packet.get("origin")
        coverage = packet.get("BOOK_COVERAGE")
        support = packet.get("supporting_evidence")
        if origin == "BOOK_DIRECT":
            if coverage != "SUFFICIENT" or not isinstance(support, list) or not support:
                return None
        elif origin == "NOVEL_SYNTHESIZED_HYPOTHESIS":
            if coverage != "INSUFFICIENT" or support != []:
                return None
        else:
            return None
        normalized = packet.get("normalized_parameters")
        if not isinstance(normalized, Mapping) or set(normalized) != _PARAMETER_KEYS:
            return None
        if not all(_finite_number(value) for value in normalized.values()):
            return None
        if normalized["r_multiple"] <= 0 or normalized["cost_r"] < 0:
            return None
        parameters[policy] = normalized
    return parameters


def _prepare_rows(rows: Any) -> list[dict[str, Any]] | str | None:
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)) or not rows:
        return None
    prepared: list[dict[str, Any]] = []
    last_timestamp: float | None = None
    last_partition = -1
    for row in rows:
        if not isinstance(row, Mapping):
            return None
        timestamp = _timestamp(row.get("timestamp"))
        partition = row.get("partition")
        if timestamp is None or partition not in _PARTITION_ORDER:
            return None
        if last_timestamp is not None and timestamp <= last_timestamp:
            return None
        if _PARTITION_ORDER[partition] < last_partition:
            return None
        if "cost_usd" not in row or not _finite_number(row.get("cost_usd")) or row["cost_usd"] < 0:
            return "missing_cost"
        if not _finite_number(row.get("initial_risk_usd")) or row["initial_risk_usd"] <= 0:
            return None
        if not _finite_number(row.get("capture_ratio")) or not _finite_number(row.get("turnover")):
            return None
        if row["turnover"] < 0:
            return None
        prepared.append(dict(row))
        last_timestamp = timestamp
        last_partition = _PARTITION_ORDER[partition]
    return prepared


def _has_policy_outcomes(rows: Sequence[Mapping[str, Any]], policies: Sequence[str]) -> bool:
    for row in rows:
        outcomes = row.get("policy_outcomes")
        if not isinstance(outcomes, Mapping):
            return False
        for policy in policies:
            outcome = outcomes.get(policy)
            if not isinstance(outcome, Mapping) or not _finite_number(outcome.get("gross_pnl_usd")):
                return False
    return True


def _walk_forward(train_rows: Sequence[Mapping[str, Any]], validation_rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    history = list(train_rows)
    replay: list[dict[str, Any]] = []
    for row in validation_rows:
        historical_metrics = {policy: _metrics(history, policy) for policy in _POLICIES}
        winner = _winner(historical_metrics)
        if winner is None:
            return []
        replay.append({"timestamp": row["timestamp"], "winner": winner})
        history.append(row)
    return replay


def _metrics(rows: Sequence[Mapping[str, Any]], policy: str) -> dict[str, float]:
    returns = [
        (row["policy_outcomes"][policy]["gross_pnl_usd"] - row["cost_usd"])
        / row["initial_risk_usd"]
        for row in rows
    ]
    gross_profit = sum(value for value in returns if value > 0)
    gross_loss = -sum(value for value in returns if value < 0)
    profit_factor = gross_profit / gross_loss if gross_loss else float("inf")
    equity = peak = 0.0
    max_drawdown = 0.0
    for value in returns:
        equity += value
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)
    return {
        "expectancy_r": sum(returns) / len(returns),
        "profit_factor": profit_factor,
        "tail_r": min(returns),
        "max_drawdown_r": max_drawdown,
        "capture_ratio": sum(row["capture_ratio"] for row in rows) / len(rows),
        "turnover": sum(row["turnover"] for row in rows),
        "win_rate": sum(value > 0 for value in returns) / len(returns),
    }


def _winner(metrics_by_policy: Mapping[str, Mapping[str, float]]) -> str | None:
    if not metrics_by_policy:
        return None
    return max(
        metrics_by_policy,
        key=lambda policy: (
            _score_value(metrics_by_policy[policy]["expectancy_r"]),
            _score_value(metrics_by_policy[policy]["profit_factor"]),
            _score_value(metrics_by_policy[policy]["tail_r"]),
            -_score_value(metrics_by_policy[policy]["max_drawdown_r"]),
            _score_value(metrics_by_policy[policy]["capture_ratio"]),
            -_score_value(metrics_by_policy[policy]["turnover"]),
            policy,
        ),
    )


def _score_value(value: float) -> float:
    """Ignore binary representation noise before applying ordered policy gates."""
    return round(value, 12) if isfinite(value) else value


def _timestamp(value: Any) -> float | None:
    if _finite_number(value):
        return float(value)
    if isinstance(value, datetime):
        return value.timestamp()
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return None
    return None


def _finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value)


def _no_evidence(reason: str) -> dict[str, str]:
    return {"status": "NO_EVIDENCE", "reason": reason}
