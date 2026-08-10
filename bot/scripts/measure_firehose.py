#!/usr/bin/env python3
"""Measure video-firehose trade rate across FX basket on 1m bars."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aegis.backtest import run_backtest  # noqa: E402
from aegis.data import fetch_ohlcv  # noqa: E402
from aegis.strategy import prepare, signal_from_row  # noqa: E402

SYMBOLS = [
    "EURUSD=X",
    "GBPUSD=X",
    "USDJPY=X",
    "AUDUSD=X",
    "USDCAD=X",
    "NZDUSD=X",
    "EURJPY=X",
    "GBPJPY=X",
]


def main() -> None:
    cfg = yaml.safe_load((ROOT / "config_video_firehose.yaml").read_text())
    rows = []
    total_trades = 0
    total_days = 0.0
    for sym in SYMBOLS:
        c = dict(cfg)
        c["symbol"] = sym
        if "JPY" in sym:
            c["firehose_pip_size"] = 0.01
            c["volman_pip_size"] = 0.01
        try:
            raw = fetch_ohlcv(sym, c["timeframe"], int(c["lookback_days"]))
            if raw is None or len(raw) < 200:
                rows.append({"symbol": sym, "error": "thin_data", "n": 0 if raw is None else len(raw)})
                continue
            df = prepare(raw, c)
            # Count raw signals (upper bound before one-position gate)
            sig_n = 0
            for _, row in df.iterrows():
                if signal_from_row(row, c) is not None:
                    sig_n += 1
            # run_backtest calls prepare() again — pass raw OHLCV, not enriched frame
            bt = run_backtest(raw, c)
            trades = int(bt.total_trades)
            days = max(len(raw) / (24 * 60), 0.01)  # 1m bars
            # Prefer calendar span if available
            if "time" in raw.columns:
                t0, t1 = raw["time"].iloc[0], raw["time"].iloc[-1]
                span_days = max((t1 - t0).total_seconds() / 86400.0, 0.01)
            else:
                span_days = days
            wr = float(bt.win_rate) / 100.0  # BacktestResult stores percent
            eq = float(bt.final_equity)
            tpd = trades / span_days
            spd = sig_n / span_days
            total_trades += trades
            total_days = max(total_days, span_days)
            rows.append(
                {
                    "symbol": sym,
                    "bars": len(raw),
                    "span_days": round(span_days, 2),
                    "signals": sig_n,
                    "signals_per_day": round(spd, 1),
                    "trades": trades,
                    "trades_per_day": round(tpd, 1),
                    "win_rate": round(wr, 3),
                    "end_equity": round(eq, 2),
                }
            )
            print(
                f"{sym:12} signals/d={spd:6.1f} trades/d={tpd:6.1f} "
                f"n={trades:4} wr={wr:.1%} eq={eq:.2f}"
            )
        except Exception as e:
            rows.append({"symbol": sym, "error": str(e)})
            print(f"{sym:12} ERROR {e}")

    basket_tpd = sum(r.get("trades", 0) for r in rows if "trades" in r) / max(total_days, 0.01)
    out = {
        "mode": "firehose_1m",
        "note": "1m OHLC ceiling; video-style thousands/day needs MT5 ticks",
        "basket_trades_per_day_approx": round(basket_tpd, 1),
        "rows": rows,
    }
    path = ROOT / "reports" / "VIDEO_FIREHOSE.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Video firehose (1m OHLC max)",
        "",
        f"**Basket ~{basket_tpd:.0f} closed trades/day** across {len(SYMBOLS)} pairs (measured).",
        "",
        "Ceiling on yfinance 1m: one decision per bar → hundreds/day per pair, not thousands of tick round-trips.",
        "True video firehose = MT5 tick/DMA on Windows.",
        "",
        "```json",
        json.dumps(out, indent=2),
        "```",
        "",
    ]
    path.write_text("\n".join(lines))
    print(f"\nBasket ~{basket_tpd:.0f} trades/day → {path}")


if __name__ == "__main__":
    main()
