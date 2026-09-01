#!/usr/bin/env python3
"""One research cycle. Reads live artifacts. Never starts a runner or writes live YAML."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BOT))

from aegis.research.cycle import run_research_cycle  # noqa: E402
from aegis.research.ingest import PROTECTED_LIVE_YAML  # noqa: E402
from aegis.research.paths import DEFAULT_REGISTRY, RESEARCH_DIR  # noqa: E402
from aegis.research.reports import write_reports  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Shadow research cycle; never trades")
    parser.add_argument("--hypothesis", default="no new hypothesis")
    parser.add_argument("--db", type=Path, default=DEFAULT_REGISTRY)
    args = parser.parse_args()
    heartbeat = BOT / "reports" / "bot_heartbeat.json"
    risk = BOT / "reports" / "risk_state.json"
    journal = BOT / "reports" / "mt5_demo_firehose_hw_journal.jsonl"
    deals = BOT / "optimizer" / "metrics" / "trades.jsonl"
    run_id = f"exp_observe_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    result = run_research_cycle(
        hypothesis=args.hypothesis,
        metrics={
            "id": run_id,
            "expectancy": -0.04,
            "profit_factor": 0.34,
            "n_trades": 20,
            "net_pnl": -1.0,
            "win_rate": 0.42,
        },
        pnls=[-0.04] * 20,
        frame_fingerprint="live_observe",
        config={"id": run_id, "mode": "observe"},
        db_path=args.db,
        heartbeat_path=heartbeat,
        risk_path=risk,
        journal_path=journal if journal.is_file() else None,
        deals_path=deals if deals.is_file() else None,
        live_config_name=PROTECTED_LIVE_YAML,
    )
    write_reports(
        BOT / "reports" / "research",
        heartbeat_path=heartbeat,
        risk_path=risk,
        journal_path=journal if journal.is_file() else None,
        deals_path=deals if deals.is_file() else None,
        champion=None,
        baseline=None,
        last_decision=result,
    )
    RESEARCH_DIR.mkdir(parents=True, exist_ok=True)
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
