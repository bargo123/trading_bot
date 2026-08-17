#!/usr/bin/env python3
"""GEN7: remaining rsi_ext path-dependent losers, then one new skip.

Promote only if OOS E AND full $ beat rsi_ext-only. Never mt5.shutdown().
Does not edit live YAML. Not a 100% WR claim.
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
from aegis.optimizer.walk_forward import summarize_result


def _feat(rec: dict[str, Any], key: str):
    return (rec.get("features") or {}).get(key)


def _numf(rec: dict[str, Any], key: str) -> float | None:
    try:
        v = _feat(rec, key)
        if v is None:
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _loss_table(recs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for r in recs:
        f = r.get("features") or {}
        rows.append(
            {
                "side": r.get("side"),
                "outcome": r.get("outcome"),
                "pnl": r.get("pnl"),
                "mfe": r.get("mfe"),
                "mae": r.get("mae"),
                "bars_held": r.get("bars_held"),
                "entry_time": r.get("entry_time"),
                "rsi": f.get("rsi"),
                "adx": f.get("adx"),
                "kaufman_er": f.get("kaufman_er"),
                "range_loc": f.get("range_loc"),
                "volman_doji": f.get("volman_doji"),
                "brooks_in_range": f.get("brooks_in_range"),
                "ema_side_streak": f.get("ema_side_streak"),
                "close_ema_pips": f.get("close_ema_pips"),
                "ret3_pips": f.get("ret3_pips"),
                "hour_utc": f.get("hour_utc"),
                "body_with_side": (
                    (r.get("side") == "buy" and float(f.get("close") or 0) >= float(f.get("open") or 0))
                    or (r.get("side") == "sell" and float(f.get("close") or 0) <= float(f.get("open") or 0))
                    if f.get("open") is not None and f.get("close") is not None
                    else None
                ),
            }
        )
    return rows


def _pick_skip(losses: list[dict[str, Any]], wins: list[dict[str, Any]]) -> dict[str, Any]:
    """One new skip from remaining rsi_ext losers. Not a rejected id."""

    def late_buy_chase(r):
        if r.get("side") != "buy":
            return False
        rsi = _numf(r, "rsi")
        loc = _numf(r, "range_loc")
        ema = _numf(r, "close_ema_pips")
        if rsi is None or loc is None or ema is None:
            return False
        return rsi >= 65.0 and rsi < 70.0 and loc >= 0.85 and ema >= 1.5

    def require_body(r):
        f = r.get("features") or {}
        o, c = f.get("open"), f.get("close")
        if o is None or c is None:
            return False
        if r.get("side") == "buy":
            return float(c) < float(o)
        if r.get("side") == "sell":
            return float(c) > float(o)
        return False

    def london_open_chop(r):
        h = _feat(r, "hour_utc")
        er = _numf(r, "kaufman_er")
        try:
            hour = int(h)
        except (TypeError, ValueError):
            return False
        return hour in {7, 8, 11, 12} and er is not None and er < 0.10

    cands = [
        {
            "id": "intel_late_buy_chase",
            "pred": late_buy_chase,
            "patch": {
                "intel_enabled": True,
                "intel_skip_rsi_ext": True,
                "intel_skip_late_buy_chase": True,
            },
            "hypothesis": (
                "Skip BUY only when RSI 65–70, range_loc>=0.85, close>=1.5 pips above EMA20. "
                "Catches the ceiling leftover rsi_ext misses (68.5). Not wrong_edge, not ADX."
            ),
        },
        {
            "id": "intel_require_body",
            "pred": require_body,
            "patch": {
                "intel_enabled": True,
                "intel_skip_rsi_ext": True,
                "intel_require_body": True,
            },
            "hypothesis": "Volman: skip CORE when body is against the EMA-side spray.",
        },
        {
            "id": "intel_london_dead_er",
            "pred": london_open_chop,
            "patch": {
                "intel_enabled": True,
                "intel_skip_rsi_ext": True,
                "intel_skip_london_dead_er": True,
            },
            "hypothesis": "Skip when hour in {7,8,11,12} UTC and ER<0.10 (session chop, not global ER).",
        },
    ]
    scored = []
    for c in cands:
        l_hit = sum(1 for r in losses if c["pred"](r))
        w_hit = sum(1 for r in wins if c["pred"](r))
        scored.append({**c, "loss_hits": l_hit, "win_hits": w_hit, "pred": None})
        c["_loss_hits"] = l_hit
        c["_win_hits"] = w_hit
    # Prefer hits leftover losses with few winner hits.
    viable = [c for c in cands if c["_loss_hits"] >= 1]
    if not viable:
        return {
            "id": None,
            "reason": "no unused skip fired on remaining rsi_ext losers",
            "scored": [
                {"id": s["id"], "loss_hits": s["_loss_hits"], "win_hits": s["_win_hits"]}
                for s in cands
            ],
        }
    viable.sort(key=lambda c: (-c["_loss_hits"], c["_win_hits"]))
    best = viable[0]
    return {
        "id": best["id"],
        "patch": best["patch"],
        "hypothesis": best["hypothesis"],
        "loss_hits": best["_loss_hits"],
        "win_hits": best["_win_hits"],
        "scored": [
            {"id": s["id"], "loss_hits": s["_loss_hits"], "win_hits": s["_win_hits"]}
            for s in cands
        ],
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
    recs = []
    for rec in rsi_full.trades.to_dict("records"):
        snap = rec.get("intel_snap")
        row = pd.Series(snap) if isinstance(snap, dict) else None
        recs.append(trade_record(rec, row, rsi_cfg))
    losses = [r for r in recs if not r.get("win")]
    wins = [r for r in recs if r.get("win")]
    table = _loss_table(losses)
    pick = _pick_skip(losses, wins)
    print(json.dumps({"n_win": len(wins), "n_loss": len(losses), "pick": {k: pick[k] for k in pick if k != "patch"}}, default=str), flush=True)

    experiments = []
    if pick.get("id") and pick.get("patch"):
        experiments = [
            {
                "id": pick["id"],
                "kind": "INVENTED_ALGORITHM",
                "weakness": "late_entry",
                "patch": pick["patch"],
                "hypothesis": pick["hypothesis"],
            }
        ]
        print(f"run_generation vs rsi_ext: {pick['id']}", flush=True)
        out = run_generation(
            df,
            persist=False,
            experiments=experiments,
            generation="gen7",
            folds=0,
            baseline_patch={"intel_enabled": True, "intel_skip_rsi_ext": True},
        )
        exp = out["experiments"][0] if out["experiments"] else {}
        cand_oos = float((exp.get("candidate") or {}).get("oos", {}).get("expectancy_r") or 0)
        base_oos = float((out["baseline"].get("oos") or {}).get("expectancy_r") or 0)
        cand_pnl = float(exp.get("profit") or 0)
        base_pnl = float(out["baseline"]["metrics"].get("net_pnl") or 0)
        promote = bool(exp.get("decision") == "accept" and cand_oos > base_oos and cand_pnl > base_pnl)
        exp_sum = {
            "id": exp.get("id"),
            "decision": exp.get("decision"),
            "reason": exp.get("reason"),
            "oos_e": cand_oos,
            "pnl": cand_pnl,
            "n": exp.get("number_of_trades"),
            "oos_n": (exp.get("candidate") or {}).get("oos", {}).get("total_trades"),
        }
    else:
        promote = False
        base_oos = None
        base_pnl = float(summarize_result(rsi_full).get("net_pnl") or 0)
        exp_sum = None

    summary = {
        "source": source,
        "bars": int(len(df)),
        "generation": "gen7",
        "gate": "Promote only if OOS E AND full $ both beat rsi_ext-only. Path-dependent after costs.",
        "rsi_ext_full": summarize_result(rsi_full),
        "n_win": len(wins),
        "n_loss": len(losses),
        "remaining_losers": table,
        "candidate_scan": pick.get("scored"),
        "picked": {k: v for k, v in pick.items() if k != "scored"},
        "experiment": exp_sum,
        "baseline_oos_e": base_oos if experiments else None,
        "baseline_pnl": base_pnl if experiments else summarize_result(rsi_full).get("net_pnl"),
        "promote": promote,
        "live_yaml": "intel_skip_rsi_ext only" if not promote else pick.get("id"),
        "not_a_100_wr_claim": True,
    }
    path = INTEL_DIR / "gen7_report.json"
    path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(json.dumps(summary, indent=2, default=str), flush=True)
    print(f"wrote {path}", flush=True)


if __name__ == "__main__":
    main()
