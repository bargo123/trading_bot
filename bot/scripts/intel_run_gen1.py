#!/usr/bin/env python3
"""Freeze CORE_STRATEGY_V1, run baseline + gen-1 intel challengers. Offline.

Does not edit config_mt5_demo_firehose_hw.yaml. Does not place live orders.
Does not call mt5.shutdown(). 100% WR is a target, not a claim.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aegis.intel.paths import INTEL_DIR, ensure_intel_dirs
from aegis.intel.runner import run_generation
from aegis.optimizer.walk_forward import synthetic_ohlcv


def main() -> None:
    p = argparse.ArgumentParser(description="CORE_STRATEGY_V1 intel generation-1 (offline)")
    p.add_argument("--bars", type=int, default=2500)
    p.add_argument("--seed", type=int, default=7)
    args = p.parse_args()
    ensure_intel_dirs()
    df = synthetic_ohlcv(n=max(400, int(args.bars)), seed=int(args.seed))
    out = run_generation(df, persist=True)
    summary = {
        "champion": out["baseline"]["id"],
        "baseline_trades": out["baseline"]["metrics"].get("total_trades"),
        "baseline_wr": out["baseline"]["metrics"].get("win_rate"),
        "baseline_e": out["baseline"]["metrics"].get("expectancy_r"),
        "baseline_pnl": out["baseline"]["metrics"].get("net_pnl"),
        "families": out["families"],
        "db": out["db"],
        "challenger": out["challenger"],
        "experiments": [
            {
                "id": r["id"],
                "decision": r["decision"],
                "reason": r["reason"],
                "wr": r["win_rate"],
                "e": r["expectancy"],
                "pnl": r["profit"],
                "n": r["number_of_trades"],
                "loss_removal": r["loss_removal"],
            }
            for r in out["experiments"]
        ],
    }
    print(json.dumps(summary, indent=2, default=str))
    print(f"wrote {INTEL_DIR}")


if __name__ == "__main__":
    main()
