"""Read-only historical replay for the individually authored Watcher rules.

Each algorithm sees only the row's pre-entry feature snapshot.  The completed
captured-exit net outcome is attached after evaluation for descriptive research
statistics; it is never included in the evaluator state.
"""
from __future__ import annotations

import json
import math
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence

from .watcher_algorithms import ALGORITHM_MODULES, evaluate_all, evaluate_selected
from .watcher_feature_engine import enrich_watcher_state
from .watcher_book_perspectives import BOOK_ALGORITHM_COVERAGE, BOOK_REVIEW_COVERAGE


_PRE_ENTRY_FIELDS = frozenset({
    "symbol", "side", "session", "regime", "structure", "family",
    "horizon_s", "entry_price", "entry_spread", "spread", "quote_age_s",
    "tick_velocity", "price_acceleration", "spread_change",
    "spread_acceleration", "micro_volatility", "realized_vol_60s",
    "volatility_expansion", "momentum_persistence", "momentum_decay",
    "cost_to_movement", "distance_to_micro_high", "distance_to_micro_low",
    "hour_utc", "dow_utc", "session_asia_or_off", "session_london",
    "session_new_york", "session_overlap", "spread_percentile",
    "spread_to_micro_vol", "spread_to_realized_vol", "candidate_source",
    "candidate_authority", "family_version",
})
_RETURN_FIELDS = tuple(f"return_{seconds}s" for seconds in (1, 2, 3, 5, 8, 10, 15, 20, 30, 60))
_OUTCOME_FIELDS = frozenset({
    "captured_exit_net_pnl", "captured_exit_return", "captured_exit_reason",
    "captured_win_1s", "captured_win_2s", "captured_win_3s",
    "captured_win_5s", "captured_win_8s", "captured_win_10s",
    "captured_win_15s", "captured_win_20s", "captured_win_30s",
    "captured_win_45s", "terminal_net_pnl", "terminal_return", "mfe",
    "mae", "tail_loss", "immediate_adverse_move", "first_green",
    "never_green", "green_then_loser", "time_to_green_s", "time_to_profit_s",
    "time_to_failure_s", "time_to_mfe_s", "time_in_red_s", "winner_giveback",
    "first_profitable_executable_close", "first_profitable_close_net_pnl",
    "future_path_observed_n", "exit_policy", "exit_time_s", "time_to_peak",
})
_HISTORY_QUOTE_FIELDS = frozenset({
    "time", "timestamp", "time_utc", "time_msc", "bid", "ask", "mid",
    "tick_volume", "volume", "bid_size", "bid_volume", "ask_size",
    "ask_volume", "signed_order_flow", "order_flow", "transaction_price",
    "trade_price", "last",
})
_CONTEXT_ROW_OVERRIDE_FIELDS = _PRE_ENTRY_FIELDS | frozenset({
    "time", "timestamp", "time_utc", "time_msc", "symbol", "bid", "ask", "mid",
    "side", "horizon_s", "entry", "entry_price", "entry_spread", "spread_pips",
    "quote_fresh", "short_returns",
})
_COST_MODEL_SCHEMA = "aegis.shadow_cost_model.v1"
_COST_MODEL_OUTCOME_UNITS = (
    "captured_exit_return is broker-unit-normalized after-cost return"
)


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def _row_cost_model_is_complete(row: Mapping[str, Any]) -> bool:
    """Check that a replay row carries its executable cost provenance."""
    if row.get("cost_model_schema") != _COST_MODEL_SCHEMA:
        return False
    if row.get("cost_model_outcome_units") != _COST_MODEL_OUTCOME_UNITS:
        return False
    try:
        bid = _number(row.get("bid"))
        ask = _number(row.get("ask"))
        decision_spread = _number(row.get("decision_spread"))
        entry_spread = _number(row.get("entry_spread"))
        slippage_bps = _number(row.get("slippage_bps"))
        commission = _number(row.get("commission_round_trip_usd"))
        slippage_price = _number(row.get("slippage_price"))
        unit = _number(row.get("usd_per_price_unit"))
        entry_latency = _number(row.get("entry_latency_s"))
        close_latency = _number(row.get("close_latency_s"))
    except (TypeError, ValueError, OverflowError):
        return False
    return (
        bid is not None
        and ask is not None
        and bid > 0.0
        and ask >= bid
        and decision_spread is not None
        and decision_spread >= 0.0
        and entry_spread is not None
        and entry_spread >= 0.0
        and slippage_bps is not None
        and slippage_bps >= 0.0
        and commission is not None
        and commission >= 0.0
        and slippage_price is not None
        and slippage_price >= 0.0
        and unit is not None
        and unit > 0.0
        and entry_latency is not None
        and entry_latency >= 0.0
        and close_latency is not None
        and close_latency >= 0.0
    )


def _usable(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (Mapping, list, tuple, set)):
        return bool(value)
    return True


