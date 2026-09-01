#!/usr/bin/env python3
"""GEN21: unused skip on 30d leftovers vs five-flag live combo.

Do not re-queue hour-0 dead-ER sell or hour-5 stretch buy.
Both OOS E and full $ must strictly beat. Replay is not the gate.
Never mt5.shutdown(). YAML unchanged unless both gates pass.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any, Callable

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aegis.backtest import run_backtest
from aegis.intel.frozen_v1 import research_cfg
from aegis.intel.lossdb import trade_record
from aegis.intel.paths import INTEL_DIR, ensure_intel_dirs
from aegis.intel.runner import loss_removal
from aegis.optimizer.cycle import _load_bars
from aegis.optimizer.walk_forward import chronological_split, summarize_result

LIVE = {
    "intel_enabled": True,
    "intel_skip_rsi_ext": True,
    "intel_skip_doji_against": True,
    "intel_skip_stretched_doji_buy": True,
    "intel_skip_barbwire_sell": True,
    "intel_skip_late_buy_chase": True,
}

POISON_PREFIX = "2026-08-06 19:20"
TRAP_PREFIX = "2026-08-06 09:48"


def _num(rec: dict[str, Any], key: str) -> float | None:
    try:
        v = (rec.get("features") or {}).get(key)
        if v is None:
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _flag(rec: dict[str, Any], key: str) -> bool:
    v = (rec.get("features") or {}).get(key)
    try:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return False
    except (TypeError, ValueError):
        return False
    return bool(v)


def _is_sl(rec: dict[str, Any]) -> bool:
    return str(rec.get("outcome") or "") == "sl"


def _is_poison(rec: dict[str, Any]) -> bool:
    ts = str(rec.get("entry_time") or "")
    return rec.get("side") == "sell" and POISON_PREFIX in ts


def _is_trap(rec: dict[str, Any]) -> bool:
    ts = str(rec.get("entry_time") or "")
    return rec.get("side") == "buy" and TRAP_PREFIX in ts


def _is_eof(rec: dict[str, Any]) -> bool:
    return str(rec.get("outcome") or "") == "eof"


def _blocked(rec: dict[str, Any]) -> bool:
    return _is_poison(rec) or _is_trap(rec) or _is_eof(rec)


def _hour(rec: dict[str, Any]) -> int | None:
    try:
        return int((rec.get("features") or {}).get("hour_utc"))
    except (TypeError, ValueError):
        return None


def _rejected_rename_reason(rec: dict[str, Any]) -> str | None:
    """Leftovers already covered by a rejected skip. Do not re-queue under a new name."""
    side = rec.get("side")
    hour = _hour(rec)
    loc = _num(rec, "range_loc")
    ema = _num(rec, "close_ema_pips")
    er = _num(rec, "kaufman_er")
    rsi = _num(rec, "rsi")
    adx = _num(rec, "adx")
    ret3 = _num(rec, "ret3_pips")
    doji = _flag(rec, "volman_doji")
    barb = _flag(rec, "brooks_barbwire")
    impulse_green = _flag(rec, "impulse_green")
    in_range = _flag(rec, "brooks_in_range")

    if side == "buy" and hour == 5 and loc is not None and ema is not None and 0.80 <= loc <= 1.0 and ema >= 2.0:
        return "asia_hour_5_stretch_buy"
    if side == "sell" and hour == 0 and er is not None and er < 0.10:
        return "hour_0_dead_er_sell"
    if side == "buy" and loc is not None and loc > 1.0:
        return "above_range_buy"
    if side == "buy" and barb:
        return "barbwire_buy"
    if side == "sell" and ema is not None and ema <= -3.0:
        return "stretched_sell"
    if side == "sell" and loc is not None and loc < 0.0:
        return "below_range_sell"
    if doji and in_range and (er is None or er < 0.20):
        return "chop_doji"
    if side == "sell" and hour == 19:
        return "ny_hour_19_sell"
    if side == "sell" and loc is not None and er is not None and loc <= 0.15 and er >= 0.40:
        return "floor_run_sell"
    if side == "sell" and ret3 is not None and ret3 <= -1.8:
        return "ret3_chase_sell"
    if side == "sell" and hour == 12:
        return "london_hour_12_sell"
    if side == "sell" and hour == 4:
        return "asia_hour_4_sell"
    if side == "sell" and hour == 21:
        return "hour_21_sell"
    if side == "buy" and hour == 9 and impulse_green and ret3 is not None and ret3 >= 1.0:
        return "london_open_chase_buy"
    if side == "buy" and adx is not None and ema is not None and adx >= 35.0 and ema >= 1.2:
        return "strong_adx_stretch_buy"
    if side == "buy" and doji and loc is not None and loc >= 0.90:
        return "ceiling_doji_buy"
    if side == "buy" and rsi is not None and loc is not None and 65.0 <= rsi < 70.0 and loc < 0.85:
        return "late_buy_chase_widen"
    return None


def _ceiling_stretch_buy(rec: dict[str, Any]) -> bool:
    if rec.get("side") != "buy":
        return False
    loc = _num(rec, "range_loc")
    ema = _num(rec, "close_ema_pips")
    return loc is not None and ema is not None and 0.90 <= loc <= 1.0 and ema >= 2.0


def _hour_13_dead_er_buy(rec: dict[str, Any]) -> bool:
    if rec.get("side") != "buy":
        return False
    hour = _hour(rec)
    er = _num(rec, "kaufman_er")
    return hour == 13 and er is not None and er < 0.10


def _ny_hour_18_stretch_buy(rec: dict[str, Any]) -> bool:
    if rec.get("side") != "buy":
        return False
    hour = _hour(rec)
    ema = _num(rec, "close_ema_pips")
    return hour == 18 and ema is not None and ema >= 2.5


SKIP_IDEAS: list[dict[str, Any]] = [
    {
        "id": "intel_ceiling_stretch_buy",
        "kind": "book",
        "weakness": "chase",
        "pred": _ceiling_stretch_buy,
        "patch": {**LIVE, "intel_skip_ceiling_stretch_buy": True},
        "hypothesis": (
            "Skip BUY at 0.90<=loc<=1.0 with EMA stretch >=2.0 pips. Hits Jul 23 15:14 "
            "ceiling chase (RSI 62, not doji). Not ceiling-doji-buy, not late_buy RSI 65–70, "
            "not loc>1 hydra, not hour-5 stretch."
        ),
    },
    {
        "id": "intel_hour_13_dead_er_buy",
        "kind": "book",
        "weakness": "chop",
        "pred": _hour_13_dead_er_buy,
        "patch": {**LIVE, "intel_skip_hour_13_dead_er_buy": True},
        "hypothesis": (
            "Skip BUY at UTC hour 13 when Kaufman ER<0.10. Hits Jul 27 13:44 dead-tape "
            "London afternoon. Not hour-0 sell, not london_dead_er 7/8/11/12, not hour-5."
        ),
    },
    {
        "id": "intel_ny_hour_18_stretch_buy",
        "kind": "book",
        "weakness": "chase",
        "pred": _ny_hour_18_stretch_buy,
        "patch": {**LIVE, "intel_skip_ny_hour_18_stretch_buy": True},
        "hypothesis": (
            "Skip BUY at UTC hour 18 when EMA stretch >=2.5 pips. Not strong_adx (no ADX "
            "floor), not hour-19 sell. Only path-test if it hits a leftover that is not a "
            "strong_adx rejected-rename."
        ),
    },
]


def _records(res, cfg) -> list[dict[str, Any]]:
    out = []
    if res.trades is None or res.trades.empty:
        return out
    for rec in res.trades.to_dict("records"):
        snap = rec.get("intel_snap")
        row = pd.Series(snap) if isinstance(snap, dict) else None
        out.append(trade_record(rec, row, cfg))
    return out


def _dump_loss(r: dict[str, Any]) -> dict[str, Any]:
    f = dict(r.get("features") or {})
    return {
        "entry_time": str(r.get("entry_time")),
        "exit_time": str(r.get("exit_time")),
        "side": r.get("side"),
        "outcome": r.get("outcome"),
        "pnl": r.get("pnl"),
        "mfe": r.get("mfe"),
        "bars_held": r.get("bars_held"),
        "quality": r.get("quality"),
        "poison": _is_poison(r),
        "hydra_trap": _is_trap(r),
        "eof": _is_eof(r),
        "rejected_rename": _rejected_rename_reason(r),
        "features": f,
        "hits": {idea["id"]: bool(idea["pred"](r)) for idea in SKIP_IDEAS},
    }


def _scan(losses: list[dict[str, Any]], wins: list[dict[str, Any]], pred: Callable) -> dict[str, int]:
    sl = [r for r in losses if _is_sl(r)]
    allowed = [r for r in sl if not _blocked(r)]
    new_sl = [r for r in allowed if _rejected_rename_reason(r) is None]
    return {
        "loss_hits": sum(1 for r in losses if pred(r)),
        "sl_hits": sum(1 for r in sl if pred(r)),
        "allowed_sl_hits": sum(1 for r in allowed if pred(r)),
        "new_sl_hits": sum(1 for r in new_sl if pred(r)),
        "poison_hits": sum(1 for r in sl if pred(r) and _is_poison(r)),
        "trap_hits": sum(1 for r in sl if pred(r) and _is_trap(r)),
        "win_hits": sum(1 for r in wins if pred(r)),
    }


def _pick_idea(scans: dict[str, dict[str, int]]) -> dict[str, Any] | None:
    ranked = []
    for idea in SKIP_IDEAS:
        sc = scans[idea["id"]]
        if sc["new_sl_hits"] < 1:
            continue
        if sc["poison_hits"] or sc["trap_hits"]:
            continue
        ranked.append((sc["win_hits"], -sc["new_sl_hits"], idea))
    if not ranked:
        return None
    ranked.sort(key=lambda x: (x[0], x[1]))
    return ranked[0][2]


def main() -> None:
    ensure_intel_dirs()
    cfg0 = research_cfg()
    print("load_bars 30d readonly vs five-flag live combo", flush=True)
    df, source = _load_bars(cfg0, no_mt5=False, lookback_days=30)
    print(
        f"source={source} bars={len(df)} tmin={df['time'].iloc[0]} tmax={df['time'].iloc[-1]}",
        flush=True,
    )
    if source != "mt5_bars":
        print(json.dumps({"error": "not mt5_bars", "source": source}), file=sys.stderr)
        sys.exit(2)

    live_cfg = copy.deepcopy(cfg0)
    live_cfg.update(LIVE)
    print("live five-flag full backtest", flush=True)
    live_full = run_backtest(df, live_cfg)
    recs = _records(live_full, live_cfg)
    losses = [r for r in recs if not r.get("win")]
    wins = [r for r in recs if r.get("win")]
    remaining = [_dump_loss(r) for r in losses]
    allowed_sl = [r for r in losses if _is_sl(r) and not _blocked(r)]
    new_sl = [r for r in allowed_sl if _rejected_rename_reason(r) is None]
    scans = {idea["id"]: _scan(losses, wins, idea["pred"]) for idea in SKIP_IDEAS}
    print(
        json.dumps(
            {
                "n_loss": len(losses),
                "n_win": len(wins),
                "n_allowed_sl": len(allowed_sl),
                "n_new_sl": len(new_sl),
                "scans": scans,
            },
            default=str,
        ),
        flush=True,
    )

    idea = _pick_idea(scans) if new_sl else None
    path = "five_flag_unused_skip" if idea is not None else "none"
    verdict = None
    if idea is None:
        verdict = "skip_exhausted_this_sequence"
        print("skip_exhausted_this_sequence", flush=True)

    experiments: list[dict[str, Any]] = []
    promote_id = None
    live_oos = None
    live_pnl = None
    live_n = None
    live_wr = None
    live_e = None
    picked = None
    out_path = INTEL_DIR / "gen21_report.json"
    dump_preview = {
        "generation": "gen21",
        "bars": int(len(df)),
        "lookback_days": 30,
        "n_loss": len(losses),
        "n_win": len(wins),
        "n_allowed_sl": len(allowed_sl),
        "n_new_sl": len(new_sl),
        "scans": scans,
        "remaining_losers": remaining,
        "status": "dump_done",
    }
    out_path.write_text(json.dumps(dump_preview, indent=2, default=str), encoding="utf-8")
    print(f"wrote dump preview {out_path}", flush=True)

    if idea is not None:
        picked = idea["id"]
        print(
            f"path-test {picked} replay={scans[picked]} (replay is not the gate)",
            flush=True,
        )
        _, oos_df = chronological_split(df, 0.7)
        print(f"baseline OOS bars={len(oos_df)}", flush=True)
        base_oos = summarize_result(run_backtest(oos_df, live_cfg))
        print(f"baseline OOS E={base_oos.get('expectancy_r')} n={base_oos.get('total_trades')}", flush=True)
        cand_cfg = copy.deepcopy(live_cfg)
        cand_cfg.update(idea["patch"])
        print("candidate full backtest", flush=True)
        cand_full = summarize_result(run_backtest(df, cand_cfg))
        print(
            f"candidate full $={cand_full.get('net_pnl')} E={cand_full.get('expectancy_r')} n={cand_full.get('total_trades')}",
            flush=True,
        )
        print("candidate OOS backtest", flush=True)
        cand_oos = summarize_result(run_backtest(oos_df, cand_cfg))
        print(f"candidate OOS E={cand_oos.get('expectancy_r')} n={cand_oos.get('total_trades')}", flush=True)

        live_oos = float(base_oos.get("expectancy_r") or 0)
        live_pnl = float(live_full.net_pnl or 0)
        live_n = int(live_full.total_trades)
        live_wr = float(live_full.win_rate)
        live_e = float(live_full.expectancy_r)
        cand_oos_e = float(cand_oos.get("expectancy_r") or 0)
        cand_pnl = float(cand_full.get("net_pnl") or 0)
        oos_n = int(cand_oos.get("total_trades") or 0)
        accept = cand_oos_e > live_oos and oos_n >= 8 and cand_pnl > live_pnl
        row = {
            "id": idea["id"],
            "decision": "accept" if accept else "reject",
            "reason": (
                f"OOS E {cand_oos_e:.4f} vs baseline {live_oos:.4f}, n={oos_n}, "
                f"full pnl {cand_pnl:.2f} vs {live_pnl:.2f}"
            ),
            "oos_e": cand_oos_e,
            "oos_n": oos_n,
            "pnl": cand_pnl,
            "n": cand_full.get("total_trades"),
            "wr": cand_full.get("win_rate"),
            "full_e": cand_full.get("expectancy_r"),
            "loss_removal": loss_removal(
                {
                    "total_trades": live_n,
                    "win_rate": live_wr,
                    "wins": len(wins),
                    "losses": len(losses),
                },
                cand_full,
            ),
            "beats_live_oos_e": cand_oos_e > live_oos,
            "beats_live_full_usd": cand_pnl > live_pnl,
            "winner_sacrifice_replay": scans.get(picked),
            "path": path,
            "hypothesis": idea["hypothesis"],
        }
        row["promote"] = bool(
            row["decision"] == "accept" and row["beats_live_oos_e"] and row["beats_live_full_usd"]
        )
        experiments.append(row)
        if row["promote"]:
            promote_id = row["id"]
            verdict = "promoted"
        else:
            verdict = "rejected"

    summary = {
        "source": source,
        "bars": int(len(df)),
        "lookback_days": 30,
        "generation": "gen21",
        "verdict": verdict,
        "path": path,
        "gate": "Promote only if OOS E AND full $ both STRICTLY beat the five-flag live combo. Tie = reject. Do not target poison 19:20 or hydra-trap 09:48. Do not re-queue hour-0 dead-ER sell or hour-5 stretch buy. Replay is not the gate. Small-n. Not 100% WR.",
        "poison": "2026-08-06 19:20 sell",
        "hydra_trap": "2026-08-06 09:48 buy",
        "live_combo": {
            "flags": [
                "intel_skip_rsi_ext",
                "intel_skip_doji_against",
                "intel_skip_stretched_doji_buy",
                "intel_skip_barbwire_sell",
                "intel_skip_late_buy_chase",
            ],
            "oos_e": live_oos,
            "pnl": live_pnl,
            "full_e": live_e,
            "n": live_n if live_n is not None else (len(losses) + len(wins)),
            "wr": live_wr,
            "n_loss": len(losses),
            "n_win": len(wins),
            "n_allowed_sl": len(allowed_sl),
            "n_new_sl": len(new_sl),
        },
        "remaining_losers": remaining,
        "winner_sacrifice_replay": scans,
        "picked": picked,
        "experiments": experiments,
        "promote": promote_id,
        "live_yaml_unchanged_unless_promote": promote_id is None,
        "paper_restart": False,
        "not_a_100_wr_claim": True,
        "skip_exhausted_is_not_100_wr": True,
    }
    out_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(
        json.dumps(
            {
                "verdict": verdict,
                "path": path,
                "picked": picked,
                "promote": promote_id,
                "live_combo": summary["live_combo"],
                "experiments": experiments,
                "scans": scans,
            },
            indent=2,
            default=str,
        ),
        flush=True,
    )
    print(f"wrote {out_path}", flush=True)


if __name__ == "__main__":
    main()
