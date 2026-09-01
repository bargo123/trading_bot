#!/usr/bin/env python3
"""Implement and promote the Asia-session range sell strategy.

Runs the governed champion promotion against a time-split (first 70% validation,
last 30% true holdout) of the mt5_m1 analogue index. On acceptance it writes:
  - intel/intelligent_champion.json            (governed champion)
  - research/strategies/asia_sell_range.json    (exact frozen filter)
  - mql5/asia_sell_range_ea.mq5                (EA skeleton, exact filter)

Never places orders and never edits live YAML.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BOT))

from aegis.research.asia_sell_strategy import (  # noqa: E402
    CONFIG,
    STRATEGY_ID,
    build_challenger_spec,
    save_strategy_spec,
)
from aegis.research.fingerprint import config_fingerprint  # noqa: E402
from aegis.research.promote import (  # noqa: E402
    PromotionReject,
    challenger_promotion_result,
    promotion_result_markdown,
)
from aegis.research.registry import ExperimentRegistry  # noqa: E402

MQL5_EA = r"""//+------------------------------------------------------------------+
//| asia_sell_range_ea.mq5                                            |
//| Asia-session range sell strategy - research skeleton              |
//|                                                                  |
//| EXACT FILTER (frozen in bot/aegis/research/asia_sell_strategy.py)|
//|   side      = SELL                                                |
//|   regime    = range  (flat, no trend bias)                        |
//|   structure = none   (no retest/breakout structure active)        |
//|   session   = Asia    (00:00-08:00 broker time, configurable)     |
//|   timeframe = M1                                                  |
//|                                                                  |
//| RESEARCH ONLY. Not enabled for live/promo trading.               |
//| PROMOTED: {promoted_at}  CHAMPION: {champion_id}                  |
//+------------------------------------------------------------------+
#property strict
#property description "Asia-session range sell research skeleton"

input string  InpSessionStart   = "00:00"; // Asia session start (HH:MM)
input string  InpSessionEnd     = "08:00"; // Asia session end (HH:MM)
input double  InpRiskFraction   = 0.01;    // validated risk fraction
input int     InpMagicNumber    = 5551;    // EA magic

//--- Regime/structure state (set by the research brain; MQL5 side is
//--- a skeleton - classification lives in the research pipeline).
bool   g_range_regime = false;
bool   g_no_structure = false;
bool   g_asia_session = false;

//+------------------------------------------------------------------+
bool InAsiaSession()
{
   datetime now = TimeCurrent();
   string start = InpSessionStart;
   string end   = InpSessionEnd;
   string cur   = TimeToString(now, TIME_MINUTES);
   return(StringCompare(cur, start) >= 0 && StringCompare(cur, end) < 0);
}

//+------------------------------------------------------------------+
bool FilterAllowsSell()
{
   return(g_range_regime && g_no_structure && g_asia_session);
}

