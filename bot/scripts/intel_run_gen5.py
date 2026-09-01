#!/usr/bin/env python3
"""GEN5: skip incomplete warmup + Volman extreme doji around live rsi_ext.

Path-dependent OOS vs rsi_ext (not CORE spray, not TP3 stored best).
Promote only if OOS E AND full $ both beat rsi_ext-only.
Never mt5.shutdown(). Does not edit live YAML. Not a 100% WR claim.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aegis.intel.frozen_v1 import research_cfg
from aegis.intel.paths import INTEL_DIR, ensure_intel_dirs
from aegis.intel.runner import GEN5, run_generation
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
    print("run_generation GEN5 vs rsi_ext baseline folds=0", flush=True)
    out = run_generation(
        df,
        persist=False,
        experiments=GEN5,
        generation="gen5",
        folds=0,
        baseline_patch={"intel_enabled": True, "intel_skip_rsi_ext": True},
    )
    rsi = out["baseline"]
    summary = {
        "source": source,
        "bars": int(len(df)),
        "generation": "gen5",
        "gate": (
            "path-dependent OOS E after costs AND full $ vs live rsi_ext-only. "
            "Not WR. Not TP3 stored best. Not CORE-naked."
        ),
        "baseline_id": "intel_skip_rsi_ext",
        "baseline_oos_e": (rsi.get("oos") or {}).get("expectancy_r"),
        "baseline_pnl": rsi["metrics"].get("net_pnl"),
        "baseline_wr": rsi["metrics"].get("win_rate"),
        "baseline_n": rsi["metrics"].get("total_trades"),
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
    path = INTEL_DIR / "gen5_report.json"
    path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(json.dumps(summary, indent=2, default=str), flush=True)
    print(f"wrote {path}", flush=True)


if __name__ == "__main__":
    main()
