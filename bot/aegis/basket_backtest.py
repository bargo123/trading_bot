"""Chronological shared-equity basket backtester for Aegis strategies."""
from __future__ import annotations

from collections import Counter
from typing import Any, Callable, Mapping, Optional

import numpy as np
import pandas as pd

from aegis.backtest import BacktestResult
from aegis.high_risk import HighRiskController
from aegis.risk import RiskEngine
from aegis.strategy import Signal, prepare, signal_from_row

PrepareFn = Callable[[pd.DataFrame, dict[str, Any]], pd.DataFrame]
SignalFn = Callable[[pd.Series, dict[str, Any]], Optional[Signal]]


def _currencies(symbol: str) -> tuple[str, str] | None:
    clean = symbol.upper().replace("=X", "").replace("/", "")
    if len(clean) < 6:
        return None
    return clean[:3], clean[3:6]


def _exposure(positions: Mapping[str, dict[str, Any]]) -> Counter[str]:
    out: Counter[str] = Counter()
    for symbol, pos in positions.items():
        pair = _currencies(symbol)
        if pair is None:
            continue
        sign = 1 if pos["side"] == "buy" else -1
        out[pair[0]] += sign
        out[pair[1]] -= sign
    return out


def _candidate_exposure_ok(
    positions: Mapping[str, dict[str, Any]],
    symbol: str,
    side: str,
    limit: int,
) -> bool:
    if limit <= 0:
        return True
    pair = _currencies(symbol)
    if pair is None:
        return True
    net = _exposure(positions)
    sign = 1 if side == "buy" else -1
    net[pair[0]] += sign
    net[pair[1]] -= sign
    return all(abs(v) <= limit for v in net.values())


