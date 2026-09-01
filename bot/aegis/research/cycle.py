"""Shadow research cycle. Reads live artifacts; never controls the MT5 runner."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from aegis.research.champion import ChampionStore
from aegis.research.fingerprint import config_fingerprint
from aegis.research.gates import GateReject
from aegis.research.govern import governed_accept
from aegis.research.ingest import PROTECTED_LIVE_YAML, ingest_live_state
from aegis.research.registry import DuplicateExperimentError, EquivalentExperimentError


def run_research_cycle(
    *,
    hypothesis: str,
    metrics: dict[str, Any],
    pnls: list[float],
    frame_fingerprint: str,
    config: dict[str, Any],
    db_path: Path,
    heartbeat_path: Path | None = None,
    risk_path: Path | None = None,
    journal_path: Path | None = None,
    deals_path: Path | None = None,
    n_searches: int = 1,
    new_reason: str = "",
    worst_case_loss: float | None = None,
    live_config_name: str = PROTECTED_LIVE_YAML,
) -> dict[str, Any]:
    live = ingest_live_state(
        heartbeat_path=heartbeat_path or Path("_missing_hb"),
        risk_path=risk_path or Path("_missing_risk"),
        journal_path=journal_path,
        deals_path=deals_path,
    )
    store = ChampionStore(db_path)
    row = {
        "id": str(config.get("id") or metrics.get("id") or "exp_research"),
        "hypothesis": hypothesis,
        "config_fingerprint": config_fingerprint(config),
        "dataset_fingerprint": frame_fingerprint,
        "status": "open",
        "expectancy": float(metrics.get("expectancy") or metrics.get("expectancy_r") or 0.0),
        "profit_factor": metrics.get("profit_factor"),
        "n_trades": int(metrics.get("n_trades") or metrics.get("total_trades") or 0),
        "net_pnl": float(metrics.get("net_pnl") or 0.0),
        "win_rate": float(metrics.get("win_rate") or 0.0),
        "new_reason": new_reason,
    }
    decision = "rejected"
    reason = ""
    try:
        governed_accept(
            row,
            store.current(),
            pnls=pnls,
            n_searches=n_searches,
            worst_case_loss=worst_case_loss,
        )
        store.promote(row)
        decision = "accepted"
        reason = "holdout gates passed (shadow champion only)"
    except (GateReject, EquivalentExperimentError, ValueError) as exc:
        reason = str(exc)
        row["status"] = "rejected"
        row["rejection_reason"] = reason
        try:
            store.registry.record(row)
        except (EquivalentExperimentError, DuplicateExperimentError):
            pass
    return {
        "decision": decision,
        "reason": reason,
        "champion_id": None if store.current() is None else store.current().get("id"),
        "placed_orders": False,
        "mt5_touched": False,
        "promoted_live_yaml": False,
        "live_config_name": live_config_name,
        "refuses_live_yaml": live_config_name == PROTECTED_LIVE_YAML,
        "live": live,
    }
