#!/usr/bin/env python3
"""Build a MEASURED point-in-time analogue index from real MT5 M1 history.

The committed offline index is a synthetic fixture (two outcome values on a
mechanical time grid) that hands back a "calibrated" profit factor of 6.0 for any
query. The runtime now refuses non-measured provenance, so a real index has to
exist before the Intelligent Firehose can fire at all.

``build_analogues_from_m1`` rebuilds market state from a growing history slice for
every sampled bar, which is O(n^2) over a symbol and far too slow to run 26 symbols
serially. Symbols are independent, so they fan out across processes.

Read-only: fetches bars and places no orders.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

BOT = Path(__file__).resolve().parents[1]
if str(BOT) not in sys.path:
    sys.path.insert(0, str(BOT))

from aegis.config import configured_symbols, load_config, pip_size_for  # noqa: E402
from aegis.intel.expected_value import payoff_metrics  # noqa: E402
from aegis.intel.paths import INTEL_DIR  # noqa: E402
from aegis.research.analogues import build_analogues_from_m1, save_analogue_index  # noqa: E402

MT5_PATH = r"C:\Program Files\MetaTrader 5\terminal64.exe"


def fetch_m1(symbols: list[str], bars: int, mt5_path: str) -> dict[str, pd.DataFrame]:
    """Pull completed M1 bars for each symbol from the running terminal."""
    import MetaTrader5 as mt5

    if not mt5.initialize(path=mt5_path):
        raise SystemExit(f"mt5.initialize failed: {mt5.last_error()}")
    try:
        account = mt5.account_info()
        if account is None:
            raise SystemExit("mt5.account_info() is None - terminal not logged in")
        # Never build an index off a live account's terminal by accident.
        demo = int(getattr(mt5, "ACCOUNT_TRADE_MODE_DEMO", 0))
        contest = int(getattr(mt5, "ACCOUNT_TRADE_MODE_CONTEST", 1))
        if int(getattr(account, "trade_mode", 2)) not in {demo, contest}:
            raise SystemExit("refusing to run against a live account terminal")
        print(f"terminal: {account.server} login={account.login} mode=DEMO", flush=True)

        frames: dict[str, pd.DataFrame] = {}
        for symbol in symbols:
            if mt5.symbol_info(symbol) is None and not mt5.symbol_select(symbol, True):
                print(f"skip {symbol}: not available", flush=True)
                continue
            raw = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, bars)
            if raw is None or len(raw) < 500:
                print(f"skip {symbol}: {0 if raw is None else len(raw)} bars", flush=True)
                continue
            frame = pd.DataFrame(raw)
            frame["time"] = pd.to_datetime(frame["time"], unit="s", utc=True)
            frame = frame.rename(columns={"tick_volume": "volume"})
            # Drop the still-forming final bar; the index must use completed bars only.
            frames[symbol] = frame.iloc[:-1][["time", "open", "high", "low", "close", "volume"]].copy()
            print(f"{symbol}: {len(frames[symbol])} completed M1 bars", flush=True)
        return frames
    finally:
        mt5.shutdown()


def _build_one(args: tuple[str, str, float, int, int]) -> tuple[str, list[dict], float]:
    """Worker: rebuild one symbol's analogues from a parquet-free CSV round-trip."""
    symbol, csv_path, pip, min_bars, step = args
    if str(BOT) not in sys.path:
        sys.path.insert(0, str(BOT))
    from aegis.research.analogues import build_analogues_from_m1 as build

    started = time.time()
    frame = pd.read_csv(csv_path, parse_dates=["time"])
    rows = build({symbol: frame}, pip_by_symbol={symbol: pip}, min_bars=min_bars, step=step)
    return symbol, rows, time.time() - started


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(BOT / "config_mt5_demo_firehose_hw.yaml"))
    parser.add_argument("--output", default=str(INTEL_DIR / "analogue_index.json"))
    parser.add_argument("--bars", type=int, default=6000, help="M1 bars per symbol to fetch")
    parser.add_argument("--min-bars", type=int, default=400, help="history needed before sampling")
    parser.add_argument("--step", type=int, default=15, help="sample every Nth bar")
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--scratch", default=None, help="dir for worker CSV handoff")
    args = parser.parse_args()

    cfg = load_config(args.config)
    symbols = configured_symbols(cfg)
    print(f"{len(symbols)} configured symbols", flush=True)

    frames = fetch_m1(symbols, int(args.bars), str(cfg.get("mt5_path") or MT5_PATH))
    if not frames:
        raise SystemExit("no M1 frames collected")

    scratch = Path(args.scratch) if args.scratch else Path(args.output).parent / "_analogue_build"
    scratch.mkdir(parents=True, exist_ok=True)
    jobs = []
    for symbol, frame in frames.items():
        csv_path = scratch / f"{symbol}.csv"
        frame.to_csv(csv_path, index=False)
        jobs.append(
            (symbol, str(csv_path), float(pip_size_for(symbol, cfg)), int(args.min_bars), int(args.step))
        )

    rows: list[dict] = []
    per_symbol: dict[str, int] = {}
    started = time.time()
    with ProcessPoolExecutor(max_workers=int(args.workers)) as pool:
        futures = {pool.submit(_build_one, job): job[0] for job in jobs}
        for done in as_completed(futures):
            symbol, produced, elapsed = done.result()
            rows.extend(produced)
            per_symbol[symbol] = len(produced)
            print(
                f"{symbol}: {len(produced)} analogues in {elapsed:.0f}s "
                f"({len(per_symbol)}/{len(jobs)} symbols, {time.time() - started:.0f}s total)",
                flush=True,
            )

    for csv_path in scratch.glob("*.csv"):
        csv_path.unlink()
    try:
        scratch.rmdir()
    except OSError:
        pass

    if not rows:
        raise SystemExit("builder produced no analogue records")

    outcomes = [float(row["outcome"]) for row in rows]
    stats = payoff_metrics(outcomes)
    payload = save_analogue_index(
        rows,
        Path(args.output),
        provenance="mt5_m1",
        outcome_unit="pips",
        source={
            "builder": "build_real_analogue_index.py",
            "engine": "mt5",
            "timeframe": "1m",
            "bars_requested": int(args.bars),
            "min_bars": int(args.min_bars),
            "step": int(args.step),
            "symbols": sorted(per_symbol),
            "records_per_symbol": per_symbol,
            "built_utc": pd.Timestamp.utcnow().isoformat(),
        },
    )

    summary = {
        "records": payload["n"],
        "provenance": payload["provenance"],
        "outcome_unit": payload["outcome_unit"],
        "symbols": len(per_symbol),
        "distinct_outcomes": len(set(outcomes)),
        "payoff": stats,
    }
    report = BOT / "reports" / "claude" / "analogue_index_real.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(json.dumps(summary, indent=2, default=str), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
