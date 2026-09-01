#!/usr/bin/env python3
"""Measured symbol/session execution-cost profiles (defect 9).

Aggregates live spread observations from the runner journal (spread_skip and
order events carry the observed spread at decision time) into per-symbol,
per-session profiles:

  spread p50 / p75 / p90, observation count, slippage estimate, commission,
  and a CONSERVATIVE validation cost chosen for research gating.

Conservative rule (documented):
  validation_cost_pips = p75(spread) + slippage_pips + commission_pips
Fallback when observations < MIN_OBS: config-formula cost (bps -> pips) with a
prohibitive safety multiplier so unknown symbols never look cheap.

Output: bot/intel/cost_profiles.json (committed artifact; deterministic given
the same journal tail).
"""
from __future__ import annotations

import argparse
import collections
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

BOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BOT))

from aegis.config import configured_symbols, load_config, pip_size_for  # noqa: E402
from aegis.research.exit_research import bps_to_pips  # noqa: E402

MIN_OBS = 30  # below this, evidence is insufficient -> documented fallback
SESSIONS = (("00", "07", "asia"), ("07", "12", "london"), ("12", "16", "london"),
            ("16", "21", "newyork"), ("21", "24", "asia"))


def session_of(ts: str) -> str:
    hour = ts[11:13] if len(ts) > 13 else ""
    for start, end, name in SESSIONS:
        if start <= hour < end:
            return name
    return "unknown"


def _pctl(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = min(len(s) - 1, max(0, int(q * len(s))))
    return round(s[idx], 6)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build measured cost profiles")
    parser.add_argument("--journal", type=Path,
                        default=BOT / "reports" / "mt5_demo_firehose_hw_journal.jsonl")
    parser.add_argument("--config", type=Path, default=BOT / "config_mt5_demo_firehose_hw.yaml")
    parser.add_argument("--out", type=Path, default=BOT / "intel" / "cost_profiles.json")
    args = parser.parse_args()

    cfg = load_config(args.config)
    symbols = list(configured_symbols(cfg))
    pip_by_symbol = {s: float(pip_size_for(s, cfg)) for s in symbols}
    spread_bps = float(cfg.get("spread_bps", 0.2) or 0.2)
    slippage_bps = float(cfg.get("slippage_bps", 0.1) or 0.1)
    commission_rt = float(cfg.get("commission_round_trip_usd", 0.0) or 0.0)

    # symbol -> session -> [spread in PIPS...] (journal stores price units)
    obs: dict[str, dict[str, list[float]]] = collections.defaultdict(lambda: collections.defaultdict(list))
    with args.journal.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            ev = row.get("event")
            if ev not in {"spread_skip", "order"}:
                continue
            spread = row.get("spread")
            sym = row.get("symbol")
            bar = str(row.get("bar") or "")
            if spread is None or not sym or not bar:
                continue
            pip = pip_by_symbol.get(str(sym).upper())
            if not pip:
                continue
            try:
                obs[str(sym).upper()][session_of(bar)].append(float(spread) / float(pip))
            except (TypeError, ValueError):
                continue

    profiles: dict[str, Any] = {}
    for symbol in symbols:
        pip = pip_by_symbol.get(symbol, 0.0001)
        slippage_pips = bps_to_pips(slippage_bps, symbol, pip)
        # Commission expressed in pips via 0.01-lot pip value.
        commission_pips = (
            commission_rt / max(float(pip) * 1000.0, 1e-9) if commission_rt else 0.0
        )
        sessions_out: dict[str, Any] = {}
        all_spreads = [v for vals in obs.get(symbol, {}).values() for v in vals]
        for session, values in sorted(obs.get(symbol, {}).items()):
            if not values:
                continue
            p50, p75, p90 = _pctl(values, 0.50), _pctl(values, 0.75), _pctl(values, 0.90)
            sufficient = len(values) >= MIN_OBS
            sessions_out[session] = {
                "observations": len(values),
                "spread_p50": p50,
                "spread_p75": p75,
                "spread_p90": p90,
                "slippage_pips": round(slippage_pips, 4),
                "commission_pips": round(commission_pips, 4),
                "validation_cost_pips": round(p75 + slippage_pips + commission_pips, 4)
                if sufficient else None,
                "evidence_sufficient": sufficient,
                "fallback": None if sufficient else f"insufficient_observations<{MIN_OBS}",
            }
        # Symbol-level profile: conservative across sessions.
        if all_spreads:
            sufficient = len(all_spreads) >= MIN_OBS
            p50, p75, p90 = _pctl(all_spreads, 0.50), _pctl(all_spreads, 0.75), _pctl(all_spreads, 0.90)
            measured_cost = round(p75 + slippage_pips + commission_pips, 4) if sufficient else None
            fallback_cost = round(
                bps_to_pips(spread_bps, symbol, pip) * 2.0 + slippage_pips + commission_pips, 4
            )
            profiles[symbol] = {
                "pip_size": pip,
                "observations": len(all_spreads),
                "spread_p50": p50,
                "spread_p75": p75,
                "spread_p90": p90,
                "slippage_pips": round(slippage_pips, 4),
                "commission_pips": round(commission_pips, 4),
                "validation_cost_pips": measured_cost or fallback_cost,
                "cost_source": "measured_p75" if sufficient else "config_fallback_x2",
                "sessions": sessions_out,
            }
        else:
            fallback_cost = round(
                bps_to_pips(spread_bps, symbol, pip) * 2.0 + slippage_pips + commission_pips, 4
            )
            profiles[symbol] = {
                "pip_size": pip,
                "observations": 0,
                "validation_cost_pips": fallback_cost,
                "cost_source": "no_evidence_config_fallback_x2",
                "sessions": {},
            }

    payload = {
        "schema": "cost_profiles.v1",
        "built_at": datetime.now(timezone.utc).isoformat(),
        "rule": "validation_cost_pips = spread_p75 + slippage + commission; "
                "fallback = 2x config-bps spread + slippage + commission "
                "(conservative by design)",
        "min_observations": MIN_OBS,
        "symbols": profiles,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({
        "out": str(args.out),
        "symbols": len(profiles),
        "measured": sum(1 for p in profiles.values() if p["cost_source"] == "measured_p75"),
        "sample_costs": {s: profiles[s]["validation_cost_pips"]
                         for s in list(sorted(profiles))[:8]},
    }, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
