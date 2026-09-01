#!/usr/bin/env python3
"""Measure live MT5 demo spread/contract facts. No orders.

Harris: half-spread is the immediacy tax. Aldridge: do not scalp when cost ≫ edge.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aegis.engines.mt5 import MT5Engine  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser(description="MT5 cost snapshot (read-only)")
    p.add_argument("--symbol", default="EURUSD")
    p.add_argument("--lots", type=float, default=0.01)
    p.add_argument(
        "--mt5-path",
        default=r"C:\Program Files\MetaTrader 5\terminal64.exe",
    )
    args = p.parse_args()
    eng = MT5Engine(
        {
            "allow_live": False,
            "mode": "mt5_demo",
            "mt5_path": args.mt5_path,
            "mt5_max_lots": 0.10,
        }
    )
    eng.connect()
    try:
        acct = eng.account()
        if not acct.is_paper:
            raise SystemExit("Refusing cost snapshot on non-demo account")
        spec = eng.symbol_spec(args.symbol)
        rt = eng.round_trip_spread_usd(args.symbol, args.lots)
        ticks = eng.copy_ticks(args.symbol, lookback_seconds=30)
        payload = {
            "account": acct.account_id,
            "equity": acct.equity,
            "currency": acct.currency,
            "paper": acct.is_paper,
            "symbol": spec,
            "lots": args.lots,
            "round_trip_spread_usd": round(rt, 6),
            "tick_count_30s": len(ticks),
        }
        print(json.dumps(payload, indent=2, default=str))
        print(
            f"COST {spec['name']} {args.lots} lots  spread={spec['spread_price']}  "
            f"RT_spread_usd={rt:.4f}  ticks_30s={len(ticks)}"
        )
    finally:
        eng.disconnect()


if __name__ == "__main__":
    main()
