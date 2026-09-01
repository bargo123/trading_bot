#!/usr/bin/env python3
"""Build point-in-time analogue index from MT5 M1 history or synthetic data."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

BOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BOT))

from aegis.config import configured_symbols, load_config, pip_size_for  # noqa: E402
from aegis.intel.paths import INTEL_DIR  # noqa: E402
from aegis.research.analogues import build_analogues_from_m1, save_analogue_index  # noqa: E402
from aegis.research.shadow_observe import bars_to_frame  # noqa: E402


def _synthetic_m1(*, n: int = 800, start: float = 1.10) -> pd.DataFrame:
    time = pd.date_range("2026-01-01", periods=n, freq="min", tz="UTC")
    close = pd.Series([start + index * 0.00001 for index in range(n)])
    return pd.DataFrame(
        {
            "time": time,
            "open": close - 0.00005,
            "high": close + 0.00012,
            "low": close - 0.00012,
            "close": close,
            "volume": 100.0,
        }
    )


def _synthetic_records(symbols: list[str], *, per_symbol: int = 60) -> list[dict]:
    """Fast labelled index for offline/demo bootstrap (research_proxy)."""
    rows: list[dict] = []
    setups = ("breakout", "retest", "none")
    regimes = ("trend", "range", "unknown")
    structures = ("breakout", "retest", "none")
    vols = ("expanding", "compressing", "stable")
    sessions = ("asia", "london", "new_york", "late")
    for sym in symbols:
        for index in range(per_symbol):
            hour = index % 24
            rows.append(
                {
                    "bar_time": f"2026-01-{(index % 28) + 1:02d}T{hour:02d}:00:00+00:00",
                    "symbol": str(sym).upper(),
                    "side": "buy" if index % 2 == 0 else "sell",
                    "setup": setups[index % len(setups)],
                    "regime": regimes[index % len(regimes)],
                    "structure": structures[index % len(structures)],
                    "volatility": vols[index % len(vols)],
                    "session": sessions[index % len(sessions)],
                    "h1_direction": "up" if index % 3 else "down",
                    "m5_direction": "up" if index % 5 else "down",
                    "outcome": 0.04 if index % 4 else -0.02,
                    "label": "research_proxy",
                }
            )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default=str(BOT / "config_mt5_demo_firehose_hw.yaml"),
        help="Demo YAML for symbol list and pip sizes",
    )
    parser.add_argument(
        "--output",
        default=str(INTEL_DIR / "analogue_index.json"),
        help="Where to write analogue_index.v1",
    )
    parser.add_argument("--lookback-days", type=int, default=5, help="MT5 M1 lookback days")
    parser.add_argument(
        "--synthetic",
        action="store_true",
        help="Build from synthetic trending M1 (CI/offline; no MT5 required)",
    )
    parser.add_argument("--min-bars", type=int, default=400)
    parser.add_argument("--step", type=int, default=3)
    args = parser.parse_args()

    cfg = load_config(args.config)
    symbols = configured_symbols(cfg)
    pip_by_symbol = {sym: pip_size_for(sym, cfg) for sym in symbols}
    frames: dict[str, pd.DataFrame] = {}

    if args.synthetic:
        rows = _synthetic_records(symbols[: min(8, len(symbols))], per_symbol=80)
        provenance = "synthetic_proxy"
        outcome_unit = "usd_fixture"
        source: dict = {"builder": "_synthetic_records", "note": "offline fixture; not market evidence"}
    else:
        from aegis.engines import create_engine

        engine = create_engine({**cfg, "allow_live": False})
        if not hasattr(engine, "connect_readonly"):
            raise SystemExit("engine lacks read-only attach; use --synthetic")
        engine.connect_readonly()
        for sym in symbols:
            bars = engine.bars(sym, str(cfg.get("timeframe") or "1m"), int(args.lookback_days))
            if len(bars) < args.min_bars:
                print(f"skip {sym}: only {len(bars)} bars")
                continue
            frames[sym] = bars_to_frame(bars)

        if not frames:
            raise SystemExit("no M1 frames collected; try --synthetic or increase lookback")

        rows = build_analogues_from_m1(
            frames,
            pip_by_symbol=pip_by_symbol,
            min_bars=int(args.min_bars),
            step=int(args.step),
        )
        provenance = "mt5_m1"
        outcome_unit = "pips"
        source = {
            "builder": "build_analogues_from_m1",
            "engine": str(cfg.get("engine") or ""),
            "timeframe": str(cfg.get("timeframe") or ""),
            "lookback_days": int(args.lookback_days),
            "step": int(args.step),
            "min_bars": int(args.min_bars),
            "symbols": sorted(frames),
            "bars_per_symbol": {sym: int(len(frame)) for sym, frame in sorted(frames.items())},
        }

    out = Path(args.output)
    payload = save_analogue_index(
        rows, out, provenance=provenance, outcome_unit=outcome_unit, source=source
    )
    print(
        f"wrote {payload['n']} analogue records -> {out} "
        f"(provenance={payload['provenance']}, outcome_unit={payload['outcome_unit']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
