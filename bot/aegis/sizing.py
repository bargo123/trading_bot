"""Conservative stop-distance position sizing for broker contracts."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_FLOOR
from math import isfinite
from typing import Any, Mapping


@dataclass(frozen=True)
class ContractSpec:
    symbol: str
    tick_size: float
    tick_value: float
    contract_size: float
    volume_min: float
    volume_max: float
    volume_step: float

    @classmethod
    def from_mapping(cls, symbol: str, raw: Mapping[str, Any]) -> "ContractSpec":
        tick_values: list[float] = []
        for field in (
            "trade_tick_value_profit",
            "trade_tick_value_loss",
            "trade_tick_value",
        ):
            supplied = raw.get(field)
            try:
                value = 0.0 if supplied is None else abs(float(supplied))
            except (TypeError, ValueError) as exc:
                raise ValueError("tick_value") from exc
            if not isfinite(value):
                raise ValueError("tick_value")
            tick_values.append(value)
        return cls(
            symbol=str(raw.get("name") or symbol),
            tick_size=float(raw.get("trade_tick_size") or raw.get("point") or 0.0),
            tick_value=max(tick_values),
            contract_size=float(raw.get("trade_contract_size") or 0.0),
            volume_min=float(raw.get("volume_min") or 0.0),
            volume_max=float(raw.get("volume_max") or 0.0),
            volume_step=float(raw.get("volume_step") or 0.0),
        )


@dataclass(frozen=True)
class SizingDecision:
    allowed: bool
    lots: float
    risk_usd: float
    budget_usd: float
    reason: str = ""


def size_lots_for_risk(
    *, equity: float, risk_percent: float, entry: float, stop: float, spec: ContractSpec
) -> SizingDecision:
    budget = equity * risk_percent / 100.0
    if not isfinite(equity) or equity <= 0:
        return SizingDecision(False, 0.0, 0.0, budget, "equity")
    if not isfinite(risk_percent) or risk_percent <= 0:
        return SizingDecision(False, 0.0, 0.0, budget, "risk_percent")
    if (
        not isfinite(entry)
        or not isfinite(stop)
        or entry <= 0
        or stop <= 0
        or abs(entry - stop) <= 0
    ):
        return SizingDecision(False, 0.0, 0.0, budget, "stop_distance")
    if (
        not isfinite(spec.tick_size)
        or not isfinite(spec.tick_value)
        or spec.tick_size <= 0
        or spec.tick_value <= 0
    ):
        return SizingDecision(False, 0.0, 0.0, budget, "tick_value")
    if not isfinite(spec.contract_size) or spec.contract_size <= 0:
        return SizingDecision(False, 0.0, 0.0, budget, "contract_size")
    if (
        not isfinite(spec.volume_min)
        or not isfinite(spec.volume_max)
        or not isfinite(spec.volume_step)
        or spec.volume_min <= 0
        or spec.volume_max <= 0
        or spec.volume_step <= 0
        or spec.volume_max < spec.volume_min
    ):
        return SizingDecision(False, 0.0, 0.0, budget, "volume_spec")
    decimal_budget = Decimal(str(equity)) * Decimal(str(risk_percent)) / Decimal("100")
    ticks = abs(Decimal(str(entry)) - Decimal(str(stop))) / Decimal(str(spec.tick_size))
    loss_per_lot = ticks * Decimal(str(spec.tick_value))
    raw_lots = decimal_budget / loss_per_lot
    step = Decimal(str(spec.volume_step))
    lots_decimal = (raw_lots / step).to_integral_value(rounding=ROUND_FLOOR) * step
    maximum = Decimal(str(spec.volume_max))
    maximum = (maximum / step).to_integral_value(rounding=ROUND_FLOOR) * step
    lots_decimal = min(lots_decimal, maximum)
    lots = float(lots_decimal)
    if lots + 1e-12 < spec.volume_min:
        return SizingDecision(False, 0.0, 0.0, budget, "minimum_lot_exceeds_risk")
    risk_usd = float(lots_decimal * loss_per_lot)
    return SizingDecision(risk_usd <= budget + 1e-9, lots, risk_usd, budget)
