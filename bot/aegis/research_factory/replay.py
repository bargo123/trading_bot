"""Chronological replay using explicit broker-native execution evidence."""
from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from typing import Any, Mapping, Optional, Tuple

import pandas as pd

from aegis.intel.broker_math import BrokerSymbolSpec
from aegis.research_factory.rules import CompileResult


@dataclass(frozen=True)
class ReplayCostEvidence:
    """Observed execution costs and broker conversion evidence."""

    symbol_spec: BrokerSymbolSpec
    lots: float
    spread_price: Optional[float]
    commission_usd: float
    slippage_price: float


@dataclass(frozen=True)
class ReplayTrade:
    """One closed replay position."""

    side: str
    entry_time: Any
    exit_time: Any
    entry_price: float
    exit_price: float
    exit_reason: str
    gross_pnl_usd: float
    cost_usd: float
    net_pnl_usd: float
    mfe_r: float | None = None
    mae_r: float | None = None
    holding_s: float | None = None
    loss_r: float | None = None


@dataclass(frozen=True)
class ReplayResult:
    """Auditable terminal replay outcome."""

    status: str
    trades: Tuple[ReplayTrade, ...]
    metrics: Optional[Mapping[str, float]]
    reason: str


def _result(status: str, reason: str) -> ReplayResult:
    return ReplayResult(status=status, trades=(), metrics=None, reason=reason)


def _real_number(value: Any) -> bool:
    if not isinstance(value, Real) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except (OverflowError, TypeError, ValueError):
        return False


def _cost_evidence_reason(costs: Any) -> Optional[str]:
    if not isinstance(costs, ReplayCostEvidence):
        return "replay cost evidence is malformed"
    if not isinstance(costs.symbol_spec, BrokerSymbolSpec):
        return "broker symbol specification is required"
    values = (
        costs.symbol_spec.trade_tick_value,
        costs.symbol_spec.trade_tick_size,
        costs.symbol_spec.volume_min,
        costs.lots,
    )
    if not all(_real_number(value) and value > 0 for value in values):
        return "positive broker tick, volume, and lot evidence is required"
    non_negative = (costs.commission_usd, costs.slippage_price)
    if not all(_real_number(value) and value >= 0 for value in non_negative):
        return "commission and slippage evidence must be non-negative"
    if costs.spread_price is not None and (
        not _real_number(costs.spread_price) or costs.spread_price < 0
    ):
        return "spread evidence must be non-negative"
    return None


def _entry_signals(data: pd.DataFrame, compiled: CompileResult) -> pd.Series:
    rule = compiled.entry_rule or {}
    direction = rule.get("direction")
    if rule.get("type") == "breakout":
        window = rule["window"]
        if direction == "long":
            boundary = data["high"].rolling(window).max().shift(1)
            return (data["close"] > boundary).fillna(False)
        boundary = data["low"].rolling(window).min().shift(1)
        return (data["close"] < boundary).fillna(False)
    if rule.get("type") == "mean_reversion":
        z_score = (data["close"] - data["sma_20"]) / data["close"].rolling(20).std()
        threshold = rule["z_threshold"]
        if direction == "long":
            return (z_score < -threshold).fillna(False)
        return (z_score > threshold).fillna(False)
    if rule.get("type") == "regime_structure_alignment":
        regime_ok = data["regime"].isin(rule["required_regimes"])
        structure_ok = data["structure"].notna()
        return (regime_ok & structure_ok).fillna(False)
    raise ValueError(f"unsupported compiled entry rule: {rule.get('type')}")


def _quote_columns(columns: set[str]) -> Optional[tuple[str, str]]:
    if {"bid", "ask"} <= columns:
        return "bid", "ask"
    if {"close_bid", "close_ask"} <= columns:
        return "close_bid", "close_ask"
    return None


