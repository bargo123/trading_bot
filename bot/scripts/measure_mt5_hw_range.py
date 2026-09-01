#!/usr/bin/env python3
"""Costed hw_range on live MT5 demo bars. No orders. Not a 100% WR claim.

Uses broker H1 OHLC + the current bid/ask spread as Harris immediacy tax.
Sizes at the demo min lot (0.01) so the path matches what run_broker_paper would send.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aegis.backtest import format_report, run_backtest  # noqa: E402
from aegis.config import load_config  # noqa: E402
from aegis.engines.mt5 import MT5Engine  # noqa: E402


def bars_to_frame(bars) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "time": pd.Timestamp(b.time),
                "open": b.open,
                "high": b.high,
                "low": b.low,
                "close": b.close,
                "volume": b.volume,
            }
            for b in bars
        ]
    )


def wilson_ci(wins: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n <= 0:
        return 0.0, 0.0
    p = wins / n
    den = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n) / den
    return max(0.0, (centre - half) * 100), min(100.0, (centre + half) * 100)


def main() -> None:
    p = argparse.ArgumentParser(description="MT5 hw_range costed measurement")
    p.add_argument("--config", default=str(ROOT / "config_mt5_demo_eurusd.yaml"))
    args = p.parse_args()
    cfg = load_config(args.config)
    cfg["allow_live"] = False
    eng = MT5Engine(cfg)
    eng.connect()
    try:
        acct = eng.account()
        if not acct.is_paper:
            raise SystemExit("Refusing measurement on non-demo account")
        symbol = str(cfg.get("symbol", "EURUSD"))
        spec = eng.symbol_spec(symbol)
        mid = (spec["bid"] + spec["ask"]) / 2.0 if spec["bid"] and spec["ask"] else 0.0
        spread_bps = (spec["spread_price"] / mid * 10000.0) if mid > 0 else float(cfg.get("spread_bps", 0.8))
        lots = float(cfg.get("order_quantity", spec["volume_min"]) or spec["volume_min"])
        lots = max(lots, float(spec["volume_min"]))
        fixed_units = lots * float(spec["trade_contract_size"])
        rt_spread = eng.round_trip_spread_usd(symbol, lots)
        bars = eng.bars(symbol, str(cfg.get("timeframe", "1h")), int(cfg.get("lookback_days", 60)))
        df = bars_to_frame(bars)
        if df.empty:
            raise SystemExit("No MT5 bars")
        df["time"] = pd.to_datetime(df["time"], utc=True)
        measure_cfg = dict(cfg)
        measure_cfg["spread_bps"] = spread_bps
        measure_cfg["slippage_bps"] = float(cfg.get("slippage_bps", 0.4))
        measure_cfg["commission_round_trip_usd"] = float(cfg.get("commission_round_trip_usd", 0.0) or 0.0)
        measure_cfg["fixed_units"] = fixed_units
        measure_cfg["starting_equity"] = float(cfg.get("starting_equity", acct.equity) or 100)
        res = run_backtest(df, measure_cfg)
        start = pd.Timestamp(df["time"].iloc[0])
        end = pd.Timestamp(df["time"].iloc[-1])
        span_days = max((end - start).total_seconds() / 86400.0, 1e-9)
        wins = int((res.trades["pnl"] > 0).sum()) if not res.trades.empty else 0
        ci_lo, ci_hi = wilson_ci(wins, res.total_trades)
        payload = {
            "measured_at_utc": datetime.now(timezone.utc).isoformat(),
            "account": acct.account_id,
            "server": acct.raw.get("server"),
            "equity_live": acct.equity,
            "paper": acct.is_paper,
            "trade_expert": acct.raw.get("trade_expert"),
            "symbol": spec["name"],
            "timeframe": cfg.get("timeframe"),
            "sample_start_utc": str(start),
            "sample_end_utc": str(end),
            "bars": int(len(df)),
            "span_days": round(span_days, 4),
            "lots": lots,
            "fixed_units": fixed_units,
            "live_bid": spec["bid"],
            "live_ask": spec["ask"],
            "spread_price": spec["spread_price"],
            "spread_bps_one_way": round(spread_bps, 4),
            "slippage_bps_one_way": measure_cfg["slippage_bps"],
            "commission_round_trip_usd": measure_cfg["commission_round_trip_usd"],
            "round_trip_spread_usd_at_lot": round(rt_spread, 6),
            "signal_mode": cfg.get("signal_mode"),
            "trades": res.total_trades,
            "trades_per_day": round(res.total_trades / span_days, 4),
            "win_rate_pct": round(res.win_rate, 4),
            "wr_wilson_95": [round(ci_lo, 2), round(ci_hi, 2)],
            "expectancy_r_net": round(res.expectancy_r, 6),
            "profit_factor": None if res.profit_factor == float("inf") else round(res.profit_factor, 4),
            "max_drawdown_pct": round(res.max_drawdown_pct, 4),
            "start_equity": measure_cfg["starting_equity"],
            "end_equity": round(res.final_equity, 4),
            "net_pnl": round(res.net_pnl, 4),
            "halt_reason": res.halt_reason or "none",
            "ambiguous_exits": res.ambiguous_exits,
            "paper_promoted": False,
            "notes": [
                "OHLC next-open fill with constant live spread snapshot — not tick path.",
                "Commission unknown until a filled deal exists; currently 0 unless set in yaml.",
                "Not a 100% WR claim. Not firehose. Not Yahoo gold trophy.",
            ],
        }
        out_json = ROOT / "reports" / "MT5_HW_RANGE_MEASURED.json"
        out_md = ROOT / "reports" / "MT5_HW_RANGE_MEASURED.md"
        out_json.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        pf = "inf" if res.profit_factor == float("inf") else f"{res.profit_factor:.2f}"
        md = "\n".join(
            [
                "# MT5 demo hw_range — costed measurement",
                "",
                "Not promoted. Not 100% WR. Spread from live bid/ask at measurement time.",
                "",
                f"- Symbol: `{spec['name']}` {cfg.get('timeframe')}  lots={lots}",
                f"- Window: {start} → {end}  ({span_days:.2f} days, {len(df)} bars)",
                f"- Live spread: {spec['spread_price']} ({spread_bps:.3f} bps one-way); RT at {lots} lots ≈ ${rt_spread:.4f}",
                f"- Trades: {res.total_trades}  ({res.total_trades / span_days:.3f}/day)",
                f"- WR: {res.win_rate:.2f}%  (Wilson 95% {ci_lo:.1f}–{ci_hi:.1f})",
                f"- Net E[R]: {res.expectancy_r:.3f}  PF: {pf}  max DD: {res.max_drawdown_pct:.2f}%",
                f"- Equity: ${measure_cfg['starting_equity']:.2f} → ${res.final_equity:.2f}  halt: {res.halt_reason or 'none'}",
                f"- trade_expert={acct.raw.get('trade_expert')}  paper_promoted=false",
                "",
                "```",
                format_report(res),
                "```",
                "",
            ]
        )
        out_md.write_text(md, encoding="utf-8")
        print(json.dumps(payload, indent=2, default=str))
        print(format_report(res))
        print(f"Wrote {out_md}")
    finally:
        eng.disconnect()


if __name__ == "__main__":
    main()
