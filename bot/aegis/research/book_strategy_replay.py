"""After-cost, executable-price replay for exact strategy evidence."""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Iterable, Mapping, Sequence


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _timestamp(value: Any) -> float | None:
    return _number(value)


def _valid_quote(row: Mapping[str, Any]) -> bool:
    return _number(row.get("bid")) is not None and _number(row.get("ask")) is not None


def _favorable(entry: float, row: Mapping[str, Any], side: str) -> float | None:
    bid = _number(row.get("bid"))
    ask = _number(row.get("ask"))
    if bid is None or ask is None:
        return None
    return (bid - entry) if side == "BUY" else (entry - ask)


def replay_executable_outcome(
    quotes: Sequence[Mapping[str, Any]],
    *,
    side: str,
    horizon_s: int,
    entry_cost_usd: float = 0.0,
    commission_usd: float = 0.0,
    slippage_usd: float = 0.0,
    strategy_id: str | None = None,
    symbol: str | None = None,
    mechanism: str | None = None,
    evidence_source: str = "historical_executable_replay",
) -> dict[str, Any]:
    """Replay one sample using the broker-executable side of every quote."""
    normalized_side = str(side or "").upper()
    if normalized_side not in {"BUY", "SELL"} or int(horizon_s) <= 0:
        return {"status": "INVALID_INPUT", "reason": "invalid_side_or_horizon"}
    ordered = sorted((row for row in quotes if isinstance(row, Mapping)), key=lambda row: _timestamp(row.get("timestamp")) or 0.0)
    valid = [row for row in ordered if _valid_quote(row) and _timestamp(row.get("timestamp")) is not None]
    if not valid:
        return {"status": "MISSING_QUOTE", "reason": "no_executable_quotes", "horizon_s": int(horizon_s)}
    entry_row = valid[0]
    entry_time = _timestamp(entry_row.get("timestamp"))
    bid = _number(entry_row.get("bid"))
    ask = _number(entry_row.get("ask"))
    assert entry_time is not None and bid is not None and ask is not None
    entry_price = ask if normalized_side == "BUY" else bid
    exit_time = entry_time + int(horizon_s)
    horizon_row = next((row for row in valid if (_timestamp(row.get("timestamp")) or 0.0) >= exit_time), None)
    if horizon_row is None:
        return {
            "status": "MISSING_QUOTE",
            "reason": "horizon_quote_missing",
            "horizon_s": int(horizon_s),
            "entry_time": entry_time,
            "entry_price": entry_price,
        }
    liquidation = _number(horizon_row.get("bid")) if normalized_side == "BUY" else _number(horizon_row.get("ask"))
    if liquidation is None:
        return {"status": "MISSING_QUOTE", "reason": "invalid_liquidation_quote", "horizon_s": int(horizon_s)}
    gross = (liquidation - entry_price) if normalized_side == "BUY" else (entry_price - liquidation)
    costs = sum(value for value in (_number(entry_cost_usd), _number(commission_usd), _number(slippage_usd)) if value is not None)
    net = gross - costs
    path = [row for row in valid if (_timestamp(row.get("timestamp")) or 0.0) <= (_timestamp(horizon_row.get("timestamp")) or exit_time)]
    favorable_values = [value for value in (_favorable(entry_price, row, normalized_side) for row in path) if value is not None]
    favorable = max(favorable_values, default=0.0)
    adverse = min(favorable_values, default=0.0)
    green_row = next((row for row in path if (_favorable(entry_price, row, normalized_side) or 0.0) - costs > 0), None)
    peak_value = max(favorable_values, default=0.0)
    peak_row = next((row for row in path if _favorable(entry_price, row, normalized_side) == peak_value), None)
    result = {
        "status": "REPLAYED",
        "evidence_source": evidence_source,
        "strategy_id": strategy_id,
        "symbol": symbol,
        "side": normalized_side,
        "mechanism": mechanism,
        "horizon_s": int(horizon_s),
        "entry_time": entry_time,
        "entry_price": entry_price,
        "exit_time": _timestamp(horizon_row.get("timestamp")),
        "exit_price": liquidation,
        "gross_pnl": gross,
        "costs_usd": costs,
        "entry_cost_usd": _number(entry_cost_usd) or 0.0,
        "commission_usd": _number(commission_usd) or 0.0,
        "slippage_usd": _number(slippage_usd) or 0.0,
        "net_pnl": net,
        "p_captured_win": float(net > 0),
        "mfe": favorable,
        "mae": adverse,
        "time_to_first_net_green": (
            (_timestamp(green_row.get("timestamp")) or entry_time) - entry_time if green_row is not None else None
        ),
        "never_green": green_row is None,
        "green_then_loser": green_row is not None and net <= 0,
        "time_to_peak": (
            (_timestamp(peak_row.get("timestamp")) or entry_time) - entry_time if peak_row is not None else None
        ),
        "spread": ask - bid,
        "tail_loss": min(0.0, net),
    }
    return result


