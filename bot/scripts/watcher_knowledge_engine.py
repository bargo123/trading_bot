#!/usr/bin/env python3
"""Read-only knowledge, shadow-replay, and outcome analysis for the Watcher.

This module deliberately has no broker, strategy, or production-runner imports.
It consumes copied journal observations and writes only under the Watcher report
directory.  Its opinions are research observations, never execution intent.
"""
from __future__ import annotations

import hashlib
import gzip
import json
import math
import os
import re
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

try:
    from .watcher_parquet import INDEX_FILE, append_study, flush_pending_to_parquet
except ImportError:
    from watcher_parquet import INDEX_FILE, append_study, flush_pending_to_parquet

try:
    from aegis.research.book_strategy_evidence import evaluate_strategy_evidence
except ImportError:  # pragma: no cover - direct script execution fallback
    evaluate_strategy_evidence = None


STRUCTURED_KB_FILES = (
    "concepts.jsonl",
    "strategy_hypotheses.jsonl",
    "entry_patterns.jsonl",
    "exit_patterns.jsonl",
    "execution_rules.jsonl",
    "validation_rules.jsonl",
    "risk_rules.jsonl",
    "firehose_hypotheses.jsonl",
)

# The compiled sinks above are the canonical corpus.  This separately compiled
# book-memory sink is also part of the repository knowledge base and is loaded
# without treating its research proxies as validated strategies.
ADDITIONAL_KB_FILES = ("research/book_memory/knowledge_records.jsonl",)

_CATEGORY_BY_FILE = {
    "concepts.jsonl": "concept",
    "strategy_hypotheses.jsonl": "strategy",
    "firehose_hypotheses.jsonl": "strategy",
    "entry_patterns.jsonl": "entry",
    "exit_patterns.jsonl": "exit",
    "execution_rules.jsonl": "execution",
    "validation_rules.jsonl": "validation",
    "risk_rules.jsonl": "risk",
    "research/book_memory/knowledge_records.jsonl": "knowledge",
}

_DECISION_EVENTS = {
    "candidate_blocked",
    "intel_brain_skip",
    "firehose_funnel.v1",
    "global_opportunity_discovered",
    "global_opportunity_allocation",
    "order_blocked",
    "order_check",
    "order",
    "open_skip",
    "spread_skip",
    "sizing_skip",
    "margin_precheck_skip",
    "oms_reject",
    "quote_unusable_for_scan",
    "quote_not_executable_for_send",
    "virtual_geometry_reject",
    "broker_geometry_reject",
    "firehose_open",
}

_QUOTE_EVENTS = {
    "quote",
    "tick",
    "quote_sample",
    "raw_tick",
}

_CLOSE_EVENTS = {
    "confirmed_close_finalization",
    "outcome_learning",
    "firehose_close",
    "firehose_close_unconfirmed",
}

RETENTION_INTERVAL_S = 600.0
ACTIVE_STUDY_LIMIT = 500
ARCHIVE_FRACTION = 0.30
ARCHIVE_RETENTION_S = 7 * 24 * 60 * 60


def _json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _first(source: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = source.get(key)
        if value is not None and value != "":
            return value
    return None


def _text(value: Any) -> str:
    return str(value or "").strip()


def _hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:20]


def _event_time(event: Mapping[str, Any]) -> float | None:
    value = _first(event, "timestamp", "observed_at", "ts", "time", "time_msc")
    if isinstance(value, (int, float)):
        number = _finite(value)
        if number is not None and number > 10_000_000_000:
            return number / 1000.0
        return number
    if value:
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
        except (TypeError, ValueError, OverflowError):
            return None
    return None


def _side(value: Any) -> str | None:
    normalized = _text(value).lower()
    return normalized if normalized in {"buy", "sell"} else None


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _state_has(state: Mapping[str, Any], *keys: str) -> bool:
    for key in keys:
        if key in state and state[key] is not None and state[key] != "":
            return True
    contexts = _mapping(state.get("context"))
    return any(key in contexts and contexts[key] is not None for key in keys)


def _required_data_fields(value: Any) -> list[str]:
    text = _text(value).lower()
    fields: list[str] = []
    if "m15" in text:
        fields.append("m15")
    if re.search(r"(?<!\d)m1(?!\d)", text):
        fields.append("m1")
    if "m5" in text:
        fields.append("m5")
    for needle, field in (
        ("structure", "structure"),
        ("spread", "spread"),
        ("quote", "quote"),
        ("tick", "quote"),
        ("volatility", "volatility"),
        ("atr", "volatility"),
        ("volume", "volume"),
        ("session", "session"),
        ("regime", "regime"),
        ("momentum", "momentum"),
    ):
        if needle in text:
            fields.append(field)
    return list(dict.fromkeys(fields))


def _required_values(value: Any) -> list[str]:
    text = _text(value).lower()
    if not text or text in {"unspecified", "any", "unknown", "none"}:
        return []
    return [item for item in re.split(r"[,/|+ ]+", text) if item and item not in {"or", "and"}]