def _side(value: Any) -> str | None:
    normalized = str(value or "").strip().upper()
    return normalized if normalized in {"BUY", "SELL"} else None


def _history_quote_snapshot(row: Mapping[str, Any]) -> dict[str, Any]:
    """Keep only fields consumed by the causal quote-history adapter."""
    return {
        str(key): row[key]
        for key in _HISTORY_QUOTE_FIELDS
        if key in row
    }


def _overlay_cached_context(
    cached: Mapping[str, Any], row: Mapping[str, Any]
) -> dict[str, Any]:
    """Reuse same-quote derived context while restoring row identity fields."""
    result = dict(cached)
    row_state = build_pre_entry_state(row, pre_enriched=True)
    for key in _CONTEXT_ROW_OVERRIDE_FIELDS:
        value = row_state.get(key)
        if key in row_state and not (
            isinstance(value, str)
            and value.strip().lower().startswith(
                ("unknown", "unavailable", "not_observed", "not_available")
            )
        ):
            result[key] = row_state[key]
    return result


def build_pre_entry_state(
    row: Mapping[str, Any],
    *,
    symbol_history: Iterable[Mapping[str, Any]] = (),
    universe_history: Mapping[str, Iterable[Mapping[str, Any]]] | None = None,
    pre_enriched: bool = False,
) -> dict[str, Any]:
    """Adapt one historical shadow row to the Watcher state contract.

    ``pre_enriched`` is an explicit research-only fast path for datasets whose
    feature columns were already generated causally.  It still passes through
    the row sanitizer, so outcome/future payload fields never reach an
    evaluator.  The default reconstructs features from point-in-time history.
    """
    if not isinstance(row, Mapping):
        return {}
    if pre_enriched:
        return enrich_watcher_state(
            {}, row, symbol_history=(), universe_history=None, derive=False
        )
    state = {
        key: row[key]
        for key in _PRE_ENTRY_FIELDS
        if key in row and _usable(row[key])
    }
    side = _side(row.get("side"))
    if side:
        state["side"] = side
    horizon = _number(row.get("horizon_s"))
    if horizon is not None:
        state["horizon_s"] = int(horizon) if horizon.is_integer() else horizon
    entry = _number(row.get("entry_price"))
    if entry is not None:
        state["entry"] = entry
    spread = row.get("entry_spread") if row.get("entry_spread") is not None else row.get("spread")
    if _usable(spread):
        state["spread_pips"] = spread
    age = _number(row.get("quote_age_s"))
    if age is not None:
        state["quote_age_s"] = age
        state["quote_fresh"] = age <= 5.0

    short_returns: dict[str, float] = {}
    for field in _RETURN_FIELDS:
        value = _number(row.get(field))
        if value is None:
            continue
        key = field[:-1]
        short_returns[key] = value
        state[key] = value
    if short_returns:
        state["short_returns"] = short_returns
        first_return = next(iter(short_returns.values()))
        if first_return > 0:
            state["tick_direction"] = "up"
        elif first_return < 0:
            state["tick_direction"] = "down"
    return enrich_watcher_state(
        state,
        row,
        symbol_history=symbol_history,
        universe_history=universe_history,
    )


def _net_outcome(row: Mapping[str, Any]) -> float | None:
    """Return a comparable after-cost outcome.

    New quote replays carry broker-unit-normalized returns.  Prefer that
    dimensionless value so EURUSD, USDJPY, and other symbols are comparable;
    retain the legacy raw-PnL fallback for older fixtures.
    """
    for key in (
        "captured_exit_return",
        "exit_capturedexitreplay_return",
        "captured_exit_net_pnl",
        "exit_capturedexitreplay_net_pnl",
    ):
        value = _number(row.get(key))
        if value is not None:
            return value
    return None


def _validate_rejection_rate(value: Any) -> float:
    try:
        rate = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("rejection_rate is invalid") from exc
    if not math.isfinite(rate) or rate < 0.0 or rate >= 1.0:
        raise ValueError("rejection_rate is invalid")
    return rate


def _exact_strategy_key(
    algorithm: str,
    state: Mapping[str, Any],
    row: Mapping[str, Any],
) -> tuple[str, str, str, str, str] | None:
    """Canonical identity for a measurable execution candidate."""
    symbol = str(row.get("symbol") or state.get("symbol") or "").strip().upper()
    side = _side(state.get("side") or row.get("side"))
    horizon = _number(state.get("horizon_s") if state.get("horizon_s") is not None else row.get("horizon_s"))
    mechanism = str(
        row.get("mechanism")
        or row.get("family_version")
        or row.get("family")
        or "unknown_mechanism"
    ).strip()
    if not symbol or not side or horizon is None or not mechanism:
        return None
    horizon_key = str(int(horizon)) if horizon.is_integer() else str(horizon)
    return str(algorithm), symbol, side, horizon_key, mechanism


