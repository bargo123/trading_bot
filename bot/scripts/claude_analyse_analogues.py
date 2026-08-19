#!/usr/bin/env python3
"""Aggregate the analogue index + demo journals into a compact economics report.

Deliberately prints only aggregates: the raw index and journals are far too large
to reason about directly.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "bot"))

from aegis.intel.expected_value import payoff_metrics  # noqa: E402


def analyse_index(path: Path) -> dict:
    if not path.is_file():
        return {"error": f"missing {path}"}
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("records") if isinstance(payload, dict) else payload
    rows = [r for r in rows if isinstance(r, dict)]
    outcomes = [float(r["outcome"]) for r in rows if "outcome" in r]
    keys: Counter = Counter()
    for row in rows:
        keys.update(row.keys())
    return {
        "records": len(rows),
        "fields": dict(keys),
        "symbols": dict(Counter(str(r.get("symbol")) for r in rows).most_common(12)),
        "sides": dict(Counter(str(r.get("side")) for r in rows)),
        "regimes": dict(Counter(str(r.get("regime")) for r in rows)),
        "structures": dict(Counter(str(r.get("structure")) for r in rows).most_common(10)),
        "setups": dict(Counter(str(r.get("setup")) for r in rows).most_common(10)),
        "sessions": dict(Counter(str(r.get("session")) for r in rows)),
        "outcome_payoff": payoff_metrics(outcomes),
        "outcome_min": min(outcomes) if outcomes else None,
        "outcome_max": max(outcomes) if outcomes else None,
        "bar_time_range": [
            min((str(r.get("bar_time")) for r in rows), default=None),
            max((str(r.get("bar_time")) for r in rows), default=None),
        ],
    }


def analyse_journal(path: Path) -> dict:
    if not path.is_file():
        return {"error": f"missing {path}"}
    events: Counter = Counter()
    reasons: Counter = Counter()
    actions: Counter = Counter()
    pnls: list[float] = []
    lines = 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        lines += 1
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        events[str(row.get("event"))] += 1
        if row.get("reason"):
            reasons[str(row.get("reason"))] += 1
        if row.get("action"):
            actions[str(row.get("action"))] += 1
        if isinstance(row.get("pnl"), (int, float)):
            pnls.append(float(row["pnl"]))
    return {
        "path": str(path.relative_to(REPO)),
        "lines": lines,
        "events": dict(events.most_common(20)),
        "actions": dict(actions),
        "top_reasons": dict(reasons.most_common(20)),
        "pnl_payoff": payoff_metrics(pnls),
    }


def main() -> None:
    out = {
        "analogue_index": analyse_index(REPO / "bot" / "intel" / "analogue_index.json"),
        "journals": [],
    }
    journal_dir = REPO / "bot" / "reports"
    for candidate in sorted(journal_dir.rglob("*.jsonl")):
        if candidate.stat().st_size == 0:
            continue
        out["journals"].append(
            {**analyse_journal(candidate), "bytes": candidate.stat().st_size}
        )
    dest = REPO / "bot" / "reports" / "claude" / "economics_scan.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")

    idx = out["analogue_index"]
    print("=== ANALOGUE INDEX ===")
    print(json.dumps({k: v for k, v in idx.items() if k != "fields"}, indent=2, default=str)[:3000])
    print("\n=== JOURNALS (name, lines, bytes, actions, payoff n/wr/pf/expectancy) ===")
    for j in out["journals"]:
        if "error" in j:
            continue
        p = j["pnl_payoff"]
        print(
            f"{j['path']} lines={j['lines']} bytes={j['bytes']} "
            f"actions={j['actions']} "
            f"n={p['n']} wr={p['win_rate']} pf={p['profit_factor']} exp={p['expectancy']} "
            f"avg_win={p['avg_win']} avg_loss={p['avg_loss']} net={p['net_pnl']}"
        )
    print(f"\nfull scan -> {dest.relative_to(REPO)}")


if __name__ == "__main__":
    main()