def load_knowledge_library(knowledge_dir: Path) -> dict[str, Any]:
    """Load every structured knowledge sink with provenance intact."""
    root = Path(knowledge_dir)
    manifest = _json(root / "corpus_manifest.json", {})
    source_index = _json(root / "source_index.json", {})
    records: list[dict[str, Any]] = []
    counts_by_file: dict[str, int] = {}
    invalid_by_file: dict[str, int] = {}
    files: dict[str, dict[str, Any]] = {}
    all_sources = tuple(STRUCTURED_KB_FILES) + tuple(ADDITIONAL_KB_FILES)
    for name in all_sources:
        path = root / name if name in STRUCTURED_KB_FILES else root.parent / name
        rows = 0
        invalid = 0
        if path.is_file():
            try:
                with path.open(encoding="utf-8") as handle:
                    for line_number, line in enumerate(handle, 1):
                        if not line.strip():
                            continue
                        try:
                            raw = json.loads(line)
                        except json.JSONDecodeError:
                            invalid += 1
                            continue
                        if not isinstance(raw, Mapping):
                            invalid += 1
                            continue
                        raw_record = dict(raw)
                        rows += 1
                        record_id = _hash({"file": name, "line": line_number, "row": raw_record})
                        records.append({
                            "record_id": record_id,
                            "category": _CATEGORY_BY_FILE[name],
                            "source_file": name,
                            "source_line": line_number,
                            "raw_record": raw_record,
                            "provenance": {
                                "book": raw_record.get("book") or raw_record.get("source_title"),
                                "book_hash": raw_record.get("file_hash") or raw_record.get("source_hash"),
                                "passage_hash": raw_record.get("passage_hash"),
                                "location": raw_record.get("location") or raw_record.get("provenance"),
                            },
                            "applicability_requirements": {
                                "required_data": raw_record.get("required_data"),
                                "required_regime": raw_record.get("required_regime"),
                                "required_timeframe": raw_record.get("required_timeframe"),
                                "side_rule": raw_record.get("side_rule"),
                            },
                            "validation_status": raw_record.get("status") or "UNVALIDATED_RESEARCH",
                            "testability": "TESTABLE" if raw_record.get("falsification_condition") else "INSUFFICIENT_SPECIFICATION",
                        })
            except OSError:
                invalid += 1
        counts_by_file[name] = rows
        invalid_by_file[name] = invalid
        files[name] = {"exists": path.is_file(), "rows": rows, "invalid": invalid}

    counts = {
        "records": len(records),
        "strategy_records": sum(row["category"] == "strategy" for row in records),
        "concept_records": sum(row["category"] == "concept" for row in records),
        "entry_records": sum(row["category"] == "entry" for row in records),
        "exit_records": sum(row["category"] == "exit" for row in records),
        "execution_records": sum(row["category"] == "execution" for row in records),
        "validation_records": sum(row["category"] == "validation" for row in records),
        "risk_records": sum(row["category"] == "risk" for row in records),
        "book_memory_records": sum(row["category"] == "knowledge" for row in records),
    }
    source_files = source_index.get("files") if isinstance(source_index, Mapping) else []
    books = []
    if isinstance(source_files, list):
        books = [dict(item) for item in source_files if isinstance(item, Mapping)]
    result = {
        "schema": "watcher_knowledge_library.v1",
        "built_utc": datetime.now(timezone.utc).isoformat(),
        "corpus_version": manifest.get("corpus_version"),
        "manifest": manifest,
        "source_index": source_index,
        "books": books,
        "files": files,
        "counts": counts,
        "counts_by_file": counts_by_file,
        "invalid_by_file": invalid_by_file,
        "processed_all_structured_kb": all(item["exists"] for item in files.values()),
        "records": records,
        "strategy_records": [row for row in records if row["category"] == "strategy"],
    }
    return result


def evaluate_applicability(record: Mapping[str, Any], state: Mapping[str, Any]) -> dict[str, Any]:
    """Return applicability without filling missing market state."""
    source = _mapping(record.get("raw_record")) or record
    missing: list[str] = []
    reasons: list[str] = []
    required_regime = _required_values(source.get("required_regime"))
    current_regime = _text(state.get("regime")).lower()
    if required_regime:
        if not current_regime:
            missing.append("regime")
        elif current_regime not in required_regime:
            return {"status": "NOT_APPLICABLE", "missing": [], "reasons": ["regime_mismatch"]}

    required_timeframe = _required_values(source.get("required_timeframe"))
    if required_timeframe:
        current_timeframe = _text(state.get("timeframe")).lower()
        if not current_timeframe:
            for candidate, token in (("m1_context", "m1"), ("m5_context", "m5"), ("m15_context", "m15")):
                if _state_has(state, candidate):
                    current_timeframe = token
                    break
        if not current_timeframe:
            missing.append("timeframe")
        elif current_timeframe not in required_timeframe:
            return {"status": "NOT_APPLICABLE", "missing": [], "reasons": ["timeframe_mismatch"]}

    side_rule = _side(source.get("side_rule"))
    current_side = _side(state.get("side"))
    if side_rule and current_side and side_rule != current_side:
        return {"status": "NOT_APPLICABLE", "missing": [], "reasons": ["side_mismatch"]}

    for field in _required_data_fields(source.get("required_data")):
        aliases = {
            "m1": ("m1", "m1_context", "m1_features"),
            "m5": ("m5", "m5_context", "m5_features"),
            "m15": ("m15", "m15_context", "m15_features"),
            "quote": ("quote", "quotes", "tick", "quote_tick_dynamics"),
            "volatility": ("volatility", "vol", "atr", "volatility_context"),
            "structure": ("structure", "structure_context"),
            "spread": ("spread", "spread_pips", "spread_context"),
            "volume": ("volume", "volume_context"),
            "session": ("session",),
            "regime": ("regime",),
            "momentum": ("momentum", "momentum_context", "short_returns"),
        }[field]
        if not _state_has(state, *aliases):
            missing.append(field)
    if missing:
        reasons.extend(f"missing_{field}" for field in missing)
        return {"status": "INSUFFICIENT_DATA", "missing": list(dict.fromkeys(missing)), "reasons": reasons}
    return {"status": "APPLICABLE", "missing": [], "reasons": ["requirements_satisfied"]}


def evaluate_strategy(record: Mapping[str, Any], state: Mapping[str, Any]) -> dict[str, Any]:
    raw_record = _mapping(record.get("raw_record"))
    exact_statuses = {"CODED_EXACT", "FAMILY_PROXY", "UNTESTABLE_SOURCE", "COMPILE_ERROR"}
    if evaluate_strategy_evidence is not None and str(raw_record.get("status") or "").upper() in exact_statuses:
        evidence = evaluate_strategy_evidence(raw_record, state)
        evaluation_status = str(evidence.get("evaluation_status") or evidence.get("status") or "UNKNOWN")
        if evaluation_status == "MATCH":
            applicability = {"status": "APPLICABLE", "missing": [], "reasons": ["exact_predicates_satisfied"]}
            opinion = str(raw_record.get("side_rule") or state.get("side") or "NO_TRADE").upper()
        elif evaluation_status == "MISSING_INPUT":
            applicability = {
                "status": "INSUFFICIENT_DATA",
                "missing": list(evidence.get("missing") or []),
                "reasons": [f"missing_{item}" for item in evidence.get("missing") or []],
            }
            opinion = "NOT_APPLICABLE"
        elif evaluation_status == "NO_MATCH":
            applicability = {
                "status": "NOT_APPLICABLE",
                "missing": [],
                "reasons": [f"predicate_failed:{item}" for item in evidence.get("failed_predicates") or []],
            }
            opinion = "NOT_APPLICABLE"
        else:
            applicability = {"status": "NOT_APPLICABLE", "missing": [], "reasons": [str(evidence.get("reason") or "context_only")]}
            opinion = "NOT_APPLICABLE"
        return {
            "record_id": record.get("record_id") or raw_record.get("strategy_id"),
            "book": record.get("provenance", {}).get("book") or raw_record.get("source_title"),
            "source_file": record.get("source_file") or raw_record.get("source_path"),
            "source_line": record.get("source_line"),
            "provenance": record.get("provenance", {}),
            "strategy_family": raw_record.get("strategy_family"),
            "opinion": opinion,
            "reason": str(evidence.get("reason") or evaluation_status.lower()),
            "applicability": applicability,
            "applicability_status": applicability["status"],
            "evidence_status": evidence.get("evidence_status"),
            "evaluation_status": evaluation_status,
            "context_hash": evidence.get("context_hash"),
            "failed_predicates": evidence.get("failed_predicates", []),
            "missing": evidence.get("missing", []),
            "execution_authority": False,
            "uses_future_data": False,
            "validation_status": record.get("validation_status") or raw_record.get("validation_status"),
        }
    applicability = evaluate_applicability(record, state)
    side_rule = _side(record.get("side_rule") or raw_record.get("side_rule"))
    opinion = side_rule or "NO_TRADE"
    reason = "source_direction_rule" if side_rule else "no_directional_rule"
    if applicability["status"] != "APPLICABLE":
        opinion = "NOT_APPLICABLE"
        reason = ";".join(applicability["reasons"]) or applicability["status"].lower()
    return {
        "record_id": record.get("record_id"),
        "book": record.get("provenance", {}).get("book"),
        "source_file": record.get("source_file"),
        "source_line": record.get("source_line"),
        "provenance": record.get("provenance", {}),
        "strategy_family": raw_record.get("strategy_family"),
        "opinion": opinion.upper(),
        "reason": reason,
        "applicability": applicability,
        "applicability_status": applicability["status"],
        "evidence_status": "LEGACY_UNCOMPILED",
        "evaluation_status": applicability["status"],
        "execution_authority": False,
        "uses_future_data": False,
        "validation_status": record.get("validation_status"),
    }


