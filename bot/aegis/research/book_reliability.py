"""Conservative, deduplicated reliability evidence for book rules.

The artifact is research-only.  Positive aggregate replay statistics are
deliberately insufficient for runtime activation; independent chronological
splits must be supplied by a later governed promotion step.
"""
from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any


_REPLAY_SCHEMA = "book_strategy_historical_replay.v1"
_ARTIFACT_SCHEMA = "aegis.book_algorithm_reliability.v1"
_PREDICTION_SCOPE = "GITHUB_TOOLS_AND_BOOK_ALGORITHMS_ONLY"


def _finite(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def _count(value: Any) -> int | None:
    number = _finite(value)
    if number is None or not number.is_integer() or number < 0:
        return None
    return int(number)


def _passes_split(stats: Mapping[str, Any], *, min_signal_samples: int, min_losses: int) -> bool:
    samples = _count(stats.get("signal_samples"))
    wins = _count(stats.get("wins"))
    losses = _count(stats.get("losses"))
    expectancy = _finite(stats.get("expectancy"))
    expectancy_lcb95 = _finite(stats.get("expectancy_lcb95"))
    profit_factor = _finite(stats.get("profit_factor"))
    return bool(
        samples is not None
        and wins is not None
        and losses is not None
        and samples >= int(min_signal_samples)
        and wins >= int(min_losses)
        and losses >= int(min_losses)
        and expectancy is not None
        and expectancy > 0.0
        and expectancy_lcb95 is not None
        and expectancy_lcb95 > 0.0
        and profit_factor is not None
        and profit_factor > 1.0
    )


def build_book_reliability_artifact(
    replay_report: Mapping[str, Any],
    *,
    min_signal_samples: int = 50,
    min_losses: int = 5,
) -> dict[str, Any]:
    """Build deduplicated shadow evidence from a book replay report."""
    if not isinstance(replay_report, Mapping):
        raise ValueError("replay report must be a mapping")
    if replay_report.get("schema") != _REPLAY_SCHEMA:
        raise ValueError("replay report schema mismatch")
    if (
        replay_report.get("research_only") is not True
        or replay_report.get("execution_authority") is not False
    ):
        raise ValueError("replay report must be research-only")
    if replay_report.get("no_lookahead") is not True:
        raise ValueError("replay report must declare no lookahead")
    if replay_report.get("pre_enriched_rows") is True:
        raise ValueError("pre-enriched row replay is not eligible for reliability")
    if int(min_signal_samples) < 1 or int(min_losses) < 1:
        raise ValueError("reliability thresholds must be positive")

    raw_groups = replay_report.get("evaluator_groups")
    strategies = replay_report.get("strategies")
    if not isinstance(raw_groups, list) or not isinstance(strategies, Mapping):
        raise ValueError("replay report evaluator groups and strategies are required")
    declared_group_count = _count(replay_report.get("evaluator_group_count"))
    if declared_group_count is not None and declared_group_count != len(raw_groups):
        raise ValueError("replay report evaluator group count mismatch")

    raw_split_replay = replay_report.get("split_replay")
    split_names = ("train", "validation", "sealed")
    split_groups: dict[str, dict[str, Mapping[str, Any]]] = {}
    if raw_split_replay is not None:
        if not isinstance(raw_split_replay, Mapping):
            raise ValueError("split replay must be a mapping")
        for split_name in split_names:
            split = raw_split_replay.get(split_name)
            if not isinstance(split, Mapping):
                raise ValueError("split replay is missing a required split")
            if (
                split.get("no_lookahead") is not True
                or split.get("research_only") is not True
                or split.get("execution_authority") is not False
            ):
                raise ValueError("split replay must be research-only")
            raw_split_groups = split.get("groups")
            if not isinstance(raw_split_groups, list):
                raise ValueError("split replay groups are required")
            indexed: dict[str, Mapping[str, Any]] = {}
            for raw_split_group in raw_split_groups:
                if not isinstance(raw_split_group, Mapping):
                    raise ValueError("split replay group is invalid")
                group_id = str(raw_split_group.get("group_id") or "").strip()
                if not group_id or group_id in indexed:
                    raise ValueError("split replay group identity is invalid")
                indexed[group_id] = raw_split_group
            split_groups[split_name] = indexed

    groups: list[dict[str, Any]] = []
    for raw_group in raw_groups:
        if not isinstance(raw_group, Mapping):
            raise ValueError("evaluator group must be a mapping")
        group_id = str(raw_group.get("group_id") or "").strip()
        representative = str(raw_group.get("representative_record_id") or "").strip()
        record_ids = raw_group.get("record_ids")
        if not group_id or not representative or not isinstance(record_ids, list):
            raise ValueError("evaluator group identity is incomplete")
        if representative not in strategies or not record_ids:
            raise ValueError("evaluator group representative is missing")
        if any(str(record_id).strip() not in strategies for record_id in record_ids):
            raise ValueError("evaluator group contains an unknown record")
        duplicate_count = _count(raw_group.get("duplicate_count"))
        if duplicate_count is None:
            duplicate_count = len(record_ids)
        if duplicate_count != len(record_ids):
            raise ValueError("evaluator group duplicate count mismatch")
        stats = strategies[representative]
        if not isinstance(stats, Mapping):
            raise ValueError("representative strategy statistics are missing")
        samples = _count(stats.get("signal_samples"))
        wins = _count(stats.get("wins"))
        losses = _count(stats.get("losses"))
        if samples is None or wins is None or losses is None:
            raise ValueError("strategy signal statistics are invalid")
        expectancy = _finite(stats.get("expectancy"))
        profit_factor = _finite(stats.get("profit_factor"))
        p95_loss = _finite(stats.get("p95_loss"))
        candidate = (
            samples >= int(min_signal_samples)
            and wins >= int(min_losses)
            and losses >= int(min_losses)
            and expectancy is not None
            and expectancy > 0.0
            and profit_factor is not None
            and profit_factor > 1.0
        )
        if split_groups:
            split_statuses: dict[str, str] = {}
            for split_name in split_names:
                split_stats = split_groups[split_name].get(group_id)
                if split_stats is None:
                    raise ValueError("split replay group coverage is incomplete")
                split_statuses[split_name] = (
                    "PASS"
                    if _passes_split(
                        split_stats,
                        min_signal_samples=int(min_signal_samples),
                        min_losses=int(min_losses),
                    )
                    else "REJECTED"
                )
            independent_status = (
                "PASS"
                if all(value == "PASS" for value in split_statuses.values())
                else "REJECTED"
            )
        else:
            split_statuses = {}
            independent_status = "NOT_AVAILABLE"
        groups.append(
            {
                "group_id": group_id,
                "implementation_status": str(raw_group.get("implementation_status") or ""),
                "representative_record_id": representative,
                "record_ids": [str(record_id) for record_id in record_ids],
                "duplicate_count": duplicate_count,
                "source_title": str(raw_group.get("source_title") or "") or None,
                "strategy_family": str(raw_group.get("strategy_family") or "") or None,
                "signal_samples": samples,
                "wins": wins,
                "losses": losses,
                "expectancy": expectancy,
                "expectancy_lcb95": _finite(stats.get("expectancy_lcb95")),
                "profit_factor": profit_factor,
                "p95_loss": p95_loss,
                "candidate_status": (
                    "REQUIRES_INDEPENDENT_SPLITS" if candidate
                    else "INSUFFICIENT_OR_NEGATIVE_EVIDENCE"
                ),
                "independent_split_status": independent_status,
                "independent_split_results": split_statuses,
            }
        )
    groups.sort(key=lambda item: item["group_id"])
    candidates = [
        {
            "group_id": item["group_id"],
            "representative_record_id": item["representative_record_id"],
            "candidate_status": item["candidate_status"],
        }
        for item in groups
        if item["candidate_status"] == "REQUIRES_INDEPENDENT_SPLITS"
    ]
    independent_candidates = [
        {
            "group_id": item["group_id"],
            "representative_record_id": item["representative_record_id"],
        }
        for item in groups
        if (
            item["candidate_status"] == "REQUIRES_INDEPENDENT_SPLITS"
            and item["independent_split_status"] == "PASS"
        )
    ]
    if not split_groups:
        independent_split_status = "NOT_AVAILABLE"
        activation_reason = "independent_split_evidence_required"
    elif independent_candidates:
        independent_split_status = "PASS"
        activation_reason = "governed_runtime_artifact_required"
    else:
        independent_split_status = "REJECTED"
        activation_reason = "no_group_passed_independent_split_gates"
    return {
        "schema": _ARTIFACT_SCHEMA,
        "prediction_scope": _PREDICTION_SCOPE,
        "status": "SHADOW_ONLY",
        "runtime_activation": False,
        "activation_reason": activation_reason,
        "book_record_count": _count(replay_report.get("book_record_count")) or 0,
        "evaluator_group_count": len(raw_groups),
        "deduplicated_group_count": len(groups),
        "candidate_count": len(candidates),
        "candidates": candidates,
        "independent_split_status": independent_split_status,
        "independent_candidate_count": len(independent_candidates),
        "independent_candidates": independent_candidates,
        "groups": groups,
        "source_replay_schema": _REPLAY_SCHEMA,
        "split_replay_purge_seconds": _finite(
            replay_report.get("split_replay_purge_seconds")
        ),
        "split_replay_policy": str(
            replay_report.get("split_replay_policy") or "unknown"
        ),
        "no_lookahead": True,
        "research_only": True,
        "execution_authority": False,
        "notes": [
            "Duplicate extracted records share one evaluator group and one evidence row.",
            "Aggregate replay positivity is not independent OOS proof.",
            "Independent split activation requires a positive 95% expectancy lower confidence bound.",
            "No group in this artifact authorizes broker execution.",
        ],
    }


__all__ = ["build_book_reliability_artifact"]