def _format_exact_strategy_key(key: tuple[str, str, str, str, str]) -> str:
    return "|".join(key)


def _bucket() -> dict[str, Any]:
    return {
        "evaluated": 0,
        "applicable": 0,
        "signal_samples": 0,
        "wins": 0,
        "losses": 0,
        "draws": 0,
        "net_pnl": 0.0,
        "view_counts": Counter(),
        "reason_counts": Counter(),
        "side_counts": Counter(),
        "loss_values": [],
    }


def _update_bucket(bucket: dict[str, Any], result: Mapping[str, Any], state: Mapping[str, Any], net: float | None) -> None:
    bucket["evaluated"] += 1
    candidate_side = _side(state.get("side"))
    if candidate_side:
        bucket["side_counts"][candidate_side] += 1
    view = str(result.get("view") or "UNKNOWN")
    bucket["view_counts"][view] += 1
    for reason in result.get("reasons") or ():
        bucket["reason_counts"][str(reason)] += 1
    if result.get("applicability") == "APPLICABLE":
        bucket["applicable"] += 1
    if net is None or view != candidate_side or result.get("applicability") != "APPLICABLE":
        return
    bucket["signal_samples"] += 1
    bucket["net_pnl"] += net
    if net > 0:
        bucket["wins"] += 1
    elif net < 0:
        bucket["losses"] += 1
        bucket["loss_values"].append(net)
    else:
        bucket["draws"] += 1


def _finalize_bucket(
    bucket: dict[str, Any],
    *,
    rejection_rate: float = 0.0,
) -> dict[str, Any]:
    signal_samples = int(bucket["signal_samples"])
    wins_value = float(bucket["net_pnl"])
    losses_value = sum(bucket["loss_values"])
    result = {
        key: bucket[key]
        for key in ("evaluated", "applicable", "signal_samples", "wins", "losses", "draws")
    }
    result.update({
        "net_pnl": round(float(bucket["net_pnl"]), 12),
        "win_rate": bucket["wins"] / signal_samples if signal_samples else None,
        "expectancy": bucket["net_pnl"] / signal_samples if signal_samples else None,
        "rejection_rate": rejection_rate,
        "rejection_adjusted_net_pnl": round(
            float(bucket["net_pnl"]) * (1.0 - rejection_rate), 12
        ),
        "rejection_adjusted_expectancy": (
            float(bucket["net_pnl"]) / signal_samples * (1.0 - rejection_rate)
            if signal_samples else None
        ),
        "profit_factor": None,
        "p95_loss": None,
        "view_counts": dict(bucket["view_counts"]),
        "reason_counts": dict(bucket["reason_counts"]),
        "side_counts": dict(bucket["side_counts"]),
    })
    if losses_value < 0:
        positive_pnl = wins_value - losses_value
        result["profit_factor"] = positive_pnl / abs(losses_value) if positive_pnl > 0 else 0.0
        losses = sorted(bucket["loss_values"])
        result["p95_loss"] = losses[max(0, math.ceil(len(losses) * 0.95) - 1)]
    bucket_horizon = bucket.get("by_horizon")
    if bucket_horizon is not None:
        result["by_horizon"] = {
            str(key): _finalize_bucket(value, rejection_rate=rejection_rate)
            for key, value in sorted(bucket_horizon.items(), key=lambda item: str(item[0]))
        }
    return result


_BOOK_RANK_BINS = (
    "strong_opposition",
    "opposition",
    "neutral",
    "support",
    "strong_support",
)


def _book_consensus_snapshot(
    results: Iterable[Mapping[str, Any]],
    state: Mapping[str, Any],
    *,
    algorithm_count: int | None = None,
) -> dict[str, Any]:
    """Summarize one causal 616-algorithm decision before its outcome exists."""
    candidate_side = _side(state.get("side"))
    evaluated = 0
    supporting = 0
    opposing = 0
    missing = 0
    for result in results:
        if not isinstance(result, Mapping):
            continue
        evaluated += 1
        view = str(result.get("view") or "").upper()
        applicability = str(result.get("applicability") or "").upper()
        if applicability == "MISSING_DATA" or view == "MISSING_DATA":
            missing += 1
        if applicability != "APPLICABLE" or view not in {"BUY", "SELL"}:
            continue
        if candidate_side and view == candidate_side:
            supporting += 1
        elif candidate_side:
            opposing += 1
    algorithm_count = len(ALGORITHM_MODULES) if algorithm_count is None else int(algorithm_count)
    directional = supporting + opposing
    directional_ratio = directional / algorithm_count if algorithm_count else 0.0
    support_ratio = supporting / directional if directional else 0.5
    rank_confidence = min(1.0, evaluated / algorithm_count) * math.sqrt(
        min(1.0, directional_ratio)
    ) if algorithm_count else 0.0
    rank_delta = (
        (supporting - opposing) / directional if directional else 0.0
    )
    rank_score = min(1.0, max(0.0, 0.5 + 0.5 * rank_delta * rank_confidence))
    return {
        "side": candidate_side,
        "evaluated_count": evaluated,
        "supporting_count": supporting,
        "opposing_count": opposing,
        "missing_count": missing,
        "directional_count": directional,
        "directional_ratio": directional_ratio,
        "support_ratio": support_ratio,
        "rank_confidence": rank_confidence,
        "rank_score": rank_score,
    }


