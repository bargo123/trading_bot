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
    for key in (
        "structure", "h1_direction", "m5_direction", "breakout_state",
        "rejection_state", "expansion_state", "session_phase", "source",
    ):
        if features.get(key) is not None:
            normalized[key] = str(features.get(key) or "").lower()
    for key in (
        "entry_ev", "authority_probability", "authority_capture_lcb95",
        "spread_pips", "stop_pips", "target_pips", "momentum", "compression",
        "expansion", "volatility_value", "quote_age_s", "time_to_green_s",
        "mfe_usd", "mae_usd", "hold_s",
    ):
        value = _finite(features.get(key))
        if value is not None:
            normalized[key] = value
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
        "structure": 0.06,
        "h1_direction": 0.04,
        "m5_direction": 0.04,
        "momentum": 0.04,
        "compression": 0.03,
        "spread_pips": 0.03,
        "stop_pips": 0.02,
        "target_pips": 0.02,
    }
    score = 0.0
    total = 0.0
    for key, weight in weights.items():
        value = left.get(key)
        other = right.get(key)
        if value in {None, "", 0} or other in {None, "", 0}:
            continue
        if key in {"momentum", "compression", "spread_pips", "stop_pips", "target_pips"}:
            try:
                left_value = float(value)
                right_value = float(other)
            except (TypeError, ValueError):
                continue
            scale = max(abs(left_value), abs(right_value), 1.0)
            score += weight * max(0.0, 1.0 - abs(left_value - right_value) / scale)
            total += weight
        elif key == "horizon_s":
            score += weight if int(value) == int(other) else 0.0
            total += weight
        else:
            score += weight if str(value) == str(other) else 0.0
            total += weight
    return score / total if total > 0 else 0.0


