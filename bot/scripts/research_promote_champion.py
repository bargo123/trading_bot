#!/usr/bin/env python3
"""Governed champion promotion. Never places orders, never edits live YAML.

Consumes a challenger spec JSON describing validation/holdout evidence and,
if and only if every gate passes, produces `intel/intelligent_champion.json`
via the governed pipeline (validation -> freeze -> one-shot sealed holdout ->
bootstrap/tail/stress -> strategy-model readiness).
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

from aegis.intel.paths import INTEL_DIR  # noqa: E402
from aegis.research.fingerprint import config_fingerprint  # noqa: E402
from aegis.research.promote import (  # noqa: E402
    PromotionReject,
    challenger_promotion_result,
    promotion_result_markdown,
)
from aegis.research.registry import ExperimentRegistry  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the governed Intelligent champion promotion")
    parser.add_argument("--spec", type=Path, required=True, help="challenger spec JSON")
    parser.add_argument(
        "--report", type=Path, default=BOT / "reports" / "research" / "champion_promotion.json"
    )
    args = parser.parse_args()

    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    try:
        result = challenger_promotion_result(
            strategy_id=str(spec["strategy_id"]),
            code_hash=str(spec.get("code_hash") or "unset"),
            artifact_hash=str(spec.get("artifact_hash") or hashlib.sha256(
                json.dumps(spec, sort_keys=True, default=str).encode("utf-8")
            ).hexdigest()),
            config=dict(spec.get("config") or {}),
            validation_pnls=[float(x) for x in spec.get("validation_pnls", [])],
            holdout_metrics=dict(spec.get("holdout_metrics") or {}),
            holdout_pnls=[float(x) for x in spec.get("holdout_pnls", [])],
            validated_risk_fraction=float(spec["validated_risk_fraction"]),
            n_searches=int(spec.get("n_searches", 1) or 1),
            champion=spec.get("champion"),
        )
    except PromotionReject as exc:
        payload = {
            "status": "rejected",
            "schema": "champion_promotion.v1",
            "label": "research_proxy",
            "placed_orders": False,
            "mt5_touched": False,
            "promoted_live_yaml": False,
            "strategy_id": spec.get("strategy_id"),
            "reason": str(exc),
        }
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        print(json.dumps(payload, indent=2))
        return 1

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    md = args.report.with_suffix(".md")
    md.write_text(promotion_result_markdown(result), encoding="utf-8")

    registry = ExperimentRegistry()
    champ = result["champion"]
    row = {
        "id": f"promote_{champ['id']}_{result['frozen']['frozen_hash'][:12]}",
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "hypothesis": f"Governed promotion of {champ['id']} through sealed holdout.",
        "status": "accepted",
        "config_fingerprint": config_fingerprint(dict(spec.get("config") or {})),
        "dataset_fingerprint": str(result["frozen"]["artifact_hash"]),
        "params": {
            "strategy_id": champ["id"],
            "label": "research_proxy",
            "strategy_implemented": False,
        },
        "metrics": {
            "n_trades": champ["n_trades"],
            "n_losses": champ["n_losses"],
            "expectancy": champ["expectancy"],
            "profit_factor": champ["profit_factor"],
            "win_rate": None,
        },
        "provenance": {
            "frozen_hash": result["frozen"]["frozen_hash"],
            "sealed_holdout": result["sealed_holdout"],
            "mt5_touched": False,
            "placed_orders": False,
            "promoted_live_yaml": False,
        },
    }
    registry.record(row)
    print(
        json.dumps(
            {
                "status": "accepted",
                "champion_id": champ["id"],
                "artifact": str(INTEL_DIR / "intelligent_champion.json"),
                "report": str(args.report),
                "experiment_id": row["id"],
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