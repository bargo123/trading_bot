#!/usr/bin/env python3
"""GEN14: unused skip on a NON-poison leftover.

Poison: Aug 6 19:20 sell — do not target (stretched_sell / hour-19 / floor_run
all killed ~30 one-pip clips). skip-NaN and loc>1 buy already rejected.

London-open chase buy (hour 9 + impulse_green + ret3>=1) is not loc>1, not doji,
not EMA stretch. Path-dependent vs live combo. Replay is not the gate.
If nothing unused remains that isn't poison, verdict skip_exhausted_this_sequence.
Never mt5.shutdown(). Does not edit YAML. Not a 100% WR claim.
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
from aegis.intel.runner import run_generation
from aegis.optimizer.cycle import _load_bars

LIVE = {
    "intel_enabled": True,
    "intel_skip_rsi_ext": True,
    "intel_skip_doji_against": True,
    "intel_skip_stretched_doji_buy": True,
    "intel_skip_barbwire_sell": True,
}

POISON_PREFIX = "2026-08-06 19:20"


def _num(rec: dict[str, Any], key: str) -> float | None:
    try:
        v = (rec.get("features") or {}).get(key)
        if v is None:
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _flag(rec: dict[str, Any], key: str) -> bool:
    return bool((rec.get("features") or {}).get(key))


def _is_sl(rec: dict[str, Any]) -> bool:
    return str(rec.get("outcome") or "") == "sl"


def _is_poison(rec: dict[str, Any]) -> bool:
    ts = str(rec.get("entry_time") or "")
    return rec.get("side") == "sell" and POISON_PREFIX in ts


def _london_open_chase_buy(rec: dict[str, Any]) -> bool:
    if rec.get("side") != "buy":
        return False
    hour = (rec.get("features") or {}).get("hour_utc")
    ret3 = _num(rec, "ret3_pips")
    try:
        h = int(hour)
    except (TypeError, ValueError):
        return False
    return h == 9 and _flag(rec, "impulse_green") and ret3 is not None and ret3 >= 1.0


IDEA = {
    "id": "intel_london_open_chase_buy",
    "kind": "book",
    "weakness": "late_entry",
    "patch": {**LIVE, "intel_skip_london_open_chase_buy": True},
    "hypothesis": "Skip BUY at London hour 9 with impulse-green and ret3>=1. Not loc>1, not doji, not EMA stretch, not poison sell.",
}


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
    o, c = f.get("open"), f.get("close")
    body_against = None
    if o is not None and c is not None:
        if r.get("side") == "buy":
            body_against = float(c) < float(o)
        elif r.get("side") == "sell":
            body_against = float(c) > float(o)
    return {
        "entry_time": str(r.get("entry_time")),
        "exit_time": str(r.get("exit_time")),
        "side": r.get("side"),
        "outcome": r.get("outcome"),
        "pnl": r.get("pnl"),
        "mfe": r.get("mfe"),
        "bars_held": r.get("bars_held"),
        "quality": r.get("quality"),
        "body_against": body_against,
        "poison": _is_poison(r),
        "features": f,
        "hits": {"london_open_chase_buy": _london_open_chase_buy(r)},
    }


def _scan(rows: list[dict[str, Any]], pred: Callable) -> dict[str, int]:
    sl = [r for r in rows if _is_sl(r)]
    non_poison_sl = [r for r in sl if not _is_poison(r)]
    return {
        "loss_hits": sum(1 for r in rows if pred(r)),
        "sl_hits": sum(1 for r in sl if pred(r)),
        "non_poison_sl_hits": sum(1 for r in non_poison_sl if pred(r)),
        "poison_hits": sum(1 for r in sl if _is_poison(r) and pred(r)),
        "win_hits": 0,
    }


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

    live_cfg = copy.deepcopy(cfg0)
    live_cfg.update(LIVE)
    print("live combo full backtest", flush=True)
    live_full = run_backtest(df, live_cfg)
    recs = _records(live_full, live_cfg)
    losses = [r for r in recs if not r.get("win")]
    wins = [r for r in recs if r.get("win")]
    remaining = [_dump_loss(r) for r in losses]
    scan = _scan(losses, _london_open_chase_buy)
    scan["win_hits"] = sum(1 for r in wins if _london_open_chase_buy(r))
    print(
        json.dumps({"n_loss": len(losses), "n_win": len(wins), "scan": scan}, default=str),
        flush=True,
    )
    print(json.dumps({"remaining": remaining}, indent=2, default=str), flush=True)

    non_poison_sl = [r for r in losses if _is_sl(r) and not _is_poison(r)]
    exhausted = scan["non_poison_sl_hits"] < 1
    verdict = None
    experiments: list[dict[str, Any]] = []
    promote_id = None
    live_oos = None
    live_pnl = None
    live_n = None
    live_wr = None
    live_e = None
    picked = None

    if exhausted:
        verdict = "skip_exhausted_this_sequence"
        print("no unused skip hits a non-poison SL; skip_exhausted_this_sequence", flush=True)
    else:
        picked = IDEA["id"]
        print(
            f"path-test {picked} replay={scan} (replay is not the gate; poison hits={scan['poison_hits']})",
            flush=True,
        )
        out = run_generation(
            df,
            persist=False,
            experiments=[
                {
                    "id": IDEA["id"],
                    "kind": IDEA["kind"],
                    "weakness": IDEA["weakness"],
                    "patch": IDEA["patch"],
                    "hypothesis": IDEA["hypothesis"],
                }
            ],
            generation="gen14",
            folds=0,
            baseline_patch=LIVE,
        )
        live_oos = float((out["baseline"].get("oos") or {}).get("expectancy_r") or 0)
        live_pnl = float(out["baseline"]["metrics"].get("net_pnl") or 0)
        live_n = out["baseline"]["metrics"].get("total_trades")
        live_wr = out["baseline"]["metrics"].get("win_rate")
        live_e = out["baseline"]["metrics"].get("expectancy_r")
        for r in out["experiments"]:
            row = _exp_row(r)
            cand_oos = float(row["oos_e"] or 0)
            cand_pnl = float(row["pnl"] or 0)
            row["beats_live_oos_e"] = cand_oos > live_oos
            row["beats_live_full_usd"] = cand_pnl > live_pnl
            row["promote"] = bool(
                r.get("decision") == "accept" and cand_oos > live_oos and cand_pnl > live_pnl
            )
            row["winner_sacrifice_replay"] = scan
            experiments.append(row)
            if row["promote"] and promote_id is None:
                promote_id = row["id"]

    summary = {
        "source": source,
        "bars": int(len(df)),
        "generation": "gen14",
        "verdict": verdict,
        "gate": "Promote only if OOS E AND full $ both beat the four-flag live combo. Do not target poison Aug 6 19:20 sell. Replay is not the gate. Small-n. Not 100% WR.",
        "poison": "2026-08-06 19:20 sell",
        "n_non_poison_sl": len(non_poison_sl),
        "live_combo": {
            "flags": [
                "intel_skip_rsi_ext",
                "intel_skip_doji_against",
                "intel_skip_stretched_doji_buy",
                "intel_skip_barbwire_sell",
            ],
            "oos_e": live_oos,
            "pnl": live_pnl,
            "full_e": live_e,
            "n": live_n if live_n is not None else (len(losses) + len(wins)),
            "wr": live_wr,
            "n_loss": len(losses),
            "n_win": len(wins),
        },
        "remaining_losers": remaining,
        "winner_sacrifice_replay": {"intel_london_open_chase_buy": scan},
        "picked": picked,
        "experiments": experiments,
        "promote": promote_id,
        "live_yaml_unchanged_unless_promote": promote_id is None,
        "paper_restart": False,
        "not_a_100_wr_claim": True,
    }
    path = INTEL_DIR / "gen14_report.json"
    path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(json.dumps(summary, indent=2, default=str), flush=True)
    print(f"wrote {path}", flush=True)


if __name__ == "__main__":
    main()