def run_basket_backtest(
    data: Mapping[str, pd.DataFrame],
    cfg: dict[str, Any],
    *,
    prepare_fn: Optional[PrepareFn] = None,
    signal_fn: Optional[SignalFn] = None,
) -> BacktestResult:
    """Run synchronized symbols against one equity/risk/position state."""
    prep = prepare_fn or prepare
    signal = signal_fn or signal_from_row
    frames: dict[str, pd.DataFrame] = {}
    events: list[dict[str, Any]] = []
    for symbol, raw in sorted(data.items()):
        frame = prep(raw.copy(), cfg).sort_values("time").reset_index(drop=True)
        frames[symbol] = frame
        records = frame.to_dict("records")
        for i in range(max(0, len(records) - 1)):
            events.append(
                {
                    "time": pd.Timestamp(records[i + 1]["time"]),
                    "symbol": symbol,
                    "row": records[i],
                    "nxt": records[i + 1],
                }
            )
    events.sort(key=lambda e: (e["time"], e["symbol"]))

    start_equity = float(cfg.get("starting_equity", 100.0))
    equity = start_equity
    risk = RiskEngine.from_config(cfg)
    hr = HighRiskController.from_config(cfg, equity)
    cost_bps = (
        float(cfg.get("spread_bps", 1.0))
        + float(cfg.get("slippage_bps", 0.5))
        + float(cfg.get("commission_bps", 0.0))
    )
    positions: dict[str, dict[str, Any]] = {}
    trades: list[dict[str, Any]] = []
    skipped: Counter[str] = Counter()
    curve: list[float] = [equity]
    ambiguous = 0
    halt_reason = ""

    def close_position(symbol: str, exit_time, exit_price: float, outcome: str) -> None:
        nonlocal equity, halt_reason
        pos = positions.pop(symbol)
        move = (
            exit_price - float(pos["entry"])
            if pos["side"] == "buy"
            else float(pos["entry"]) - exit_price
        )
        cost = float(pos["entry"]) * (cost_bps / 10000.0) * 2.0
        pnl = float(pos["units"]) * (move - cost)
        initial_risk_money = float(pos["initial_risk_money"])
        if bool(cfg.get("negative_balance_protection", True)) and equity + pnl <= 0:
            pnl = -equity
            outcome = "bankruptcy"
            halt_reason = "bankruptcy"
        r_mult = pnl / initial_risk_money if initial_risk_money > 0 else 0.0
        equity += pnl
        hr.on_trade_closed(pnl, equity)
        trades.append(
            {
                "symbol": symbol,
                "entry_time": pos["time"],
                "exit_time": exit_time,
                "side": pos["side"],
                "mode": pos["mode"],
                "reason": pos["reason"],
                "entry": pos["entry"],
                "exit": exit_price,
                "sl": pos["sl"],
                "tp": pos["tp"],
                "units": pos["units"],
                "pnl": pnl,
                "r": r_mult,
                "outcome": outcome,
                "risk_pct": pos["risk_pct"],
            }
        )

    # Process all exits for a timestamp before any new entries at that timestamp.
    at = 0
    while at < len(events):
        now = events[at]["time"]
        end = at + 1
        while end < len(events) and events[end]["time"] == now:
            end += 1
        group = events[at:end]
        now_dt = now.to_pydatetime()
        risk.update(equity, now=now_dt)

        for event in group:
            symbol = event["symbol"]
            pos = positions.get(symbol)
            if pos is None:
                continue
            nxt = event["nxt"]
            pos["bars_held"] += 1
            high, low, close_n = float(nxt["high"]), float(nxt["low"]), float(nxt["close"])
            if pos.get("trail_atr_mult") and not pd.isna(nxt.get("atr")):
                trail = float(pos["trail_atr_mult"]) * float(nxt["atr"])
                if pos["side"] == "buy":
                    pos["sl"] = max(float(pos["sl"]), close_n - trail)
                else:
                    pos["sl"] = min(float(pos["sl"]), close_n + trail)

            sl, tp = float(pos["sl"]), pos.get("tp")
            if pos["side"] == "buy":
                hit_sl = low <= sl
                hit_tp = tp is not None and high >= float(tp)
            else:
                hit_sl = high >= sl
                hit_tp = tp is not None and low <= float(tp)
            exit_price = None
            outcome = None
            if hit_sl and hit_tp:
                ambiguous += 1
                exit_price, outcome = sl, "sl"
            elif hit_sl:
                exit_price, outcome = sl, "sl"
            elif hit_tp:
                exit_price, outcome = float(tp), "tp"
            max_hold = int(cfg.get("max_hold_bars", 0) or 0)
            if exit_price is None and max_hold > 0 and pos["bars_held"] >= max_hold:
                exit_price, outcome = close_n, "time"
            if exit_price is not None:
                close_position(symbol, nxt["time"], float(exit_price), str(outcome))

        for event in group:
            symbol = event["symbol"]
            if symbol in positions:
                continue
            if equity <= 0:
                halt_reason = "bankruptcy"
                skipped["bankruptcy"] += 1
                continue
            ok, why = risk.allow(equity, len(positions), now=now_dt)
            if not ok:
                skipped[why.split()[0]] += 1
                if why != "max_positions":
                    halt_reason = why
                continue
            hr_ok, hr_why = hr.allow(equity)
            if not hr_ok:
                skipped[hr_why.split()[0]] += 1
                halt_reason = hr_why
                continue
            sig = signal(event["row"], cfg)
            if sig is None:
                continue
            if not _candidate_exposure_ok(
                positions,
                symbol,
                sig.side,
                int(cfg.get("max_currency_exposure", 2)),
            ):
                skipped["currency_exposure"] += 1
                continue

            entry = float(event["nxt"]["open"])
            if sig.side == "buy":
                sl = entry - abs(float(sig.entry) - float(sig.sl))
                tp = entry + abs(float(sig.tp) - float(sig.entry)) if sig.tp is not None else None
            else:
                sl = entry + abs(float(sig.sl) - float(sig.entry))
                tp = entry - abs(float(sig.entry) - float(sig.tp)) if sig.tp is not None else None
            stop_distance = abs(entry - sl)
            min_stop = abs(entry) * float(cfg.get("min_atr_pct", 0.0))
            risk_den = max(stop_distance, min_stop)
            if risk_den <= 0:
                skipped["invalid_stop"] += 1
                continue
            risk_pct = hr.effective_risk_percent(equity)
            units = risk.size_units(
                equity,
                entry,
                sl,
                min_stop=min_stop,
                risk_percent=risk_pct,
            )
            step = float(cfg.get("unit_step", 0.0) or 0.0)
            if step > 0:
                units = np.floor(units / step) * step
            min_units = float(cfg.get("min_units", 0.0) or 0.0)
            if units <= 0 or units < min_units:
                skipped["min_units"] += 1
                continue

            open_heat = sum(float(p["initial_risk_money"]) for p in positions.values())
            gross_notional = sum(abs(float(p["units"]) * float(p["entry"])) for p in positions.values())
            if equity <= 0:
                skipped["bankrupt"] += 1
                continue
            max_heat_money = equity * float(cfg.get("max_portfolio_heat_percent", 5.0)) / 100.0
            heat_capacity_units = max(0.0, max_heat_money - open_heat) / risk_den
            leverage_capacity_notional = max(
                0.0,
                equity * float(cfg.get("max_gross_leverage", 30.0)) - gross_notional,
            )
            leverage_capacity_units = leverage_capacity_notional / abs(entry) if entry else 0.0
            capped_units = min(units, heat_capacity_units, leverage_capacity_units)
            if step > 0:
                capped_units = np.floor(capped_units / step) * step
            if capped_units < units:
                skipped["sized_down"] += 1
            units = capped_units
            if units <= 0 or units < min_units:
                reason = "portfolio_heat" if heat_capacity_units < min_units else "gross_leverage"
                skipped[reason] += 1
                continue
            risk_money = units * risk_den

            positions[symbol] = {
                "side": sig.side,
                "mode": sig.mode,
                "reason": sig.reason,
                "entry": entry,
                "sl": sl,
                "tp": tp,
                "trail_atr_mult": sig.trail_atr_mult,
                "units": float(units),
                "time": event["nxt"]["time"],
                "bars_held": 0,
                "risk_pct": risk_pct,
                "initial_risk_money": risk_money,
            }
        curve.append(equity)
        at = end

    for symbol in sorted(list(positions)):
        frame = frames[symbol]
        if len(frame):
            last = frame.iloc[-1]
            close_position(symbol, last["time"], float(last["close"]), "eof")
    if curve[-1] != equity:
        curve.append(equity)

    trades_df = pd.DataFrame(trades)
    eq = pd.Series(curve, name="equity", dtype=float)
    peak = eq.cummax()
    dd = (eq - peak) / peak.replace(0, np.nan) * 100.0
    if trades_df.empty:
        return BacktestResult(
            trades=trades_df,
            equity_curve=eq,
            win_rate=0.0,
            profit_factor=0.0,
            max_drawdown_pct=max(0.0, float(-dd.min())) if len(dd) else 0.0,
            expectancy_r=0.0,
            total_trades=0,
            net_pnl=0.0,
            final_equity=equity,
            halt_reason=halt_reason,
            ambiguous_exits=ambiguous,
            skipped_entries=dict(skipped),
        )
    wins = trades_df.loc[trades_df["pnl"] > 0, "pnl"]
    losses = trades_df.loc[trades_df["pnl"] <= 0, "pnl"]
    gp = float(wins.sum()) if len(wins) else 0.0
    gl = float(-losses.sum()) if len(losses) else 0.0
    return BacktestResult(
        trades=trades_df,
        equity_curve=eq,
        win_rate=float((trades_df["pnl"] > 0).mean() * 100.0),
        profit_factor=gp / gl if gl > 0 else float("inf"),
        max_drawdown_pct=max(0.0, float(-dd.min())) if len(dd) else 0.0,
        expectancy_r=float(trades_df["r"].mean()),
        total_trades=len(trades_df),
        net_pnl=float(trades_df["pnl"].sum()),
        final_equity=equity,
        halt_reason=halt_reason,
        ambiguous_exits=ambiguous,
        skipped_entries=dict(skipped),
    )
