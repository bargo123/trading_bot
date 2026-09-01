#!/usr/bin/env python3
"""Smoke-test a broker engine (IBKR paper or MT5 demo).

MT5: keep the terminal open and logged into a DEMO account.
IBKR: Gateway/TWS paper API (port 4002 / 7497).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aegis.engines import create_engine  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser(description="Broker engine smoke test")
    p.add_argument("--engine", default="ibkr", choices=["ibkr", "mt5"])
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=4002, help="Gateway paper=4002, TWS paper=7497")
    p.add_argument("--symbol", default="EURUSD")
    p.add_argument(
        "--quantity",
        type=float,
        default=None,
        help="IBKR: FX base units. MT5: lots (default 0.01).",
    )
    p.add_argument(
        "--order",
        action="store_true",
        help="Place a far-away limit and cancel it (no intended fill)",
    )
    p.add_argument("--allow-live", action="store_true")
    p.add_argument(
        "--mt5-path",
        default=r"C:\Program Files\MetaTrader 5\terminal64.exe",
        help="Path to terminal64.exe",
    )
    args = p.parse_args()

    if args.engine == "mt5":
        cfg = {
            "engine": "mt5",
            "mode": "mt5_demo",
            "allow_live": args.allow_live,
            "symbol": args.symbol,
            "mt5_path": args.mt5_path,
            "mt5_max_lots": 0.10,
        }
        quantity = 0.01 if args.quantity is None else float(args.quantity)
    else:
        cfg = {
            "engine": args.engine,
            "mode": "ib_paper",
            "ib_host": args.host,
            "ib_port": args.port,
            "allow_live": args.allow_live,
            "symbol": args.symbol,
        }
        quantity = 2000.0 if args.quantity is None else float(args.quantity)

    eng = create_engine(cfg)
    print(f"engine={eng.name}")
    eng.connect()
    try:
        acct = eng.account()
        print(
            f"account={acct.account_id} equity={acct.equity} {acct.currency} "
            f"avail={acct.available_funds} paper={acct.is_paper}"
        )
        if not acct.is_paper and not args.allow_live:
            raise SystemExit("Refusing non-paper session without --allow-live")
        q = eng.quote(args.symbol)
        print(f"quote {args.symbol} bid={q.bid} ask={q.ask} time={q.time}")
        bars = eng.bars(args.symbol, "1h", 5)
        print(f"bars={len(bars)} last_close={bars[-1].close if bars else 'n/a'}")
        if args.order:
            limit = round(q.bid * 0.95, 5)
            print(f"smoke order: BUY limit {quantity} @ {limit} then cancel")
            res = eng.place_and_cancel_limit(args.symbol, "buy", quantity, limit)
            print(f"order_result ok={res.ok} id={res.broker_order_id} msg={res.message}")
            if not res.ok:
                raise SystemExit(f"SMOKE_ORDER_FAIL {res.message}")
        print("SMOKE_OK")
    finally:
        eng.disconnect()


if __name__ == "__main__":
    main()