def _book_outcome_bucket() -> dict[str, Any]:
    return {
        "rows": 0,
        "rows_with_net_outcome": 0,
        "wins": 0,
        "losses": 0,
        "draws": 0,
        "net_pnl": 0.0,
        "loss_values": [],
    }


def _update_book_outcome_bucket(
    bucket: dict[str, Any], net: float | None
) -> None:
    bucket["rows"] += 1
    if net is None:
        return
    bucket["rows_with_net_outcome"] += 1
    bucket["net_pnl"] += net
    if net > 0:
        bucket["wins"] += 1
    elif net < 0:
        bucket["losses"] += 1
        bucket["loss_values"].append(net)
    else:
        bucket["draws"] += 1


def _finalize_book_outcome_bucket(bucket: Mapping[str, Any]) -> dict[str, Any]:
    rows = int(bucket.get("rows_with_net_outcome", 0))
    net = float(bucket.get("net_pnl", 0.0))
    losses = sorted(float(value) for value in bucket.get("loss_values", ()))
    gross_wins = net - sum(losses)
    result = {
        key: int(bucket.get(key, 0))
        for key in ("rows", "rows_with_net_outcome", "wins", "losses", "draws")
    }
    result.update({
        "net_pnl": round(net, 12),
        "win_rate": (
            int(bucket.get("wins", 0)) / rows if rows else None
        ),
        "expectancy": net / rows if rows else None,
        "profit_factor": (
            gross_wins / abs(sum(losses))
            if losses and gross_wins > 0 else 0.0 if losses else None
        ),
        "p95_loss": (
            losses[max(0, math.ceil(len(losses) * 0.95) - 1)]
            if losses else None
        ),
    })
    return result


def _book_rank_bin(score: float) -> str:
    if score >= 0.60:
        return "strong_support"
    if score >= 0.55:
        return "support"
    if score >= 0.45:
        return "neutral"
    if score >= 0.40:
        return "opposition"
    return "strong_opposition"


def _update_book_consensus(
    aggregate: dict[str, Any],
    snapshot: Mapping[str, Any],
    net: float | None,
) -> None:
    aggregate["rows"] += 1
    score = float(snapshot.get("rank_score", 0.5))
    aggregate["rank_sum"] += score
    aggregate["rank_confidence_sum"] += float(snapshot.get("rank_confidence", 0.0))
    aggregate["support_ratio_sum"] += float(snapshot.get("support_ratio", 0.5))
    if int(snapshot.get("directional_count", 0) or 0) > 0:
        aggregate["directional_rows"] += 1
    if net is None:
        aggregate["rows_without_net_outcome"] += 1
    else:
        aggregate["rows_with_net_outcome"] += 1
    rank_bin = _book_rank_bin(score)
    _update_book_outcome_bucket(aggregate["by_rank_bin"][rank_bin], net)
    side = str(snapshot.get("side") or "").upper()
    if side in {"BUY", "SELL"}:
        _update_book_outcome_bucket(aggregate["by_side"].setdefault(side, _book_outcome_bucket()), net)


def _finalize_book_consensus(aggregate: Mapping[str, Any]) -> dict[str, Any]:
    rows = int(aggregate.get("rows", 0))
    by_side = aggregate.get("by_side") or {}
    return {
        "rows": rows,
        "rows_with_net_outcome": int(aggregate.get("rows_with_net_outcome", 0)),
        "rows_without_net_outcome": int(aggregate.get("rows_without_net_outcome", 0)),
        "book_algorithm_count": int(aggregate.get("algorithm_count", len(ALGORITHM_MODULES))),
        "rank_mean": float(aggregate.get("rank_sum", 0.0)) / rows if rows else None,
        "rank_confidence_mean": (
            float(aggregate.get("rank_confidence_sum", 0.0)) / rows if rows else None
        ),
        "support_ratio_mean": (
            float(aggregate.get("support_ratio_sum", 0.0)) / rows if rows else None
        ),
        "directional_rate": (
            int(aggregate.get("directional_rows", 0)) / rows if rows else None
        ),
        "by_rank_bin": {
            name: _finalize_book_outcome_bucket(
                (aggregate.get("by_rank_bin") or {}).get(name, _book_outcome_bucket())
            )
            for name in _BOOK_RANK_BINS
        },
        "by_side": {
            str(side): _finalize_book_outcome_bucket(bucket)
            for side, bucket in sorted(by_side.items())
        },
        "formula": "coverage_shrunk_v1",
        "no_lookahead": True,
        "research_only": True,
        "execution_authority": False,
    }