//+------------------------------------------------------------------+
int OnInit()
{
   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
void OnTick()
{
   //--- Research skeleton: state flags are wired by the AEGIS brain.
   //--- This block encodes the exact frozen filter and does NOT trade.
   if(FilterAllowsSell())
   {
      Comment("asia_sell_range: filter satisfied (research skeleton, no orders)");
   }
}
//+------------------------------------------------------------------+
"""


def _write_mql5_skeleton(promoted: dict[str, Any], path: Path) -> Path:
    body = MQL5_EA.format(
        promoted_at=datetime.now(timezone.utc).isoformat(),
        champion_id=promoted.get("id") or STRATEGY_ID,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Promote the Asia-session range sell strategy")
    parser.add_argument("--index", type=Path, default=BOT / "intel" / "analogue_index.json")
    parser.add_argument("--spec", type=Path, default=BOT / "research" / "strategies" / f"{STRATEGY_ID}_challenger.json")
    parser.add_argument("--report", type=Path, default=BOT / "reports" / "research" / "asia_sell_promotion.json")
    parser.add_argument("--champion", type=Path, default=BOT / "intel" / "intelligent_champion.json")
    parser.add_argument("--mql5", type=Path, default=BOT / "mql5" / "asia_sell_range_ea.mq5")
    args = parser.parse_args()

    spec = build_challenger_spec(args.index)
    spec_path = save_strategy_spec(spec, path=args.spec)

    try:
        result = challenger_promotion_result(
            strategy_id=str(spec["strategy_id"]),
            code_hash=str(spec.get("code_hash") or "unset"),
            artifact_hash=str(
                spec.get("artifact_hash")
                or hashlib.sha256(json.dumps(spec, sort_keys=True, default=str).encode()).hexdigest()
            ),
            config=dict(spec.get("config") or {}),
            validation_pnls=[float(x) for x in spec.get("validation_pnls", [])],
            holdout_metrics=dict(spec.get("holdout_metrics") or {}),
            holdout_pnls=[float(x) for x in spec.get("holdout_pnls", [])],
            validated_risk_fraction=float(spec["validated_risk_fraction"]),
            n_searches=int(spec.get("n_searches", 1) or 1),
            champion=spec.get("champion"),
            champion_path=args.champion,
        )
    except PromotionReject as exc:
        payload = {
            "status": "rejected",
            "schema": "champion_promotion.v1",
            "label": "research_proxy",
            "placed_orders": False,
            "mt5_touched": False,
            "promoted_live_yaml": False,
            "strategy_id": STRATEGY_ID,
            "reason": str(exc),
            "challenger_spec": str(spec_path),
        }
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        registry = ExperimentRegistry()
        row = {
            "id": f"promote_{STRATEGY_ID}_rejected_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
            "ts_utc": datetime.now(timezone.utc).isoformat(),
            "hypothesis": "Asia-session range sell (regime=range, structure=none) has positive "
                          "costed expectancy and survives a true time-split holdout.",
            "status": "rejected",
            "config_fingerprint": config_fingerprint(dict(CONFIG)),
            "dataset_fingerprint": "mt5_m1_analogue_index",
            "params": {
                "strategy_id": STRATEGY_ID,
                "label": "research_proxy",
                "strategy_implemented": False,
            },
            "metrics": {"n_trades": len(spec.get("holdout_pnls") or []), "win_rate": None},
            "provenance": {
                "rejection_reason": str(exc),
                "challenger_spec": str(spec_path),
                "mt5_touched": False,
                "placed_orders": False,
                "promoted_live_yaml": False,
            },
        }
        registry.record(row)
        print(
            json.dumps(
                {
                    "status": "rejected",
                    "strategy_id": STRATEGY_ID,
                    "reason": str(exc),
                    "report": str(args.report),
                    "experiment_id": row["id"],
                    "mt5_touched": False,
                    "placed_orders": False,
                    "promoted_live_yaml": False,
                },
                indent=2,
            )
        )
        return 1

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    args.report.with_suffix(".md").write_text(promotion_result_markdown(result), encoding="utf-8")

    champion = result["champion"]
    mql5_path = _write_mql5_skeleton(champion, args.mql5)

    registry = ExperimentRegistry()
    row = {
        "id": f"promote_{champion['id']}_{result['frozen']['frozen_hash'][:12]}",
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "hypothesis": "Asia-session range sell (regime=range, structure=none) has positive "
                      "costed expectancy and survives a true time-split holdout.",
        "status": "accepted",
        "config_fingerprint": config_fingerprint(dict(CONFIG)),
        "dataset_fingerprint": str(result["frozen"]["artifact_hash"]),
        "params": {
            "strategy_id": champion["id"],
            "label": "research_proxy",
            "strategy_implemented": True,
        },
        "metrics": {
            "n_trades": champion["n_trades"],
            "n_losses": champion["n_losses"],
            "expectancy": champion["expectancy"],
            "profit_factor": champion["profit_factor"],
            "win_rate": None,
        },
        "provenance": {
            "frozen_hash": result["frozen"]["frozen_hash"],
            "sealed_holdout": result["sealed_holdout"],
            "mql5_skeleton": str(mql5_path),
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
                "champion_id": champion["id"],
                "champion": str(args.champion),
                "spec": str(spec_path),
                "mql5_skeleton": str(mql5_path),
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