def replay_counterfactual(
    *,
    quotes: list[Mapping[str, Any]],
    entry_time: float,
    side: str,
    stop: float,
    target: float,
    horizon_s: float,
    cost_usd: float = 0.0,
    usd_per_price_unit: float = 1.0,
) -> dict[str, Any]:
    """Replay one chosen side using sequential executable bid/ask quotes.

    This is an evidence adapter for learning only. It never submits an order and
    refuses incomplete or non-directional geometry.
    """
    normalized_side = str(side or "").lower()
    try:
        start = float(entry_time)
        stop_price = float(stop)
        target_price = float(target)
        horizon = float(horizon_s)
        unit_value = float(usd_per_price_unit)
        cost = float(cost_usd)
    except (TypeError, ValueError, OverflowError):
        return {"status": "UNAVAILABLE", "reason": "counterfactual_inputs_invalid"}
    if normalized_side not in {"buy", "sell"} or not all(
        math.isfinite(value) for value in (start, stop_price, target_price, horizon, unit_value, cost)
    ) or horizon <= 0 or unit_value <= 0 or cost < 0:
        return {"status": "UNAVAILABLE", "reason": "counterfactual_inputs_invalid"}
    if (
        normalized_side == "buy" and not stop_price < target_price
        or normalized_side == "sell" and not target_price < stop_price
    ):
        return {"status": "UNAVAILABLE", "reason": "counterfactual_geometry_invalid"}
    sign = 1.0 if normalized_side == "buy" else -1.0
    rows: list[tuple[float, float, float]] = []
    for row in quotes:
        try:
            timestamp = float(row.get("timestamp", row.get("time")))
            bid = float(row["bid"])
            ask = float(row["ask"])
        except (AttributeError, KeyError, TypeError, ValueError, OverflowError):
            continue
        if (
            math.isfinite(timestamp) and math.isfinite(bid) and math.isfinite(ask)
            and bid > 0 and ask >= bid and start <= timestamp <= start + horizon
        ):
            rows.append((timestamp, bid, ask))
    rows.sort(key=lambda item: item[0])
    if not rows:
        return {"status": "UNAVAILABLE", "reason": "counterfactual_quote_history_missing"}
    entry_price = rows[0][2] if normalized_side == "buy" else rows[0][1]
    if (
        normalized_side == "buy" and not stop_price < entry_price < target_price
        or normalized_side == "sell" and not target_price < entry_price < stop_price
    ):
        return {"status": "UNAVAILABLE", "reason": "counterfactual_geometry_invalid"}
    close_price = None
    close_timestamp = None
    close_reason = "timeout"
    for timestamp, bid, ask in rows[1:]:
        liquidation = bid if normalized_side == "buy" else ask
        move = (liquidation - entry_price) * sign
        if move >= (target_price - entry_price) * sign:
            close_price, close_timestamp, close_reason = liquidation, timestamp, "target"
            break
        if move <= (stop_price - entry_price) * sign:
            close_price, close_timestamp, close_reason = liquidation, timestamp, "stop"
            break
    if close_price is None:
        _, bid, ask = rows[-1]
        close_price = bid if normalized_side == "buy" else ask
        close_timestamp = rows[-1][0]
    gross = (float(close_price) - entry_price) * sign * unit_value
    net = gross - cost
    return {
        "status": "REPLAYED",
        "chosen_net_usd": net,
        "chosen_gross_usd": gross,
        "chosen_entry_price": entry_price,
        "chosen_close_price": float(close_price),
        "chosen_close_timestamp": close_timestamp,
        "chosen_close_reason": close_reason,
        "opposite_net_usd": None,
        "abstain_net_usd": 0.0,
        "opposite_status": "UNAVAILABLE_NO_OPPOSITE_GEOMETRY",
        "cost_usd": cost,
    }


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
        counterfactual_quotes: list[Mapping[str, Any]] | None = None,
        counterfactual_cost_usd: float = 0.0,
        counterfactual_usd_per_price_unit: float = 1.0,
    ) -> dict[str, Any]:
        lifecycle = classify_lifecycle(
            realized_net_usd=realized_net_usd,
            mfe_usd=mfe_usd,
            mae_usd=mae_usd,
            time_to_green_s=time_to_green_s,
            selected_horizon_s=features.get("selected_horizon_s", features.get("horizon_s")),
        )
        replay = None
        if counterfactual_quotes is not None:
            replay = replay_counterfactual(
                quotes=counterfactual_quotes,
                entry_time=float(features.get("entry_time", 0.0) or 0.0),
                side=str(features.get("side") or ""),
                stop=features.get("stop_price"),
                target=features.get("target_price"),
                horizon_s=features.get("horizon_s"),
                cost_usd=counterfactual_cost_usd,
                usd_per_price_unit=counterfactual_usd_per_price_unit,
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
                **(
                    replay if replay is not None and replay.get("status") == "REPLAYED"
                    else {"status": replay.get("status"), "reason": replay.get("reason")}
                    if replay is not None else {}
                ),
            },
        }
        self.records = [item for item in self.records if item.get("outcome_id") != row["outcome_id"]]
        self.records.append(row)
        self._persist()
        return row

    def import_prior_autopsy(self, report_path: Path) -> dict[str, int]:
        """Reconstruct only explicitly complete prior-trade observations.

        The historical autopsy often lacks entry geometry and horizon identity.
        Those rows are useful for aggregate winner/loser research, but are not
        allowed to suppress a future state without that identity. Partial rows
        are counted and skipped rather than filled with guessed values.
        """
        try:
            payload = json.loads(Path(report_path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"imported": 0, "skipped": 0, "unavailable": 1}
        rows = payload.get("trades") if isinstance(payload, Mapping) else None
        if not isinstance(rows, list):
            return {"imported": 0, "skipped": 0, "unavailable": 1}
        imported = skipped = 0
        for item in rows:
            if not isinstance(item, Mapping) or str(item.get("evidence_status") or "") != "COMPLETE":
                skipped += 1
                continue
            outcome_id = str(item.get("ticket") or "").strip()
            symbol = str(item.get("symbol") or "").strip()
            side = str(item.get("side") or "").strip().lower()
            pnl = _finite(item.get("pnl"))
            if not outcome_id or not symbol or side not in {"buy", "sell"} or pnl is None:
                skipped += 1
                continue
            self.record_closed(
                outcome_id=f"prior_autopsy:{outcome_id}",
                features={
                    "symbol": symbol,
                    "side": side,
                    "source": "prior_autopsy",
                    "hold_s": item.get("hold_s"),
                    "time_to_green_s": item.get("time_to_green_s"),
                    "mfe_usd": item.get("mfe_usd"),
                    "mae_usd": item.get("mae_usd"),
                },
                realized_net_usd=pnl,
                mfe_usd=item.get("mfe_usd"),
                mae_usd=item.get("mae_usd"),
                time_to_green_s=item.get("time_to_green_s"),
            )
            imported += 1
        return {"imported": imported, "skipped": skipped, "unavailable": 0}

    def similarity(self, features: Mapping[str, Any]) -> list[tuple[float, dict[str, Any]]]:
        query = _normalized_features(features)
        scored = [
            (_similarity(query, row.get("features") or {}), row)
            for row in self.records
        ]
        return sorted(scored, key=lambda item: item[0], reverse=True)

    def similarity_summary(self, features: Mapping[str, Any]) -> dict[str, Any]:
        """Return winner/loser state similarity used by ranking and suppression."""
        scored = self.similarity(features)
        winners = [
            score for score, row in scored
            if row.get("speed_label") == "FAST_WINNER"
            or row.get("classification") == "GOOD_ENTRY_GOOD_EXIT"
        ]
        losers = [
            score for score, row in scored
            if row.get("speed_label") == "FAST_LOSER"
            or row.get("classification") == "BAD_ENTRY"
        ]
        return {
            "winner_similarity": max(winners, default=0.0),
            "loser_similarity": max(losers, default=0.0),
            "winner_count": len(winners),
            "loser_count": len(losers),
        }

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
            and not (
                str((row.get("features") or {}).get("source") or "") == "prior_autopsy"
                and (
                    not str((row.get("features") or {}).get("mechanism") or "")
                    or int((row.get("features") or {}).get("horizon_s") or 0) <= 0
                )
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
