"""Chronological, read-only replay of the testable book strategy records.

The registry is already a research artifact.  This module does not extract or
rewrite book material: it evaluates records that have either an exact compiled
predicate, an explicitly mapped family perspective, or a known-family context
view. Context views do not recover missing entry/exit parameters and are never
execution authority. Records without a known family remain visible as
``SPECIFICATION_ONLY``.
"""
from __future__ import annotations

import json
import hashlib
import math
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping

from .book_strategy_extraction import source_label_from_path
from .book_strategy_evidence import compact_context_event
from .watcher_book_perspectives import evaluate_book_algorithm, strategy_implementation_status
from .watcher_historical_replay import build_pre_entry_state


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def _net_outcome(row: Mapping[str, Any]) -> float | None:
    for key in ("captured_exit_net_pnl", "exit_capturedexitreplay_net_pnl"):
        value = _number(row.get(key))
        if value is not None:
            return value
    return None


def _record_id(record: Mapping[str, Any], index: int) -> str:
    algorithm = record.get("algorithm")
    algorithm = algorithm if isinstance(algorithm, Mapping) else {}
    return str(record.get("strategy_id") or algorithm.get("algorithm_id") or f"record_{index}")


def _family(record: Mapping[str, Any]) -> str:
    algorithm = record.get("algorithm")
    algorithm = algorithm if isinstance(algorithm, Mapping) else {}
    return str(record.get("strategy_family") or algorithm.get("family") or "").strip().lower()


def _signature(record: Mapping[str, Any], implementation: str) -> str:
    if implementation == "WATCHER_EXACT_RULE":
        algorithm = record.get("algorithm")
        algorithm = algorithm if isinstance(algorithm, Mapping) else {}
        payload = {
            "status": "CODED_EXACT",
            "side_rule": record.get("side_rule"),
            "family": _family(record),
            "compiled_entry_predicates": algorithm.get("compiled_entry_predicates"),
        }
        return "exact:" + json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    if implementation in {"WATCHER_FAMILY_PERSPECTIVE", "WATCHER_FAMILY_CONTEXT"}:
        return "family:" + _family(record)
    return "specification:" + _record_id(record, 0)


def _bucket(record: Mapping[str, Any], implementation: str) -> dict[str, Any]:
    source_path = str(record.get("source_path") or "").strip()
    source_title = source_label_from_path(source_path) if source_path else str(record.get("source_title") or "")
    return {
        "strategy_id": _record_id(record, 0),
        "source_title": source_title,
        "strategy_family": _family(record) or None,
        "implementation_status": implementation,
        "evaluated": 0,
        "applicable": 0,
        "signal_samples": 0,
        "wins": 0,
        "losses": 0,
        "draws": 0,
        "net_pnl": 0.0,
        "sum_pnl_sq": 0.0,
        "view_counts": Counter(),
        "reason_counts": Counter(),
        "loss_values": [],
    }


def _update(bucket: dict[str, Any], result: Mapping[str, Any], state: Mapping[str, Any], net: float | None) -> None:
    bucket["evaluated"] += 1
    view = str(result.get("view") or "UNKNOWN")
    bucket["view_counts"][view] += 1
    for reason in result.get("reasons") or ():
        bucket["reason_counts"][str(reason)] += 1
    if result.get("applicability") == "APPLICABLE":
        bucket["applicable"] += 1
    side = str(state.get("side") or "").upper()
    if net is None or view != side or result.get("applicability") != "APPLICABLE":
        return
    bucket["signal_samples"] += 1
    bucket["net_pnl"] += net
    bucket["sum_pnl_sq"] += net * net
    if net > 0:
        bucket["wins"] += 1
    elif net < 0:
        bucket["losses"] += 1
        bucket["loss_values"].append(net)
    else:
        bucket["draws"] += 1


