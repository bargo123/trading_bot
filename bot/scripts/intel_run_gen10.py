#!/usr/bin/env python3
"""GEN10: one new skip around live rsi_ext + doji_against + stretched_doji_buy.

Dump remaining losers on the new path-dependent sequence. Pick ONE unused skip
that hits at least one real SL (not eof). Path-dependent vs the live combo.
Promote only if OOS E AND full $ beat that combo. Never mt5.shutdown().
Not a 100% WR claim. Does not edit YAML.
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
}


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


def _barbwire_sell(rec: dict[str, Any]) -> bool:
    return rec.get("side") == "sell" and _flag(rec, "brooks_barbwire")


def _stretched_sell(rec: dict[str, Any]) -> bool:
    ema = _num(rec, "close_ema_pips")
    return rec.get("side") == "sell" and ema is not None and ema <= -3.0


def _barbwire(rec: dict[str, Any]) -> bool:
    return _flag(rec, "brooks_barbwire")


IDEAS: list[dict[str, Any]] = [
    {
        "id": "intel_barbwire_sell",
        "pred": _barbwire_sell,
        "kind": "book",
        "weakness": "chop",
        "patch": {**LIVE, "intel_skip_barbwire_sell": True},
        "hypothesis": "Brooks barbwire SELL only. Hits overlapping-bar floor sprays. Not global barbwire WAIT.",
    },
    {
        "id": "intel_stretched_sell",
        "pred": _stretched_sell,
        "kind": "book",
        "weakness": "late_entry",
        "patch": {**LIVE, "intel_skip_stretched_sell": True},
        "hypothesis": "Skip SELL already >=3 pips through EMA. Mirror of stretched_doji_buy. Not impulse_against.",
    },
    {
        "id": "intel_barbwire",
        "pred": _barbwire,
        "kind": "book",
        "weakness": "chop",
        "patch": {**LIVE, "intel_skip_barbwire": True},
        "hypothesis": "Global Brooks barbwire WAIT. Info-only unless tighter ideas miss.",
        "info_only": True,
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
        "mae": r.get("mae"),
        "bars_held": r.get("bars_held"),
        "quality": r.get("quality"),
        "body_against": body_against,
        "features": f,
        "hits": {
            "barbwire_sell": _barbwire_sell(r),
            "stretched_sell": _stretched_sell(r),
            "barbwire": _barbwire(r),
        },
    }


def _scan(losses: list[dict[str, Any]], wins: list[dict[str, Any]], pred: Callable) -> dict[str, int]:
    sl = [r for r in losses if _is_sl(r)]
    return {
        "loss_hits": sum(1 for r in losses if pred(r)),
        "sl_hits": sum(1 for r in sl if pred(r)),
        "win_hits": sum(1 for r in wins if pred(r)),
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


def _pick(scan: dict[str, dict[str, int]]) -> dict[str, Any] | None:
    ranked: list[tuple[float, int, int, dict[str, Any]]] = []
    for idea in IDEAS:
        if idea.get("info_only"):
            continue
        hits = scan[idea["id"]]
        sl_hits = int(hits["sl_hits"])
        if sl_hits < 1:
            continue
        win_hits = int(hits["win_hits"])
        eff = sl_hits / max(win_hits, 1)
        ranked.append((eff, sl_hits, -win_hits, idea))
    if not ranked:
        return None
    ranked.sort(key=lambda t: (t[0], t[1], t[2]), reverse=True)
    return ranked[0][3]


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
    scan = {idea["id"]: _scan(losses, wins, idea["pred"]) for idea in IDEAS}
    print(
        json.dumps({"n_loss": len(losses), "n_win": len(wins), "scan": scan}, default=str),
        flush=True,
    )
    print(json.dumps({"remaining": remaining}, indent=2, default=str), flush=True)

    pick = _pick(scan)
    experiments: list[dict[str, Any]] = []
    promote_id = None
    live_oos = None
    live_pnl = None
    live_n = None
    live_wr = None
    live_e = None
    if pick is None:
        print("no skip hits remaining real SLs; skip generation", flush=True)
    else:
        print(f"picked {pick['id']} replay={scan[pick['id']]}", flush=True)
        out = run_generation(
            df,
            persist=False,
            experiments=[
                {
                    "id": pick["id"],
                    "kind": pick["kind"],
                    "weakness": pick["weakness"],
                    "patch": pick["patch"],
                    "hypothesis": pick["hypothesis"],
                }
            ],
            generation="gen10",
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
            row["winner_sacrifice_replay"] = scan[pick["id"]]
            experiments.append(row)
            if row["promote"] and promote_id is None:
                promote_id = row["id"]

    summary = {
        "source": source,
        "bars": int(len(df)),
        "generation": "gen10",
        "gate": "Promote only if OOS E AND full $ both beat rsi_ext+doji_against+stretched_doji_buy. Hydra $ without losses_avoided is allowed but must still beat both. Small-n. Not 100% WR.",
        "live_combo": {
            "flags": [
                "intel_skip_rsi_ext",
                "intel_skip_doji_against",
                "intel_skip_stretched_doji_buy",
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
        "winner_sacrifice_replay": scan,
        "picked": None if pick is None else pick["id"],
        "experiments": experiments,
        "promote": promote_id,
        "live_yaml_unchanged_unless_promote": promote_id is None,
        "paper_restart": False,
        "not_a_100_wr_claim": True,
    }
    path = INTEL_DIR / "gen10_report.json"
    path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(json.dumps(summary, indent=2, default=str), flush=True)
    print(f"wrote {path}", flush=True)


if __name__ == "__main__":
    main()