def _state_from_event(event: Mapping[str, Any]) -> dict[str, Any]:
    state: dict[str, Any] = {}
    for key, value in event.items():
        if key not in {"candidate_evaluations", "counterfactual_quotes", "quotes"}:
            state[key] = value
    for key in ("candidate_details", "entry_state", "decision_snapshot", "context"):
        value = event.get(key)
        if isinstance(value, Mapping):
            state.update(dict(value))
    state.setdefault("symbol", _first(event, "symbol", "position_symbol"))
    state.setdefault("side", _first(event, "side", "position_side"))
    state.setdefault("mechanism", _first(event, "mechanism", "family", "setup_family"))
    state.setdefault("horizon_s", _first(event, "horizon_s", "search_horizon_s", "max_hold_s"))
    return {key: value for key, value in state.items() if value is not None}


def _strategy_identity(state: Mapping[str, Any]) -> str | None:
    symbol = _text(state.get("symbol") or state.get("position_symbol")).upper()
    side = _side(state.get("side") or state.get("position_side"))
    mechanism = _text(state.get("mechanism") or state.get("family") or state.get("setup_family"))
    horizon = state.get("horizon_s") or state.get("search_horizon_s") or state.get("max_hold_s")
    if not symbol or not side or not mechanism or horizon is None:
        return None
    try:
        horizon_text = str(int(float(horizon))) if float(horizon).is_integer() else str(float(horizon))
    except (TypeError, ValueError, OverflowError):
        horizon_text = _text(horizon)
    if not horizon_text:
        return None
    return "|".join((symbol, side, mechanism, horizon_text))


def _strategy_ids(state: Mapping[str, Any]) -> list[str]:
    values = state.get("strategy_ids") or state.get("strategy_id") or state.get("strategy_record_id") or state.get("hypothesis_id")
    if isinstance(values, str):
        values = [values]
    return [str(value) for value in values or [] if value]


def _compact_candidate_state(state: Mapping[str, Any]) -> dict[str, Any]:
    fields = {
        "candidate_id", "symbol", "side", "mechanism", "horizon_s", "timestamp", "status", "final_status",
        "reason", "reject_reason", "block_reason", "entry", "stop", "target", "spread_pips", "expected_net_ev",
        "risk_usd", "lots", "tail_risk", "portfolio_ok", "distance_to_pass", "distance_to_eligibility",
        "geometry", "economics", "session", "regime", "timeframe",
    }
    return {key: value for key, value in state.items() if key in fields and value is not None}


def _prediction_evidence(event: Mapping[str, Any]) -> dict[str, Any]:
    """Return faithfully recorded candidate-level prediction evidence.

    This is intentionally separate from per-strategy ``P_CAPTURED_WIN``:
    historical broker-confirmed outcomes are not a live prediction, and a
    missing source field must remain unavailable rather than being inferred.
    """
    raw = event.get("short_horizon_prediction")
    if not isinstance(raw, Mapping):
        candidate_details = _mapping(event.get("candidate_details"))
        raw = candidate_details.get("short_horizon_prediction")
    if isinstance(raw, Mapping):
        return {
            "source": "short_horizon_prediction",
            "available": True,
            "probability": raw.get("probability"),
            "expected_net_pnl": raw.get("expected_net_pnl"),
            "decision": raw.get("decision"),
            "abstain": raw.get("abstain"),
            "abstain_reason": raw.get("abstain_reason"),
            "artifact_status": raw.get("artifact_status"),
            "execution_status": raw.get("execution_status"),
            "calibration_status": raw.get("calibration_status"),
            "uncertainty": raw.get("uncertainty"),
            "model_agreement": raw.get("model_agreement"),
            "model_disagreement": raw.get("model_disagreement"),
            "selected_side": raw.get("selected_side"),
            "side_comparison": raw.get("side_comparison"),
            "raw": dict(raw),
        }

    # Candidate-level evaluation values are useful when the source event did
    # not include a separate predictor object.  Preserve their provenance and
    # do not turn null/absent values into a probability.
    candidate_source: Mapping[str, Any] = event
    if not any(key in candidate_source for key in ("p_green", "probability", "p_captured_win")):
        candidate_source = _mapping(event.get("candidate_details"))
    probability = _first(candidate_source, "p_green", "probability", "p_captured_win")
    if candidate_source and any(key in candidate_source for key in ("p_green", "probability", "p_captured_win")):
        return {
            "source": "candidate_evaluation",
            "available": probability is not None,
            "probability": probability,
            "expected_net_pnl": _first(candidate_source, "expected_net_value_usd", "expected_net_ev"),
            "decision": None,
            "abstain": None,
            "abstain_reason": None,
            "raw": dict(candidate_source),
        }
    return {
        "source": "UNAVAILABLE",
        "available": False,
        "probability": None,
        "reason": "prediction_not_recorded_in_source_event",
    }