def _execution_prices(
    row: pd.Series,
    side: str,
    spread_price: Optional[float],
    slippage_price: float,
    quote_columns: Optional[tuple[str, str]],
) -> tuple[float, float, float, float, float]:
    half_slippage = slippage_price / 2.0
    if quote_columns is not None:
        bid = float(row[quote_columns[0]])
        ask = float(row[quote_columns[1]])
        observed_spread = ask - bid
        if not all(math.isfinite(value) for value in (bid, ask)) or observed_spread < 0:
            raise ValueError("bid/ask evidence must be finite and non-crossed")
        half_spread = observed_spread / 2.0
        if side == "buy":
            entry = ask + half_slippage
            high = float(
                row["high_bid"]
                if "high_bid" in row.index
                else float(row["high"]) - half_spread
                if "high" in row.index
                else bid
            )
            low = float(
                row["low_bid"]
                if "low_bid" in row.index
                else float(row["low"]) - half_spread
                if "low" in row.index
                else bid
            )
            liquidation = bid - half_slippage
        else:
            entry = bid - half_slippage
            high = float(
                row["high_ask"]
                if "high_ask" in row.index
                else float(row["high"]) + half_spread
                if "high" in row.index
                else ask
            )
            low = float(
                row["low_ask"]
                if "low_ask" in row.index
                else float(row["low"]) + half_spread
                if "low" in row.index
                else ask
            )
            liquidation = ask + half_slippage
        prices = (entry, high, low, liquidation, observed_spread)
        if not all(math.isfinite(value) for value in prices):
            raise ValueError("executable price observation must be finite")
        return prices

    if spread_price is None:
        raise ValueError("spread evidence is required without bid/ask data")
    half_spread = spread_price / 2.0
    if side == "buy":
        prices = (
            float(row["close"]) + half_spread + half_slippage,
            float(row["high"]) - half_spread,
            float(row["low"]) - half_spread,
            float(row["close"]) - half_spread - half_slippage,
            spread_price,
        )
    else:
        prices = (
            float(row["close"]) - half_spread - half_slippage,
            float(row["high"]) + half_spread,
            float(row["low"]) + half_spread,
            float(row["close"]) + half_spread + half_slippage,
            spread_price,
        )
    if not all(math.isfinite(value) for value in prices):
        raise ValueError("executable price observation must be finite")
    return prices


def _reference_close(
    row: pd.Series, quote_columns: Optional[tuple[str, str]]
) -> float:
    if quote_columns is not None:
        return (float(row[quote_columns[0]]) + float(row[quote_columns[1]])) / 2.0
    if "close" in row.index:
        return float(row["close"])
    raise ValueError("a close or bid/ask pair is required for replay")


def _execution_observation(
    row: pd.Series,
    side: str,
    costs: ReplayCostEvidence,
    quote_columns: Optional[tuple[str, str]],
) -> tuple[float, float, float, float, float, float]:
    prices = _execution_prices(
        row,
        side,
        costs.spread_price,
        costs.slippage_price,
        quote_columns,
    )
    reference = _reference_close(row, quote_columns)
    if not math.isfinite(reference):
        raise ValueError("executable price reference must be finite")
    return *prices, reference


def _valid_fill_geometry(compiled: CompileResult, entry_fill: float) -> bool:
    stop = compiled.invalidation_price
    target = compiled.target_price
    if compiled.side == "buy":
        return (stop is None or stop < entry_fill) and (
            target is None or target > entry_fill
        )
    return (stop is None or stop > entry_fill) and (
        target is None or target < entry_fill
    )


def _closed_trade(
    *,
    side: str,
    position: Mapping[str, Any],
    exit_time: Any,
    exit_price: float,
    exit_reference: float,
    exit_reason: str,
    costs: ReplayCostEvidence,
    entry_spread: float,
    exit_spread: float,
    mfe_r: float | None = None,
    mae_r: float | None = None,
    risk_usd: float | None = None,
) -> ReplayTrade:
    direction = 1.0 if side == "buy" else -1.0
    gross_pnl = costs.symbol_spec.price_units_to_usd(
        direction * (exit_reference - position["reference"]), costs.lots
    )
    round_trip_spread = (entry_spread + exit_spread) / 2.0
    cost_usd = costs.symbol_spec.price_units_to_usd(
        round_trip_spread + costs.slippage_price, costs.lots
    ) + costs.commission_usd
    net_pnl = gross_pnl - cost_usd
    try:
        holding_s = float((exit_time - position["time"]).total_seconds())
    except (AttributeError, TypeError, ValueError):
        holding_s = None
    loss_r = None if risk_usd is None or risk_usd <= 0 else min(net_pnl / risk_usd, 0.0)
    return ReplayTrade(
        side=side,
        entry_time=position["time"],
        exit_time=exit_time,
        entry_price=position["fill"],
        exit_price=exit_price,
        exit_reason=exit_reason,
        gross_pnl_usd=gross_pnl,
        cost_usd=cost_usd,
        net_pnl_usd=net_pnl,
        mfe_r=mfe_r,
        mae_r=mae_r,
        holding_s=holding_s,
        loss_r=loss_r,
    )


