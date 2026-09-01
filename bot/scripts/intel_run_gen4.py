#!/usr/bin/env python3
"""GEN4: weak-ADX range-edge around CORE_STRATEGY_V1.

Path-dependent OOS vs CORE 1/30 after costs. Never mt5.shutdown().
Does not edit live YAML. 100% WR is a target, not a claim.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aegis.intel.frozen_v1 import research_cfg
from aegis.intel.paths import INTEL_DIR, ensure_intel_dirs
from aegis.intel.runner import GEN4, run_generation
from aegis.optimizer.cycle import _load_bars


def main() -> None:
    ensure_intel_dirs()
    print("research_cfg", flush=True)
    cfg = research_cfg()
    print("load_bars 8d readonly", flush=True)
    df, source = _load_bars(cfg, no_mt5=False, lookback_days=8)
    print(f"source={source} bars={len(df)}", flush=True)
    if source != "mt5_bars":
        print(json.dumps({"error": "not mt5_bars", "source": source}), file=sys.stderr)
        sys.exit(2)
    print("run_generation GEN4 folds=0 (split OOS; WFA after if accepted)", flush=True)
    out = run_generation(
        df, persist=True, experiments=GEN4, generation="gen4", folds=0
    )
    summary = {
        "source": source,
        "bars": int(len(df)),
        "generation": "gen4",
        "gate": "path-dependent OOS E after costs vs CORE 1/30 (not WR, not TP3 stored best)",
        "champion": out["baseline"]["id"],
        "baseline_oos_e": (out["baseline"].get("oos") or {}).get("expectancy_r"),
        "baseline_pnl": out["baseline"]["metrics"].get("net_pnl"),
        "baseline_wr": out["baseline"]["metrics"].get("win_rate"),
        "pattern": out.get("pattern"),
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
                "oos_n": (r.get("candidate") or {}).get("oos", {}).get("total_trades"),
            }
            for r in out["experiments"]
        ],
        "not_a_100_wr_claim": True,
    }
    path = INTEL_DIR / "gen4_report.json"
    path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(json.dumps(summary, indent=2, default=str), flush=True)
    print(f"wrote {path}", flush=True)


if __name__ == "__main__":
    main()
