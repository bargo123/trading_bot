"""Build a governed short-horizon artifact from read-only MT5 DEMO ticks.

This command is research-only.  It attaches read-only, fetches completed quote
history, performs chronological/OOS training, and publishes only when the
artifact builder's positive cost-aware OOS gate passes.  It has no order path.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
import yaml

if __package__ in {None, ""}:  # support `python scripts/build_short_horizon_model.py`
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aegis.engines.mt5 import MT5Engine
from aegis.intel.paths import BOT_ROOT
from aegis.research.registry import ExperimentRegistry
from aegis.research.short_horizon import DEFAULT_HORIZONS_S
from aegis.research.short_horizon_artifact import (
    build_quote_training_frame,
    record_artifact_outcome,
    train_and_publish,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=BOT_ROOT / "config_mt5_demo_firehose_hw.yaml")
    parser.add_argument("--lookback-seconds", type=int, default=14_400)
    parser.add_argument("--sample-every-seconds", type=int, default=5)
    parser.add_argument(
        "--target-mode",
        choices=("mfe_first", "terminal_profit"),
        default="mfe_first",
        help="Research label: temporary green or terminal profit at the horizon",
    )
    parser.add_argument("--output", type=Path, default=BOT_ROOT / "intel" / "short_horizon_model")
    args = parser.parse_args()
    cfg = yaml.safe_load(args.config.read_text(encoding="utf-8")) or {}
    symbols = [str(value).upper() for value in (cfg.get("symbols") or []) if str(value).strip()]
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
    frame = build_quote_training_frame(
        quotes_by_symbol,
        horizons=DEFAULT_HORIZONS_S,
        sample_every_s=max(1, int(args.sample_every_seconds)),
        target_mode=args.target_mode,
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