def analyze_decision(
    event: Mapping[str, Any],
    library: Mapping[str, Any],
    *,
    include_strategy_opinions: bool = True,
) -> dict[str, Any]:
    state = _state_from_event(event)
    evaluated = [evaluate_strategy(row, state) for row in library.get("strategy_records", [])]
    consensus = {key: sum(item["opinion"] == key for item in evaluated) for key in (
        "BUY", "SELL", "NO_TRADE", "NOT_APPLICABLE"
    )}
    # Evaluate every strategy record, but persist a compact digest.  Full source
    # text and locations remain available through record_id in knowledge_library.
    opinions = [{
        "record_id": item.get("record_id"),
        "book": item.get("book"),
        "source_file": item.get("source_file"),
        "strategy_family": item.get("strategy_family"),
        "opinion": item.get("opinion"),
        "applicability_status": item.get("applicability", {}).get("status"),
        "reasons": item.get("applicability", {}).get("reasons", []),
        "execution_authority": False,
        "uses_future_data": False,
    } for item in evaluated]
    by_book: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for item in evaluated:
        book = _text(item.get("book")) or "UNKNOWN"
        by_book[book][item["opinion"]] += 1
    result = {
        "record_type": "watcher_decision_analysis",
        "analysis_id": _hash({"event": event, "kind": "analysis"}),
        "timestamp": _first(event, "timestamp", "observed_at", "ts", "bar"),
        "production_event": str(event.get("event") or ""),
        "production_decision": {
            "action": event.get("action"),
            "status": event.get("status") or event.get("final_status"),
            "reason": event.get("reason") or event.get("reject_reason") or event.get("exploration_skip"),
        },
        "state": state,
        "strategy_opinions": opinions if include_strategy_opinions else [],
        "strategy_opinion_counts": consensus,
        "applicable_strategy_count": sum(item["applicability"].get("status") == "APPLICABLE" for item in evaluated),
        "evaluated_strategy_count": len(evaluated),
        "consensus": consensus,
        "consensus_by_book": {book: dict(values) for book, values in by_book.items()},
        "library_coverage": {
            "processed_all_structured_kb": library.get("processed_all_structured_kb", False),
            "records": library.get("counts", {}).get("records", 0),
            "strategy_records": len(evaluated),
            "corpus_version": library.get("corpus_version"),
        },
        "no_lookahead": True,
        "research_only": True,
    }
    if not include_strategy_opinions:
        result["_evaluated_opinions"] = opinions
    return result


def _is_blocked(event: Mapping[str, Any]) -> bool:
    name = _text(event.get("event"))
    if name in {"candidate_blocked", "intel_brain_skip", "order_blocked", "open_skip", "spread_skip", "sizing_skip", "margin_precheck_skip", "oms_reject", "quote_unusable_for_scan", "quote_not_executable_for_send", "virtual_geometry_reject", "broker_geometry_reject"}:
        return True
    if name == "firehose_funnel.v1":
        return not bool(event.get("submitted") or event.get("filled")) and _text(event.get("terminal")) not in {"GLOBAL_SELECTED", "EXPLORATION_ELIGIBLE", "VALIDATED_MATCH"}
    if name in {"order", "order_check"}:
        return event.get("ok") is False or _text(event.get("execution_status")).upper() in {"BROKER_REJECT", "REJECTED", "ERROR"}
    return False


def replay_counterfactuals(
    state: Mapping[str, Any],
    quotes: Sequence[Mapping[str, Any]],
    *,
    cost_usd: float | None = None,
    usd_per_price_unit: float | None = None,
    alternative_horizons_s: Sequence[int] | None = None,
) -> dict[str, Any]:
    """Replay alternatives only after closure, using executable bid/ask."""
    ordered = sorted(
        [dict(item) for item in quotes if isinstance(item, Mapping)],
        key=lambda item: _event_time(item) if _event_time(item) is not None else float("inf"),
    )
    result: dict[str, Any] = {
        "after_the_fact": True,
        "no_lookahead_before_entry": True,
        "what_if": [],
        "alternative_horizons": [],
    }
    if not ordered:
        result["status"] = "NOT_AVAILABLE"
        return result
    first = ordered[0]
    for side in ("BUY", "SELL"):
        entry = _finite(first.get("ask" if side == "BUY" else "bid"))
        exit_price = _finite(ordered[-1].get("bid" if side == "BUY" else "ask"))
        if entry is None or exit_price is None:
            result["what_if"].append({"side": side, "status": "NOT_AVAILABLE"})
            continue
        move = (exit_price - entry) if side == "BUY" else (entry - exit_price)
        item: dict[str, Any] = {"side": side, "entry": entry, "exit": exit_price, "gross_price_move": move}
        if usd_per_price_unit is not None and cost_usd is not None:
            item["net_pnl_usd"] = move * float(usd_per_price_unit) - float(cost_usd)
        else:
            item["net_pnl_usd"] = None
        result["what_if"].append(item)
    entry_time = _event_time(first)
    for horizon in alternative_horizons_s or ():
        if entry_time is None:
            continue
        eligible = [item for item in ordered if (_event_time(item) or 0.0) >= entry_time + float(horizon)]
        if not eligible:
            continue
        result["alternative_horizons"].append({
            "horizon_s": int(horizon),
            "quote_timestamp": _event_time(eligible[0]),
            "quote": eligible[0],
        })
    result["status"] = "REPLAYED"
    return result


