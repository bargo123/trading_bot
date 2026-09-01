#!/usr/bin/env python3
"""Slim GEN3 path-dependent backtest. Prints each step. folds=0 (no WFA)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aegis.intel.frozen_v1 import research_cfg
from aegis.intel.paths import INTEL_DIR, ensure_intel_dirs
from aegis.intel.runner import GEN3, run_generation
from aegis.optimizer.cycle import _load_bars


def main() -> None:
    ensure_intel_dirs()
    print("research_cfg", flush=True)
    cfg = research_cfg()
    print("load_bars 8d", flush=True)
    df, source = _load_bars(cfg, no_mt5=False, lookback_days=8)
    print(f"source={source} bars={len(df)}", flush=True)
    if source != "mt5_bars":
        print(json.dumps({"error": "not mt5_bars", "source": source}), file=sys.stderr)
        sys.exit(2)
    specs = [s for s in GEN3 if s["id"] in {"intel_rsi_ext", "intel_wrong_extreme", "intel_rsi_ext_quality_40"}]
    print(f"run_generation n={len(specs)} folds=0", flush=True)
    out = run_generation(df, persist=True, experiments=specs, generation="gen3_slim", folds=0)
    summary = {
        "source": source,
        "bars": int(len(df)),
        "challenger": out["challenger"],
        "baseline_oos_e": (out["baseline"].get("oos") or {}).get("expectancy_r"),
        "baseline_pnl": out["baseline"]["metrics"].get("net_pnl"),
        "experiments": [
            {
                "id": r["id"],
                "decision": r["decision"],
                "reason": r["reason"],
                "oos_e": (r.get("candidate") or {}).get("oos", {}).get("expectancy_r"),
                "pnl": r["profit"],
                "n": r["number_of_trades"],
            }
            for r in out["experiments"]
        ],
    }
    path = INTEL_DIR / "gen3_slim.json"
    path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(json.dumps(summary, indent=2, default=str), flush=True)
    print(f"wrote {path}", flush=True)


if __name__ == "__main__":
    main()