def _finalize(bucket: dict[str, Any]) -> dict[str, Any]:
    samples = int(bucket["signal_samples"])
    losses = sorted(bucket.pop("loss_values", []))
    net = float(bucket["net_pnl"])
    sum_pnl_sq = float(bucket.pop("sum_pnl_sq", 0.0))
    gross_wins = net - sum(losses)
    result = dict(bucket)
    result["net_pnl"] = round(net, 12)
    result["win_rate"] = bucket["wins"] / samples if samples else None
    result["expectancy"] = net / samples if samples else None
    if samples >= 2:
        mean = net / samples
        variance = max((sum_pnl_sq - samples * mean * mean) / (samples - 1), 0.0)
        result["expectancy_lcb95"] = mean - 1.96 * math.sqrt(variance / samples)
    else:
        result["expectancy_lcb95"] = None
    result["profit_factor"] = gross_wins / abs(sum(losses)) if losses and gross_wins > 0 else (0.0 if losses else None)
    result["p95_loss"] = losses[max(0, math.ceil(len(losses) * 0.95) - 1)] if losses else None
    result["view_counts"] = dict(bucket["view_counts"])
    result["reason_counts"] = dict(bucket["reason_counts"])
    return result


def _normalize_split_ranges(
    split_ranges: Mapping[str, tuple[int, int]] | None,
) -> dict[str, tuple[int, int]]:
    """Validate disjoint row-index ranges for chronological split evidence."""
    if split_ranges is None:
        return {}
    if not isinstance(split_ranges, Mapping):
        raise ValueError("split ranges must be a mapping")
    normalized: dict[str, tuple[int, int]] = {}
    for raw_name, raw_bounds in split_ranges.items():
        name = str(raw_name or "").strip()
        if not name or not isinstance(raw_bounds, (list, tuple)) or len(raw_bounds) != 2:
            raise ValueError("split range is invalid")
        try:
            start = int(raw_bounds[0])
            end = int(raw_bounds[1])
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("split range is invalid") from exc
        if start < 0 or end <= start:
            raise ValueError("split range is invalid")
        normalized[name] = (start, end)
    ordered = sorted(normalized.values())
    if any(
        previous_end > start
        for (_, previous_end), (start, _) in zip(ordered, ordered[1:])
    ):
        raise ValueError("split ranges must be disjoint")
    return normalized


