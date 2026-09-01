"""Build a traceable external-DAG manifest from an existing shadow report."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import os
import sys
import time
from typing import Any, Mapping

BOT_ROOT = Path(__file__).resolve().parents[1]
if str(BOT_ROOT) not in sys.path:
    sys.path.insert(0, str(BOT_ROOT))


def _last_row(path: Path) -> Mapping[str, Any]:
    last = ""
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                last = line
    if not last:
        raise ValueError("shadow rows are empty")
    row = json.loads(last)
    if not isinstance(row, Mapping):
        raise ValueError("shadow row must be an object")
    return row


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _split(report: Mapping[str, Any], prefix: str) -> dict[str, Any]:
    def first(*keys: str) -> Any:
        for key in keys:
            value = report.get(key)
            if value is not None:
                return value
        return None

    values: dict[str, Any] = {}
    fields = {
        "n_trades": (f"OOS_{prefix}_N",),
        # Executable after-cost metrics are authoritative whenever the report
        # provides both executable and captured aggregates. Captured-only
        # fallback preserves older reports without inventing a value.
        "expectancy": (
            f"OOS_{prefix}_EXECUTABLE_CAPTURED_EXPECTANCY",
            f"OOS_{prefix}_CAPTURED_EXPECTANCY",
        ),
        "profit_factor": (
            f"OOS_{prefix}_EXECUTABLE_CAPTURED_PF",
            f"OOS_{prefix}_CAPTURED_PF",
        ),
        "expectancy_lcb95": (
            f"OOS_{prefix}_EXECUTABLE_CAPTURED_EXPECTANCY_LOWER_95",
            f"OOS_{prefix}_CAPTURED_EXPECTANCY_LOWER_95",
        ),
        "n_losses": (
            f"OOS_{prefix}_EXECUTABLE_CAPTURED_LOSSES",
            f"OOS_{prefix}_CAPTURED_LOSSES",
            f"OOS_{prefix}_LOSSES",
            f"OOS_{prefix}_N_LOSSES",
        ),
        "p95_loss": (f"OOS_{prefix}_P95_LOSS",),
        "p99_loss": (f"OOS_{prefix}_P99_LOSS",),
        "calibration_ece": (f"OOS_{prefix}_CALIBRATION_ECE",),
        "abstain_rate": (f"OOS_{prefix}_ABSTAIN_RATE",),
    }
    for target, keys in fields.items():
        value = first(*keys)
        if value is not None:
            values[target] = value
    return values


def _selected_replay_evidence(path: Path) -> tuple[list[str], dict[str, Any], dict[str, Any]]:
    """Extract bounded, causal replay evidence for the selected algorithms.

    The generic fast-edge leaderboard is a model-level report and may not
    describe the exact strategy identities that external tools are asked to
    replay.  A selected replay is therefore an explicit input contract.  We
    validate its bounded selection and preserve its split/exact-strategy
    evidence; missing or malformed evidence fails closed instead of silently
    producing a zero-strategy DAG.
    """
    replay_path = Path(path)
    try:
        replay = json.loads(replay_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"selected replay is unreadable: {replay_path}") from exc
    if not isinstance(replay, Mapping) or replay.get("schema") != "watcher_algorithm_historical_replay.v1":
        raise ValueError("selected replay schema is invalid")
    if replay.get("algorithm_selection") != "explicit_selected":
        raise ValueError("selected replay must be explicit_selected")
    raw_ids = replay.get("algorithm_ids")
    if not isinstance(raw_ids, (list, tuple)):
        raise ValueError("selected replay algorithm_ids are missing")
    ids = [str(value).strip() for value in raw_ids]
    if not 1 <= len(ids) <= 10 or any(not value for value in ids):
        raise ValueError("selected replay must contain 1 to 10 algorithms")
    if len(set(ids)) != len(ids):
        raise ValueError("selected replay algorithm_ids are not unique")
    if replay.get("algorithm_count") is not None and int(replay.get("algorithm_count")) != len(ids):
        raise ValueError("selected replay algorithm_count does not match algorithm_ids")
    aggregate = replay.get("algorithms")
    if not isinstance(aggregate, Mapping):
        raise ValueError("selected replay aggregate metrics are missing")
    metrics: dict[str, Any] = {}
    for algorithm_id in ids:
        item = aggregate.get(algorithm_id)
        if not isinstance(item, Mapping):
            raise ValueError(f"selected replay metrics missing: {algorithm_id}")
        metrics[algorithm_id] = dict(item)

    exact = replay.get("exact_strategies")
    if exact is not None and not isinstance(exact, Mapping):
        raise ValueError("selected replay exact_strategies are invalid")
    # Keep exact identities available to adapters without allowing an
    # unbounded registry/report to become the selected input.
    if isinstance(exact, Mapping):
        for algorithm_id in ids:
            scoped = {
                str(key): value
                for key, value in exact.items()
                if str(key).split("|", 1)[0] == algorithm_id
            }
            metrics[algorithm_id]["exact_strategies"] = scoped

    # A selected external run must be able to consume actual causal replay
    # outcomes rather than silently falling back to a synthetic fixture.  The
    # replay producer keeps this trace bounded per algorithm and attaches the
    # outcome only after the point-in-time decision was evaluated.
    raw_traces = replay.get("execution_traces")
    trace_provenance = replay.get("execution_trace_provenance")
    trace_counts: dict[str, int] = {}
    if isinstance(raw_traces, Mapping):
        for algorithm_id in ids:
            trace = raw_traces.get(algorithm_id)
            if not isinstance(trace, list):
                continue
            valid_trace: list[dict[str, Any]] = []
            for item in trace:
                if not isinstance(item, Mapping):
                    continue
                try:
                    outcome = float(item.get("net_outcome"))
                except (TypeError, ValueError, OverflowError):
                    continue
                if not math.isfinite(outcome):
                    continue
                valid_trace.append(dict(item))
            if valid_trace:
                metrics[algorithm_id]["execution_trace"] = valid_trace
                metrics[algorithm_id]["returns"] = [
                    float(item["net_outcome"]) for item in valid_trace
                ]
                trace_counts[algorithm_id] = len(valid_trace)

    try:
        replay_hash = _sha256(replay_path)
    except OSError as exc:
        raise ValueError(f"selected replay is unreadable: {replay_path}") from exc
    validation = {
        "schema": str(replay.get("schema")),
        "algorithm_selection": str(replay.get("algorithm_selection")),
        "algorithm_ids": list(ids),
        "algorithm_count": len(ids),
        "rows_replayed": replay.get("rows_replayed"),
        "rows_with_net_outcome": replay.get("rows_with_net_outcome"),
        "split_replay_ranges": replay.get("split_replay_ranges"),
        "split_replay_purge_rows": replay.get("split_replay_purge_rows"),
        "split_replay_policy": replay.get("split_replay_policy"),
        "split_replay": replay.get("split_replay"),
        "exact_strategies": exact if isinstance(exact, Mapping) else {},
        "rejection_adjustment": replay.get("rejection_adjustment"),
        "cost_model_provenance": replay.get("cost_model_provenance"),
        "no_lookahead": replay.get("no_lookahead") is True,
        "research_only": replay.get("research_only") is True,
        "execution_authority": replay.get("execution_authority"),
        "replay_report_sha256": replay_hash,
        "input_dataset_sha256": replay.get("input_dataset_sha256"),
        "source_path": str(replay_path.resolve()),
    }
    if trace_counts:
        validation["execution_trace_provenance"] = {
            "schema": str(
                trace_provenance.get("schema")
                if isinstance(trace_provenance, Mapping)
                else "aegis.replay_execution_trace.v1"
            ),
            "policy": str(
                trace_provenance.get("policy")
                if isinstance(trace_provenance, Mapping)
                else "selected_signal_after_cost_outcome"
            ),
            "counts_by_algorithm": trace_counts,
            "outcome_attached_after_evaluation": bool(
                trace_provenance.get("outcome_attached_after_evaluation")
                if isinstance(trace_provenance, Mapping)
                else False
            ),
        }
    return ids, metrics, validation


def build_manifest(
    report_path: Path,
    rows_path: Path,
    output_path: Path,
    *,
    selected_replay_path: Path | None = None,
) -> dict[str, Any]:
    report = json.loads(Path(report_path).read_text(encoding="utf-8"))
    if not isinstance(report, Mapping):
        raise ValueError("shadow report must be an object")
    row = _last_row(Path(rows_path))
    timestamp = time.time()
    metadata_path = BOT_ROOT / "intel" / "short_horizon_model" / "metadata.json"
    model_hash = hashlib.sha256(metadata_path.read_bytes()).hexdigest()
    state = {
        "symbol": str(row.get("symbol") or "").upper(),
        "side": str(row.get("side") or "").upper(),
        "horizon_s": int(float(row.get("horizon_s") or 0)),
        "bid": float(row.get("bid") or 0.0),
        "ask": float(row.get("ask") or 0.0),
        "spread_pips": float(row.get("spread") or 0.0) * 10000.0,
        "decision_ts": str(row.get("time") or ""),
    }
    validation = _split(report, "VALIDATION")
    sealed = _split(report, "SEALED")
    evidence: dict[str, Any] = {
        "target_definition": str(report.get("TARGET_DEFINITION") or ""),
        "dataset_hash": str(report.get("DATASET_HASH") or ""),
        "validation_hash": str(report.get("VALIDATION_HASH") or ""),
        "model_artifact_hash": model_hash,
        "chronological_test": _split(report, "TEST"),
        "sealed_oos": sealed,
        "calibration_ece": report.get("OOS_SEALED_CALIBRATION_ECE"),
        "p95_loss": report.get("OOS_SEALED_P95_LOSS"),
        "p99_loss": report.get("OOS_SEALED_P99_LOSS"),
        "abstain_rate": report.get("OOS_SEALED_ABSTAIN_RATE"),
        "perturbation_status": "UNTESTED",
        "replay_parity_status": "UNTESTED",
        "book_algorithm_count": 616,
        "authorized_symbols": [str(value).upper() for value in report.get("symbols") or ()],
        "authorized_horizons_s": [int(value) for value in report.get("horizons_s") or ()],
        "models": {},
        "created_at": timestamp,
        "expires_at": timestamp + 86400.0,
        "book_context": {},
    }
    if validation:
        evidence["validation_oos"] = validation
    if selected_replay_path is not None:
        selected_ids, selected_metrics, selected_validation = _selected_replay_evidence(
            selected_replay_path
        )
        replay_input_hash = selected_validation.get("input_dataset_sha256")
        if replay_input_hash:
            try:
                rows_hash = _sha256(Path(rows_path))
            except OSError as exc:
                raise ValueError("shadow rows are unreadable") from exc
            if str(replay_input_hash).lower() != rows_hash:
                raise ValueError("selected replay dataset does not match shadow rows")
        evidence.update(
            {
                "selected_strategy_ids": selected_ids,
                "selected_strategy_count": len(selected_ids),
                "selected_strategy_metrics": selected_metrics,
                "selected_strategy_validation": selected_validation,
            }
        )
    manifest = {
        "schema": "aegis.frozen_dataset_manifest.v1",
        "purpose": "current_github_tools_and_book_algorithms_shadow",
        "point_in_time_state": state,
        "validation_evidence": evidence,
    }
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    os.replace(temporary, destination)
    return {
        "manifest": str(destination),
        "dataset_hash": evidence["dataset_hash"],
        "validation_hash": evidence["validation_hash"],
        "rows_symbol": state["symbol"],
        "rows_time": state["decision_ts"],
        "validation_oos_present": "validation_oos" in evidence,
        "selected_strategy_count": len(evidence.get("selected_strategy_ids") or ()),
        "selected_strategy_replay": str(selected_replay_path) if selected_replay_path else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--rows", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--selected-replay",
        type=Path,
        help="bounded explicit-selected Watcher replay to pass to external domain tools",
    )
    args = parser.parse_args()
    print(
        json.dumps(
            build_manifest(
                args.report,
                args.rows,
                args.output,
                selected_replay_path=args.selected_replay,
            ),
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
