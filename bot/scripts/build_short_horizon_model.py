"""Build a governed short-horizon artifact from read-only MT5 DEMO ticks.

This command is research-only.  It attaches read-only, fetches completed quote
history, performs chronological/OOS training, and publishes only when the
artifact builder's positive cost-aware OOS gate passes.  It has no order path.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

import pandas as pd
import yaml

if __package__ in {None, ""}:  # support `python scripts/build_short_horizon_model.py`
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aegis.engines.mt5 import MT5Engine
from aegis.intel.paths import BOT_ROOT
from aegis.intel.trade_economics import usd_per_price_unit
from aegis.research.registry import ExperimentRegistry
from aegis.research.short_horizon import DEFAULT_HORIZONS_S
from aegis.research.short_horizon_artifact import (
    build_quote_training_frame,
    record_artifact_outcome,
    train_and_publish,
)


def select_research_symbols(
    configured: Sequence[str], overrides: Sequence[str] | None
) -> list[str]:
    """Select an ordered, configured subset for bounded read-only replay."""
    configured_order = [str(symbol).strip().upper() for symbol in configured if str(symbol).strip()]
    if not overrides:
        return configured_order
    requested = {str(symbol).strip().upper() for symbol in overrides if str(symbol).strip()}
    selected = [symbol for symbol in configured_order if symbol in requested]
    if not selected:
        raise ValueError("symbol filter did not match any configured symbol")
    return selected


def research_usd_per_price_unit_by_symbol(
    engine: MT5Engine,
    symbols: Sequence[str],
) -> dict[str, float]:
    """Price labels in broker-account USD at the broker minimum lot.

    Minimum lot is the conservative executable quantity for fixed per-trade
    costs.  Missing broker tick/contract evidence fails closed instead of
    silently treating one raw price unit as one dollar.
    """
    result: dict[str, float] = {}
    for raw_symbol in symbols:
        symbol = str(raw_symbol).strip().upper()
        spec = engine.symbol_spec(symbol)
        try:
            minimum_lot = float(spec.get("volume_min"))
        except (AttributeError, TypeError, ValueError, OverflowError):
            minimum_lot = 0.0
        conversion = usd_per_price_unit(spec, lots=minimum_lot)
        if conversion is None:
            raise ValueError(f"USD conversion unavailable for {symbol}")
        result[symbol] = float(conversion)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=BOT_ROOT / "config_mt5_demo_firehose_hw.yaml")
    parser.add_argument("--lookback-seconds", type=int, default=14_400)
    parser.add_argument("--sample-every-seconds", type=int, default=5)
    parser.add_argument(
        "--symbol",
        action="append",
        dest="symbol_overrides",
        help="bounded configured symbol replay (repeatable)",
    )
    parser.add_argument(
        "--target-mode",
        choices=("captured_exit_replay", "mfe_first", "fast_harvest", "terminal_profit"),
        default="captured_exit_replay",
        help="Point-in-time executable target; older labels remain auxiliary research targets",
    )
    parser.add_argument("--output", type=Path, default=BOT_ROOT / "intel" / "short_horizon_model")
    args = parser.parse_args()
    cfg = yaml.safe_load(args.config.read_text(encoding="utf-8")) or {}
    symbols = select_research_symbols(cfg.get("symbols") or (), args.symbol_overrides)
    if not symbols:
        raise SystemExit("config has no eligible symbols")
    engine = MT5Engine(dict(cfg))
    engine.connect_readonly()
    quotes_by_symbol: dict[str, pd.DataFrame] = {}
    for symbol in symbols:
        try:
            rows = engine.copy_ticks(symbol, lookback_seconds=max(60, int(args.lookback_seconds)))
            if rows:
                quotes_by_symbol[symbol] = pd.DataFrame(
                    {
                        "time": pd.to_datetime([row["time"] for row in rows], unit="s", utc=True),
                        "bid": [row["bid"] for row in rows],
                        "ask": [row["ask"] for row in rows],
                    }
                )
            print(f"HISTORY {symbol} ticks={len(rows)}")
        except Exception as exc:
            print(f"HISTORY_SKIP {symbol} {type(exc).__name__}: {str(exc)[:120]}")
    if not quotes_by_symbol:
        raise SystemExit("no MT5 quote history was available")
    usd_conversion = research_usd_per_price_unit_by_symbol(
        engine,
        tuple(quotes_by_symbol),
    )
    frame = build_quote_training_frame(
        quotes_by_symbol,
        horizons=DEFAULT_HORIZONS_S,
        sample_every_s=max(1, int(args.sample_every_seconds)),
        target_mode=args.target_mode,
        slippage_bps=float(cfg.get("slippage_bps", 0.0) or 0.0),
        commission_round_trip_usd=float(cfg.get("commission_round_trip_usd", 0.0) or 0.0),
        usd_per_price_unit_by_symbol=usd_conversion,
        mechanism="quote_microstructure_v1",
        provenance="mt5_quote_replay",
    )
    print(f"TRAINING_ROWS {len(frame)} SYMBOLS {frame['symbol'].nunique()} TIMES {frame['time'].min()}..{frame['time'].max()}")
    metadata = train_and_publish(
        frame,
        args.output,
        horizons=DEFAULT_HORIZONS_S,
        decision_horizon_s=10,
        target_definition=args.target_mode,
    )
    experiment_id = record_artifact_outcome(
        metadata,
        registry=ExperimentRegistry(),
    )
    print(
        "PUBLISHED",
        args.output,
        "schema=",
        metadata["schema"],
        "experiment=",
        experiment_id,
        "test=",
        metadata["oos"]["test"],
        "sealed=",
        metadata["oos"]["sealed"],
    )


if __name__ == "__main__":
    main()
