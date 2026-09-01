#!/usr/bin/env python3
"""GEN6: sell-only Kaufman floor-chop around live rsi_ext.

Path-dependent OOS vs CORE and vs rsi_ext. Promote only if OOS E AND full $
both beat rsi_ext-only. Never mt5.shutdown(). Not a 100% WR claim.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aegis.intel.frozen_v1 import research_cfg
from aegis.intel.paths import INTEL_DIR, ensure_intel_dirs
from aegis.intel.runner import GEN6, run_generation
from aegis.optimizer.cycle import _load_bars


def _row(r: dict) -> dict:
    return {
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


def main() -> None:
    ensure_intel_dirs()
    print("load_bars 8d readonly", flush=True)
    cfg = research_cfg()
    df, source = _load_bars(cfg, no_mt5=False, lookback_days=8)
    print(f"source={source} bars={len(df)}", flush=True)
    if source != "mt5_bars":
        print(json.dumps({"error": "not mt5_bars", "source": source}), file=sys.stderr)
        sys.exit(2)
    print("GEN6 vs CORE then vs rsi_ext, folds=0", flush=True)
    vs_core = run_generation(
        df, persist=False, experiments=GEN6, generation="gen6", folds=0
    )
    vs_rsi = run_generation(
        df,
        persist=False,
        experiments=[s for s in GEN6 if s["id"] == "intel_rsi_ext_floor_chop"],
        generation="gen6_vs_rsi",
        folds=0,
        baseline_patch={"intel_enabled": True, "intel_skip_rsi_ext": True},
    )
    rsi_row = next(r for r in vs_core["experiments"] if r["id"] == "intel_rsi_ext")
    chop_row = next(r for r in vs_core["experiments"] if r["id"] == "intel_rsi_ext_floor_chop")
    rsi_oos = float((rsi_row.get("candidate") or {}).get("oos", {}).get("expectancy_r") or 0)
    chop_oos = float((chop_row.get("candidate") or {}).get("oos", {}).get("expectancy_r") or 0)
    rsi_pnl = float(rsi_row.get("profit") or 0)
    chop_pnl = float(chop_row.get("profit") or 0)
    vs_rsi_exp = vs_rsi["experiments"][0] if vs_rsi["experiments"] else {}
    promote = bool(
        chop_oos > rsi_oos and chop_pnl > rsi_pnl and vs_rsi_exp.get("decision") == "accept"
    )
    summary = {
        "source": source,
        "bars": int(len(df)),
        "generation": "gen6",
        "gate": (
            "Promote only if OOS E AND full $ both beat rsi_ext-only. "
            "Path-dependent after costs. Not WR. Not TP3 stored best."
        ),
        "core_oos_e": (vs_core["baseline"].get("oos") or {}).get("expectancy_r"),
        "core_pnl": vs_core["baseline"]["metrics"].get("net_pnl"),
        "rsi_ext": _row(rsi_row),
        "floor_chop": _row(chop_row),
        "vs_rsi_ext_accept_gate": {
            "decision": vs_rsi_exp.get("decision"),
            "reason": vs_rsi_exp.get("reason"),
            "oos_e": (vs_rsi_exp.get("candidate") or {}).get("oos", {}).get("expectancy_r"),
            "pnl": vs_rsi_exp.get("profit"),
        },
        "beats_rsi_ext_oos_e": chop_oos > rsi_oos,
        "beats_rsi_ext_full_usd": chop_pnl > rsi_pnl,
        "promote": promote,
        "not_a_100_wr_claim": True,
    }
    path = INTEL_DIR / "gen6_report.json"
    path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(json.dumps(summary, indent=2, default=str), flush=True)
    print(f"wrote {path}", flush=True)


if __name__ == "__main__":
    main()