class WatcherKnowledgeEngine:
    """Incremental, persistent, read-only analysis attached to the Watcher."""

    def __init__(self, *, knowledge_dir: Path, report_dir: Path):
        self.knowledge_dir = Path(knowledge_dir)
        self.report_dir = Path(report_dir)
        self.report_dir.mkdir(parents=True, exist_ok=True)
        self.library = load_knowledge_library(self.knowledge_dir)
        self.library_path = self.report_dir / "knowledge_library.json"
        self.library_path.write_text(json.dumps(self.library, indent=2, default=str), encoding="utf-8")
        self.seen: set[str] = set()
        self.open_shadow: dict[str, dict[str, Any]] = {}
        self.shadow_records: dict[str, dict[str, Any]] = {}
        self.production_open: dict[str, dict[str, Any]] = {}
        self.production_outcomes: list[dict[str, Any]] = []
        self.strategy_observations: dict[str, dict[str, Any]] = {}
        self.stats: dict[str, Any] = {"production": self._empty_stats(), "shadow": self._empty_stats(), "by_strategy": {}, "per_strategy": {}}
        self._last_retention_check = time.time()
        self._last_parquet_flush = self._last_retention_check
        self.state_path = self.report_dir / "state.json"
        self._load_state()
        previous_stats = _json(self.report_dir / "strategy_stats.json", {})
        if isinstance(previous_stats, Mapping) and isinstance(previous_stats.get("per_strategy"), Mapping):
            self.strategy_observations = {
                str(key): dict(value) for key, value in previous_stats["per_strategy"].items()
                if isinstance(value, Mapping)
            }

    @staticmethod
    def _empty_stats() -> dict[str, Any]:
        return {
            "confirmed": 0,
            "closed": 0,
            "sample_size": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": None,
            "profit_factor": None,
            "expectancy": None,
            "avg_winner": None,
            "avg_loser": None,
            "mfe": [],
            "mae": [],
            "avg_mfe_usd": None,
            "avg_mae_usd": None,
            "r_values": [],
            "avg_r": None,
            "lifecycle_counts": {},
            "streaks": {"current": 0, "max_win": 0, "max_loss": 0},
            "drawdown": 0.0,
        }

    def _load_state(self) -> None:
        payload = _json(self.state_path, {})
        if not isinstance(payload, Mapping):
            return
        self.seen = set(str(item) for item in payload.get("seen_event_ids", []) if item)

    def _append(self, name: str, record: Mapping[str, Any]) -> None:
        with (self.report_dir / name).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(dict(record), sort_keys=True, default=str) + "\n")

    def _persist_state(self) -> None:
        payload = {
            "schema": "watcher_knowledge_state.v1",
            "updated_utc": datetime.now(timezone.utc).isoformat(),
            "seen_event_ids": sorted(self.seen),
            "open_shadow_ids": sorted(self.open_shadow),
            "open_production_tickets": sorted(self.production_open),
        }
        self.state_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        (self.report_dir / "strategy_stats.json").write_text(
            json.dumps(self.stats, indent=2, default=str), encoding="utf-8"
        )

    def _purge_expired_archives(self, now: float) -> None:
        archive_dir = self.report_dir / "archives"
        if not archive_dir.is_dir():
            return
        paths = [
            *archive_dir.glob("blocked_strategy_studies_*.jsonl.gz"),
            *archive_dir.glob("blocked_strategy_studies_index_*.jsonl.gz"),
        ]
        for path in paths:
            try:
                if now - path.stat().st_mtime > ARCHIVE_RETENTION_S:
                    path.unlink()
            except OSError:
                continue

    def _run_retention(self, *, now: float | None = None) -> None:
        """Archive the oldest studies without touching production or MT5 data."""
        now = time.time() if now is None else float(now)
        self._last_retention_check = now
        self._purge_expired_archives(now)
        for filename, archive_prefix in (
            (INDEX_FILE, "blocked_strategy_studies_index_"),
            ("blocked_strategy_studies.jsonl", "blocked_strategy_studies_"),
        ):
            if filename == "blocked_strategy_studies.jsonl" and (self.report_dir / INDEX_FILE).is_file():
                continue
            studies_path = self.report_dir / filename
            try:
                lines = [line for line in studies_path.read_text(encoding="utf-8").splitlines(True) if line.strip()]
            except OSError:
                continue
            if len(lines) <= ACTIVE_STUDY_LIMIT:
                continue
            archive_count = max(
                int(math.ceil(len(lines) * ARCHIVE_FRACTION)),
                len(lines) - ACTIVE_STUDY_LIMIT,
            )
            archive_lines = lines[:archive_count]
            active_lines = lines[archive_count:]
            archive_dir = self.report_dir / "archives"
            archive_dir.mkdir(parents=True, exist_ok=True)
            suffix = f"{int(now)}_{time.time_ns()}"
            archive_path = archive_dir / f"{archive_prefix}{suffix}.jsonl.gz"
            archive_tmp = archive_path.with_suffix(archive_path.suffix + ".tmp")
            active_tmp = studies_path.with_suffix(studies_path.suffix + ".tmp")
            try:
                with gzip.open(archive_tmp, "wt", encoding="utf-8") as handle:
                    handle.writelines(archive_lines)
                os.replace(archive_tmp, archive_path)
                active_tmp.write_text("".join(active_lines), encoding="utf-8")
                os.replace(active_tmp, studies_path)
            except OSError:
                for path in (archive_tmp, active_tmp):
                    try:
                        path.unlink()
                    except OSError:
                        pass

    def _maybe_run_retention(self) -> None:
        now = time.time()
        if now - self._last_retention_check < RETENTION_INTERVAL_S:
            return
        self._run_retention(now=now)
        try:
            flush_pending_to_parquet(self.report_dir, now=now)
        except (OSError, RuntimeError):
            pass
        self._last_parquet_flush = now

    def _record_strategy_observations(self, opinions: Sequence[Mapping[str, Any]], event: Mapping[str, Any]) -> None:
        for opinion in opinions:
            record_id = _text(opinion.get("record_id"))
            if not record_id:
                continue
            row = self.strategy_observations.setdefault(record_id, {
                "record_id": record_id,
                "book": opinion.get("book"),
                "source_file": opinion.get("source_file"),
                "strategy_family": opinion.get("strategy_family"),
                "evaluated_decisions": 0,
                "applicable_decisions": 0,
                "opinion_counts": {"BUY": 0, "SELL": 0, "NO_TRADE": 0, "NOT_APPLICABLE": 0},
                "confirmed_outcomes": 0,
                "outcome_count": 0,
                "wins": 0,
                "losses": 0,
                "net_pnl_usd": 0.0,
                "outcomes_by_identity": {},
                "last_event": None,
            })
            row.setdefault("confirmed_outcomes", 0)
            row.setdefault("outcome_count", 0)
            row.setdefault("wins", 0)
            row.setdefault("losses", 0)
            row.setdefault("net_pnl_usd", 0.0)
            row.setdefault("outcomes_by_identity", {})
            row["evaluated_decisions"] += 1
            label = _text(opinion.get("opinion")).upper()
            if label in row["opinion_counts"]:
                row["opinion_counts"][label] += 1
            if _text(opinion.get("applicability_status")).upper() == "APPLICABLE":
                row["applicable_decisions"] += 1
            row["last_event"] = _text(event.get("event"))

    def _record_strategy_outcome(self, outcome: Mapping[str, Any]) -> None:
        net = _finite(outcome.get("realized_net_usd"))
        state = _mapping(outcome.get("features"))
        identity = _strategy_identity(state)
        if net is None or identity is None:
            return
        for record_id in _strategy_ids(state):
            row = self.strategy_observations.setdefault(record_id, {
                "record_id": record_id,
                "book": None,
                "source_file": None,
                "strategy_family": state.get("mechanism"),
                "evaluated_decisions": 0,
                "applicable_decisions": 0,
                "opinion_counts": {"BUY": 0, "SELL": 0, "NO_TRADE": 0, "NOT_APPLICABLE": 0},
                "confirmed_outcomes": 0,
                "outcome_count": 0,
                "wins": 0,
                "losses": 0,
                "net_pnl_usd": 0.0,
                "outcomes_by_identity": {},
                "last_event": None,
            })
            row.setdefault("outcomes_by_identity", {})
            bucket = row["outcomes_by_identity"].setdefault(identity, {
                "sample_size": 0,
                "wins": 0,
                "losses": 0,
                "net_pnl_usd": 0.0,
            })
            bucket["sample_size"] += 1
            bucket["wins"] += int(net > 0)
            bucket["losses"] += int(net < 0)
            bucket["net_pnl_usd"] += net
            row["confirmed_outcomes"] = int(row.get("confirmed_outcomes") or 0) + 1
            row["outcome_count"] = int(row.get("outcome_count") or 0) + 1
            row["wins"] = int(row.get("wins") or 0) + int(net > 0)
            row["losses"] = int(row.get("losses") or 0) + int(net < 0)
            row["net_pnl_usd"] = float(row.get("net_pnl_usd") or 0.0) + net

    def _strategy_capture_rate(self, record_id: Any, state: Mapping[str, Any]) -> tuple[float | None, int]:
        identity = _strategy_identity(state)
        if not identity:
            return None, 0
        observation = self.strategy_observations.get(_text(record_id), {})
        buckets = observation.get("outcomes_by_identity") if isinstance(observation, Mapping) else {}
        bucket = buckets.get(identity) if isinstance(buckets, Mapping) else None
        if not isinstance(bucket, Mapping):
            return None, 0
        sample_size = int(bucket.get("sample_size") or 0)
        if sample_size <= 0:
            return None, 0
        return int(bucket.get("wins") or 0) / sample_size, sample_size

    def _blocked_strategy_study(
        self,
        event: Mapping[str, Any],
        analysis: Mapping[str, Any],
        opinions: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]:
        """Persist the complete strategy study for one blocked candidate.

        The per-event rows stay compact: stable record IDs link to the full
        source/provenance in ``knowledge_library.json``.
        """
        reason_dictionary: list[str] = []
        reason_codes: dict[str, int] = {}
        strategies = []
        for item in opinions:
            codes = []
            for reason in item.get("reasons") or []:
                reason_text = _text(reason)
                if reason_text not in reason_codes:
                    reason_codes[reason_text] = len(reason_dictionary)
                    reason_dictionary.append(reason_text)
                codes.append(reason_codes[reason_text])
            strategies.append({
                "record_id": item.get("record_id"),
                "applicability": item.get("applicability_status"),
                "reason_codes": codes,
                "opinion": item.get("opinion"),
            })
        for item in strategies:
            rate, sample_size = self._strategy_capture_rate(item.get("record_id"), analysis.get("state", {}))
            item["p_captured_win"] = rate
            item["p_captured_win_percent"] = None if rate is None else rate * 100.0
            item["p_captured_win_sample_size"] = sample_size
            item["p_captured_win_source"] = "broker_confirmed_net_pnl" if sample_size else "UNAVAILABLE"
        return {
            "record_type": "blocked_strategy_study",
            "study_id": _hash({"event": self._event_id(event), "kind": "blocked_strategy_study"}),
            "blocked_event_id": self._event_id(event),
            "timestamp": analysis.get("timestamp"),
            "candidate_state": _compact_candidate_state(analysis.get("state", {})),
            "raw_observation_event_id": self._event_id(event),
            "strategy_count": len(strategies),
            "strategy_metadata_source": "knowledge_library.json",
            "reason_dictionary": reason_dictionary,
            "strategies": strategies,
            "prediction_evidence": _prediction_evidence(event),
            "library_coverage": analysis.get("library_coverage", {}),
            "no_lookahead": True,
            "research_only": True,
        }

    def _event_id(self, event: Mapping[str, Any]) -> str:
        return _text(event.get("event_id")) or _hash(event)

    def _shadow_from_blocked(
        self,
        event: Mapping[str, Any],
        analysis: Mapping[str, Any],
        opinions: Sequence[Mapping[str, Any]] | None = None,
    ) -> dict[str, Any]:
        details = _mapping(event.get("candidate_details"))
        get = lambda *keys: _first(event, *keys) if _first(event, *keys) is not None else _first(details, *keys)
        shadow_id = _hash({"event": self._event_id(event), "candidate": get("candidate_id", "variant_id", "thesis_key")})
        if shadow_id in self.shadow_records:
            return self.shadow_records[shadow_id]
        side = _side(get("side", "position_side"))
        symbol = _text(get("symbol", "position_symbol")).upper()
        entry = _finite(get("entry", "econ_entry"))
        stop = _finite(get("stop", "virtual_stop", "econ_invalidation"))
        target = _finite(get("target", "virtual_target", "econ_target"))
        missing = [name for name, value in (("symbol", symbol), ("side", side), ("entry", entry), ("stop", stop), ("target", target)) if not value]
        geometry_valid = not missing and ((side == "buy" and stop < entry < target) or (side == "sell" and target < entry < stop))
        if not geometry_valid and not missing:
            missing.append("directional_geometry")
        record: dict[str, Any] = {
            "record_type": "shadow_trade",
            "shadow_id": shadow_id,
            "created_from_event": self._event_id(event),
            "created_after_production_decision": True,
            "no_lookahead": True,
            "symbol": symbol or None,
            "side": side,
            "mechanism": get("mechanism", "family", "setup_family"),
            "horizon_s": get("horizon_s", "search_horizon_s", "max_hold_s"),
            "entry_time": _event_time(event),
            "entry": entry,
            "stop": stop,
            "target": target,
            "spread": get("spread", "spread_pips", "econ_spread_pips"),
            "expected_net_ev": get("expected_net_ev", "expected_net_value_usd", "econ_expected_net_usd"),
            "pre_entry_state": analysis.get("state", {}),
            "strategy_ids": [
                item.get("record_id") for item in (opinions or analysis.get("strategy_opinions", []))
                if item.get("opinion") == str(side or "").upper() and item.get("applicability_status") == "APPLICABLE"
            ],
            "shadow_status": "OPEN" if geometry_valid else "NOT_CREATED",
            "missing_features": missing,
            "quotes": [],
            "mfe_price": 0.0,
            "mae_price": 0.0,
        }
        self.shadow_records[shadow_id] = record
        if geometry_valid:
            self.open_shadow[shadow_id] = record
        self._append("shadow_trades.jsonl", record)
        return record

    def _close_shadow(self, record: dict[str, Any], quote: Mapping[str, Any], reason: str) -> dict[str, Any]:
        side = record["side"]
        exit_price = _finite(quote.get("bid" if side == "buy" else "ask"))
        record["shadow_status"] = "CLOSED"
        record["exit_reason"] = reason
        record["exit_price"] = exit_price
        record["outcome_time"] = _event_time(quote)
        record["outcome_after_entry"] = True
        entry = _finite(record.get("entry"))
        if entry is not None and exit_price is not None:
            record["gross_price_move"] = (exit_price - entry) if side == "buy" else (entry - exit_price)
        self.open_shadow.pop(record["shadow_id"], None)
        self._append("shadow_trades.jsonl", record)
        return {**record, "record_type": "shadow_outcome"}

    def _process_quote(self, event: Mapping[str, Any]) -> list[dict[str, Any]]:
        symbol = _text(event.get("symbol")).upper()
        timestamp = _event_time(event)
        outputs: list[dict[str, Any]] = []
        for record in list(self.open_shadow.values()):
            if record.get("symbol") != symbol:
                continue
            if timestamp is not None and record.get("entry_time") is not None and timestamp <= record["entry_time"]:
                continue
            bid = _finite(event.get("bid"))
            ask = _finite(event.get("ask"))
            liquidation = bid if record["side"] == "buy" else ask
            if liquidation is None:
                continue
            entry = _finite(record.get("entry"))
            if entry is None:
                continue
            move = liquidation - entry if record["side"] == "buy" else entry - liquidation
            record["quotes"].append({"timestamp": timestamp, "bid": bid, "ask": ask})
            record["mfe_price"] = max(float(record.get("mfe_price") or 0.0), move)
            record["mae_price"] = min(float(record.get("mae_price") or 0.0), move)
            stop = _finite(record.get("stop"))
            target = _finite(record.get("target"))
            hit_target = target is not None and ((record["side"] == "buy" and liquidation >= target) or (record["side"] == "sell" and liquidation <= target))
            hit_stop = stop is not None and ((record["side"] == "buy" and liquidation <= stop) or (record["side"] == "sell" and liquidation >= stop))
            if hit_target or hit_stop:
                outputs.append(self._close_shadow(record, event, "TARGET" if hit_target else "STOP"))
            else:
                self._append("shadow_trades.jsonl", record)
        return outputs

    @staticmethod
    def _confirmed_close(event: Mapping[str, Any]) -> bool:
        if _text(event.get("event")) == "confirmed_close_finalization":
            return True
        if event.get("broker_confirmed") is True:
            return True
        for key in ("status", "execution_status"):
            if _text(event.get(key)).upper() == "BROKER_CONFIRMED":
                return True
        for key in ("broker_facts", "close_facts"):
            if _text(_mapping(event.get(key)).get("status")).upper() == "BROKER_CONFIRMED":
                return True
        return False

    @staticmethod
    def _broker_net(event: Mapping[str, Any]) -> float | None:
        sources = [event, _mapping(event.get("broker_facts")), _mapping(event.get("close_facts"))]
        for source in sources:
            value = _finite(source.get("realized_net_usd"))
            if value is not None:
                return value
        return None

    def _process_open(self, event: Mapping[str, Any]) -> None:
        ticket = _text(event.get("ticket"))
        if ticket:
            self.production_open[ticket] = {
                "ticket": ticket,
                "opened_event": dict(event),
                "pre_entry_state": _state_from_event(event),
            }
            self._append("raw_observations.jsonl", {"record_type": "production_open", **dict(event)})

    def _process_close(self, event: Mapping[str, Any]) -> dict[str, Any] | None:
        if not self._confirmed_close(event):
            return None
        ticket = _text(event.get("ticket"))
        opened = self.production_open.pop(ticket, {})
        net = self._broker_net(event)
        lifecycle = _mapping(event.get("lifecycle"))
        if not lifecycle:
            lifecycle = _mapping(event.get("lifecycle_detail"))
        entry_quality = _text(_first(lifecycle, "entry_quality") or event.get("entry_quality")).lower()
        if entry_quality == "bad":
            classification = "BAD_ENTRY"
        elif entry_quality == "good":
            classification = "GOOD_ENTRY_GOOD_EXIT" if (net is not None and net >= 0) else "GOOD_ENTRY_BAD_EXIT"
        else:
            classification = "AMBIGUOUS"
        labels: list[str] = []
        speed = _text(_first(lifecycle, "speed_label") or event.get("speed_label")).upper()
        if speed in {"FAST_WINNER", "FAST_LOSER"}:
            labels.append(speed)
        if lifecycle.get("never_green") is True or event.get("never_green") is True:
            labels.append("NEVER_GREEN")
        if lifecycle.get("green_then_loser") is True or event.get("green_then_loser") is True:
            labels.append("GREEN_THEN_LOSER")
        state = dict(opened.get("pre_entry_state") or _state_from_event(event))
        quotes = event.get("counterfactual_quotes") or event.get("quotes") or []
        counterfactuals = replay_counterfactuals(
            state,
            quotes if isinstance(quotes, Sequence) and not isinstance(quotes, (str, bytes)) else [],
            cost_usd=_finite(event.get("counterfactual_cost_usd")),
            usd_per_price_unit=_finite(event.get("counterfactual_usd_per_price_unit")),
            alternative_horizons_s=event.get("alternative_horizons_s") if isinstance(event.get("alternative_horizons_s"), Sequence) else None,
        )
        outcome = {
            "record_type": "production_outcome",
            "outcome_id": _text(event.get("outcome_id")) or _hash(event),
            "ticket": ticket or None,
            "broker_confirmed": True,
            "realized_net_usd": net,
            "classification": classification,
            "lifecycle_labels": labels,
            "features": state,
            "mfe_usd": _finite(_first(lifecycle, "mfe_usd") or event.get("mfe_usd")),
            "mae_usd": _finite(_first(lifecycle, "mae_usd") or event.get("mae_usd")),
            "time_to_green_s": _finite(_first(lifecycle, "time_to_green_s", "first_green_s") or event.get("time_to_green_s")),
            "exit_reason": _first(lifecycle, "exit_reason") or event.get("exit_reason") or event.get("close_reason"),
            "counterfactuals": counterfactuals,
            "no_lookahead": True,
            "raw_close_event": dict(event),
        }
        self.production_outcomes.append(outcome)
        self._record_strategy_outcome(outcome)
        self._append("outcomes.jsonl", outcome)
        self._append("research_findings.jsonl", {
            "record_type": "research_finding",
            "basis": "broker_confirmed_outcome",
            "outcome_id": outcome["outcome_id"],
            "classification": classification,
            "lifecycle_labels": labels,
            "research_only": True,
        })
        return outcome

    def _refresh_stats(self) -> None:
        def summarize(rows: Iterable[Mapping[str, Any]], *, shadow: bool = False) -> dict[str, Any]:
            stats = self._empty_stats()
            rows = list(rows)
            stats["closed"] = len(rows)
            stats["confirmed"] = sum(bool(row.get("broker_confirmed", shadow)) for row in rows)
            values = [_finite(row.get("realized_net_usd")) for row in rows]
            values = [value for value in values if value is not None]
            stats["sample_size"] = len(values)
            wins = [value for value in values if value > 0]
            losses = [value for value in values if value < 0]
            stats["wins"] = len(wins)
            stats["losses"] = len(losses)
            if values:
                stats["win_rate"] = len(wins) / len(values)
                stats["expectancy"] = sum(values) / len(values)
            if wins:
                stats["avg_winner"] = sum(wins) / len(wins)
            if losses:
                stats["avg_loser"] = sum(losses) / len(losses)
            if losses and wins:
                stats["profit_factor"] = sum(wins) / abs(sum(losses))
            stats["mfe"] = [value for row in rows if (value := _finite(row.get("mfe_usd"))) is not None]
            stats["mae"] = [value for row in rows if (value := _finite(row.get("mae_usd"))) is not None]
            if stats["mfe"]:
                stats["avg_mfe_usd"] = sum(stats["mfe"]) / len(stats["mfe"])
            if stats["mae"]:
                stats["avg_mae_usd"] = sum(stats["mae"]) / len(stats["mae"])
            r_values: list[float] = []
            for row in rows:
                net = _finite(row.get("realized_net_usd"))
                if net is None:
                    continue
                risk = _finite(_mapping(row.get("features")).get("initial_risk_usd"))
                if risk is not None and risk > 0:
                    r_values.append(net / risk)
            stats["r_values"] = r_values
            if r_values:
                stats["avg_r"] = sum(r_values) / len(r_values)
            lifecycle_counts: dict[str, int] = defaultdict(int)
            for row in rows:
                for label in row.get("lifecycle_labels") or []:
                    lifecycle_counts[str(label)] += 1
            stats["lifecycle_counts"] = dict(lifecycle_counts)
            current = 0
            current_sign = 0
            for value in values:
                sign = 1 if value > 0 else -1 if value < 0 else 0
                if sign == 0:
                    current = 0
                    current_sign = 0
                elif sign == current_sign:
                    current += 1
                else:
                    current = 1
                    current_sign = sign
                if sign > 0:
                    stats["streaks"]["max_win"] = max(stats["streaks"]["max_win"], current)
                elif sign < 0:
                    stats["streaks"]["max_loss"] = max(stats["streaks"]["max_loss"], current)
            stats["streaks"]["current"] = current * current_sign
            cumulative = 0.0
            peak = 0.0
            for value in values:
                cumulative += value
                peak = max(peak, cumulative)
                stats["drawdown"] = max(stats["drawdown"], peak - cumulative)
            return stats

        shadow_closed = [row for row in self.shadow_records.values() if row.get("shadow_status") == "CLOSED"]
        self.stats["shadow"] = summarize(shadow_closed, shadow=True)
        self.stats["production"] = summarize(self.production_outcomes)
        by_strategy: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for outcome in self.production_outcomes:
            state = _mapping(outcome.get("features"))
            key = "|".join(_text(state.get(item)) for item in (
                "mechanism", "symbol", "side", "horizon_s", "session", "regime", "volatility"
            ))
            by_strategy[key].append(outcome)
        self.stats["by_strategy"] = {key: summarize(rows) for key, rows in by_strategy.items()}
        self.stats["per_strategy"] = self.strategy_observations

    def process_event(
        self,
        event: Mapping[str, Any],
        *,
        expanded_events: Sequence[Mapping[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """Consume one copied journal event and return newly produced research records."""
        if not isinstance(event, Mapping):
            return []
        event_id = self._event_id(event)
        if event_id in self.seen:
            return []
        self.seen.add(event_id)
        outputs: list[dict[str, Any]] = []
        self._append("raw_observations.jsonl", {"record_type": "raw_observation", "event_id": event_id, "event": dict(event)})
        analysis_events: list[Mapping[str, Any]] = []
        if _text(event.get("event")) in _DECISION_EVENTS:
            analysis_events.append(event)
        for candidate in expanded_events or ():
            if _text(candidate.get("event")) == "candidate_blocked":
                analysis_events.append(candidate)
        for decision_event in analysis_events:
            analysis = analyze_decision(
                decision_event, self.library, include_strategy_opinions=False
            )
            opinions = analysis.pop("_evaluated_opinions", [])
            self._record_strategy_observations(opinions, decision_event)
            self._append("decision_analysis.jsonl", analysis)
            outputs.append(analysis)
            if _is_blocked(decision_event):
                study = self._blocked_strategy_study(decision_event, analysis, opinions)
                append_study(self.report_dir, study)
                outputs.append(study)
                shadow = self._shadow_from_blocked(decision_event, analysis, opinions)
                outputs.append(shadow)
        name = _text(event.get("event"))
        if name == "firehose_open":
            self._process_open(event)
        if name in _QUOTE_EVENTS:
            outputs.extend(self._process_quote(event))
        if name in _CLOSE_EVENTS:
            outcome = self._process_close(event)
            if outcome is not None:
                outputs.append(outcome)
        self._refresh_stats()
        self._persist_state()
        self._maybe_run_retention()
        return outputs

    def coverage_line(self) -> str:
        counts = self.library.get("counts", {})
        return (
            f"KNOWLEDGE_BOOKS={len(self.library.get('books') or [])} "
            f"KNOWLEDGE_RECORDS={counts.get('records', 0)} "
            f"STRATEGY_HYPOTHESES={counts.get('strategy_records', 0)} "
            f"PROCESSED_ALL_STRUCTURED_KB={self.library.get('processed_all_structured_kb', False)} "
            f"CORPUS_VERSION={self.library.get('corpus_version')}"
        )


__all__ = [
    "STRUCTURED_KB_FILES",
    "ADDITIONAL_KB_FILES",
    "WatcherKnowledgeEngine",
    "analyze_decision",
    "evaluate_applicability",
    "evaluate_strategy",
    "load_knowledge_library",
    "replay_counterfactuals",
]
