"""Chronological, research-only validation for Firehose basket policies."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from hashlib import sha256
from math import isfinite
from pathlib import Path
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
    if isinstance(prepared, str):
        return _no_evidence({
            "missing_cost": "missing_cost_evidence",
            "missing_features": "missing_feature_evidence",
            "future_features": "future_feature_evidence",
            "missing_lifecycle": "missing_lifecycle_evidence",
        }[prepared])

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
    walk_forward_by_policy = _walk_forward_metrics(walk_forward)
    winner = _winner(walk_forward_by_policy)
    if winner is None or not _has_policy_outcomes(oos_rows, (winner,)):
        return _no_evidence("incomplete_oos_evidence")
    validation_by_policy = {
        policy: _metrics(validation_rows, policy) for policy in _POLICIES
    }

    return {
        "status": "VALIDATED",
        "winner": winner,
        "train_metrics": _metrics(train_rows, winner),
        "validation_metrics": validation_by_policy[winner],
        "walk_forward": walk_forward,
        "walk_forward_metrics": walk_forward_by_policy[winner],
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
        contradictions = packet.get("contradicting_evidence")
        if not isinstance(contradictions, list) or not all(
            _valid_evidence_record(record, "CONTRADICTION") for record in contradictions
        ):
            return None
        if origin == "BOOK_DIRECT":
            if (
                coverage != "SUFFICIENT"
                or not isinstance(support, list)
                or not support
                or not all(_valid_evidence_record(record, "SUPPORT") for record in support)
            ):
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
        feature_status = _feature_status(row.get("features"), timestamp)
        if feature_status is not None:
            return feature_status
        if not _complete_lifecycle(row.get("lifecycle"), timestamp):
            return "missing_lifecycle"
        prepared.append(dict(row))
        last_timestamp = timestamp
        last_partition = _PARTITION_ORDER[partition]
    return prepared


def _valid_evidence_record(record: Any, label: str) -> bool:
    if not isinstance(record, Mapping):
        return False
    source_id = record.get("source_id")
    file_hash = record.get("file_hash")
    location = record.get("location")
    line_start = location.get("line_start") if isinstance(location, Mapping) else None
    line_end = location.get("line_end") if isinstance(location, Mapping) else None
    return (
        _text(record.get("filename"))
        and _hash(file_hash)
        and source_id == file_hash
        and record.get("evidence_label") == label
        and _text(record.get("passage"))
        and isinstance(location, Mapping)
        and _text(location.get("path"))
        and _positive_int(line_start)
        and _positive_int(line_end)
        and line_end >= line_start
        and _matches_source_content(record)
    )


def _matches_source_content(record: Mapping[str, Any]) -> bool:
    location = record["location"]
    try:
        path = Path(location["path"])
        body = path.read_bytes()
        lines = body.decode("utf-8").splitlines()
    except (OSError, UnicodeDecodeError, TypeError):
        return False
    line_start = location["line_start"]
    line_end = location["line_end"]
    if path.name != record["filename"] or line_end > len(lines):
        return False
    return (
        sha256(body).hexdigest() == record["file_hash"]
        and "\n".join(lines[line_start - 1:line_end]) == record["passage"]
    )


def _feature_status(features: Any, timestamp: float) -> str | None:
    if not isinstance(features, Mapping) or not features:
        return "missing_features"
    for feature in features.values():
        if not isinstance(feature, Mapping) or "value" not in feature:
            return "missing_features"
        available_at = _timestamp(feature.get("available_at"))
        if available_at is None:
            return "missing_features"
        if available_at > timestamp:
            return "future_features"
    return None


def _complete_lifecycle(lifecycle: Any, timestamp: float) -> bool:
    if not isinstance(lifecycle, Mapping):
        return False
    opened_at = _timestamp(lifecycle.get("opened_at"))
    closed_at = _timestamp(lifecycle.get("closed_at"))
    if opened_at is None or closed_at is None or not opened_at < closed_at <= timestamp:
        return False
    if lifecycle.get("confirmed_close") is not True:
        return False
    if not _text(lifecycle.get("basket_id")) or not _text(lifecycle.get("ticket_id")):
        return False
    if not all(_finite_number(lifecycle.get(field)) for field in (
        "mfe_usd", "mae_usd", "peak_net_profit_usd", "realized_net_usd",
        "capture_ratio", "age_seconds", "ev", "cost_usd", "turnover",
    )):
        return False
    if lifecycle["age_seconds"] < 0 or lifecycle["cost_usd"] < 0 or lifecycle["turnover"] < 0:
        return False
    if not _positive_int(lifecycle.get("clips")):
        return False
    reasons = lifecycle.get("decision_reasons")
    return (
        isinstance(reasons, list)
        and bool(reasons)
        and all(_text(reason) for reason in reasons)
        and _text(lifecycle.get("regime"))
        and _text(lifecycle.get("session"))
    )


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
        outcome = row["policy_outcomes"][winner]
        costed_return = (outcome["gross_pnl_usd"] - row["cost_usd"]) / row["initial_risk_usd"]
        replay.append({
            "timestamp": row["timestamp"],
            "winner": winner,
            "gross_pnl_usd": outcome["gross_pnl_usd"],
            "cost_usd": row["cost_usd"],
            "initial_risk_usd": row["initial_risk_usd"],
            "costed_return_r": costed_return,
            "capture_ratio": row["capture_ratio"],
            "turnover": row["turnover"],
        })
        history.append(row)
    return replay


def _walk_forward_metrics(decisions: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, float]]:
    by_policy: dict[str, list[Mapping[str, Any]]] = {}
    for decision in decisions:
        by_policy.setdefault(decision["winner"], []).append(decision)
    return {
        policy: _metrics_from_observations(
            [decision["costed_return_r"] for decision in values],
            [decision["capture_ratio"] for decision in values],
            [decision["turnover"] for decision in values],
        )
        for policy, values in by_policy.items()
    }


def _metrics(rows: Sequence[Mapping[str, Any]], policy: str) -> dict[str, float]:
    returns = [
        (row["policy_outcomes"][policy]["gross_pnl_usd"] - row["cost_usd"])
        / row["initial_risk_usd"]
        for row in rows
    ]
    return _metrics_from_observations(
        returns,
        [row["capture_ratio"] for row in rows],
        [row["turnover"] for row in rows],
    )


def _metrics_from_observations(
    returns: Sequence[float], capture_ratios: Sequence[float], turnovers: Sequence[float],
) -> dict[str, float]:
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
        "capture_ratio": sum(capture_ratios) / len(capture_ratios),
        "turnover": sum(turnovers),
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


def _positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _hash(value: Any) -> bool:
    return _text(value) and len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _no_evidence(reason: str) -> dict[str, str]:
    return {"status": "NO_EVIDENCE", "reason": reason}
