#!/usr/bin/env python3
"""Deep research on the two measured Asia-session sell edges.

Investigates regime=range/trend, structure=none, session=asia, side=sell from
the measured mt5_m1 analogue index: symbol concentration, day-of-week,
volatility phase, HTF/M5 direction, cost survival, time split (walk-forward
proxy), and bootstrap lower bounds. Research-only; never touches MT5.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

BOT = Path(__file__).resolve().parents[1]
REPO = BOT.parent
sys.path.insert(0, str(BOT))

from aegis.intel.expected_value import payoff_metrics  # noqa: E402
from aegis.research.fingerprint import config_fingerprint  # noqa: E402
from aegis.research.registry import ExperimentRegistry  # noqa: E402
from aegis.research.stress import bootstrap_expectancy, tail_stress  # noqa: E402

ASIA_SELL_STATES = [
    {"regime": "range", "structure": "none", "session": "asia", "side": "sell"},
    {"regime": "trend", "structure": "none", "session": "asia", "side": "sell"},
]


def _load_records(path: Path) -> list[dict]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return payload.get("records") or []


def _row_day(row: dict) -> str:
    try:
        return datetime.fromisoformat(
            str(row.get("bar_time") or "").replace(" ", "T")
        ).strftime("%A")
    except ValueError:
        return "?"


def _match(row: dict, state: dict) -> bool:
    return all(str(row.get(k) or "") == v for k, v in state.items())


def _slice(pnls: list[float], key: str) -> dict:
    return {"key": key, "n": len(pnls), **payoff_metrics(pnls)}


def analyze_state(records: list[dict], state: dict) -> dict:
    rows = [r for r in records if _match(r, state)]
    pnls = [float(r["outcome"]) for r in rows]
    by_symbol: dict[str, list[float]] = defaultdict(list)
    by_day: dict[str, list[float]] = defaultdict(list)
    by_vol: dict[str, list[float]] = defaultdict(list)
    by_h1: dict[str, list[float]] = defaultdict(list)
    by_m5: dict[str, list[float]] = defaultdict(list)
    by_symbol_day: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        symbol = str(row.get("symbol") or "?")
        by_symbol[symbol].append(float(row["outcome"]))
        try:
            dow = _row_day(row)
        except ValueError:
            dow = "?"
        by_day[dow].append(float(row["outcome"]))
        by_vol[str(row.get("volatility") or "?").lower()].append(float(row["outcome"]))
        by_h1[str(row.get("h1_direction") or "?").lower()].append(float(row["outcome"]))
        by_m5[str(row.get("m5_direction") or "?").lower()].append(float(row["outcome"]))
        by_symbol_day[f"{symbol}|{dow}"].append(float(row["outcome"]))
    total = payoff_metrics(pnls)
    boot = bootstrap_expectancy(pnls)
    tail = tail_stress(pnls)
    symbols = sorted((_slice(v, k) for k, v in by_symbol.items() if len(v) >= 20),
                     key=lambda item: float(item.get("expectancy") or 0), reverse=True)
    days = sorted((_slice(v, k) for k, v in by_day.items() if len(v) >= 20),
                  key=lambda item: float(item.get("expectancy") or 0), reverse=True)
    vols = sorted((_slice(v, k) for k, v in by_vol.items() if len(v) >= 20),
                  key=lambda item: float(item.get("expectancy") or 0), reverse=True)
    h1s = sorted((_slice(v, k) for k, v in by_h1.items() if len(v) >= 20),
                 key=lambda item: float(item.get("expectancy") or 0), reverse=True)
    m5s = sorted((_slice(v, k) for k, v in by_m5.items() if len(v) >= 20),
                 key=lambda item: float(item.get("expectancy") or 0), reverse=True)
    symbol_days = sorted((_slice(v, k) for k, v in by_symbol_day.items() if len(v) >= 20),
                         key=lambda item: float(item.get("expectancy") or 0), reverse=True)
    return {
        "state": state,
        "n": len(pnls),
        "metrics": total,
        "bootstrap": {k: float(v) for k, v in boot.items()},
        "tail": tail,
        "by_symbol": symbols,
        "by_day": days,
        "by_volatility": vols,
        "by_h1_direction": h1s,
        "by_m5_direction": m5s,
        "by_symbol_day": symbol_days,
        "symbol_count": len(by_symbol),
    }


def walk_forward_split(pnls: list[float], splits: int = 3) -> list[dict]:
    if not pnls:
        return []
    arr = np.asarray(pnls, dtype=float)
    out = []
    edges = np.linspace(0, len(arr), splits + 1, dtype=int)
    for i in range(splits):
        chunk = arr[edges[i] : edges[i + 1]]
        out.append({"window": i, "n": int(chunk.size), **payoff_metrics([float(x) for x in chunk])})
    return out


def cost_survival(pnls: list[float], cost_pips: float) -> dict:
    costed = [float(p) - cost_pips for p in pnls]
    raw = payoff_metrics(pnls)
    net = payoff_metrics(costed)
    return {
        "cost_pips": cost_pips,
        "raw_expectancy": raw.get("expectancy"),
        "costed_expectancy": net.get("expectancy"),
        "costed_pf": net.get("profit_factor"),
        "survives": bool(net.get("expectancy") is not None and net.get("expectancy") > 0),
    }


def exclusions_test(rows: list[dict], pnls: list[float], by: str) -> dict:
    """Does excluding the best single dimension value destroy the edge?"""
    best = None
    buckets: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        value = _row_day(row) if by == "day" else str(row.get(by) or "?")
        buckets[value].append(float(row["outcome"]))
    best = max(buckets, key=lambda k: float(payoff_metrics(buckets[k]).get("expectancy") or 0))
    best_pnls = buckets[best]
    rest = [
        p
        for i, p in enumerate(pnls)
        if not ((_row_day(rows[i]) if by == "day" else str(rows[i].get(by) or "?")) == best)
    ]
    return {
        "excluded": by,
        "excluded_value": best,
        "excluded_n": len(best_pnls),
        "excluded_expectancy": payoff_metrics(best_pnls).get("expectancy"),
        "remaining_n": len(rest),
        "remaining_expectancy": payoff_metrics(rest).get("expectancy"),
        "edge_survives_exclusion": bool(
            payoff_metrics(rest).get("expectancy") is not None
            and payoff_metrics(rest).get("expectancy") > 0
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Deep research on Asia-session sell edges")
    parser.add_argument("--index", type=Path, default=BOT / "intel" / "analogue_index.json")
    parser.add_argument("--report", type=Path, default=BOT / "reports" / "research" / "asia_sell_edge.json")
    args = parser.parse_args()

    records = _load_records(args.index)
    states = []
    for state in ASIA_SELL_STATES:
        analysis = analyze_state(records, state)
        pnls = [float(r["outcome"]) for r in records if _match(r, state)]
        analysis["walk_forward"] = walk_forward_split(pnls)
        analysis["cost_survival"] = [
            cost_survival(pnls, c) for c in (0.1, 0.2, 0.4, 0.8)
        ]
        analysis["exclusions"] = [
            exclusions_test([r for r in records if _match(r, state)], pnls, by)
            for by in ("symbol", "day", "volatility", "h1_direction", "m5_direction")
        ]
        states.append(analysis)

    report = {
        "schema": "asia_sell_edge.v1",
        "label": "research_proxy",
        "provenance": "mt5_m1",
        "source": str(args.index),
        "built_at": datetime.now(timezone.utc).isoformat(),
        "states": states,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    registry = ExperimentRegistry()
    for state in states:
        metrics = state["metrics"]
        fp = config_fingerprint({"task": "asia_sell_edge", "state": state["state"]})
        run_ts = datetime.now(timezone.utc)
        row = {
            "id": f"asia_edge_{fp[:8]}_{run_ts.strftime('%Y%m%d%H%M%S')}",
            "ts_utc": run_ts.isoformat(),
            "hypothesis": (
                f"Asia-session sell under {state['state']['regime']} regime, structure none, "
                "has positive costed expectancy and survives symbol/day exclusion and time split."
            ),
            "status": "completed",
            "config_fingerprint": fp,
            "dataset_fingerprint": "mt5_m1_analogue_index",
            "params": {"label": "research_proxy", "strategy_implemented": False},
            "metrics": {
                "n_trades": metrics.get("n"),
                "win_rate": metrics.get("win_rate"),
                "expectancy": metrics.get("expectancy"),
                "profit_factor": metrics.get("profit_factor"),
                "net_pnl": metrics.get("net_pnl"),
                "tail_loss": metrics.get("tail_loss"),
            },
            "provenance": {
                "state": state["state"],
                "report": str(args.report),
                "bootstrap_p05": state["bootstrap"]["p05"],
                "costed_survives": [c["survives"] for c in state["cost_survival"]],
                "mt5_touched": False,
                "placed_orders": False,
                "promoted_live_yaml": False,
            },
        }
        registry.record(row)

    print(
        json.dumps(
            {
                "report": str(args.report),
                "states": [
                    {
                        "state": s["state"],
                        "n": s["n"],
                        "expectancy": s["metrics"]["expectancy"],
                        "pf": s["metrics"]["profit_factor"],
                        "bootstrap_p05": s["bootstrap"]["p05"],
                        "costed_survives": [c["survives"] for c in s["cost_survival"]],
                        "symbols": s["symbol_count"],
                    }
                    for s in states
                ],
                "mt5_touched": False,
                "placed_orders": False,
                "promoted_live_yaml": False,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())