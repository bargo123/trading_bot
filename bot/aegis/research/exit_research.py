"""Exit-horizon research on realized M1 forward paths.

The analogue index records a single structural outcome per state. Exit research
needs the forward price path, so we re-fetch completed M1 bars (read-only), locate
each index record's entry bar, and simulate the outcome under a grid of fixed
take-profit horizons (1/2/5/10 pips) against a fixed stop-loss, then subtract the
same cost assumptions the paper runner uses (spread bps + slippage bps). The exit
horizon with the highest net expectancy after costs is the recommended exit.

Research-only. Never places orders. Fetching bars is read-only.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from aegis.intel.expected_value import payoff_metrics

# CORE benchmark stop; same shape the Intelligent Firehose is measured against.
DEFAULT_SL_PIPS = 30.0
EXIT_HORIZONS_PIPS = (1.0, 2.0, 5.0, 10.0)


@dataclass(frozen=True)
class ExitResearchRow:
    bar_time: str
    symbol: str
    side: str
    regime: str
    structure: str
    session: str
    tp_pips: float
    sl_pips: float
    outcome_pips: float
    cost_pips: float
    net_outcome_pips: float
    label: str = "research_proxy"

    def as_dict(self) -> dict[str, Any]:
        return {
            "bar_time": self.bar_time,
            "symbol": self.symbol,
            "side": self.side,
            "regime": self.regime,
            "structure": self.structure,
            "session": self.session,
            "tp_pips": self.tp_pips,
            "sl_pips": self.sl_pips,
            "outcome_pips": self.outcome_pips,
            "cost_pips": self.cost_pips,
            "net_outcome_pips": self.net_outcome_pips,
            "label": self.label,
        }


def bps_to_pips(bps: float, symbol: str, pip: float) -> float:
    """Basis points (0.01%) of price as a pip distance."""
    price = 100.0 if "JPY" in symbol.upper() else 1.0
    return (float(bps) / 10000.0 * price) / float(pip)


def per_trade_cost_pips(symbol: str, pip: float, spread_bps: float, slippage_bps: float) -> float:
    """Round-trip cost in pips: half-spread entry tax plus slippage (Harris/Aldridge)."""
    spread_pips = bps_to_pips(spread_bps, symbol, pip)
    slippage_pips = bps_to_pips(slippage_bps, symbol, pip)
    return round(spread_pips + slippage_pips, 6)


def simulate_exit(
    frame: pd.DataFrame,
    *,
    start_idx: int,
    side: str,
    tp_pips: float,
    sl_pips: float,
    pip: float,
    max_bars: int = 120,
) -> float | None:
    """Forward outcome in pips for a fixed TP/SL exit from a completed entry bar.

    Entry is the close of the record's bar. The stop and target are absolute prices
    derived from that close; for a sell, price must fall by `tp_pips` to win and rise
    by `sl_pips` to be stopped.
    """
    if start_idx >= len(frame) - 1:
        return None
    entry = float(frame["close"].iloc[start_idx])
    sign = 1.0 if str(side).lower() == "buy" else -1.0
    tp_price = entry + sign * tp_pips * float(pip)
    sl_price = entry - sign * sl_pips * float(pip)
    for offset in range(1, min(max_bars, len(frame) - start_idx)):
        bar = frame.iloc[start_idx + offset]
        high = float(bar["high"])
        low = float(bar["low"])
        close = float(bar["close"])
        if sign > 0:
            if low <= sl_price:
                return -sl_pips
            if high >= tp_price:
                return tp_pips
        else:
            if high >= sl_price:
                return -sl_pips
            if low <= tp_price:
                return tp_pips
        if offset == max_bars - 1:
            return sign * (close - entry) / float(pip)
    return None


def research_exit_horizons(
    records: Sequence[Mapping[str, Any]],
    frames: Mapping[str, pd.DataFrame],
    *,
    pip_by_symbol: Mapping[str, float],
    spread_bps: float = 0.2,
    slippage_bps: float = 0.1,
    sl_pips: float = DEFAULT_SL_PIPS,
    max_bars: int = 120,
) -> list[dict[str, Any]]:
    """Simulate every record under every TP horizon on real forward bars."""
    rows: list[dict[str, Any]] = []
    for record in records:
        symbol = str(record.get("symbol") or "").upper()
        frame = frames.get(symbol)
        if frame is None or frame.empty:
            continue
        pip = float(pip_by_symbol.get(symbol, 0.0001))
        cost = per_trade_cost_pips(symbol, pip, spread_bps, slippage_bps)
        start = _start_idx_for(frame, str(record.get("bar_time") or ""))
        if start is None:
            continue
        side = str(record.get("side") or "buy")
        for tp in EXIT_HORIZONS_PIPS:
            outcome = simulate_exit(
                frame,
                start_idx=start,
                side=side,
                tp_pips=float(tp),
                sl_pips=float(sl_pips),
                pip=pip,
                max_bars=max_bars,
            )
            if outcome is None:
                continue
            rows.append(
                ExitResearchRow(
                    bar_time=str(record.get("bar_time")),
                    symbol=symbol,
                    side=side,
                    regime=str(record.get("regime") or "?"),
                    structure=str(record.get("structure") or "?"),
                    session=str(record.get("session") or "?"),
                    tp_pips=float(tp),
                    sl_pips=float(sl_pips),
                    outcome_pips=float(outcome),
                    cost_pips=float(cost),
                    net_outcome_pips=float(outcome) - float(cost),
                ).as_dict()
            )
    return rows


def _start_idx_for(frame: pd.DataFrame, bar_time: str) -> int | None:
    try:
        target = pd.Timestamp(bar_time)
        if target.tzinfo is None:
            target = target.tz_localize("UTC")
        else:
            target = target.tz_convert("UTC")
    except (TypeError, ValueError):
        return None
    times = pd.to_datetime(frame["time"], utc=True)
    if len(times) == 0:
        return None
    matches = np.flatnonzero(times == target)
    if len(matches) == 0:
        return None
    return int(matches[0])


def exit_horizon_summary(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    by_tp: dict[float, list[float]] = {}
    for row in rows:
        by_tp.setdefault(float(row["tp_pips"]), []).append(float(row["net_outcome_pips"]))
    out = []
    for tp in EXIT_HORIZONS_PIPS:
        pnls = by_tp.get(float(tp), [])
        if not pnls:
            continue
        metrics = payoff_metrics(pnls)
        out.append(
            {
                "tp_pips": float(tp),
                "sl_pips": float(rows[0]["sl_pips"]) if rows else None,
                "n": metrics["n"],
                "win_rate": metrics["win_rate"],
                "expectancy_net": metrics["expectancy"],
                "profit_factor": metrics["profit_factor"],
                "net_pnl": metrics["net_pnl"],
            }
        )
    out.sort(key=lambda item: float(item["expectancy_net"] or 0), reverse=True)
    return out


def recommended_exit(summary: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    if not summary:
        return None
    best = max(summary, key=lambda item: float(item["expectancy_net"] or -1e9))
    if best.get("expectancy_net") is None or float(best["expectancy_net"]) <= 0:
        return None
    return best