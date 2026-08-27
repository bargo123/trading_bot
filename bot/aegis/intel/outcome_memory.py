"""Small, broker-confirmed state memory for entry-quality feedback.

This module is deliberately independent of order submission. It consumes only
completed lifecycle facts and can veto a future entry when a sufficiently similar
state has already produced a severe fast loser.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Mapping


DEFAULT_MIN_MFE_USD = 0.10
DEFAULT_FAST_LOSER_HORIZON_MULTIPLIER = 1.0
DEFAULT_SIMILARITY_THRESHOLD = 0.75


def _finite(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def classify_lifecycle(
    *,
    realized_net_usd: float,
    mfe_usd: float | None,
    mae_usd: float | None,
    time_to_green_s: float | None,
    selected_horizon_s: int | float | None,
    min_mfe_usd: float = DEFAULT_MIN_MFE_USD,
) -> dict[str, Any]:
    """Classify a completed lifecycle without using floating PnL as its result."""
    net = _finite(realized_net_usd)
    if net is None:
        raise ValueError("broker-confirmed realized net PnL is required")
    mfe_observed = _finite(mfe_usd)
    mfe = mfe_observed or 0.0
    mae = _finite(mae_usd) or 0.0
    green_s = _finite(time_to_green_s)
    horizon = max(1.0, _finite(selected_horizon_s) or 1.0)
    excursion_known = mfe_observed is not None or green_s is not None
    never_green = (
        None if not excursion_known else green_s is None or mfe <= 0.0
    )
    green_then_loser = (
        excursion_known and net <= 0.0 and mfe >= float(min_mfe_usd)
    )
    fast_loser = (
        net < 0.0
        and excursion_known
        and not green_then_loser
        and (
            bool(never_green)
            or (green_s is not None and green_s > horizon * DEFAULT_FAST_LOSER_HORIZON_MULTIPLIER)
        )
    )
    fast_winner = net > 0.0 and green_s is not None and green_s <= horizon

    if green_then_loser:
        classification = "GOOD_ENTRY_BAD_EXIT"
    elif net < 0.0 and excursion_known and never_green:
        classification = "BAD_ENTRY"
    elif net > 0.0:
        classification = "GOOD_ENTRY_GOOD_EXIT"
    else:
        classification = "AMBIGUOUS"

    return {
        "classification": classification,
        "speed_label": "FAST_LOSER" if fast_loser else "FAST_WINNER" if fast_winner else None,
        "never_green": never_green,
        "green_then_loser": green_then_loser,
        "realized_net_usd": net,
        "mfe_usd": mfe,
        "mae_usd": mae,
        "time_to_green_s": green_s,
        "selected_horizon_s": int(horizon),
    }


def _normalized_features(features: Mapping[str, Any]) -> dict[str, Any]:
    normalized = {
        "symbol": str(features.get("symbol") or "").upper(),
        "side": str(features.get("side") or "").lower(),
        "mechanism": str(features.get("mechanism") or features.get("family") or "").lower(),
        "horizon_s": int(_finite(features.get("horizon_s") or features.get("selected_horizon_s")) or 0),
        "session": str(features.get("session") or "").lower(),
        "regime": str(features.get("regime") or "").lower(),
        "volatility": str(features.get("volatility") or "").lower(),
    }
    return normalized


def _similarity(left: Mapping[str, Any], right: Mapping[str, Any]) -> float:
    weights = {
        "symbol": 0.20,
        "side": 0.15,
        "mechanism": 0.20,
        "horizon_s": 0.10,
        "session": 0.10,
        "regime": 0.15,
        "volatility": 0.10,
    }
    score = 0.0
    total = 0.0
    for key, weight in weights.items():
        value = left.get(key)
        other = right.get(key)
        if value in {None, "", 0} or other in {None, "", 0}:
            continue
        total += weight
        if key == "horizon_s":
            score += weight if int(value) == int(other) else 0.0
        else:
            score += weight if str(value) == str(other) else 0.0
    return score / total if total > 0 else 0.0


class OutcomeMemoryStore:
    """Persisted, normalized lifecycle memory; never an execution owner."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.records: list[dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        rows = payload.get("records") if isinstance(payload, dict) else payload
        if isinstance(rows, list):
            self.records = [row for row in rows if isinstance(row, dict)]

    def _persist(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"schema": "outcome_memory.v1", "records": self.records[-5000:]}
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(payload, default=str), encoding="utf-8")
        temp.replace(self.path)

    def record_closed(
        self,
        *,
        outcome_id: str,
        features: Mapping[str, Any],
        realized_net_usd: float,
        mfe_usd: float | None,
        mae_usd: float | None,
        time_to_green_s: float | None,
        counterfactuals: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        lifecycle = classify_lifecycle(
            realized_net_usd=realized_net_usd,
            mfe_usd=mfe_usd,
            mae_usd=mae_usd,
            time_to_green_s=time_to_green_s,
            selected_horizon_s=features.get("selected_horizon_s", features.get("horizon_s")),
        )
        row = {
            "outcome_id": str(outcome_id),
            "features": _normalized_features(features),
            **lifecycle,
            "counterfactuals": {
                "chosen_net_usd": float(realized_net_usd),
                "opposite_net_usd": None,
                "abstain_net_usd": None,
                "status": "UNAVAILABLE",
                **dict(counterfactuals or {}),
            },
        }
        self.records = [item for item in self.records if item.get("outcome_id") != row["outcome_id"]]
        self.records.append(row)
        self._persist()
        return row

    def similarity(self, features: Mapping[str, Any]) -> list[tuple[float, dict[str, Any]]]:
        query = _normalized_features(features)
        scored = [
            (_similarity(query, row.get("features") or {}), row)
            for row in self.records
        ]
        return sorted(scored, key=lambda item: item[0], reverse=True)

    def should_suppress(
        self,
        features: Mapping[str, Any],
        *,
        threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    ) -> bool:
        return any(
            score >= threshold
            and (
                row.get("speed_label") == "FAST_LOSER"
                or row.get("classification") == "BAD_ENTRY"
            )
            for score, row in self.similarity(features)
        )

    def snapshot(self) -> dict[str, Any]:
        return {
            "records": len(self.records),
            "fast_winner_count": sum(row.get("speed_label") == "FAST_WINNER" for row in self.records),
            "fast_loser_count": sum(row.get("speed_label") == "FAST_LOSER" for row in self.records),
            "bad_entry_count": sum(row.get("classification") == "BAD_ENTRY" for row in self.records),
            "good_entry_bad_exit_count": sum(
                row.get("classification") == "GOOD_ENTRY_BAD_EXIT" for row in self.records
            ),
            "counterfactual_status": "UNAVAILABLE" if any(
                (row.get("counterfactuals") or {}).get("status") == "UNAVAILABLE"
                for row in self.records
            ) else "NONE",
        }