def _normalize_algorithm_names(algorithm_names: Sequence[str] | None) -> tuple[str, ...]:
    if algorithm_names is None:
        return tuple(ALGORITHM_MODULES)
    if isinstance(algorithm_names, str):
        algorithm_names = (algorithm_names,)
    names = tuple(dict.fromkeys(str(name) for name in algorithm_names if str(name)))
    unknown = [name for name in names if name not in ALGORITHM_MODULES]
    if unknown:
        raise ValueError("unknown Watcher algorithm: " + ",".join(unknown))
    if not names:
        raise ValueError("algorithm_names must not be empty")
    return names


def _normalize_split_ranges(
    split_ranges: Mapping[str, tuple[int, int]] | None,
    *,
    purge_rows: int = 0,
) -> dict[str, tuple[int, int]]:
    if split_ranges is None:
        return {}
    try:
        purge = int(purge_rows)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("purge_rows is invalid") from exc
    if purge < 0:
        raise ValueError("purge_rows is invalid")
    normalized: dict[str, tuple[int, int]] = {}
    for raw_name, raw_bounds in split_ranges.items():
        name = str(raw_name or "").strip()
        if not name or not isinstance(raw_bounds, (list, tuple)) or len(raw_bounds) != 2:
            raise ValueError("split range is invalid")
        try:
            start, end = int(raw_bounds[0]), int(raw_bounds[1])
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("split range is invalid") from exc
        if start < 0 or end <= start:
            raise ValueError("split range is invalid")
        normalized[name] = (start, end)
    ordered = sorted(normalized.values())
    if any(previous_end > start or start - previous_end < purge
           for (_, previous_end), (start, _) in zip(ordered, ordered[1:])):
        raise ValueError("split ranges overlap or violate purge_rows")
    return normalized


