"""Asia-session range sell strategy: exact filter, evidence and promotion spec.

Research-only definition consumed by the promotion pipeline and the MQL5 EA
skeleton. Never trades; the exact filter is frozen here and mirrored in
``bot/mql5/asia_sell_range_ea.mq5``.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

BOT = Path(__file__).resolve().parents[2]
if str(BOT) not in sys.path:
    sys.path.insert(0, str(BOT))

from aegis.intel.expected_value import payoff_metrics  # noqa: E402
from aegis.research.fingerprint import config_fingerprint  # noqa: E402

STRATEGY_ID = "asia_sell_range"
SIDE = "sell"
CONFIG: dict[str, Any] = {
    "strategy": "asia_sell_range",
    "side": "sell",
    "regime": "range",
    "structure": "none",
    "session": "asia",
    "timeframe": "m1",
    "validated_risk_fraction": 0.01,
    "filters": {
        "regime": "range",
        "structure": "none",
        "session": "asia",
        "side": "sell",
        "h1_direction": "any",
        "m5_direction": "any",
        "volatility": "any",
    },
}


def asia_sell_range_matches(row: Mapping[str, Any]) -> bool:
    """Exact filter from the research proxy (mt5_m1 analogue index schema)."""
    return (
        str(row.get("regime") or "") == "range"
        and str(row.get("structure") or "") == "none"
        and str(row.get("session") or "") == "asia"
        and str(row.get("side") or "") == "sell"
    )


def _time_split_pnls(records: list[Mapping[str, Any]], validation_fraction: float = 0.7):
    rows = [row for row in records if asia_sell_range_matches(row)]
    rows.sort(key=lambda row: str(row.get("bar_time") or ""))
    split = int(len(rows) * validation_fraction)
    validation_pnls = [float(row["outcome"]) for row in rows[:split]]
    holdout_pnls = [float(row["outcome"]) for row in rows[split:]]
    return validation_pnls, holdout_pnls


def build_challenger_spec(
    index_path: Path,
    *,
    validation_fraction: float = 0.7,
    n_searches: int = 1,
) -> dict[str, Any]:
    payload = json.loads(Path(index_path).read_text(encoding="utf-8"))
    records = payload.get("records") or []
    validation_pnls, holdout_pnls = _time_split_pnls(records, validation_fraction)
    metrics = payoff_metrics(holdout_pnls)
    spec = {
        "strategy_id": STRATEGY_ID,
        "code_hash": config_fingerprint({"strategy_code": "asia_sell_range_matches:v1"}),
        "config": CONFIG,
        "validation_pnls": validation_pnls,
        "holdout_pnls": holdout_pnls,
        "holdout_metrics": {
            "expectancy": metrics.get("expectancy"),
            "profit_factor": metrics.get("profit_factor"),
            "n_trades": metrics.get("n"),
            "net_pnl": metrics.get("net_pnl"),
            "win_rate": metrics.get("win_rate"),
            "avg_win": metrics.get("avg_win"),
            "avg_loss": metrics.get("avg_loss"),
            "tail_loss": metrics.get("tail_loss"),
        },
        "validated_risk_fraction": CONFIG["validated_risk_fraction"],
        "n_searches": n_searches,
        "champion": None,
        "label": "research_proxy",
        "built_at": datetime.now(timezone.utc).isoformat(),
    }
    return spec


def strategy_spec_path() -> Path:
    return BOT / "research" / "strategies" / f"{STRATEGY_ID}.json"


def save_strategy_spec(spec: Mapping[str, Any], path: Path | None = None) -> Path:
    target = Path(path) if path is not None else strategy_spec_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(dict(spec), indent=2, default=str), encoding="utf-8")
    return target