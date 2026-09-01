#!/usr/bin/env python3
"""GEN20: unused skip on 30d leftovers vs five-flag live combo.

Prefer hour-0 dead-ER sell if dump still hits it. Do not re-queue hour-5 stretch buy.
Tie on OOS E or full $ is not a promote. Replay is not the gate. Never mt5.shutdown().
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
EOF_PREFIX = "2026-08-14 19:39"


def _num(rec: dict[str, Any], key: str) -> float | None:
    try:
        v = (rec.get("features") or {}).get(key)
        if v is None:
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _is_sl(rec: dict[str, Any]) -> bool:
    return str(rec.get("outcome") or "") == "sl"


def _is_poison(rec: dict[str, Any]) -> bool:
    ts = str(rec.get("entry_time") or "")
    return rec.get("side") == "sell" and POISON_PREFIX in ts


def _is_trap(rec: dict[str, Any]) -> bool:
    ts = str(rec.get("entry_time") or "")
    return rec.get("side") == "buy" and TRAP_PREFIX in ts


def _is_eof_trio(rec: dict[str, Any]) -> bool:
    ts = str(rec.get("entry_time") or "")
    return str(rec.get("outcome") or "") == "eof" and EOF_PREFIX in ts


def _blocked(rec: dict[str, Any]) -> bool:
    return _is_poison(rec) or _is_trap(rec) or _is_eof_trio(rec)


def _hour(rec: dict[str, Any]) -> int | None:
    try:
        return int((rec.get("features") or {}).get("hour_utc"))
    except (TypeError, ValueError):
        return None


def _hour_0_dead_er_sell(rec: dict[str, Any]) -> bool:
    if rec.get("side") != "sell":
        return False
    hour = _hour(rec)
    er = _num(rec, "kaufman_er")
    return hour == 0 and er is not None and er < 0.10


SKIP_IDEAS: list[dict[str, Any]] = [
    {
        "id": "intel_hour_0_dead_er_sell",
        "kind": "book",
        "weakness": "chop",
        "pred": _hour_0_dead_er_sell,
        "patch": {**LIVE, "intel_skip_hour_0_dead_er_sell": True},
        "hypothesis": (
            "Skip SELL at UTC hour 0 when Kaufman ER<0.10. Hits Jul 9 00:55 dead-tape "
            "Asia midnight. Not hour-4/21, not london_dead_er 7/8/11/12, not hour-5 stretch buy."
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
        "eof_trio": _is_eof_trio(r),
        "features": f,
        "hits": {idea["id"]: bool(idea["pred"](r)) for idea in SKIP_IDEAS},
    }


def _scan(losses: list[dict[str, Any]], wins: list[dict[str, Any]], pred: Callable) -> dict[str, int]:
    sl = [r for r in losses if _is_sl(r)]
    allowed = [r for r in sl if not _blocked(r)]
    return {
        "loss_hits": sum(1 for r in losses if pred(r)),
        "sl_hits": sum(1 for r in sl if pred(r)),
        "allowed_sl_hits": sum(1 for r in allowed if pred(r)),
        "poison_hits": sum(1 for r in sl if pred(r) and _is_poison(r)),
        "trap_hits": sum(1 for r in sl if pred(r) and _is_trap(r)),
        "win_hits": sum(1 for r in wins if pred(r)),
    }


def _pick_idea(scans: dict[str, dict[str, int]]) -> dict[str, Any] | None:
    ranked = []
    for idea in SKIP_IDEAS:
        sc = scans[idea["id"]]
        if sc["allowed_sl_hits"] < 1:
            continue
        if sc["poison_hits"] or sc["trap_hits"]:
            continue
        ranked.append((sc["win_hits"], -sc["allowed_sl_hits"], idea))
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
    scans = {idea["id"]: _scan(losses, wins, idea["pred"]) for idea in SKIP_IDEAS}
    print(
        json.dumps(
            {
                "n_loss": len(losses),
                "n_win": len(wins),
                "n_allowed_sl": len(allowed_sl),
                "scans": scans,
            },
            default=str,
        ),
        flush=True,
    )

    idea = _pick_idea(scans) if allowed_sl else None
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
    out_path = INTEL_DIR / "gen20_report.json"
    dump_preview = {
        "generation": "gen20",
        "bars": int(len(df)),
        "lookback_days": 30,
        "n_loss": len(losses),
        "n_win": len(wins),
        "n_allowed_sl": len(allowed_sl),
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

    summary = {
        "source": source,
        "bars": int(len(df)),
        "lookback_days": 30,
        "generation": "gen20",
        "verdict": verdict,
        "path": path,
        "gate": "Promote only if OOS E AND full $ both STRICTLY beat the five-flag live combo. Tie = reject. Do not target poison 19:20 or hydra-trap 09:48. Do not re-queue hour-5 stretch buy. Replay is not the gate. Small-n. Not 100% WR.",
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