def replay_rows(
    rows: Iterable[Mapping[str, Any]],
    *,
    max_rows: int | None = None,
    algorithm_names: Sequence[str] | None = None,
    split_ranges: Mapping[str, tuple[int, int]] | None = None,
    purge_rows: int = 0,
    rejection_rate: float = 0.0,
    rejection_evidence: Mapping[str, Any] | None = None,
    pre_enriched: bool = False,
    include_universe_context: bool = True,
    reuse_same_quote_context: bool = False,
    capture_execution_trace: bool = False,
    execution_trace_limit: int = 256,
) -> dict[str, Any]:
    """Replay selected Watcher algorithms causally, optionally by time splits.

    ``split_ranges`` are half-open row-index intervals.  Rows in purge gaps
    still build prior-only history but contribute no split statistics, so a
    boundary cannot leak a just-finished label into the next split.
    """
    selected_names = _normalize_algorithm_names(algorithm_names)
    if not isinstance(execution_trace_limit, int) or isinstance(execution_trace_limit, bool) or execution_trace_limit <= 0:
        raise ValueError("execution_trace_limit must be a positive integer")
    execution_traces: dict[str, list[dict[str, Any]]] = (
        {name: [] for name in selected_names}
        if capture_execution_trace and algorithm_names is not None
        else {}
    )
    rejection_rate = _validate_rejection_rate(rejection_rate)
    normalized_splits = _normalize_split_ranges(split_ranges, purge_rows=purge_rows)
    aggregates = {name: _bucket() for name in selected_names}
    for bucket in aggregates.values():
        bucket["by_horizon"] = {}
    exact_buckets: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    split_state: dict[str, dict[str, Any]] = {
        name: {
            "start": start,
            "end": end,
            "rows_replayed": 0,
            "rows_with_net_outcome": 0,
            "rows_without_net_outcome": 0,
            "history_start": None,
            "history_end": None,
            "algorithms": {
                algorithm: {**_bucket(), "by_horizon": {}}
                for algorithm in selected_names
            },
            "exact_strategies": {},
        }
        for name, (start, end) in normalized_splits.items()
    }
    rows_replayed = 0
    rows_with_outcome = 0
    missing_outcome = 0
    cost_rows_complete = 0
    cost_rows_incomplete = 0
    cost_model_variants: set[tuple[float, ...]] = set()
    first_cost_model: dict[str, Any] | None = None
    first_time = None
    last_time = None
    # Rows are fed to the feature adapter only after the current row has been
    # evaluated.  This makes the replay chronological and prevents later
    # observations from becoming pre-entry context.
    history_by_symbol: dict[str, deque[dict[str, Any]]] = defaultdict(lambda: deque(maxlen=5000))
    cached_context_by_symbol: dict[str, tuple[Any, dict[str, Any]]] = {}
    book_consensus = {
        "algorithm_count": len(selected_names),
        "rows": 0,
        "rows_with_net_outcome": 0,
        "rows_without_net_outcome": 0,
        "rank_sum": 0.0,
        "rank_confidence_sum": 0.0,
        "support_ratio_sum": 0.0,
        "directional_rows": 0,
        "by_rank_bin": {name: _book_outcome_bucket() for name in _BOOK_RANK_BINS},
        "by_side": {},
    }
    for row in rows:
        if max_rows is not None and rows_replayed >= max_rows:
            break
        if not isinstance(row, Mapping):
            continue
        row_index = rows_replayed
        rows_replayed += 1
        symbol = str(row.get("symbol") or "").strip()
        quote_key = (symbol, row.get("time"))
        cached_context = cached_context_by_symbol.get(symbol)
        if (
            reuse_same_quote_context
            and not pre_enriched
            and cached_context is not None
            and cached_context[0] == quote_key[1]
        ):
            state = _overlay_cached_context(cached_context[1], row)
        else:
            state = build_pre_entry_state(
                row,
                symbol_history=history_by_symbol.get(symbol, ()),
                universe_history=history_by_symbol if include_universe_context else None,
                pre_enriched=pre_enriched,
            )
            if reuse_same_quote_context and not pre_enriched:
                cached_context_by_symbol[symbol] = (quote_key[1], dict(state))
        net = _net_outcome(row)
        if net is None:
            missing_outcome += 1
        else:
            rows_with_outcome += 1
        if _row_cost_model_is_complete(row):
            cost_rows_complete += 1
            if first_cost_model is None:
                first_cost_model = {
                    "spread": "executable_bid_ask_entry_and_liquidation",
                    "slippage_bps": _number(row.get("slippage_bps")),
                    "commission_round_trip_usd": _number(
                        row.get("commission_round_trip_usd")
                    ),
                    "entry_latency_s": _number(row.get("entry_latency_s")),
                    "close_latency_s": _number(row.get("close_latency_s")),
                    "usd_per_price_unit": _number(row.get("usd_per_price_unit")),
                    "outcome_units": _COST_MODEL_OUTCOME_UNITS,
                }
            if len(cost_model_variants) < 2:
                cost_model_variants.add(
                    (
                        float(row["slippage_bps"]),
                        float(row["commission_round_trip_usd"]),
                        float(row["entry_latency_s"]),
                        float(row["close_latency_s"]),
                    )
                )
        else:
            cost_rows_incomplete += 1
        timestamp = row.get("time")
        if timestamp is not None:
            first_time = timestamp if first_time is None else first_time
            last_time = timestamp
        horizon = state.get("horizon_s", "unknown")
        side = _side(state.get("side"))
        results = (
            evaluate_all(state)
            if algorithm_names is None
            else evaluate_selected(selected_names, state)
        )
        book_snapshot = _book_consensus_snapshot(
            results, state, algorithm_count=len(selected_names)
        )
        _update_book_consensus(book_consensus, book_snapshot, net)
        active_splits = []
        for split_name, split_info in split_state.items():
            if split_info["start"] <= row_index < split_info["end"]:
                active_splits.append(split_name)
                split_info["rows_replayed"] += 1
                if net is None:
                    split_info["rows_without_net_outcome"] += 1
                else:
                    split_info["rows_with_net_outcome"] += 1
                if timestamp is not None:
                    split_info["history_start"] = (
                        timestamp if split_info["history_start"] is None
                        else split_info["history_start"]
                    )
                    split_info["history_end"] = timestamp
        for result in results:
            name = str(result.get("algorithm_id") or "unknown")
            if name not in aggregates:
                continue
            bucket = aggregates[name]
            _update_bucket(bucket, result, state, net)
            horizon_bucket = bucket["by_horizon"].setdefault(str(horizon), _bucket())
            _update_bucket(horizon_bucket, result, state, net)
            for split_name in active_splits:
                split_bucket = split_state[split_name]["algorithms"][name]
                _update_bucket(split_bucket, result, state, net)
                identity = _exact_strategy_key(name, state, row)
                if identity is not None:
                    identity_bucket = split_state[split_name]["exact_strategies"].setdefault(
                        identity, _bucket()
                    )
                    _update_bucket(identity_bucket, result, state, net)
            identity = _exact_strategy_key(name, state, row)
            if identity is not None:
                identity_bucket = exact_buckets.setdefault(identity, _bucket())
                _update_bucket(identity_bucket, result, state, net)
            if (
                execution_traces
                and net is not None
                and str(result.get("view") or "").upper() == side
                and result.get("applicability") == "APPLICABLE"
                and len(execution_traces[name]) < execution_trace_limit
            ):
                from aegis.intel.integration_contracts import BasketIntent, OrderIntent

                basket_id = f"replay-basket-{row_index}"
                correlation_id = f"{name}:{symbol}:{row_index}"
                entry_price = _number(state.get("entry_price"))
                if entry_price is None:
                    entry_price = _number(state.get("entry"))
                order = OrderIntent(
                    event_id=f"replay-order-{name}-{row_index}",
                    correlation_id=correlation_id,
                    strategy_id=name,
                    basket_id=basket_id,
                    symbol=symbol,
                    event_ts=row.get("time"),
                    source="historical_replay",
                    reason="selected_causal_signal",
                    status="INTENDED",
                    payload={
                        "side": side,
                        "quantity": 1.0,
                        "entry_price": entry_price,
                        "horizon_s": state.get("horizon_s"),
                    },
                )
                basket = BasketIntent(
                    event_id=f"replay-basket-intent-{name}-{row_index}",
                    correlation_id=correlation_id,
                    strategy_id=name,
                    basket_id=basket_id,
                    symbol=symbol,
                    event_ts=row.get("time"),
                    source="historical_replay",
                    reason="selected_causal_signal",
                    status="CREATED",
                    payload={"legs": [order.to_dict()]},
                )
                execution_traces[name].append(
                    {
                        "event_index": row_index,
                        "timestamp": row.get("time"),
                        "strategy_id": name,
                        "symbol": symbol,
                        "side": side,
                        "horizon_s": state.get("horizon_s"),
                        "entry_price": entry_price,
                        "bid": _number(row.get("bid")),
                        "ask": _number(row.get("ask")),
                        "net_outcome": float(net),
                        "outcome_field": "captured_exit_return_preferred",
                        "order_intent": order.to_dict(),
                        "basket_intent": basket.to_dict(),
                    }
                )
        if symbol:
            history = history_by_symbol[symbol]
            row_time = row.get("time")
            if history and row_time is not None and history[-1].get("time") == row_time:
                history[-1] = _history_quote_snapshot(row)
            else:
                history.append(_history_quote_snapshot(row))
    algorithms = {}
    for name, bucket in aggregates.items():
        finalized = _finalize_bucket(bucket, rejection_rate=rejection_rate)
        algorithms[name] = finalized
    split_report: dict[str, Any] = {}
    for split_name, split_info in split_state.items():
        split_report[split_name] = {
            "row_start": split_info["start"],
            "row_end": split_info["end"],
            "rows_replayed": split_info["rows_replayed"],
            "rows_with_net_outcome": split_info["rows_with_net_outcome"],
            "rows_without_net_outcome": split_info["rows_without_net_outcome"],
            "history_start": split_info["history_start"],
            "history_end": split_info["history_end"],
            "algorithm_count": len(selected_names),
            "algorithm_ids": list(selected_names),
            "algorithms": {
                name: _finalize_bucket(bucket, rejection_rate=rejection_rate)
                for name, bucket in split_info["algorithms"].items()
            },
            "exact_strategies": {
                _format_exact_strategy_key(identity): _finalize_bucket(
                    bucket, rejection_rate=rejection_rate
                )
                for identity, bucket in sorted(
                    split_info["exact_strategies"].items(),
                    key=lambda item: _format_exact_strategy_key(item[0]),
                )
            },
            "no_lookahead": True,
            "research_only": True,
            "execution_authority": False,
        }
    book_status_counts = {
        status: sum(value == status for value in BOOK_REVIEW_COVERAGE.values())
        for status in sorted(set(BOOK_REVIEW_COVERAGE.values()))
    }
    report = {
        "schema": "watcher_algorithm_historical_replay.v1",
        "evidence_source": "fast_edge_shadow_rows",
        "feature_adapter": "watcher_feature_engine.v1",
        "feature_history_order": "prior_rows_only",
        "input_feature_mode": (
            "pre_enriched_causal_row" if pre_enriched else "reconstructed_prior_history"
        ),
        "universe_context": "included" if include_universe_context else "omitted_for_selected_replay",
        "same_quote_context_reuse": bool(reuse_same_quote_context and not pre_enriched),
        "outcome_field": "captured_exit_return_preferred",
        "outcome_attached_after_evaluation": True,
        "rows_replayed": rows_replayed,
        "rows_with_net_outcome": rows_with_outcome,
        "rows_without_net_outcome": missing_outcome,
        "cost_model_provenance": {
            "schema": _COST_MODEL_SCHEMA,
            "status": (
                "COMPLETE"
                if rows_replayed > 0 and cost_rows_complete == rows_replayed
                else "INCOMPLETE"
            ),
            "rows_checked": rows_replayed,
            "rows_complete": cost_rows_complete,
            "rows_incomplete": cost_rows_incomplete,
            "uniform_parameters": len(cost_model_variants) <= 1,
            "per_row": True,
            "spread": (
                first_cost_model.get("spread") if first_cost_model is not None else None
            ),
            "slippage_bps": (
                first_cost_model.get("slippage_bps")
                if first_cost_model is not None else None
            ),
            "commission_round_trip_usd": (
                first_cost_model.get("commission_round_trip_usd")
                if first_cost_model is not None else None
            ),
            "entry_latency_s": (
                first_cost_model.get("entry_latency_s")
                if first_cost_model is not None else None
            ),
            "close_latency_s": (
                first_cost_model.get("close_latency_s")
                if first_cost_model is not None else None
            ),
            "usd_per_price_unit": (
                first_cost_model.get("usd_per_price_unit")
                if first_cost_model is not None else None
            ),
            "outcome_units": _COST_MODEL_OUTCOME_UNITS,
        },
        "history_start": first_time,
        "history_end": last_time,
        "algorithm_count": len(selected_names),
        "algorithm_ids": list(selected_names),
        "algorithm_selection": (
            "all_registered" if algorithm_names is None else "explicit_selected"
        ),
        "algorithms": algorithms,
        "exact_strategies": {
            _format_exact_strategy_key(identity): _finalize_bucket(
                bucket, rejection_rate=rejection_rate
            )
            for identity, bucket in sorted(
                exact_buckets.items(),
                key=lambda item: _format_exact_strategy_key(item[0]),
            )
        },
        "rejection_adjustment": {
            "rate": rejection_rate,
            "applied_to_expectancy": True,
            "classification_counts_unchanged": True,
            "evidence": dict(rejection_evidence or {}),
        },
        "book_consensus": _finalize_book_consensus(book_consensus),
        "book_coverage": {
            "book_count": len(BOOK_REVIEW_COVERAGE),
            "book_status_counts": book_status_counts,
            "all_books_mapped": set(BOOK_REVIEW_COVERAGE) == set(BOOK_ALGORITHM_COVERAGE),
            "book_to_algorithms": {
                book: list(algorithms)
                for book, algorithms in BOOK_ALGORITHM_COVERAGE.items()
            },
        },
        "no_lookahead": True,
        "research_only": True,
        "execution_authority": False,
        "notes": [
            "Signal statistics are descriptive historical shadow results, not execution authorization.",
            "Rows lacking a captured net outcome are excluded from outcome statistics.",
            "Quote-derived chart and microstructure features use only observations at or before the row timestamp.",
            "Tick activity and tick-price profiles are explicitly proxies, not traded-volume measurements.",
            "M1/generic or synthetic context is not promoted to micro-horizon broker probability.",
            "Explicit selected replay evaluates only the requested algorithms; it does not rerun the full registry.",
            "Primary outcome prefers captured_exit_return, a broker-unit-normalized after-cost return; legacy raw net PnL is fallback only.",
            "Cost-model provenance is complete only when every input row carries executable spread, slippage, commission, latency, conversion, and outcome-unit metadata.",
            "Rejection adjustment is reported separately as effective expectancy; it never changes signal win/loss classification or safety gates.",
        ],
    }
    if execution_traces:
        report["execution_traces"] = execution_traces
        report["execution_trace_provenance"] = {
            "schema": "aegis.replay_execution_trace.v1",
            "policy": "selected_signal_after_cost_outcome",
            "max_rows_per_strategy": execution_trace_limit,
            "outcome_attached_after_evaluation": True,
        }
    if normalized_splits:
        report["split_replay_ranges"] = {
            name: {"start": start, "end": end}
            for name, (start, end) in normalized_splits.items()
        }
        report["split_replay_purge_rows"] = int(purge_rows)
        report["split_replay_policy"] = "chronological_forward_horizon_purge.v1"
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
    path: Path,
    *,
    max_rows: int | None = None,
    algorithm_names: Sequence[str] | None = None,
    split_ranges: Mapping[str, tuple[int, int]] | None = None,
    purge_rows: int = 0,
    rejection_rate: float = 0.0,
    rejection_evidence: Mapping[str, Any] | None = None,
    pre_enriched: bool = False,
    include_universe_context: bool = True,
    reuse_same_quote_context: bool = False,
    capture_execution_trace: bool = False,
    execution_trace_limit: int = 256,
) -> dict[str, Any]:
    report = replay_rows(
        iter_jsonl(path),
        max_rows=max_rows,
        algorithm_names=algorithm_names,
        split_ranges=split_ranges,
        purge_rows=purge_rows,
        rejection_rate=rejection_rate,
        rejection_evidence=rejection_evidence,
        pre_enriched=pre_enriched,
        include_universe_context=include_universe_context,
        reuse_same_quote_context=reuse_same_quote_context,
        capture_execution_trace=capture_execution_trace,
        execution_trace_limit=execution_trace_limit,
    )
    report["input_path"] = str(Path(path))
    return report


__all__ = ["build_pre_entry_state", "iter_jsonl", "replay_jsonl", "replay_rows"]
