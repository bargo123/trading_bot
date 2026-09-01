#!/usr/bin/env python3
"""Summarize Mode A paper journal for the 14-day real test."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

JOURNAL = ROOT / "reports" / "real_14d_forever_safe_journal.jsonl"
PROTECTED = 80.0
START = 100.0


def main() -> None:
    if not JOURNAL.exists():
        print("No journal yet. Start paper:")
        print("  python scripts/run_paper.py --config config_paper_forever_safe_14d.yaml")
        print(f"Expected journal: {JOURNAL}")
        return
    events = []
    for line in JOURNAL.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    entries = [e for e in events if e.get("event") == "entry"]
    exits = [e for e in events if e.get("event") == "exit"]
    pnls = [float(e.get("pnl", 0)) for e in exits]
    equity = START + sum(pnls)
    # prefer last logged equity
    for e in reversed(events):
        if "equity" in e:
            equity = float(e["equity"])
            break
    wins = sum(1 for p in pnls if p > 0)
    n = len(pnls)
    halted = any(e.get("hr_halt") for e in exits)
    print("=== Real test paper status ===")
    print(f"Journal events: {len(events)}")
    print(f"Entries: {len(entries)}  Exits: {n}")
    print(f"WR: {100*wins/n:.1f}%" if n else "WR: n/a (no closed trades)")
    print(f"Net PnL: {sum(pnls):.2f}")
    print(f"Equity: {equity:.2f}  (protected floor ${PROTECTED:.0f})")
    print(f"Floor OK: {equity >= PROTECTED}")
    print(f"HR halt seen: {halted}")
    if n:
        print("Last exits:")
        for e in exits[-5:]:
            print(f"  pnl={e.get('pnl'):.4f} how={e.get('how')} equity={e.get('equity')}")
    verdict = "PASS so far" if equity >= PROTECTED else "FAIL — below protected floor"
    print(f"Verdict: {verdict}")


if __name__ == "__main__":
    main()
