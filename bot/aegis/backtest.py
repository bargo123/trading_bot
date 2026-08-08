from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

import numpy as np
import pandas as pd

from aegis.risk import RiskEngine
from aegis.strategy import Signal, prepare, signal_from_row
from aegis.pyramid import next_pyramid_sl, should_pyramid
from aegis.high_risk import HighRiskController

PrepareFn = Callable[[pd.DataFrame, dict[str, Any]], pd.DataFrame]
SignalFn = Callable[[pd.Series, dict[str, Any]], Optional[Signal]]


@dataclass
class BacktestResult:
    trades: pd.DataFrame
    equity_curve: pd.Series
    win_rate: float
    profit_factor: float
    max_drawdown_pct: float
    expectancy_r: float
    total_trades: int
    net_pnl: float
    final_equity: float
    halt_reason: str = ""


def run_backtest(
    df: pd.DataFrame,
    cfg: dict[str, Any],
    *,
    prepare_fn: Optional[PrepareFn] = None,
    signal_fn: Optional[SignalFn] = None,
) -> BacktestResult:
    prep = prepare_fn or prepare
    signal = signal_fn or signal_from_row
    frame = prep(df, cfg)
    risk = RiskEngine.from_config(cfg)
    equity = float(cfg.get("starting_equity", 10_000))
    spread_bps = float(cfg.get("spread_bps", 1.0))
    slip_bps = float(cfg.get("slippage_bps", 0.5))
    cost_bps = spread_bps + slip_bps

    hr = HighRiskController.from_config(cfg, equity)
    # Fuller pyramid: mode or legacy flag
    pyramid_on = bool(cfg.get("pyramid_enabled", False)) or hr.fuller_pyramid_enabled()
    pyramid_max = int(cfg.get("pyramid_max_adds", 2))
    pyramid_add_r = float(cfg.get("pyramid_add_r", 1.0))
    pyramid_adx = float(cfg.get("pyramid_adx_min", 25.0))
    flatten_utc = cfg.get("ntz_flatten_utc")  # optional session flatten (Fabris 17:00)

    trades: list[dict[str, Any]] = []
    curve = []
    pos = None
    halt_reason = ""

    for i in range(len(frame) - 1):
        row = frame.iloc[i]
        nxt = frame.iloc[i + 1]
        curve.append(equity)
        risk.update(equity, now=pd.Timestamp(row["time"]).to_pydatetime())

        if pos is not None:
            side = pos["side"]
            high, low = float(nxt["high"]), float(nxt["low"])
            close_n = float(nxt["close"])
            pos["bars_held"] = int(pos.get("bars_held", 0)) + 1

            # Fuller: scale into winner without increasing total risk beyond 1R
            if pyramid_on and int(pos.get("adds", 0)) < pyramid_max:
                adx_v = float(nxt["adx"]) if not pd.isna(nxt.get("adx")) else 0.0
                if should_pyramid(
                    side=side,
                    entry=float(pos["entry0"]),
                    price=close_n,
                    initial_risk=float(pos["initial_risk"]),
                    adds=int(pos["adds"]),
                    max_adds=pyramid_max,
                    add_r=pyramid_add_r,
                    adx=adx_v,
                    adx_min=pyramid_adx,
                    enabled=True,
                ):
                    add_px = close_n
                    new_sl = next_pyramid_sl(side, pos["entries"], add_px)
                    add_units = float(pos["unit0"])
                    tot_u = float(pos["units"]) + add_units
                    avg = (float(pos["entry"]) * float(pos["units"]) + add_px * add_units) / tot_u
                    pos["entries"].append(add_px)
                    pos["adds"] = int(pos["adds"]) + 1
                    pos["units"] = tot_u
                    pos["entry"] = avg
                    pos["sl"] = new_sl
                    if pos.get("tp") is not None and float(pos["initial_risk"]) > 0:
                        ext = float(pos["initial_risk"])
                        if side == "buy":
                            pos["tp"] = float(pos["tp"]) + ext
                        else:
                            pos["tp"] = float(pos["tp"]) - ext

            if (not pyramid_on) and pos.get("trail_atr_mult") and not pd.isna(nxt.get("atr")):
                atr_v = float(nxt["atr"])
                if side == "buy":
                    pos["sl"] = max(pos["sl"], close_n - pos["trail_atr_mult"] * atr_v)
                else:
                    pos["sl"] = min(pos["sl"], close_n + pos["trail_atr_mult"] * atr_v)

            exit_price = None
            outcome = None
            sl, tp = pos["sl"], pos.get("tp")
            if side == "buy":
                hit_sl = low <= sl
                hit_tp = tp is not None and high >= tp
                if hit_sl and hit_tp:
                    exit_price, outcome = sl, "sl"
                elif hit_sl:
                    exit_price, outcome = sl, "sl"
                elif hit_tp:
                    exit_price, outcome = tp, "tp"
            else:
                hit_sl = high >= sl
                hit_tp = tp is not None and low <= tp
                if hit_sl and hit_tp:
                    exit_price, outcome = sl, "sl"
                elif hit_sl:
                    exit_price, outcome = sl, "sl"
                elif hit_tp:
                    exit_price, outcome = tp, "tp"

            max_hold = int(cfg.get("max_hold_bars", 0) or 0)
            if exit_price is None and max_hold > 0 and pos["bars_held"] >= max_hold:
                exit_price, outcome = close_n, "time"

            if exit_price is None and flatten_utc is not None:
                ts = pd.Timestamp(nxt["time"])
                h = ts.tz_convert("UTC").hour if getattr(ts, "tzinfo", None) else ts.hour
                if h >= int(flatten_utc):
                    exit_price, outcome = close_n, "flatten"

            if exit_price is not None:
                move = (exit_price - pos["entry"]) if side == "buy" else (pos["entry"] - exit_price)
                cost = pos["entry"] * (cost_bps / 10000.0) * 2
                pnl = pos["units"] * (move - cost)
                r_den = abs(pos["entry0"] - pos["entry_sl"])
                r = move / r_den if r_den else 0
                equity += pnl
                hr.on_trade_closed(pnl, equity)
                trades.append(
                    {
                        "entry_time": pos["time"],
                        "exit_time": nxt["time"],
                        "side": side,
                        "mode": pos["mode"],
                        "reason": pos["reason"],
                        "entry": pos["entry"],
                        "exit": exit_price,
                        "pnl": pnl,
                        "r": r,
                        "outcome": outcome,
                        "adds": int(pos.get("adds", 0)),
                        "risk_pct": pos.get("risk_pct"),
                        "hr_step": pos.get("hr_step"),
                    }
                )
                pos = None

        if pos is not None:
            continue

        ok, why = risk.allow(equity, 0)
        if not ok:
            halt_reason = why
            continue

        hr_ok, hr_why = hr.allow(equity)
        if not hr_ok:
            halt_reason = hr_why
            continue

        max_day = int(cfg.get("ntz_max_trades_day", 0) or 0)
        if max_day > 0:
            day = pd.Timestamp(nxt["time"])
            if getattr(day, "tzinfo", None) is not None:
                day = day.tz_convert("UTC").floor("D")
            else:
                day = day.floor("D")

            def _entry_day(ts) -> pd.Timestamp:
                t = pd.Timestamp(ts)
                if getattr(t, "tzinfo", None) is not None:
                    return t.tz_convert("UTC").floor("D")
                return t.floor("D")

            day_n = sum(1 for t in trades if _entry_day(t["entry_time"]) == day)
            if day_n >= max_day:
                continue

        sig = signal(row, cfg)
        if sig is None:
            continue

        entry = float(nxt["open"])
        if sig.side == "buy":
            sl_dist = abs(sig.entry - sig.sl)
            sl = entry - sl_dist
            tp = entry + abs(sig.tp - sig.entry) if sig.tp is not None else None
        else:
            sl_dist = abs(sig.sl - sig.entry)
            sl = entry + sl_dist
            tp = entry - abs(sig.entry - sig.tp) if sig.tp is not None else None

        # Always require a stop (solves Brown no-stop DCA / hedge chapters)
        if abs(entry - sl) <= 0:
            continue

        risk_pct = hr.effective_risk_percent(equity)
        units = risk.size_units(
            equity,
            entry,
            sl,
            min_stop=abs(entry) * float(cfg.get("min_atr_pct", 0.0004)),
            risk_percent=risk_pct,
        )
        if units <= 0:
            continue
        pos = {
            "side": sig.side,
            "mode": sig.mode,
            "reason": sig.reason,
            "entry": entry,
            "entry0": entry,
            "sl": sl,
            "entry_sl": sl,
            "initial_risk": abs(entry - sl),
            "tp": tp,
            "trail_atr_mult": sig.trail_atr_mult,
            "units": units,
            "unit0": units,
            "entries": [entry],
            "adds": 0,
            "time": nxt["time"],
            "bars_held": 0,
            "risk_pct": risk_pct,
            "hr_step": hr.step,
        }

    curve.append(equity)
    trades_df = pd.DataFrame(trades)
    eq = pd.Series(curve, name="equity")
    if hr.halt_reason and not halt_reason:
        halt_reason = hr.halt_reason
    if trades_df.empty:
        return BacktestResult(trades_df, eq, 0, 0, 0, 0, 0, 0, equity, halt_reason)

    wins = trades_df.loc[trades_df["pnl"] > 0, "pnl"]
    losses = trades_df.loc[trades_df["pnl"] <= 0, "pnl"]
    gp = float(wins.sum()) if len(wins) else 0.0
    gl = float((-losses).sum()) if len(losses) else 0.0
    peak = eq.cummax()
    dd = (eq - peak) / peak.replace(0, np.nan) * 100
    return BacktestResult(
        trades=trades_df,
        equity_curve=eq,
        win_rate=float((trades_df["pnl"] > 0).mean() * 100),
        profit_factor=(gp / gl) if gl > 0 else float("inf"),
        max_drawdown_pct=float((-dd.min()) if len(dd) else 0),
        expectancy_r=float(trades_df["r"].mean()),
        total_trades=len(trades_df),
        net_pnl=float(trades_df["pnl"].sum()),
        final_equity=equity,
        halt_reason=halt_reason,
    )


def format_report(res: BacktestResult) -> str:
    pf = "inf" if res.profit_factor == float("inf") else f"{res.profit_factor:.2f}"
    lines = [
        "=== Aegis Backtest ===",
        f"Trades:        {res.total_trades}",
        f"Win rate:      {res.win_rate:.2f}%",
        f"Profit factor: {pf}",
        f"Max drawdown:  {res.max_drawdown_pct:.2f}%",
        f"Expectancy R:  {res.expectancy_r:.3f}",
        f"Net PnL:       {res.net_pnl:.2f}",
        f"Final equity:  {res.final_equity:.2f}",
    ]
    if getattr(res, "halt_reason", ""):
        lines.append(f"Halt:          {res.halt_reason}")
    return "\n".join(lines)
