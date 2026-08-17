#!/usr/bin/env python3
"""Generation-2 intel around CORE_STRATEGY_V1.

Loads MT5 M1 bars read-only (no shutdown). Does not edit live YAML.
Does not place orders. 100% WR is a target, not a claim.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aegis.intel.paths import INTEL_DIR, ensure_intel_dirs
from aegis.intel.runner import GEN2, GEN2B, run_generation
from aegis.optimizer.cycle import _load_bars
from aegis.intel.frozen_v1 import research_cfg


def main() -> None:
    p = argparse.ArgumentParser(description="CORE_STRATEGY_V1 intel generation-2 (offline)")
    p.add_argument("--days", type=int, default=10)
    p.add_argument("--folds", type=int, default=2)
    p.add_argument("--no-mt5", action="store_true")
    p.add_argument("--synthetic-bars", type=int, default=2500)
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--set", dest="expset", choices=("gen2", "gen2b"), default="gen2")
    args = p.parse_args()
    ensure_intel_dirs()
    cfg = research_cfg()
    cfg["lookback_days"] = int(args.days)
    source = "synthetic"
    if args.no_mt5:
        from aegis.optimizer.walk_forward import synthetic_ohlcv

        df = synthetic_ohlcv(n=max(400, int(args.synthetic_bars)), seed=int(args.seed))
    else:
        df, source = _load_bars(cfg, no_mt5=False, lookback_days=int(args.days))
        if source != "mt5_bars":
            print(
                json.dumps(
                    {
                        "error": "refusing to overwrite loss_db without MT5 bars",
                        "source": source,
                        "hint": "Keep MT5 open on the demo, or pass --no-mt5 for synthetic only.",
                    }
                ),
                file=sys.stderr,
            )
            sys.exit(2)
    specs = GEN2B if args.expset == "gen2b" else GEN2
    out = run_generation(
        df,
        persist=True,
        experiments=specs,
        generation=args.expset,
        folds=int(args.folds),
    )
    summary = {
        "source": source,
        "bars": int(len(df)),
        "days": int(args.days),
        "champion": out["baseline"]["id"],
        "baseline_trades": out["baseline"]["metrics"].get("total_trades"),
        "baseline_wr": out["baseline"]["metrics"].get("win_rate"),
        "baseline_e": out["baseline"]["metrics"].get("expectancy_r"),
        "baseline_pnl": out["baseline"]["metrics"].get("net_pnl"),
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
                "loss_removal": r["loss_removal"],
            }
            for r in out["experiments"]
        ],
    }
    report = INTEL_DIR / f"{args.expset}_report.json"
    report.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(json.dumps(summary, indent=2, default=str))
    print(f"wrote {report}")


if __name__ == "__main__":
    main()
