#!/usr/bin/env python3
"""Write the $100/day firehose economic gap report. Never touches the MT5 runner."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BOT))

from aegis.research.firehose_economics import (  # noqa: E402
    markdown_firehose_economics,
    snapshot_from_defaults,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Research-only $100/day economic gap")
    parser.add_argument("--deals", type=Path, default=BOT / "optimizer" / "metrics" / "trades.jsonl")
    parser.add_argument("--heartbeat", type=Path, default=BOT / "reports" / "bot_heartbeat.json")
    parser.add_argument(
        "--champion",
        type=Path,
        default=BOT / "intel" / "intelligent_champion.json",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=BOT / "reports" / "research" / "hundred_day_gap.md",
    )
    parser.add_argument("--capital", type=float, default=None)
    args = parser.parse_args()
    snap = snapshot_from_defaults(
        deals_path=args.deals,
        heartbeat_path=args.heartbeat,
        champion_path=args.champion if args.champion.exists() else Path("__missing__"),
        current_capital=args.capital,
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(markdown_firehose_economics(snap), encoding="utf-8")
    json_path = args.report.with_suffix(".json")
    json_path.write_text(json.dumps(snap, indent=2, default=str), encoding="utf-8")
    print(
        json.dumps(
            {
                "report": str(args.report),
                "json": str(json_path),
                "verified_champion": snap["verified_champion"]["status"],
                "expected_net_day": snap["gap"]["current_expected_day"],
                "required_capital_usd": snap["required_capital"]["required_capital_usd"],
                "close_through": snap["gap"]["close_through"],
                "leverage_increase_recommended": snap["leverage_increase_recommended"],
                "placed_orders": False,
                "promoted_live_yaml": False,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
