#!/usr/bin/env python3
"""Incremental market-evidence ingestion (research-only, read-only MT5).

Fetches completed M1 bars newer than the persisted cursor for each configured
symbol, appends raw evidence, labels rows whose forward horizon has completed,
merges them into the analogue index (deduped), and advances the cursor.

Restart-safe: re-running never duplicates observations.
"""
from __future__ import annotations

import argparse
import json
import time
import sys
from pathlib import Path

BOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BOT))

from aegis.config import configured_symbols, load_config, pip_size_for  # noqa: E402
from aegis.research.incremental_ingest import (  # noqa: E402
    ingest_symbol,
    load_cursor,
    index_record_keys,
    save_cursor,
)

MT5_PATH = r"C:\Program Files\MetaTrader 5\terminal64.exe"


def main() -> int:
    parser = argparse.ArgumentParser(description="Incremental analogue ingestion")
    parser.add_argument("--config", type=Path, default=BOT / "config_mt5_demo_firehose_hw.yaml")
    parser.add_argument("--index", type=Path, default=BOT / "intel" / "analogue_index.json")
    parser.add_argument("--cursor", type=Path, default=BOT / "intel" / "ingest_cursor.json")
    parser.add_argument("--raw-evidence", type=Path, default=BOT / "intel" / "market_evidence.jsonl")
    parser.add_argument("--max-bars", type=int, default=600,
                        help="max NEW bars accepted per symbol per cycle")
    parser.add_argument("--lookback-days", type=int, default=2,
                        help="calendar days of M1 history fetched per symbol")
    parser.add_argument("--time-budget-s", type=float, default=600.0,
                        help="stop starting new symbols after this many seconds")
    parser.add_argument("--symbols", type=str, default="", help="comma list override")
    args = parser.parse_args()

    cfg = load_config(args.config)
    if bool(cfg.get("allow_live", False)):
        raise SystemExit("allow_live must be false; refusing ingestion run")
    symbols = (
        [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
        if args.symbols
        else list(configured_symbols(cfg))
    )
    pip_by_symbol = {s: float(pip_size_for(s, cfg)) for s in symbols}

    from aegis.engines import create_engine

    eng = create_engine({**cfg, "allow_live": False})
    if not hasattr(eng, "connect_readonly"):
        raise SystemExit("engine lacks read-only attach")
    eng.connect_readonly()
    account = eng.account()
    if not getattr(account, "is_paper", True):
        raise SystemExit("refusing ingestion against a non-demo account")

    cursor = load_cursor(args.cursor)
    existing = index_record_keys(args.index)
    # Symbols with the OLDEST (or missing) cursor go first; a time budget keeps
    # each cycle bounded and the cursor persists after EVERY symbol so a kill
    # mid-run never repeats work.
    def _freshness(sym: str):
        return (cursor.get("symbols") or {}).get(str(sym).upper()) or ""

    ordered = sorted(symbols, key=_freshness)
    budget_s = float(args.time_budget_s)
    started = time.time()
    results = []
    try:
        for symbol in ordered:
            if results and time.time() - started > budget_s:
                results.append({"symbol": str(symbol).upper(),
                                "deferred": "time_budget"})
                continue
            try:
                res = ingest_symbol(
                    eng,
                    symbol,
                    cursor=cursor,
                    pip_by_symbol=pip_by_symbol,
                    raw_evidence_path=args.raw_evidence,
                    index_path=args.index,
                    existing_keys=existing,
                    max_bars=int(args.max_bars),
                    lookback_days=int(args.lookback_days),
                )
            except Exception as exc:  # one symbol failing never blocks the rest
                res = {"symbol": symbol, "error": str(exc)[:160]}
            results.append(res)
            last = res.get("last_bar")
            if last and not res.get("error"):
                cursor.setdefault("symbols", {})[str(symbol).upper()] = last
                save_cursor(cursor, args.cursor)  # persist per symbol
            # keep existing keys fresh so cross-symbol dupes are caught
            existing = index_record_keys(args.index)
    finally:
        save_cursor(cursor, args.cursor)
        try:
            eng.disconnect()
        except Exception:
            pass

    print(
        json.dumps(
            {
                "ingested_symbols": len(results),
                "added_total": sum(r.get("index_added", 0) for r in results),
                "new_bars_total": sum(r.get("new_bars", 0) for r in results),
                "results": results,
                "placed_orders": False,
                "mt5_touched": True,
            },
            indent=1,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
