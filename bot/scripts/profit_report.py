#!/usr/bin/env python3
"""Profit-capture / winner-to-loser report (spec H, G, M).

Reads the exploration experiment store and produces
bot/reports/research/profit_capture.json:

  winner_to_loser_count / usd given back
  profit_capture_ratio (realized / MFE) avg, median, p25, p75
  grouped by strategy family, symbol, side, session, regime, exit reason

Point-in-time (spec M): every field used here was recorded while the trade
was open (samples, MFE/MAE, pl_at_minutes) or at the close decision itself.
Counterfactual policy profits are descriptive only - they never feed
promotion, which still requires the full governed stack (spec N).
"""
from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

BOT = Path(__file__).resolve().parents[1]


def _pctl(values: list[float], q: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    idx = min(len(s) - 1, max(0, int(q * len(s))))
    return round(s[idx], 4)


def capture_stats(trades: list[dict]) -> dict:
    ratios = []
    w2l = 0
    w2l_given = 0.0
    total_mfe = 0.0
    for t in trades:
        mfe = float(t.get("mfe_before_close") or 0.0)
        realized = float(t.get("realized_pnl") or 0.0)
        total_mfe += max(0.0, mfe)
        if mfe >= 0.10:  # meaningful positive MFE only
            ratios.append(realized / mfe)
            if realized <= 0:
                w2l += 1
                w2l_given += max(0.0, mfe - realized)
    out: dict = {
        "n": len(trades),
        "total_mfe_usd": round(total_mfe, 4),
        "winner_to_loser_count": w2l,
        "winner_to_loser_usd_given_back": round(w2l_given, 4),
    }
    if ratios:
        out.update({
            "realized_vs_mfe_capture_ratio": round(statistics.mean(ratios), 4),
            "average_profit_capture_ratio": round(statistics.mean(ratios), 4),
            "median_profit_capture_ratio": round(statistics.median(ratios), 4),
            "p25_capture_ratio": _pctl(ratios, 0.25),
            "p75_capture_ratio": _pctl(ratios, 0.75),
            "sample_size": len(ratios),
        })
    else:
        for key in ("realized_vs_mfe_capture_ratio", "average_profit_capture_ratio",
                    "median_profit_capture_ratio", "p25_capture_ratio",
                    "p75_capture_ratio"):
            out[key] = None
        out["sample_size"] = 0
    return out


def group_by(trades: list[dict], key: str) -> dict:
    groups: dict[str, list] = defaultdict(list)
    for t in trades:
        groups[str(t.get(key) or "unknown")].append(t)
    return {k: capture_stats(v) for k, v in sorted(groups.items())}


def main() -> int:
    parser = argparse.ArgumentParser(description="Profit-capture report")
    parser.add_argument("--store", type=Path,
                        default=BOT / "intel" / "exploration_experiments.json")
    parser.add_argument("--out", type=Path,
                        default=BOT / "reports" / "research" / "profit_capture.json")
    args = parser.parse_args()

    try:
        store = json.loads(args.store.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        store = {"experiments": {}}

    flat: list[dict] = []
    for rec in store.get("experiments", {}).values():
        stage = "EXPLORATION_CANARY"
        for t in rec.get("trades", []):
            flat.append({
                **t,
                "strategy_family": rec.get("strategy_family"),
                "symbol": rec.get("symbol"),
                "side": rec.get("side"),
                "session": t.get("session") or rec.get("session"),
                "regime": t.get("regime") or rec.get("regime"),
                "exit_method": t.get("exit_reason") or "broker",
                "stage": stage,
                "experiment_status": rec.get("status"),
            })

    report = {
        "schema": "profit_capture.v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "point_in_time_note": (
            "All inputs recorded during trade life or at close decision. "
            "Counterfactual profits are descriptive; promotion still requires "
            "the governed stack (OOS/walk-forward/sealed holdout)."
        ),
        "overall": capture_stats(flat),
        "by_strategy_family": group_by(flat, "strategy_family"),
        "by_symbol": group_by(flat, "symbol"),
        "by_side": group_by(flat, "side"),
        "by_session": group_by(flat, "session"),
        "by_regime": group_by(flat, "regime"),
        "by_exit_method": group_by(flat, "exit_method"),
        "by_stage": group_by(flat, "stage"),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({
        "out": str(args.out),
        "trades": len(flat),
        "overall": report["overall"],
    }, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
