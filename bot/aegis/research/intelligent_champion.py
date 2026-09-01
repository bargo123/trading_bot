"""Intelligent Firehose champion pointer. Never writes CORE frozen_v1 or live YAML."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from aegis.intel.paths import INTEL_DIR, ensure_intel_dirs
from aegis.intel.strategy_model import ValidatedStrategyModel, strategy_model_ready

INTELLIGENT_CHAMPION_PATH = INTEL_DIR / "intelligent_champion.json"

STATE_KEYS = ("regime", "structure", "session", "side")


def state_sig(state: Mapping[str, Any]) -> frozenset[str]:
    """Normalise a state signature dict into a frozenset usable in allowed_states."""
    return frozenset((k, str(state.get(k) or "")) for k in STATE_KEYS)


def allowed_states_from_payload(payload: Mapping[str, Any]) -> frozenset[frozenset[str]]:
    states = payload.get("allowed_states") or []
    out = set()
    for item in states:
        if isinstance(item, Mapping):
            out.add(state_sig(item))
        elif isinstance(item, (list, tuple, frozenset, set)) and len(item) == len(STATE_KEYS):
            out.add(frozenset(str(x) for x in item))
    return frozenset(out)


def _allowed_states_to_payload(states: Iterable[frozenset[str]]) -> list[dict[str, str]]:
    rows = []
    for state in states:
        mapping = dict(state)
        rows.append({key: str(mapping.get(key) or "") for key in STATE_KEYS})
    return rows


def load_intelligent_champion(path: Path | None = None) -> dict[str, Any]:
    target = Path(path) if path is not None else INTELLIGENT_CHAMPION_PATH
    if not target.exists():
        return {"id": None, "status": "none", "role": "INTELLIGENT_FIREHOSE_CHAMPION"}
    return json.loads(target.read_text(encoding="utf-8"))


def save_intelligent_champion(
    model: ValidatedStrategyModel,
    *,
    path: Path | None = None,
) -> dict[str, Any]:
    ready, reason = strategy_model_ready(model)
    if not ready:
        raise ValueError(reason)
    ensure_intel_dirs()
    target = Path(path) if path is not None else INTELLIGENT_CHAMPION_PATH
    payload = {
        "id": model.strategy_id,
        "status": "accepted",
        "role": "INTELLIGENT_FIREHOSE_CHAMPION",
        "n_trades": model.n_trades,
        "n_losses": model.n_losses,
        "expectancy": model.expectancy,
        "profit_factor": model.profit_factor,
        "bootstrap_p05": model.bootstrap_p05,
        "wins_erased_by_average_loss": model.wins_erased_by_average_loss,
        "artifact_hash": model.artifact_hash,
        "validated_risk_fraction": model.validated_risk_fraction,
        "allowed_states": _allowed_states_to_payload(model.allowed_states),
    }
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def strategy_from_champion(payload: Mapping[str, Any] | None) -> ValidatedStrategyModel | None:
    """Rebuild a ready model from the intelligent-champion artifact. None if unready."""
    if not payload or str(payload.get("status") or "") != "accepted":
        return None
    try:
        model = ValidatedStrategyModel(
            strategy_id=str(payload.get("id") or ""),
            promoted=True,
            n_trades=int(payload["n_trades"]),
            n_losses=int(payload["n_losses"]),
            expectancy=float(payload["expectancy"]),
            profit_factor=float(payload["profit_factor"]),
            bootstrap_p05=float(payload.get("bootstrap_p05") or 0.0),
            wins_erased_by_average_loss=float(payload["wins_erased_by_average_loss"]),
            wins_erased_by_tail_loss=float(payload.get("wins_erased_by_tail_loss") or 0.0),
            validated_risk_fraction=payload.get("validated_risk_fraction"),
            artifact_hash=str(payload.get("artifact_hash") or ""),
            allowed_states=allowed_states_from_payload(payload),
        )
    except (KeyError, TypeError, ValueError):
        return None
    ready, _reason = strategy_model_ready(model)
    return model if ready else None
