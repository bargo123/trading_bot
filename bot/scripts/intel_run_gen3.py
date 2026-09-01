#!/usr/bin/env python3
"""Generation-3 intel around CORE_STRATEGY_V1.

Compares challengers to CORE 1/30 after costs (OOS E, not WR).
Does not edit live YAML. Does not place orders. Never mt5.shutdown().
100% WR is a target, not a claim.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aegis.intel.frozen_v1 import research_cfg
from aegis.intel.paths import INTEL_DIR, ensure_intel_dirs
from aegis.intel.runner import GEN3, run_generation
from aegis.optimizer.cycle import _load_bars


def _summary(out: dict, *, source: str, bars: int, days: int, expset: str) -> dict:
    return {
        "source": source,
        "bars": bars,
        "days": days,
        "champion": out["baseline"]["id"],
        "baseline_trades": out["baseline"]["metrics"].get("total_trades"),
        "baseline_wr": out["baseline"]["metrics"].get("win_rate"),
        "baseline_e": out["baseline"]["metrics"].get("expectancy_r"),
        "baseline_pnl": out["baseline"]["metrics"].get("net_pnl"),
        "baseline_oos_e": (out["baseline"].get("oos") or {}).get("expectancy_r"),
        "pattern": out.get("pattern"),
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
                "oos_wr": (r.get("candidate") or {}).get("oos", {}).get("win_rate"),
                "oos_e": (r.get("candidate") or {}).get("oos", {}).get("expectancy_r"),
                "wf_mean_e": (r.get("walk_forward") or {}).get("mean_oos_expectancy_r"),
                "loss_removal": r["loss_removal"],
            }
            for r in out["experiments"]
        ],
        "generation": expset,
    }


def main() -> None:
    p = argparse.ArgumentParser(description="CORE_STRATEGY_V1 intel generation-3 (offline)")
    p.add_argument("--days", type=int, default=10)
    p.add_argument("--folds", type=int, default=2)
    args = p.parse_args()
    ensure_intel_dirs()
    cfg = research_cfg()
    cfg["lookback_days"] = int(args.days)
    df, source = _load_bars(cfg, no_mt5=False, lookback_days=int(args.days))
    if source != "mt5_bars":
        print(
            json.dumps(
                {
                    "error": "refusing to overwrite loss_db without MT5 bars",
                    "source": source,
                    "hint": "Keep MT5 open on the demo.",
                }
            ),
            file=sys.stderr,
        )
        sys.exit(2)

    vs_core = run_generation(
        df,
        persist=True,
        experiments=GEN3,
        generation="gen3",
        folds=int(args.folds),
    )
    # Incremental vs what is already live (rsi_ext), not vs naked CORE.
    live_like = [
        spec
        for spec in GEN3
        if spec["id"] in {"intel_wrong_extreme", "intel_quality_min_40", "intel_rsi_ext_wrong_extreme", "intel_rsi_ext_quality_40"}
    ]
    vs_live = run_generation(
        df,
        persist=False,
        experiments=live_like,
        generation="gen3_vs_rsi_ext",
        folds=int(args.folds),
        baseline_patch={"intel_enabled": True, "intel_skip_rsi_ext": True},
    )
    summary = _summary(
        vs_core, source=source, bars=int(len(df)), days=int(args.days), expset="gen3"
    )
    summary["vs_live_rsi_ext"] = {
        "baseline_oos_e": (vs_live["baseline"].get("oos") or {}).get("expectancy_r"),
        "baseline_pnl": vs_live["baseline"]["metrics"].get("net_pnl"),
        "challenger": vs_live["challenger"],
        "experiments": [
            {
                "id": r["id"],
                "decision": r["decision"],
                "reason": r["reason"],
                "oos_e": (r.get("candidate") or {}).get("oos", {}).get("expectancy_r"),
                "pnl": r["profit"],
                "n": r["number_of_trades"],
            }
            for r in vs_live["experiments"]
        ],
    }
    report = INTEL_DIR / "gen3_report.json"
    report.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(json.dumps(summary, indent=2, default=str))
    print(f"wrote {report}")


if __name__ == "__main__":
    main()
