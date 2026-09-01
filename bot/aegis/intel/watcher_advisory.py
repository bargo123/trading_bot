"""Read-only bridge from the Watcher book algorithms to Firehose decisions.

The Watcher and the Firehose consume the same point-in-time market snapshot,
but they have different authorities.  This module adapts the runner's current
quote/bar state, evaluates every individually authored Watcher algorithm, and
returns a compact advisory digest.  It never creates an order intent and never
imports an execution engine.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
from typing import Any, Iterable, Mapping

from aegis.research.watcher_algorithms import ALGORITHM_MODULES
from aegis.research.watcher_book_perspectives import analyze_book_perspectives
from aegis.research.watcher_feature_engine import enrich_watcher_state


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def _timestamp(value: Any) -> float | None:
    numeric = _number(value)
    if numeric is not None:
        return numeric / 1000.0 if numeric > 10_000_000_000 else numeric
    if isinstance(value, datetime):
        item = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return item.timestamp()
    if isinstance(value, str):
        try:
            item = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
        if item.tzinfo is None:
            item = item.replace(tzinfo=timezone.utc)
        return item.timestamp()
    return None


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    converter = getattr(value, "to_dict", None)
    if callable(converter):
        try:
            converted = converter()
        except Exception:
            return {}
        return dict(converted) if isinstance(converted, Mapping) else {}
    return {}


def _quote_point(value: Any) -> dict[str, float] | None:
    raw = _mapping(value)
    if raw:
        timestamp = _timestamp(
            raw.get("time", raw.get("timestamp", raw.get("time_utc")))
        )
        bid = _number(raw.get("bid"))
        ask = _number(raw.get("ask"))
    else:
        timestamp = _timestamp(getattr(value, "timestamp", None))
        bid = _number(getattr(value, "bid", None))
        ask = _number(getattr(value, "ask", None))
    if bid is None or ask is None or bid <= 0 or ask <= 0 or ask < bid:
        return None
    result: dict[str, float] = {
        "bid": bid,
        "ask": ask,
        "mid": (bid + ask) / 2.0,
    }
    if timestamp is not None and math.isfinite(timestamp):
        result["time"] = timestamp
    return result


def _buffer_history(
    quote_buffer: Any,
    symbol: str,
    *,
    since: float | None = None,
    max_points: int | None = None,
) -> list[dict[str, float]]:
    buffers = getattr(quote_buffer, "buffers", None)
    if not isinstance(buffers, Mapping):
        return []
    raw_buffer = buffers.get(str(symbol).upper())
    if raw_buffer is None:
        return []
    points = getattr(raw_buffer, "points", ())
    result: list[dict[str, float]] = []
    for point in points or ():
        item = _quote_point(point)
        if item is None:
            continue
        if since is not None and item.get("time", float("-inf")) < since:
            continue
        result.append(item)
    if max_points is not None and max_points > 0:
        result = result[-max_points:]
    return result


def _unavailable(
    *, symbol: str, side: str, mechanism: str, horizon_s: int | float | None,
    reason: str,
) -> dict[str, Any]:
    return {
        "status": "UNAVAILABLE",
        "reason": str(reason),
        "symbol": str(symbol).upper(),
        "side": str(side).upper(),
        "mechanism": str(mechanism or ""),
        "horizon_s": horizon_s,
        "algorithm_count": len(ALGORITHM_MODULES),
        "evaluated_count": 0,
        "applicable_count": 0,
        "counts": {
            "BUY": 0,
            "SELL": 0,
            "WAIT": 0,
            "NOT_APPLICABLE": 0,
            "MISSING_DATA": 0,
        },
        "consensus": "UNRESOLVED",
        "supporting_algorithms": [],
        "opposing_algorithms": [],
        "missing_data_algorithms": [],
        "execution_authority": False,
        "research_only": True,
        "no_lookahead": False,
        "order_intent": False,
    }


def watcher_advisory_for_firehose(
    *,
    symbol: str,
    side: str,
    mechanism: str,
    horizon_s: int | float | None,
    runtime_state: Mapping[str, Any] | None = None,
    row: Mapping[str, Any] | Any = None,
    quote_buffer: Any = None,
    actual_bid: float | None = None,
    actual_ask: float | None = None,
    now_ts: float | None = None,
    symbol_history: Iterable[Mapping[str, Any]] | None = None,
    universe_history: Mapping[str, Iterable[Mapping[str, Any]]] | None = None,
    include_perspectives: bool = False,
) -> dict[str, Any]:
    """Evaluate all Watcher algorithms on the runner's causal snapshot.

    Explicit histories are used by replay/tests.  When they are omitted, the
    runner's bounded ``QuoteBuffer`` is exported without changing broker
    timestamps.  The current row is never populated with outcome fields and
    future quote observations are filtered by ``enrich_watcher_state``.
    """
    normalized_symbol = str(symbol or "").upper()
    normalized_side = str(side or "").upper()
    base = _mapping(runtime_state)
    base.update({
        "symbol": normalized_symbol,
        "side": normalized_side,
        "mechanism": str(mechanism or ""),
        "family": str(mechanism or ""),
        "setup_family": str(mechanism or ""),
    })
    normalized_horizon = _number(horizon_s)
    if normalized_horizon is not None:
        base["horizon_s"] = (
            int(normalized_horizon)
            if normalized_horizon.is_integer()
            else normalized_horizon
        )

    row_data = _mapping(row)
    row_time = _timestamp(
        row_data.get("time", row_data.get("timestamp", row_data.get("time_utc")))
    )
    history: list[Mapping[str, Any]]
    if symbol_history is None:
        history = _buffer_history(quote_buffer, normalized_symbol)
    else:
        history = list(symbol_history)

    # A runner row is a completed-bar timestamp, while QuoteBuffer contains
    # the most recent broker event.  Prefer that genuine broker timestamp when
    # the buffer is the source; explicit replay rows retain their own as-of.
    if symbol_history is None and history:
        latest_time = _timestamp(history[-1].get("time"))
        if latest_time is not None:
            row_time = latest_time
    if row_time is not None:
        row_data["time"] = row_time
    if actual_bid is not None and actual_ask is not None:
        bid = _number(actual_bid)
        ask = _number(actual_ask)
        if bid is not None and ask is not None and bid > 0 and ask >= bid:
            row_data.update({
                "bid": bid,
                "ask": ask,
                "mid": (bid + ask) / 2.0,
            })
            if row_time is None:
                row_time = _timestamp(row_data.get("time"))
    if normalized_side == "BUY" and _number(row_data.get("ask")) is not None:
        base.setdefault("entry", _number(row_data.get("ask")))
    elif normalized_side == "SELL" and _number(row_data.get("bid")) is not None:
        base.setdefault("entry", _number(row_data.get("bid")))

    if universe_history is None and quote_buffer is not None:
        asof = row_time
        since = None if asof is None else asof - 300.0
        universe: dict[str, Iterable[Mapping[str, Any]]] = {}
        buffers = getattr(quote_buffer, "buffers", {})
        if isinstance(buffers, Mapping):
            for name in buffers:
                universe[str(name).upper()] = _buffer_history(
                    quote_buffer,
                    str(name),
                    since=since,
                    max_points=1200,
                )
        universe_history = universe

    try:
        enriched = enrich_watcher_state(
            base,
            row_data,
            symbol_history=history,
            universe_history=universe_history,
        )
        analysis = analyze_book_perspectives(enriched)
        perspectives = analysis.get("perspectives")
        if not isinstance(perspectives, list) or len(perspectives) != len(ALGORITHM_MODULES):
            return _unavailable(
                symbol=normalized_symbol,
                side=normalized_side,
                mechanism=mechanism,
                horizon_s=horizon_s,
                reason="watcher_algorithm_count_mismatch",
            )
        if (
            analysis.get("execution_authority") is not False
            or analysis.get("research_only") is not True
            or analysis.get("no_lookahead") is not True
        ):
            return _unavailable(
                symbol=normalized_symbol,
                side=normalized_side,
                mechanism=mechanism,
                horizon_s=horizon_s,
                reason="watcher_algorithm_contract_violation",
            )
        identifiers = [
            str(item.get("algorithm_id") or item.get("perspective_id") or "")
            for item in perspectives
            if isinstance(item, Mapping)
        ]
        if len(identifiers) != len(ALGORITHM_MODULES) or set(identifiers) != set(ALGORITHM_MODULES):
            return _unavailable(
                symbol=normalized_symbol,
                side=normalized_side,
                mechanism=mechanism,
                horizon_s=horizon_s,
                reason="watcher_algorithm_count_mismatch",
            )
        if any(
            item.get("execution_authority") is not False
            or item.get("research_only") is not True
            or item.get("uses_future_data") is not False
            for item in perspectives
            if isinstance(item, Mapping)
        ):
            return _unavailable(
                symbol=normalized_symbol,
                side=normalized_side,
                mechanism=mechanism,
                horizon_s=horizon_s,
                reason="watcher_algorithm_contract_violation",
            )
        compact = []
        directional_signals: list[dict[str, Any]] = []
        supporting: list[str] = []
        opposing: list[str] = []
        missing: list[str] = []
        source_books: set[str] = set()
        for item in perspectives:
            if not isinstance(item, Mapping):
                return _unavailable(
                    symbol=normalized_symbol,
                    side=normalized_side,
                    mechanism=mechanism,
                    horizon_s=horizon_s,
                    reason="watcher_algorithm_result_invalid",
                )
            algorithm_id = str(item.get("algorithm_id") or item.get("perspective_id") or "")
            view = str(item.get("view") or "MISSING_DATA").upper()
            applicability = str(item.get("applicability") or "MISSING_DATA").upper()
            compact.append({
                "algorithm_id": algorithm_id,
                "view": view,
                "applicability": applicability,
                "reasons": [str(value) for value in item.get("reasons") or ()],
            })
            if (
                applicability == "APPLICABLE"
                and view in {"BUY", "SELL"}
            ):
                directional_signals.append({
                    "algorithm_id": algorithm_id,
                    "view": view,
                    "applicability": applicability,
                    "reasons": [str(value) for value in item.get("reasons") or ()],
                    "source_books": [str(value) for value in item.get("source_books") or ()],
                    "execution_authority": False,
                    "research_only": True,
                    "uses_future_data": False,
                })
            if applicability == "APPLICABLE" and view == normalized_side:
                supporting.append(algorithm_id)
            elif applicability == "APPLICABLE" and view in {"BUY", "SELL"}:
                opposing.append(algorithm_id)
            elif view == "MISSING_DATA" or applicability == "MISSING_DATA":
                missing.append(algorithm_id)
            for book in item.get("source_books") or ():
                if str(book).strip():
                    source_books.add(str(book))

        counts = {
            key: sum(item["view"] == key for item in compact)
            for key in ("BUY", "SELL", "WAIT", "NOT_APPLICABLE", "MISSING_DATA")
        }
        directional = len(supporting) + len(opposing)
        if supporting and len(supporting) > len(opposing):
            consensus = "BUY" if normalized_side == "BUY" else "SELL"
        elif opposing and len(opposing) > len(supporting):
            consensus = "SELL" if normalized_side == "BUY" else "BUY"
        elif directional:
            consensus = "MIXED"
        else:
            consensus = str(analysis.get("consensus") or "UNRESOLVED")
        digest = hashlib.sha256(
            json.dumps(compact, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        result: dict[str, Any] = {
            "status": "AVAILABLE",
            "symbol": normalized_symbol,
            "side": normalized_side,
            "mechanism": str(mechanism or ""),
            "horizon_s": base.get("horizon_s", horizon_s),
            "algorithm_count": len(ALGORITHM_MODULES),
            "evaluated_count": len(compact),
            "applicable_count": int(analysis.get("applicable_count", 0) or 0),
            "counts": counts,
            "consensus": consensus,
            "supporting_count": len(supporting),
            "opposing_count": len(opposing),
            "directional_support_ratio": (
                len(supporting) / directional if directional else None
            ),
            # Keep runner journals bounded.  ``algorithm_result_sha256`` and
            # the counts prove that the full set was evaluated; the complete
            # per-algorithm detail remains available from the read-only
            # Watcher reports.
            "supporting_algorithm_count": len(supporting),
            "opposing_algorithm_count": len(opposing),
            "missing_data_algorithm_count": len(missing),
            "supporting_algorithms": supporting[:25],
            "opposing_algorithms": opposing[:25],
            "directional_signals": directional_signals,
            "missing_data_algorithms": missing[:25],
            "source_books": sorted(source_books),
            "algorithm_result_sha256": digest,
            "quote_history_n": enriched.get("quote_history_n"),
            "quote_history_last_time": enriched.get("quote_history_last_time"),
            "quote_history_future_excluded": bool(
                enriched.get("quote_history_future_excluded", False)
            ),
            "feature_provenance": enriched.get("feature_provenance", {}),
            "execution_authority": False,
            "research_only": True,
            "no_lookahead": bool(analysis.get("no_lookahead", True)),
            "order_intent": False,
        }
        result["book_features"] = book_feature_snapshot(
            result,
            candidate_side=normalized_side,
        )
        result["book_rank_score"] = result["book_features"]["book_rank_score"]
        if include_perspectives:
            result["perspectives"] = perspectives
        return result
    except Exception as exc:
        return _unavailable(
            symbol=normalized_symbol,
            side=normalized_side,
            mechanism=mechanism,
            horizon_s=horizon_s,
            reason=f"watcher_advisory_error:{type(exc).__name__}",
        )


def book_signal_rows(
    advisory: Mapping[str, Any] | None,
    *,
    symbol: str,
    side: str,
    mechanism: str,
    horizon_s: int | float | None,
) -> list[dict[str, Any]]:
    """Project safe, attributable Watcher views onto one exact candidate.

    This is deliberately not an order compiler.  It only exposes applicable
    directional research views whose advisory and perspective contracts are
    still read-only and causal.  Broker geometry, probability, economics,
    sizing, and execution remain owned by the Firehose.
    """
    if not isinstance(advisory, Mapping):
        return []
    if (
        str(advisory.get("status") or "").upper() != "AVAILABLE"
        or advisory.get("execution_authority") is not False
        or advisory.get("research_only") is not True
        or advisory.get("no_lookahead") is not True
    ):
        return []

    normalized_symbol = str(symbol or "").upper()
    normalized_side = str(side or "").upper()
    normalized_mechanism = str(mechanism or "")
    normalized_horizon = _number(horizon_s)
    advisory_horizon = _number(advisory.get("horizon_s"))
    if (
        str(advisory.get("symbol") or "").upper() != normalized_symbol
        or str(advisory.get("side") or "").upper() != normalized_side
        or str(advisory.get("mechanism") or "") != normalized_mechanism
        or (
            normalized_horizon is not None
            and advisory_horizon != normalized_horizon
        )
    ):
        return []

    perspectives = advisory.get("perspectives")
    if not isinstance(perspectives, list):
        perspectives = advisory.get("directional_signals")
    if not isinstance(perspectives, list):
        return []
    rows: list[dict[str, Any]] = []
    for item in perspectives:
        if not isinstance(item, Mapping):
            continue
        algorithm_id = str(
            item.get("algorithm_id") or item.get("perspective_id") or ""
        ).strip()
        view = str(item.get("view") or "").upper()
        applicability = str(item.get("applicability") or "").upper()
        if not algorithm_id or applicability != "APPLICABLE" or view not in {"BUY", "SELL"}:
            continue
        if (
            item.get("execution_authority") is not False
            or item.get("research_only") is not True
            or item.get("uses_future_data") is not False
        ):
            continue
        rows.append({
            "signal_id": (
                f"book:{algorithm_id}:{normalized_symbol}:{view}:"
                f"{normalized_mechanism}:{int(normalized_horizon) if normalized_horizon is not None and normalized_horizon.is_integer() else normalized_horizon}"
            ),
            "algorithm_id": algorithm_id,
            "source_books": [str(value) for value in item.get("source_books") or ()],
            "signal_side": view,
            "candidate_side": normalized_side,
            "alignment": "SUPPORTS" if view == normalized_side else "OPPOSES",
            "symbol": normalized_symbol,
            "mechanism": normalized_mechanism,
            "horizon_s": (
                int(normalized_horizon)
                if normalized_horizon is not None and normalized_horizon.is_integer()
                else normalized_horizon
            ),
            "reasons": [str(value) for value in item.get("reasons") or ()],
            "execution_authority": False,
            "research_only": True,
            "uses_future_data": False,
        })
    return rows


def book_support_score(
    rows: Iterable[Mapping[str, Any]], *, candidate_side: str
) -> float | None:
    """Return bounded directional support for secondary candidate ranking."""
    normalized_side = str(candidate_side or "").upper()
    directional = [
        row for row in rows
        if isinstance(row, Mapping)
        and str(row.get("signal_side") or "").upper() in {"BUY", "SELL"}
    ]
    if not directional or normalized_side not in {"BUY", "SELL"}:
        return None
    supporting = sum(
        str(row.get("signal_side") or "").upper() == normalized_side
        for row in directional
    )
    return round(supporting / len(directional), 6)


def book_feature_snapshot(
    advisory: Mapping[str, Any] | None,
    *,
    candidate_side: str | None = None,
) -> dict[str, Any]:
    """Return bounded, causal book features for secondary ranking.

    Directional support is intentionally shrunk toward neutral when only a
    small fraction of the 616 algorithms are applicable.  The snapshot is
    descriptive evidence: it cannot create a probability, order intent, or
    execution authority.
    """
    neutral: dict[str, Any] = {
        "book_status": "UNAVAILABLE",
        "book_available": 0.0,
        "book_registry_complete": 0.0,
        "book_algorithm_count": 0.0,
        "book_evaluated_ratio": 0.0,
        "book_applicable_ratio": 0.0,
        "book_directional_ratio": 0.0,
        "book_support_ratio": 0.5,
        "book_consensus_strength": 0.0,
        "book_missing_ratio": 0.0,
        "book_source_book_count": 0.0,
        "book_rank_confidence": 0.0,
        "book_rank_score": 0.5,
    }
    if not isinstance(advisory, Mapping):
        return neutral
    if (
        str(advisory.get("status") or "").upper() != "AVAILABLE"
        or advisory.get("execution_authority") is not False
        or advisory.get("research_only") is not True
        or advisory.get("no_lookahead") is not True
        or (
            "order_intent" in advisory
            and advisory.get("order_intent") is not False
        )
    ):
        return neutral

    def count(key: str, default: int | None = None) -> int | None:
        if key not in advisory:
            return default
        value = _number(advisory.get(key))
        if value is None or not value.is_integer() or value < 0:
            return None
        return int(value)

    algorithm_count = count("algorithm_count", 0)
    if not algorithm_count:
        return neutral
    evaluated_count = count("evaluated_count", algorithm_count)
    supporting_count = count("supporting_count", 0)
    opposing_count = count("opposing_count", 0)
    applicable_count = count(
        "applicable_count",
        (supporting_count or 0) + (opposing_count or 0),
    )
    if "missing_data_algorithm_count" in advisory:
        missing_count = count("missing_data_algorithm_count")
    elif "missing_data_count" in advisory:
        missing_count = count("missing_data_count")
    else:
        missing_count = max((evaluated_count or 0) - (applicable_count or 0), 0)
    values = (
        evaluated_count,
        supporting_count,
        opposing_count,
        applicable_count,
        missing_count,
    )
    if any(value is None for value in values):
        return neutral
    evaluated_count = int(evaluated_count or 0)
    supporting_count = int(supporting_count or 0)
    opposing_count = int(opposing_count or 0)
    applicable_count = int(applicable_count or 0)
    missing_count = int(missing_count or 0)
    directional_count = supporting_count + opposing_count
    if (
        evaluated_count > algorithm_count
        or applicable_count > evaluated_count
        or directional_count > applicable_count
        or missing_count > evaluated_count
    ):
        return neutral

    normalized_side = str(candidate_side or advisory.get("side") or "").upper()
    absolute_views = bool(advisory.get("absolute_views", False))
    advisory_side = str(advisory.get("side") or "").upper()
    if absolute_views and normalized_side not in {"BUY", "SELL"}:
        return neutral
    if absolute_views and normalized_side == "SELL":
        supporting_count, opposing_count = opposing_count, supporting_count
    elif (
        not absolute_views
        and normalized_side in {"BUY", "SELL"}
        and advisory_side in {"BUY", "SELL"}
        and normalized_side != advisory_side
    ):
        supporting_count, opposing_count = opposing_count, supporting_count

    algorithm_ids = advisory.get("algorithm_ids")
    registry_complete = (
        algorithm_count == len(ALGORITHM_MODULES)
        and (
            not isinstance(algorithm_ids, (list, tuple, set, frozenset))
            or (
                len(algorithm_ids) == len(ALGORITHM_MODULES)
                and set(str(value) for value in algorithm_ids) == set(ALGORITHM_MODULES)
            )
        )
    )
    directional_ratio = directional_count / algorithm_count
    support_ratio = (
        supporting_count / directional_count if directional_count else 0.5
    )
    consensus_strength = (
        abs(supporting_count - opposing_count) / directional_count
        if directional_count else 0.0
    )
    rank_confidence = min(1.0, evaluated_count / algorithm_count) * math.sqrt(
        min(1.0, directional_ratio)
    )
    rank_delta = (
        (supporting_count - opposing_count) / directional_count
        if directional_count else 0.0
    )
    rank_score = min(1.0, max(0.0, 0.5 + 0.5 * rank_delta * rank_confidence))
    source_books = advisory.get("source_books")
    source_count = (
        len({str(value).strip() for value in source_books if str(value).strip()})
        if isinstance(source_books, (list, tuple, set, frozenset))
        else 0
    )
    return {
        "book_status": "AVAILABLE",
        "book_available": 1.0,
        "book_registry_complete": 1.0 if registry_complete else 0.0,
        "book_algorithm_count": float(algorithm_count),
        "book_evaluated_ratio": evaluated_count / algorithm_count,
        "book_applicable_ratio": applicable_count / algorithm_count,
        "book_directional_ratio": directional_ratio,
        "book_support_ratio": support_ratio,
        "book_consensus_strength": consensus_strength,
        "book_missing_ratio": missing_count / algorithm_count,
        "book_source_book_count": float(source_count),
        "book_rank_confidence": rank_confidence,
        "book_rank_score": rank_score,
    }


__all__ = [
    "book_feature_snapshot",
    "book_signal_rows",
    "book_support_score",
    "watcher_advisory_for_firehose",
]
