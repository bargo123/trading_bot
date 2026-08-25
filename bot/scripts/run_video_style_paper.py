#!/usr/bin/env python3
"""Run the all-symbol video-style hypothesis against CSV bars.

This is a research artifact generator.  Its MT5 mode reads completed bars
through the existing read-only engine path and never places orders.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Sequence

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aegis.research.video_style_paper import (  # noqa: E402
    VideoStyleConfig,
    VideoStyleResult,
    simulate_video_style,
)


def collect_mt5_bars(
    engine: object,
    symbols: Sequence[str],
    timeframe: str,
    lookback_days: int,
) -> dict[str, pd.DataFrame]:
    """Collect read-only completed bars through the existing engine interface."""
    frames: dict[str, pd.DataFrame] = {}
    failures: list[str] = []
    for raw_symbol in symbols:
        symbol = str(raw_symbol or "").strip().upper()
        if not symbol:
            continue
        try:
            bars = engine.bars(symbol, timeframe, lookback_days)  # type: ignore[attr-defined]
            rows = [
                {
                    "time": bar.time,
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                }
                for bar in bars
            ]
            if not rows:
                failures.append(f"{symbol}: no bars")
                continue
            frames[symbol] = pd.DataFrame(rows)
        except Exception as exc:  # fail closed for the whole all-symbol snapshot
            failures.append(f"{symbol}: {exc}")
    if failures:
        raise RuntimeError("MT5 bar collection failed: " + "; ".join(failures))
    if not frames:
        raise RuntimeError("MT5 bar collection returned no symbols")
    return frames


def _load_bars(bars_dir: Path) -> dict[str, pd.DataFrame]:
    files = sorted(bars_dir.glob("*.csv"))
    if not files:
        raise ValueError(f"no CSV bar files found in {bars_dir}")
    loaded: dict[str, pd.DataFrame] = {}
    for path in files:
        symbol = path.stem.strip().upper()
        if not symbol or symbol in loaded:
            raise ValueError(f"duplicate or empty symbol filename: {path.name}")
        loaded[symbol] = pd.read_csv(path)
    return loaded


def _result_json(result: VideoStyleResult) -> dict[str, object]:
    payload = asdict(result)
    payload["trades"] = [asdict(trade) for trade in result.trades]
    return payload


def _write_artifacts(result: VideoStyleResult, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "video_style_paper_result.json").write_text(
        json.dumps(_result_json(result), indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    trades = pd.DataFrame([asdict(trade) for trade in result.trades])
    if trades.empty:
        trades = pd.DataFrame(
            columns=[
                "symbol", "side", "layer", "entry_time", "exit_time",
                "entry_price", "exit_price", "quantity", "gross_pnl",
                "costs", "net_pnl", "r_multiple", "exit_reason",
            ]
        )
    trades.to_csv(output_dir / "video_style_paper_trades.csv", index=False)
    lines = [
        "# All-Symbol Video-Style Paper Simulation",
        "",
        "placed_orders: false",
        f"starting_equity: {result.starting_equity:.8f}",
        f"ending_equity: {result.ending_equity:.8f}",
        f"net_pnl: {result.ending_equity - result.starting_equity:.8f}",
        f"max_drawdown: {result.max_drawdown:.8f}",
        f"trades: {len(result.trades)}",
        f"wins: {result.wins}",
        f"losses: {result.losses}",
        "",
        "## Per symbol",
        "",
    ]
    for symbol, summary in sorted(result.per_symbol.items()):
        lines.append(
            f"- `{symbol}`: trades={summary['trades']} wins={summary['wins']} "
            f"losses={summary['losses']} net_pnl={float(summary['net_pnl']):.8f}"
        )
    (output_dir / "video_style_paper_summary.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def _run_mt5_readonly(
    *,
    config_path: Path,
    output_dir: Path,
    timeframe: str,
    lookback_days: int,
    interval_s: float,
    once: bool,
    cfg: VideoStyleConfig,
) -> int:
    from aegis.config import configured_symbols, load_config
    from aegis.engines.mt5 import MT5Engine

    raw_cfg = load_config(config_path)
    if str(raw_cfg.get("engine") or "").lower() != "mt5":
        raise ValueError("MT5 feed requires engine: mt5")
    if str(raw_cfg.get("mode") or "").lower() != "mt5_demo":
        raise ValueError("MT5 feed requires mode: mt5_demo")
    if bool(raw_cfg.get("allow_live", False)):
        raise ValueError("MT5 feed refuses allow_live: true")
    engine = MT5Engine(raw_cfg)
    engine.connect_readonly()
    try:
        symbols = configured_symbols(raw_cfg)
        while True:
            frames = collect_mt5_bars(engine, symbols, timeframe, lookback_days)
            result = simulate_video_style(frames, cfg)
            _write_artifacts(result, output_dir)
            print(
                f"Read-only MT5 snapshot: symbols={len(frames)} trades={len(result.trades)} "
                f"ending_equity={result.ending_equity:.8f} placed_orders={result.placed_orders}"
            )
            if once:
                return 0
            time.sleep(max(1.0, interval_s))
    finally:
        engine.disconnect(shutdown=False)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="All-symbol video-style paper simulator")
    parser.add_argument("--bars-dir", type=Path)
    parser.add_argument("--mt5-config", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--timeframe", default="M1")
    parser.add_argument("--lookback-days", type=int, default=30)
    parser.add_argument("--interval-s", type=float, default=60.0)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--starting-equity", type=float, default=100.0)
    parser.add_argument("--risk-per-trade", type=float, default=0.15)
    parser.add_argument("--reward-to-risk", type=float, default=3.0)
    parser.add_argument("--max-layers", type=int, default=4)
    parser.add_argument("--stop-r", type=float, default=0.5)
    parser.add_argument("--scale-after-r", type=float, default=0.75)
    parser.add_argument("--spread-cost", type=float, default=0.0)
    parser.add_argument("--slippage-cost", type=float, default=0.0)
    parser.add_argument("--commission-cost", type=float, default=0.0)
    parser.add_argument("--max-hold-bars", type=int, default=0)
    parser.add_argument("--max-hold-s", type=int, default=45)
    args = parser.parse_args(argv)
    try:
        if bool(args.bars_dir) == bool(args.mt5_config):
            raise ValueError("provide exactly one of --bars-dir or --mt5-config")
        sim_cfg = VideoStyleConfig(
            starting_equity=args.starting_equity,
            risk_per_trade=args.risk_per_trade,
            stop_r=args.stop_r,
            reward_to_risk=args.reward_to_risk,
            scale_after_r=args.scale_after_r,
            max_layers=args.max_layers,
            spread_cost=args.spread_cost,
            slippage_cost=args.slippage_cost,
            commission_cost=args.commission_cost,
            max_hold_bars=args.max_hold_bars,
            max_hold_s=args.max_hold_s,
        )
        if args.mt5_config:
            return _run_mt5_readonly(
                config_path=args.mt5_config,
                output_dir=args.output_dir,
                timeframe=args.timeframe,
                lookback_days=args.lookback_days,
                interval_s=args.interval_s,
                once=args.once,
                cfg=sim_cfg,
            )
        result = simulate_video_style(_load_bars(args.bars_dir), sim_cfg)
        _write_artifacts(result, args.output_dir)
    except (OSError, ValueError, TypeError) as exc:
        print(f"video-style paper simulation failed: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote research-only paper artifacts to {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
