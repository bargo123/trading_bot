#!/usr/bin/env python3
"""GEN8: doji AND body-against CORE spray (tighter than require-body).

If that is a no-op, try ceiling-doji buys (loc>=0.90), not full wrong_edge.
Promote only if OOS E AND full $ beat rsi_ext-only. Never mt5.shutdown().
Not a 100% WR claim. Does not edit live YAML.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aegis.backtest import run_backtest
from aegis.intel.frozen_v1 import research_cfg
from aegis.intel.lossdb import trade_record
from aegis.intel.paths import INTEL_DIR, ensure_intel_dirs
from aegis.intel.runner import run_generation
from aegis.optimizer.cycle import _load_bars


def _against(rec: dict[str, Any]) -> bool:
    f = rec.get("features") or {}
    o, c = f.get("open"), f.get("close")
    if o is None or c is None:
        return False
    side = rec.get("side")
    if side == "buy":
        return float(c) < float(o)
    if side == "sell":
        return float(c) > float(o)
    return False


def _doji_against(rec: dict[str, Any]) -> bool:
    return bool((rec.get("features") or {}).get("volman_doji")) and _against(rec)


def _ceiling_doji_buy(rec: dict[str, Any]) -> bool:
    if rec.get("side") != "buy":
        return False
    f = rec.get("features") or {}
    if not f.get("volman_doji"):
        return False
    try:
        return float(f.get("range_loc")) >= 0.90
    except (TypeError, ValueError):
        return False


def _records(res, cfg) -> list[dict[str, Any]]:
    out = []
    if res.trades is None or res.trades.empty:
        return out
    for rec in res.trades.to_dict("records"):
        snap = rec.get("intel_snap")
        row = pd.Series(snap) if isinstance(snap, dict) else None
        out.append(trade_record(rec, row, cfg))
    return out


def _exp_row(r: dict[str, Any]) -> dict[str, Any]:
    full = (r.get("candidate") or {}).get("full") or {}
    return {
        "id": r.get("id"),
        "decision": r.get("decision"),
        "reason": r.get("reason"),
        "oos_e": (r.get("candidate") or {}).get("oos", {}).get("expectancy_r"),
        "oos_n": (r.get("candidate") or {}).get("oos", {}).get("total_trades"),
        "pnl": r.get("profit"),
        "n": r.get("number_of_trades"),
        "wr": r.get("win_rate"),
        "full_e": full.get("expectancy_r"),
        "loss_removal": r.get("loss_removal"),
    }


def main() -> None:
    ensure_intel_dirs()
    print("load_bars 8d readonly", flush=True)
    cfg0 = research_cfg()
    df, source = _load_bars(cfg0, no_mt5=False, lookback_days=8)
    print(f"source={source} bars={len(df)}", flush=True)
    if source != "mt5_bars":
        print(json.dumps({"error": "not mt5_bars", "source": source}), file=sys.stderr)
        sys.exit(2)

    rsi_cfg = copy.deepcopy(cfg0)
    rsi_cfg.update({"intel_enabled": True, "intel_skip_rsi_ext": True})
    print("rsi_ext full backtest", flush=True)
    rsi_full = run_backtest(df, rsi_cfg)
    recs = _records(rsi_full, rsi_cfg)
    losses = [r for r in recs if not r.get("win")]
    wins = [r for r in recs if r.get("win")]
    remaining = []
    for r in losses:
        f = r.get("features") or {}
        remaining.append(
            {
                "entry_time": str(r.get("entry_time")),
                "side": r.get("side"),
                "outcome": r.get("outcome"),
                "pnl": r.get("pnl"),
                "mfe": r.get("mfe"),
                "rsi": f.get("rsi"),
                "range_loc": f.get("range_loc"),
                "kaufman_er": f.get("kaufman_er"),
                "volman_doji": f.get("volman_doji"),
                "body_against": _against(r),
                "doji_against": _doji_against(r),
                "ceiling_doji_buy": _ceiling_doji_buy(r),
            }
        )
    scan = {
        "doji_against": {
            "loss_hits": sum(_doji_against(r) for r in losses),
            "win_hits": sum(_doji_against(r) for r in wins),
            "note": "Replay on rsi_ext fills. Path-dependent can free bars and mint new trades.",
        },
        "ceiling_doji_buy": {
            "loss_hits": sum(_ceiling_doji_buy(r) for r in losses),
            "win_hits": sum(_ceiling_doji_buy(r) for r in wins),
            "note": "Buy loc>=0.90 AND doji. GEN7 leftover #2 loc was ~0.897 so this may miss it.",
        },
    }
    print(json.dumps({"n_loss": len(losses), "n_win": len(wins), "scan": scan}), flush=True)

    specs = [
        {
            "id": "intel_doji_against",
            "kind": "book",
            "weakness": "chop",
            "patch": {
                "intel_enabled": True,
                "intel_skip_rsi_ext": True,
                "intel_skip_doji_against": True,
            },
            "hypothesis": "Volman doji AND body against CORE EMA-side. Tighter than require-body.",
        }
    ]
    first_noop = scan["doji_against"]["loss_hits"] == 0
    if first_noop:
        specs.append(
            {
                "id": "intel_ceiling_doji_buy",
                "kind": "book",
                "weakness": "false_breakout",
                "patch": {
                    "intel_enabled": True,
                    "intel_skip_rsi_ext": True,
                    "intel_skip_ceiling_doji_buy": True,
                },
                "hypothesis": "Skip BUY only when doji and loc>=0.90. Not full wrong_edge.",
            }
        )

    print(f"run_generation vs rsi_ext n={len(specs)}", flush=True)
    out = run_generation(
        df,
        persist=False,
        experiments=specs,
        generation="gen8",
        folds=0,
        baseline_patch={"intel_enabled": True, "intel_skip_rsi_ext": True},
    )
    rsi_oos = float((out["baseline"].get("oos") or {}).get("expectancy_r") or 0)
    rsi_pnl = float(out["baseline"]["metrics"].get("net_pnl") or 0)
    experiments = []
    promote_id = None
    for r in out["experiments"]:
        row = _exp_row(r)
        cand_oos = float(row["oos_e"] or 0)
        cand_pnl = float(row["pnl"] or 0)
        row["beats_rsi_oos_e"] = cand_oos > rsi_oos
        row["beats_rsi_full_usd"] = cand_pnl > rsi_pnl
        row["promote"] = bool(
            r.get("decision") == "accept" and cand_oos > rsi_oos and cand_pnl > rsi_pnl
        )
        experiments.append(row)
        if row["promote"] and promote_id is None:
            promote_id = row["id"]

    summary = {
        "source": source,
        "bars": int(len(df)),
        "generation": "gen8",
        "gate": "Promote only if OOS E AND full $ both beat rsi_ext-only. Small-n: 4 remaining losses. Not 100% WR.",
        "rsi_ext": {
            "oos_e": rsi_oos,
            "pnl": rsi_pnl,
            "n": out["baseline"]["metrics"].get("total_trades"),
            "wr": out["baseline"]["metrics"].get("win_rate"),
        },
        "winner_sacrifice_replay": scan,
        "n_rsi_ext_losses": len(losses),
        "n_rsi_ext_wins": len(wins),
        "remaining_rsi_ext_losers": remaining,
        "doji_against_noop": first_noop,
        "experiments": experiments,
        "promote": promote_id,
        "live_yaml": "intel_skip_rsi_ext only" if not promote_id else promote_id,
        "not_a_100_wr_claim": True,
    }
    path = INTEL_DIR / "gen8_report.json"
    path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(json.dumps(summary, indent=2, default=str), flush=True)
    print(f"wrote {path}", flush=True)


if __name__ == "__main__":
    main()