def _single_summary(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    outcomes = [row for row in rows if _number(row.get("net_pnl")) is not None]
    nets = [_number(row.get("net_pnl")) for row in outcomes]
    values = [number for number in nets if number is not None]
    wins = [value for value in values if value > 0]
    losses = [value for value in values if value < 0]
    summary: dict[str, Any] = {
        "sample_size": len(values),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": len(wins) / len(values) if values else None,
        "expectancy": sum(values) / len(values) if values else None,
        "avg_winner": sum(wins) / len(wins) if wins else None,
        "avg_loser": sum(losses) / len(losses) if losses else None,
        "profit_factor": sum(wins) / abs(sum(losses)) if wins and losses else None,
        "p95_loss": sorted(losses)[max(0, math.ceil(len(losses) * 0.95) - 1)] if losses else None,
    }
    probabilities = [_number(row.get("predicted_probability")) for row in outcomes]
    paired = [(p, float(_number(row.get("net_pnl")) > 0)) for row, p in zip(outcomes, probabilities) if p is not None]
    if paired:
        bins: dict[int, list[tuple[float, float]]] = defaultdict(list)
        for probability, label in paired:
            bins[min(9, int(probability * 10))].append((probability, label))
        summary["calibration_ece"] = sum(
            len(bucket) / len(paired) * abs(sum(p for p, _ in bucket) / len(bucket) - sum(label for _, label in bucket) / len(bucket))
            for bucket in bins.values()
        )
    else:
        summary["calibration_ece"] = None
    return summary


def summarize_strategy_evidence(outcomes: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    rows = [dict(row) for row in outcomes if isinstance(row, Mapping)]
    summary = _single_summary(rows)
    by_horizon: dict[str, dict[str, Any]] = {}
    provenance_counts: dict[str, int] = {}
    for row in rows:
        horizon = row.get("horizon_s")
        if horizon is not None:
            key = str(int(float(horizon)))
            by_horizon[key] = _single_summary([item for item in rows if str(item.get("horizon_s")) == key])
        source = str(row.get("evidence_source") or "UNKNOWN")
        provenance_counts[source] = provenance_counts.get(source, 0) + 1
    summary["by_horizon"] = by_horizon
    summary["provenance_counts"] = provenance_counts
    return summary


def replay_strategy_matches(
    strategy: Mapping[str, Any],
    contexts: Sequence[Mapping[str, Any]],
    quote_history: Mapping[str, Sequence[Mapping[str, Any]]] | Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Replay only contexts already matched before entry, with no lookahead."""
    matches: list[dict[str, Any]] = []
    for context in contexts:
        if str(context.get("evaluation_status") or context.get("status") or "").upper() not in {"MATCH", "APPLICABLE"}:
            continue
        if isinstance(quote_history, Mapping):
            quotes = quote_history.get(str(context.get("symbol") or ""), ())
        else:
            quotes = quote_history
        result = replay_executable_outcome(
            quotes,
            side=str(context.get("side") or strategy.get("side_rule") or ""),
            horizon_s=int(float(context.get("horizon_s") or strategy.get("horizon_s") or 0)),
            strategy_id=str(strategy.get("strategy_id") or strategy.get("record_id") or "") or None,
            symbol=str(context.get("symbol") or "") or None,
            mechanism=str(context.get("mechanism") or strategy.get("strategy_family") or "") or None,
        )
        result["context_hash"] = context.get("context_hash")
        matches.append(result)
    return matches


__all__ = ["replay_executable_outcome", "replay_strategy_matches", "summarize_strategy_evidence"]