def _metrics(trades: tuple[ReplayTrade, ...]) -> Mapping[str, float]:
    net = [trade.net_pnl_usd for trade in trades]
    running = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for pnl in net:
        running += pnl
        peak = max(peak, running)
        max_drawdown = max(max_drawdown, peak - running)
    return {
        "trade_count": float(len(trades)),
        "gross_pnl_usd": sum(trade.gross_pnl_usd for trade in trades),
        "cost_usd": sum(trade.cost_usd for trade in trades),
        "net_pnl_usd": sum(net),
        "expectancy_usd": sum(net) / len(net),
        "win_rate": sum(pnl > 0 for pnl in net) / len(net),
        "max_drawdown_usd": max_drawdown,
    }


def replay_hypothesis(
    data: pd.DataFrame,
    compiled: Optional[CompileResult],
    costs: Optional[ReplayCostEvidence],
    *,
    entry_signals: Optional[pd.Series] = None,
) -> ReplayResult:
    """Replay an executable hypothesis or fail closed without cost evidence."""
    if costs is None:
        return _result("NO_EVIDENCE", "replay cost evidence is required")
    evidence_reason = _cost_evidence_reason(costs)
    if evidence_reason:
        return _result("NO_EVIDENCE", evidence_reason)
    if compiled is None or compiled.status != "EXECUTABLE":
        return _result("NOT_EXECUTABLE", "an executable compiled hypothesis is required")
    if compiled.side not in {"buy", "sell"}:
        return _result("NOT_EXECUTABLE", "compiled side must be buy or sell")
    missing = sorted(set(compiled.required_columns) - set(data.columns))
    if missing:
        return _result("NOT_EXECUTABLE", f"missing replay columns: {', '.join(missing)}")
    if data.empty:
        return _result("NO_DATA", "replay data is empty")
    quote_columns = _quote_columns(set(data.columns))
    if costs.spread_price is None and quote_columns is None:
        return _result("NO_EVIDENCE", "spread evidence is required without bid/ask data")

    frame = data.copy()
    if "time" in frame:
        timestamps = pd.to_datetime(frame["time"], utc=True, errors="coerce")
        if timestamps.isna().any():
            return _result("NO_DATA", "replay timestamps must be valid")
        frame = frame.assign(time=timestamps).sort_values("time", kind="stable")
    try:
        signals = _entry_signals(frame, compiled)
    except (KeyError, TypeError, ValueError) as exc:
        return _result("NOT_EXECUTABLE", str(exc))
    if entry_signals is not None:
        if len(entry_signals) != len(frame):
            return _result("NOT_EXECUTABLE", "ML entry signals do not match replay rows")
        signals = signals & pd.Series(
            entry_signals.to_numpy(dtype=bool), index=frame.index
        )
    side = compiled.side
    trades: list[ReplayTrade] = []
    position: Optional[dict[str, Any]] = None

    for offset, (_, row) in enumerate(frame.iterrows()):
        if position is None:
            if not bool(signals.iloc[offset]):
                continue
            try:
                entry_fill, _, _, _, observed_spread, reference = _execution_observation(
                    row,
                    side,
                    costs,
                    quote_columns,
                )
            except (KeyError, OverflowError, TypeError, ValueError) as exc:
                return _result("NO_EVIDENCE", str(exc))
            if not _valid_fill_geometry(compiled, entry_fill):
                return _result(
                    "NOT_EXECUTABLE",
                    "stop/target geometry is invalid at the replay entry fill",
                )
            position = {
                "time": row.get("time", frame.index[offset]),
                "fill": entry_fill,
                "reference": reference,
                "offset": offset,
                "spread": observed_spread,
                "risk_price": (
                    abs(reference - float(compiled.invalidation_price))
                    if compiled.invalidation_price is not None else None
                ),
                "mfe_r": 0.0,
                "mae_r": 0.0,
            }
            continue

        try:
            (
                _,
                executable_high,
                executable_low,
                liquidation,
                observed_spread,
                reference,
            ) = (
                _execution_observation(
                    row,
                    side,
                    costs,
                    quote_columns,
                )
            )
        except (KeyError, OverflowError, TypeError, ValueError) as exc:
            return _result("NO_EVIDENCE", str(exc))
        risk_price = position.get("risk_price")
        if risk_price is not None and risk_price > 0:
            if side == "buy":
                favorable = max(0.0, executable_high - position["reference"])
                adverse = max(0.0, position["reference"] - executable_low)
            else:
                favorable = max(0.0, position["reference"] - executable_low)
                adverse = max(0.0, executable_high - position["reference"])
            position["mfe_r"] = max(position["mfe_r"], favorable / risk_price)
            position["mae_r"] = max(position["mae_r"], adverse / risk_price)
        stop = compiled.invalidation_price
        target = compiled.target_price
        stop_hit = stop is not None and (
            executable_low <= stop if side == "buy" else executable_high >= stop
        )
        target_hit = target is not None and (
            executable_high >= target if side == "buy" else executable_low <= target
        )
        elapsed = False
        if compiled.max_hold_s is not None:
            elapsed = (
                row["time"] - position["time"]
            ).total_seconds() >= compiled.max_hold_s
        regime_changed = (
            (compiled.exit_rule or {}).get("type") == "regime_change"
            and offset > 0
            and row["regime"] != frame.iloc[offset - 1]["regime"]
        )
        if not stop_hit and not target_hit and not regime_changed and not elapsed:
            continue

        if stop_hit:
            exit_price = float(stop)
            exit_reference = exit_price
            exit_reason = "stop"
        elif target_hit:
            exit_price = float(target)
            exit_reference = exit_price
            exit_reason = "target"
        elif regime_changed:
            exit_price = liquidation
            exit_reference = reference
            exit_reason = "regime_change"
        else:
            exit_price = liquidation
            exit_reference = reference
            exit_reason = "elapsed_time"
        trades.append(
            _closed_trade(
                side=side,
                exit_time=row.get("time", frame.index[offset]),
                position=position,
                exit_price=exit_price,
                exit_reference=exit_reference,
                exit_reason=exit_reason,
                costs=costs,
                entry_spread=position["spread"],
                exit_spread=observed_spread,
                mfe_r=position["mfe_r"],
                mae_r=position["mae_r"],
                risk_usd=(
                    costs.symbol_spec.price_units_to_usd(risk_price, costs.lots)
                    if risk_price is not None and risk_price > 0 else None
                ),
            )
        )
        position = None

    if position is not None:
        final_row = frame.iloc[-1]
        try:
            _, _, _, liquidation, observed_spread, reference = _execution_observation(
                final_row,
                side,
                costs,
                quote_columns,
            )
        except (KeyError, OverflowError, TypeError, ValueError) as exc:
            return _result("NO_EVIDENCE", str(exc))
        trades.append(
            _closed_trade(
                side=side,
                position=position,
                exit_time=final_row.get("time", frame.index[-1]),
                exit_price=liquidation,
                exit_reference=reference,
                exit_reason="end_of_data",
                costs=costs,
                entry_spread=position["spread"],
                exit_spread=observed_spread,
                mfe_r=position["mfe_r"],
                mae_r=position["mae_r"],
                risk_usd=(
                    costs.symbol_spec.price_units_to_usd(position["risk_price"], costs.lots)
                    if position.get("risk_price") is not None and position["risk_price"] > 0
                    else None
                ),
            )
        )
    closed = tuple(trades)
    if not closed:
        return _result("NO_TRADES", "no executable entry signals")
    return ReplayResult(
        status="COMPLETED",
        trades=closed,
        metrics=_metrics(closed),
        reason="",
    )