def replay_book_records(
    records: Iterable[Mapping[str, Any]],
    rows: Iterable[Mapping[str, Any]],
    *,
    max_rows: int | None = None,
    split_ranges: Mapping[str, tuple[int, int]] | None = None,
    pre_enriched_rows: bool = False,
) -> dict[str, Any]:
    """Replay every registry record that has a truthful Watcher implementation.

    Evaluator-equivalent records share one evaluation group for efficiency, but
    each registry record receives its own statistics and implementation status.
    The current row is evaluated before it is appended to history, and its net
    outcome is read only after evaluation.
    """
    normalized_splits = _normalize_split_ranges(split_ranges)
    materialized = [dict(record) for record in records if isinstance(record, Mapping)]
    strategies: dict[str, dict[str, Any]] = {}
    groups: dict[str, list[str]] = defaultdict(list)
    representatives: dict[str, Mapping[str, Any]] = {}
    implementation_counts = Counter()
    for index, record in enumerate(materialized):
        record_id = _record_id(record, index)
        if record_id in strategies:
            record_id = f"{record_id}#{index}"
        implementation = strategy_implementation_status(record)
        implementation_counts[implementation] += 1
        bucket = _bucket(record, implementation)
        bucket["strategy_id"] = record_id
        strategies[record_id] = bucket
        if implementation != "SPECIFICATION_ONLY":
            signature = _signature(record, implementation)
            groups[signature].append(record_id)
            representatives.setdefault(signature, record)
        else:
            bucket["reason_counts"]["source is incomplete or unsupported"] += 1

    evaluator_groups = []
    group_by_signature: dict[str, dict[str, Any]] = {}
    group_buckets: dict[str, dict[str, Any]] = {}
    for signature, record_ids in groups.items():
        if not record_ids:
            continue
        group = {
            "group_id": hashlib.sha256(signature.encode("utf-8")).hexdigest(),
            "implementation_status": strategies[record_ids[0]]["implementation_status"],
            "representative_record_id": record_ids[0],
            "record_ids": list(record_ids),
            "duplicate_count": len(record_ids),
            "source_title": strategies[record_ids[0]].get("source_title"),
            "strategy_family": strategies[record_ids[0]].get("strategy_family"),
        }
        evaluator_groups.append(group)
        group_by_signature[signature] = group
        group_buckets[signature] = _bucket(
            representatives[signature],
            group["implementation_status"],
        )
    evaluator_groups.sort(key=lambda item: item["group_id"])
    has_exact_group = any(
        group["implementation_status"] == "WATCHER_EXACT_RULE"
        for group in evaluator_groups
    )

    split_state: dict[str, dict[str, Any]] = {}
    for name, (start, end) in normalized_splits.items():
        split_state[name] = {
            "start": start,
            "end": end,
            "rows_replayed": 0,
            "rows_with_net_outcome": 0,
            "rows_without_net_outcome": 0,
            "first_time": None,
            "last_time": None,
            "groups": {
                signature: _bucket(
                    representatives[signature],
                    group_by_signature[signature]["implementation_status"],
                )
                for signature in groups
            },
        }

    rows_replayed = 0
    rows_with_outcome = 0
    rows_without_outcome = 0
    history_by_symbol: dict[str, deque[dict[str, Any]]] = defaultdict(lambda: deque(maxlen=5000))
    for row in rows:
        if max_rows is not None and rows_replayed >= max_rows:
            break
        if not isinstance(row, Mapping):
            continue
        row_index = rows_replayed
        rows_replayed += 1
        symbol = str(row.get("symbol") or "").strip()
        state = build_pre_entry_state(
            row,
            symbol_history=history_by_symbol.get(symbol, ()),
            universe_history=history_by_symbol,
            pre_enriched=pre_enriched_rows,
        )
        net = _net_outcome(row)
        if net is None:
            rows_without_outcome += 1
        else:
            rows_with_outcome += 1
        exact_context_snapshot = (
            compact_context_event(state)
            if has_exact_group
            else None
        )
        active_splits = []
        for name, state_info in split_state.items():
            if state_info["start"] <= row_index < state_info["end"]:
                active_splits.append(name)
                state_info["rows_replayed"] += 1
                if net is None:
                    state_info["rows_without_net_outcome"] += 1
                else:
                    state_info["rows_with_net_outcome"] += 1
                timestamp = row.get("time")
                if timestamp is not None:
                    if state_info["first_time"] is None:
                        state_info["first_time"] = timestamp
                    state_info["last_time"] = timestamp
        for signature, record_ids in groups.items():
            result = evaluate_book_algorithm(
                representatives[signature],
                state,
                context_snapshot=exact_context_snapshot,
                implementation_status=group_by_signature[signature]["implementation_status"],
            )
            # Evaluator-equivalent records share one causal result and one
            # evidence bucket.  Replicate the finalized statistics to each
            # record below instead of paying duplicate update cost per row.
            _update(group_buckets[signature], result, state, net)
            for name in active_splits:
                _update(split_state[name]["groups"][signature], result, state, net)
        if symbol:
            history = history_by_symbol[symbol]
            row_copy = dict(row)
            if history and row_copy.get("time") is not None and history[-1].get("time") == row_copy.get("time"):
                history[-1] = row_copy
            else:
                history.append(row_copy)

    finalized = {
        record_id: _finalize(bucket)
        for record_id, bucket in strategies.items()
        if bucket.get("implementation_status") == "SPECIFICATION_ONLY"
    }
    for signature, record_ids in groups.items():
        group_stats = _finalize(group_buckets[signature])
        for record_id in record_ids:
            record_stats = dict(group_stats)
            # A family perspective and a family context may share the same
            # evaluator signature but retain their own provenance/status.
            source_metadata = strategies[record_id]
            for key in ("strategy_id", "source_title", "strategy_family", "implementation_status"):
                record_stats[key] = record_id if key == "strategy_id" else source_metadata[key]
            finalized[record_id] = record_stats
    report = {
        "schema": "book_strategy_historical_replay.v1",
        "evidence_source": "fast_edge_shadow_rows",
        "feature_adapter": (
            "watcher_feature_engine.row_snapshot.v1"
            if pre_enriched_rows
            else "watcher_feature_engine.v1"
        ),
        "feature_history_order": "prior_rows_only",
        "outcome_field": "captured_exit_net_pnl",
        "outcome_attached_after_evaluation": True,
        "rows_replayed": rows_replayed,
        "rows_with_net_outcome": rows_with_outcome,
        "rows_without_net_outcome": rows_without_outcome,
        "book_record_count": len(materialized),
        "testable_record_count": sum(value for key, value in implementation_counts.items() if key != "SPECIFICATION_ONLY"),
        "evaluator_group_count": len(groups),
        "implementation_counts": dict(implementation_counts),
        "evaluator_groups": evaluator_groups,
        "strategies": finalized,
        "no_lookahead": True,
        "research_only": True,
        "execution_authority": False,
        "pre_enriched_rows": bool(pre_enriched_rows),
        "notes": [
            "Only CODED_EXACT and records with a mapped family perspective or context view are replayed.",
            "Records without a known family remain SPECIFICATION_ONLY and receive no fabricated statistics.",
            "WATCHER_FAMILY_CONTEXT records are contextual research views; missing rule parameters are not inferred.",
            "Each row is evaluated before its outcome is attached and before it enters history.",
            "A replay statistic is descriptive evidence, not execution authorization.",
        ],
    }
    if normalized_splits:
        split_report: dict[str, Any] = {}
        for name, state_info in split_state.items():
            split_groups = []
            for signature, bucket in state_info["groups"].items():
                group = group_by_signature[signature]
                finalized_group = _finalize(bucket)
                split_groups.append({
                    **group,
                    **{
                        key: finalized_group[key]
                        for key in (
                            "evaluated", "applicable", "signal_samples", "wins",
                            "losses", "draws", "net_pnl", "win_rate", "expectancy",
                            "expectancy_lcb95", "profit_factor", "p95_loss",
                            "view_counts", "reason_counts",
                        )
                    },
                })
            split_groups.sort(key=lambda item: item["group_id"])
            split_report[name] = {
                "row_start": state_info["start"],
                "row_end": state_info["end"],
                "rows_replayed": state_info["rows_replayed"],
                "rows_with_net_outcome": state_info["rows_with_net_outcome"],
                "rows_without_net_outcome": state_info["rows_without_net_outcome"],
                "history_start": state_info["first_time"],
                "history_end": state_info["last_time"],
                "groups": split_groups,
                "evaluator_group_count": len(split_groups),
                "no_lookahead": True,
                "research_only": True,
                "execution_authority": False,
            }
        report["split_replay_ranges"] = {
            name: {"start": start, "end": end}
            for name, (start, end) in normalized_splits.items()
        }
        report["split_replay"] = split_report
    return report


def iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    try:
        with Path(path).open(encoding="utf-8") as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(row, dict):
                    yield row
    except OSError:
        return


def replay_jsonl(
    strategy_path: Path,
    row_path: Path,
    *,
    max_rows: int | None = None,
    split_ranges: Mapping[str, tuple[int, int]] | None = None,
    pre_enriched_rows: bool = False,
) -> dict[str, Any]:
    report = replay_book_records(
        iter_jsonl(strategy_path),
        iter_jsonl(row_path),
        max_rows=max_rows,
        split_ranges=split_ranges,
        pre_enriched_rows=pre_enriched_rows,
    )
    report["strategy_path"] = str(Path(strategy_path))
    report["row_path"] = str(Path(row_path))
    return report


__all__ = ["iter_jsonl", "replay_book_records", "replay_jsonl"]
