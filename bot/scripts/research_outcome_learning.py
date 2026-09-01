#!/usr/bin/env python3
"""Consume intel/outcome_log.jsonl into learning evidence. Never touches MT5.

Read-only consumer for the outcome-learning loop: reconciles exits into
scoreboard metrics and per-dimension slices, then writes JSON + Markdown
reports. Does not place orders and does not mutate trading state.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BOT = Path(__file__).resolve().parents[1]
REPO = BOT.parent
sys.path.insert(0, str(BOT))

from aegis.intel.outcome_log import DEFAULT_OUTCOME_PATH  # noqa: E402
from aegis.research.fingerprint import config_fingerprint  # noqa: E402
from aegis.research.outcome_learning import (  # noqa: E402
    outcome_learning_markdown,
    read_outcomes,
    summarize_outcomes,
)
from aegis.research.registry import DuplicateExperimentError, ExperimentRegistry  # noqa: E402


def _record(summary: dict, report_path: Path) -> str:
    payload_hash = hashlib.sha256(
        json.dumps(summary, default=str, sort_keys=True).encode("utf-8")
    ).hexdigest()
    registry = ExperimentRegistry()
    row = {
        "id": f"outcome_learning_{payload_hash[:16]}",
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "hypothesis": "Reconciled demo exits aggregate into payoff and slice evidence.",
        "status": "completed",
        "config_fingerprint": config_fingerprint({"task": "outcome_learning"}),
        "dataset_fingerprint": payload_hash,
        "params": {"label": "research_proxy", "strategy_implemented": False},
        "metrics": {
            "n_rows": summary["n_rows"],
            "n_exits": summary["n_exits"],
            "win_rate": summary["metrics"]["win_rate"],
            "expectancy": summary["metrics"]["expectancy"],
            "profit_factor": summary["metrics"]["profit_factor"],
        },
        "provenance": {
            "report": str(report_path),
            "mt5_touched": False,
            "placed_orders": False,
            "promoted_live_yaml": False,
        },
    }
    try:
        return registry.record(row)
    except DuplicateExperimentError:
        return row["id"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Consume the outcome log into learning evidence")
    parser.add_argument("--log", type=Path, default=DEFAULT_OUTCOME_PATH)
    parser.add_argument("--json", type=Path, default=BOT / "reports" / "research" / "outcome_learning.json")
    parser.add_argument("--md", type=Path, default=BOT / "reports" / "research" / "outcome_learning.md")
    args = parser.parse_args()

    rows = read_outcomes(args.log)
    summary = summarize_outcomes(rows)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    args.md.write_text(outcome_learning_markdown(summary), encoding="utf-8")
    experiment_id = _record(summary, args.md)
    print(
        json.dumps(
            {
                "log": str(args.log),
                "json": str(args.json),
                "md": str(args.md),
                "experiment_id": experiment_id,
                "n_rows": summary["n_rows"],
                "n_exits": summary["n_exits"],
                "expectancy": summary["metrics"]["expectancy"],
                "profit_factor": summary["metrics"]["profit_factor"],
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