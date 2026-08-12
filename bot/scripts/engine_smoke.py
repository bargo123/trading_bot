#!/usr/bin/env python3
"""Smoke-test a broker engine (default: IBKR paper).

Requires IB Gateway/TWS logged into PAPER with API port 7497 enabled.
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
        default=2000.0,
        help="FX base units (keep small for low paper margin)",
    )
    p.add_argument(
        "--order",
        action="store_true",
        help="Place a far-away limit and cancel it (no intended fill)",
    )
    p.add_argument("--allow-live", action="store_true")
    args = p.parse_args()

    cfg = {
        "engine": args.engine,
        "mode": "ib_paper",
        "ib_host": args.host,
        "ib_port": args.port,
        "allow_live": args.allow_live,
        "symbol": args.symbol,
    }
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
            # Far below market so it should not fill; then cancel.
            limit = round(q.bid * 0.95, 5)
            print(f"smoke order: BUY limit {args.quantity} @ {limit} then cancel")
            res = eng.place_and_cancel_limit(args.symbol, "buy", args.quantity, limit)
            print(f"order_result ok={res.ok} id={res.broker_order_id} msg={res.message}")
        print("SMOKE_OK")
    finally:
        eng.disconnect()


if __name__ == "__main__":
    main()
