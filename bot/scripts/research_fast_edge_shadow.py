"""Build a universal MT5 quote shadow firehose; never submits orders."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml

BOT_ROOT = Path(__file__).resolve().parents[1]
if str(BOT_ROOT) not in sys.path:
    sys.path.insert(0, str(BOT_ROOT))

from aegis.engines.mt5 import MT5Engine  # noqa: E402
from aegis.research.fast_edge_shadow import (  # noqa: E402
    SHADOW_HORIZONS_S,
    build_shadow_dataset,
    fit_shadow_model_space,
)
from aegis.research.registry import ExperimentRegistry  # noqa: E402
from aegis.config import configured_symbols  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=BOT_ROOT / "config_mt5_demo_firehose_hw.yaml")
    parser.add_argument("--lookback-seconds", type=int, default=3600)
    parser.add_argument("--sample-every-seconds", type=int, default=1)
    parser.add_argument("--out-dir", type=Path, default=BOT_ROOT / "reports" / "research")
    parser.add_argument("--no-rows", action="store_true", help="do not persist the row-level shadow dataset")
    parser.add_argument("--rows-input", type=Path, help="reuse a previously persisted shadow JSONL dataset")
    args = parser.parse_args()

    if args.rows_input:
        frame = pd.read_json(args.rows_input, orient="records", lines=True)
        frame["time"] = pd.to_datetime(frame["time"], utc=True)
        print(f"REUSED_SHADOW_ROWS {len(frame)} source={args.rows_input}", flush=True)
    else:
        cfg = yaml.safe_load(args.config.read_text(encoding="utf-8")) or {}
        symbols = list(configured_symbols(cfg))
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
                print(f"HISTORY {symbol} ticks={len(rows)}", flush=True)
            except Exception as exc:
                print(f"HISTORY_SKIP {symbol} {type(exc).__name__}: {str(exc)[:120]}", flush=True)
        if not quotes_by_symbol:
            raise SystemExit("no MT5 quote history was available")
        frame = build_shadow_dataset(
            quotes_by_symbol,
            horizons=SHADOW_HORIZONS_S,
            sample_every_s=max(1, int(args.sample_every_seconds)),
        )
    model_report = fit_shadow_model_space(frame, min_samples=20)
    primary_metrics = (
        model_report["oos_metrics"].get(model_report["primary_model"], {}).get("sealed", {})
        if model_report.get("primary_model") else {}
    )
    args.out_dir.mkdir(parents=True, exist_ok=True)
    if not args.no_rows:
        frame.to_json(
            args.out_dir / "fast_edge_shadow_rows.jsonl",
            orient="records", lines=True, date_format="iso", double_precision=15,
        )
    report = {
        "schema": "fast_edge_shadow.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "SHADOW_ONLY",
        "execution_authority": "NONE",
        "SHORT_HORIZON_MODEL_STATUS": "SHADOW_ONLY",
        "EXECUTION_STATUS": "SHADOW_ONLY_NO_POSITIVE_OOS",
        "TARGET_DEFINITION": "captured_exit_replay",
        "AUTHORIZED_SYMBOLS": [],
        "MODEL_COUNT": model_report["model_count"],
        "DATASET_HASH": model_report["dataset_hash"],
        "VALIDATION_HASH": model_report["validation_hash"],
        "DECISION_HORIZON": "multi_horizon_shadow_only",
        "candidate_source": "all_quote_entries",
        "target_definition": "captured_exit_replay",
        "horizons_s": list(SHADOW_HORIZONS_S),
        "symbols": sorted(frame["symbol"].astype(str).str.upper().unique().tolist()),
        "candidate_rows": int(len(frame)),
        "candidate_sides": sorted(frame["side"].unique().tolist()),
        "dataset_hash": model_report["dataset_hash"],
        "time_range": [str(frame["time"].min()), str(frame["time"].max())],
        "outcome_counts": {
            str(key): int(value)
            for key, value in frame["captured_exit_reason"].value_counts().to_dict().items()
        },
        "model_space": model_report,
        "OOS_TEST_N": model_report["oos"]["test_n"],
        "OOS_SEALED_N": model_report["oos"]["sealed_n"],
        "OOS_PRIMARY_MODEL": model_report["primary_model"],
        "OOS_PRECISION": primary_metrics.get("precision"),
        "OOS_CAPTURED_EXPECTANCY": primary_metrics.get("captured_exit_expectancy"),
        "OOS_CAPTURED_PF": primary_metrics.get("captured_exit_pf"),
        "P95_LOSS": primary_metrics.get("p95_loss"),
        "P99_LOSS": primary_metrics.get("p99_loss"),
        "CALIBRATION_ECE": primary_metrics.get("calibration_ece"),
        "ABSTAIN_RATE": primary_metrics.get("abstain_rate"),
        "note": "Evidence only. No model or leaderboard row authorizes broker execution.",
    }
    report_path = args.out_dir / "fast_edge_leaderboard.json"
    report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    registry = ExperimentRegistry()
    experiment_id = f"fast_edge_shadow_{model_report['dataset_hash'][:16]}"
    if registry.get(experiment_id) is None:
        registry.record(
            {
                "id": experiment_id,
                "hypothesis": "universal quote-entry captured-exit edge by short horizon",
                "status": "shadow",
                "code_commit": None,
                "config_fingerprint": "mt5_demo_readonly_shadow_v1",
                "dataset_fingerprint": model_report["dataset_hash"],
                "params": {"horizons_s": list(SHADOW_HORIZONS_S), "symbols": len(report["symbols"])},
                "metrics": {"candidate_rows": len(frame), "leaderboard_rows": len(model_report["leaderboard"])},
            }
        )
    print(
        f"SHADOW_ONLY rows={len(frame)} symbols={len(report['symbols'])} "
        f"dataset={model_report['dataset_hash']} report={report_path} experiment={experiment_id}",
        flush=True,
    )


if __name__ == "__main__":
    main()
