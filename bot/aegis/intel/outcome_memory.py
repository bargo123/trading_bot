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


def _json_safe(value: Any) -> Any:
    """Copy observed state without manufacturing values for unsupported data."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return None


def classify_lifecycle(
    *,
    realized_net_usd: float,
    mfe_usd: float | None,
    mae_usd: float | None,
    time_to_green_s: float | None,
    selected_horizon_s: int | float | None,
    min_mfe_usd: float = DEFAULT_MIN_MFE_USD,
    expected_initial_friction_usd: float = 0.0,
) -> dict[str, Any]:
    """Classify a completed lifecycle without using floating PnL as its result."""
    net = _finite(realized_net_usd)
    if net is None:
        raise ValueError("broker-confirmed realized net PnL is required")
    mfe_observed = _finite(mfe_usd)
    mfe = mfe_observed or 0.0
    mae = _finite(mae_usd) or 0.0
    expected_friction = max(0.0, _finite(expected_initial_friction_usd) or 0.0)
    adverse_beyond_friction = max(0.0, -mae - expected_friction)
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
            adverse_beyond_friction > 1e-12
            and (
                bool(never_green)
            or (green_s is not None and green_s > horizon * DEFAULT_FAST_LOSER_HORIZON_MULTIPLIER)
            )
        )
    )
    fast_winner = net > 0.0 and green_s is not None and green_s <= horizon

    if green_then_loser:
        classification = "GOOD_ENTRY_BAD_EXIT"
    elif net < 0.0 and excursion_known and never_green and adverse_beyond_friction > 1e-12:
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
        "expected_initial_friction_usd": expected_friction,
        "adverse_excursion_beyond_expected_friction_usd": adverse_beyond_friction,
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
        "p_captured_win", "spread_pips", "stop_pips", "target_pips", "momentum",
        "compression", "expansion", "volatility_value", "quote_age_s",
        "quote_change_rate", "tick_rate_per_min", "short_volatility",
        "signed_tick_imbalance", "return_3s", "return_5s", "return_8s",
        "return_10s", "return_15s", "return_20s", "return_30s", "return_60s",
        "return_3s_buy", "return_3s_sell", "return_5s_buy", "return_5s_sell",
        "return_15s_buy", "return_15s_sell", "return_30s_buy", "return_30s_sell",
        "return_60s_buy", "return_60s_sell", "m1_open", "m1_high", "m1_low",
        "m1_close", "m1_prev_close", "m1_atr", "m1_volume", "m1_range", "m1_body",
        "m5_support", "m5_resistance", "m5_atr", "m5_compression",
        "m15_support", "m15_resistance", "m15_range_mid", "m15_range_half_width",
        "expected_initial_friction_usd",
    ):
        value = _finite(features.get(key))
        if value is not None:
            normalized[key] = value
    return normalized


def _state_key(features: Mapping[str, Any]) -> str:
    """Identify a pre-entry state, never including post-entry outcome fields."""
    normalized = _normalized_features(features)
    normalized.pop("source", None)
    return json.dumps(normalized, sort_keys=True, separators=(",", ":"))


def _same_state_identity(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    required = ("symbol", "side", "mechanism", "horizon_s")
    return all(
        left.get(key) not in {None, "", 0}
        and right.get(key) not in {None, "", 0}
        and str(left.get(key)) == str(right.get(key))
        for key in required
    )


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
    from aegis.intel.trade_controller import TradeController
    entry_spread = max(rows[0][2] - rows[0][1], 1e-12)

    replay = TradeController().replay_quote_path(
        quotes=[{"time": timestamp, "bid": bid, "ask": ask} for timestamp, bid, ask in rows],
        side=normalized_side,
        horizon_s=horizon,
        target_price=target_price,
        stop_price=stop_price,
        pip_size=entry_spread,
        commission_usd=cost,
        usd_per_price_unit=unit_value,
    )
    if replay.get("status") != "REPLAYED":
        return {"status": "UNAVAILABLE", "reason": "counterfactual_quote_history_missing"}
    actions = list(replay.get("actions") or [])
    close_action = str(replay.get("captured_exit_action") or "TIMEOUT")
    close_time_s = float(replay.get("captured_exit_time_s") or 0.0)
    close_row = min(rows, key=lambda item: abs(item[0] - (start + close_time_s)))
    close_price = close_row[1] if normalized_side == "buy" else close_row[2]
    gross = (float(close_price) - entry_price) * sign * unit_value
    return {
        "status": "REPLAYED",
        "chosen_net_usd": float(replay["captured_exit_net_pnl"]),
        "chosen_gross_usd": gross,
        "chosen_entry_price": entry_price,
        "chosen_close_price": float(close_price),
        "chosen_close_timestamp": close_row[0],
        "chosen_close_reason": (
            "target" if close_action == "HARVEST"
            else "timeout" if close_action == "TIMEOUT"
            else "stop"
        ),
        "opposite_net_usd": None,
        "abstain_net_usd": 0.0,
        "opposite_status": "UNAVAILABLE_NO_OPPOSITE_GEOMETRY",
        "cost_usd": cost,
        "controller_actions": actions,
    }


def replay_counterfactuals(
    *,
    quotes: list[Mapping[str, Any]],
    entry_time: float,
    actual_side: str,
    actual_stop: object,
    actual_target: object,
    actual_horizon_s: float,
    counterfactual_geometries: Mapping[str, Mapping[str, Any]] | None = None,
    alternative_horizons_s: tuple[int, ...] | list[int] | None = None,
    cost_usd: float = 0.0,
    usd_per_price_unit: float = 1.0,
) -> dict[str, Any]:
    """Replay both directions and alternate time horizons using observed quotes.

    The caller invokes this only after a confirmed close.  An opposite-side
    replay is deliberately unavailable unless its geometry was observed or
    supplied explicitly; this prevents the learner from inventing a stop or
    target after the fact.
    """
    side = str(actual_side or "").strip().lower()
    geometries = dict(counterfactual_geometries or {})
    results: dict[str, Any] = {}
    for candidate_side in ("buy", "sell"):
        geometry = {
            "stop_price": actual_stop,
            "target_price": actual_target,
        } if candidate_side == side else geometries.get(candidate_side)
        if not isinstance(geometry, Mapping):
            results[f"what_if_{candidate_side}"] = {
                "status": "UNAVAILABLE",
                "reason": "counterfactual_geometry_missing",
                "side": candidate_side,
            }
            continue
        replay = replay_counterfactual(
            quotes=quotes,
            entry_time=entry_time,
            side=candidate_side,
            stop=geometry.get("stop_price", geometry.get("stop")),
            target=geometry.get("target_price", geometry.get("target")),
            horizon_s=actual_horizon_s,
            cost_usd=cost_usd,
            usd_per_price_unit=usd_per_price_unit,
        )
        results[f"what_if_{candidate_side}"] = {
            "side": candidate_side,
            "horizon_s": int(float(actual_horizon_s)),
            **replay,
            "net_pnl_usd": replay.get("chosen_net_usd"),
        }

    results["what_if_abstain"] = {"status": "NO_TRADE", "net_pnl_usd": 0.0}
    alternatives: dict[str, Any] = {}
    horizons = alternative_horizons_s
    if horizons is None:
        horizons = (1, 2, 3, 5, 8, 10, 15, 20)
    try:
        actual_horizon = int(float(actual_horizon_s))
    except (TypeError, ValueError, OverflowError):
        actual_horizon = 0
    actual_geometry = {"stop_price": actual_stop, "target_price": actual_target}
    for raw_horizon in horizons:
        try:
            horizon = int(raw_horizon)
        except (TypeError, ValueError, OverflowError):
            continue
        if horizon <= 0 or horizon == actual_horizon:
            continue
        replay = replay_counterfactual(
            quotes=quotes,
            entry_time=entry_time,
            side=side,
            stop=actual_geometry["stop_price"],
            target=actual_geometry["target_price"],
            horizon_s=horizon,
            cost_usd=cost_usd,
            usd_per_price_unit=usd_per_price_unit,
        )
        alternatives[str(horizon)] = {
            "side": side,
            "horizon_s": horizon,
            **replay,
            "net_pnl_usd": replay.get("chosen_net_usd"),
        }
    results["alternative_horizons"] = alternatives
    return results


class OutcomeMemoryStore:
    """Persisted, normalized lifecycle memory; never an execution owner."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.records: list[dict[str, Any]] = []
        self.pending: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        rows = payload.get("records") if isinstance(payload, dict) else payload
        if isinstance(rows, list):
            self.records = [row for row in rows if isinstance(row, dict)]
        if isinstance(payload, dict) and isinstance(payload.get("pending"), dict):
            self.pending = {
                str(key): dict(value)
                for key, value in payload["pending"].items()
                if isinstance(value, dict)
            }

    def repair_broker_position_identity(
        self,
        identities: Mapping[str, Mapping[str, Any]],
    ) -> int:
        """Repair side/symbol from exact broker entry identity.

        MT5 exit DEALs report the closing action, not the original position
        side.  This migration changes only confirmed rows whose exact broker
        entry identity is supplied; realized net PnL and lifecycle labels are
        deliberately untouched.
        """
        changed = 0
        for row in self.records:
            if str(row.get("evidence_status") or "") != "BROKER_CONFIRMED":
                continue
            identity = identities.get(str(row.get("outcome_id") or ""))
            if not isinstance(identity, Mapping):
                continue
            symbol = str(identity.get("symbol") or "").strip().upper()
            side = str(identity.get("side") or "").strip().lower()
            if not symbol or side not in {"buy", "sell"}:
                continue
            features = dict(row.get("features") or {})
            pre_entry_state = dict(row.get("pre_entry_state") or {})
            broker_facts = dict(row.get("broker_facts") or {})
            row_changed = (
                features.get("symbol") != symbol
                or features.get("side") != side
                or pre_entry_state.get("symbol") != symbol
                or pre_entry_state.get("side") != side
                or broker_facts.get("position_symbol") != symbol
                or broker_facts.get("position_side") != side
            )
            if not row_changed:
                continue
            features.update({"symbol": symbol, "side": side})
            pre_entry_state.update({"symbol": symbol, "side": side})
            broker_facts.update({"position_symbol": symbol, "position_side": side})
            row["features"] = features
            row["pre_entry_state"] = pre_entry_state
            row["state_key"] = _state_key(features)
            row["broker_facts"] = broker_facts
            changed += 1
        if changed:
            self._persist()
        return changed

    def _persist(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema": "outcome_memory.v2",
            "records": self.records[-5000:],
            "pending": self.pending,
        }
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
        counterfactual_geometries: Mapping[str, Mapping[str, Any]] | None = None,
        alternative_horizons_s: tuple[int, ...] | list[int] | None = None,
        broker_facts: Mapping[str, Any] | None = None,
        evidence_status: str | None = None,
        exit_reason: str | None = None,
    ) -> dict[str, Any]:
        """Store one completed observation; production uses ``record_confirmed_close``."""
        lifecycle = classify_lifecycle(
            realized_net_usd=realized_net_usd,
            mfe_usd=mfe_usd,
            mae_usd=mae_usd,
            time_to_green_s=time_to_green_s,
            selected_horizon_s=features.get("selected_horizon_s") or features.get("horizon_s"),
            expected_initial_friction_usd=features.get("expected_initial_friction_usd", 0.0),
        )
        replay = None
        replay_set: dict[str, Any] = {}
        if counterfactual_quotes is not None:
            replay = replay_counterfactual(
                quotes=counterfactual_quotes,
                entry_time=float(features.get("entry_time", 0.0) or 0.0),
                side=str(features.get("side") or ""),
                stop=features.get("stop_price"),
                target=features.get("target_price"),
                horizon_s=features.get("selected_horizon_s") or features.get("horizon_s"),
                cost_usd=counterfactual_cost_usd,
                usd_per_price_unit=counterfactual_usd_per_price_unit,
            )
            replay_set = replay_counterfactuals(
                quotes=counterfactual_quotes,
                entry_time=float(features.get("entry_time", 0.0) or 0.0),
                actual_side=str(features.get("side") or ""),
                actual_stop=features.get("stop_price"),
                actual_target=features.get("target_price"),
                actual_horizon_s=(
                    features.get("selected_horizon_s") or features.get("horizon_s")
                ),
                counterfactual_geometries=counterfactual_geometries,
                alternative_horizons_s=alternative_horizons_s,
                cost_usd=counterfactual_cost_usd,
                usd_per_price_unit=counterfactual_usd_per_price_unit,
            )
        safe_state = _json_safe(dict(features))
        if not isinstance(safe_state, dict):
            safe_state = {}
        observed_broker_facts = (
            _json_safe(dict(broker_facts))
            if isinstance(broker_facts, Mapping) else None
        )
        cf_payload = dict(_json_safe(dict(counterfactuals or {})) or {})
        cf_payload.update({
            "chosen_net_usd": float(realized_net_usd),
            "opposite_net_usd": None,
            "abstain_net_usd": None,
            "status": "UNAVAILABLE",
        })
        if replay is not None:
            cf_payload.update(replay)
            if replay.get("status") != "REPLAYED":
                cf_payload["reason"] = replay.get("reason")
        cf_payload.update(replay_set)
        row = {
            "outcome_id": str(outcome_id),
            "features": _normalized_features(features),
            "pre_entry_state": safe_state,
            "state_key": _state_key(features),
            **lifecycle,
            "lifecycle_labels": [
                label for label, enabled in (
                    (lifecycle.get("speed_label"), lifecycle.get("speed_label") is not None),
                    ("NEVER_GREEN", lifecycle.get("never_green") is True),
                    ("GREEN_THEN_LOSER", lifecycle.get("green_then_loser") is True),
                ) if enabled and label
            ],
            "exit_reason": str(exit_reason or "") or None,
            "evidence_status": str(evidence_status or (
                "BROKER_CONFIRMED" if observed_broker_facts is not None else "UNVERIFIED"
            )),
            "broker_facts": observed_broker_facts,
            "counterfactuals": cf_payload,
        }
        self.records = [item for item in self.records if item.get("outcome_id") != row["outcome_id"]]
        self.records.append(row)
        self._persist()
        return row

    def stage_pending_close(
        self,
        *,
        outcome_id: str,
        features: Mapping[str, Any],
        mfe_usd: float | None,
        mae_usd: float | None,
        time_to_green_s: float | None,
        counterfactual_quotes: list[Mapping[str, Any]] | None = None,
        counterfactual_geometries: Mapping[str, Mapping[str, Any]] | None = None,
        alternative_horizons_s: tuple[int, ...] | list[int] | None = None,
        counterfactual_cost_usd: float = 0.0,
        counterfactual_usd_per_price_unit: float = 1.0,
        exit_reason: str | None = None,
    ) -> dict[str, Any]:
        """Keep close context until delayed broker deal history is available."""
        self.pending[str(outcome_id)] = {
            "features": _json_safe(dict(features)),
            "mfe_usd": mfe_usd,
            "mae_usd": mae_usd,
            "time_to_green_s": time_to_green_s,
            "counterfactual_quotes": _json_safe(counterfactual_quotes),
            "counterfactual_geometries": _json_safe(counterfactual_geometries),
            "alternative_horizons_s": _json_safe(alternative_horizons_s),
            "counterfactual_cost_usd": counterfactual_cost_usd,
            "counterfactual_usd_per_price_unit": counterfactual_usd_per_price_unit,
            "exit_reason": exit_reason,
        }
        self._persist()
        return {"status": "PENDING", "outcome_id": str(outcome_id)}

    def record_confirmed_close(
        self,
        *,
        outcome_id: str,
        features: Mapping[str, Any],
        broker_facts: Mapping[str, Any],
        mfe_usd: float | None,
        mae_usd: float | None,
        time_to_green_s: float | None,
        counterfactual_quotes: list[Mapping[str, Any]] | None = None,
        counterfactual_geometries: Mapping[str, Mapping[str, Any]] | None = None,
        alternative_horizons_s: tuple[int, ...] | list[int] | None = None,
        counterfactual_cost_usd: float = 0.0,
        counterfactual_usd_per_price_unit: float = 1.0,
        exit_reason: str | None = None,
    ) -> dict[str, Any]:
        """Train exactly once from broker-confirmed realized net PnL."""
        if not isinstance(broker_facts, Mapping) or not (
            broker_facts.get("confirmed") is True
            or str(broker_facts.get("status") or "") == "BROKER_CONFIRMED"
        ):
            return {
                "status": "SKIPPED",
                "reason": "broker_confirmation_required",
                "outcome_id": str(outcome_id),
            }
        net = _finite(broker_facts.get("realized_net_usd"))
        if net is None:
            return {
                "status": "SKIPPED",
                "reason": "broker_realized_net_pnl_missing",
                "outcome_id": str(outcome_id),
            }
        existing = next(
            (row for row in reversed(self.records)
             if str(row.get("outcome_id") or "") == str(outcome_id)
             and row.get("evidence_status") == "BROKER_CONFIRMED"),
            None,
        )
        if existing is not None:
            self.pending.pop(str(outcome_id), None)
            self._persist()
            return existing
        pending = self.pending.get(str(outcome_id)) or {}
        pending_features = pending.get("features")
        merged_features = dict(features) if isinstance(features, Mapping) else {}
        if isinstance(pending_features, Mapping):
            # A delayed deal row is often sparse; never let it erase the exact
            # pre-entry snapshot captured before the broker mutation.
            merged_features = {**merged_features, **dict(pending_features)}
        row = self.record_closed(
            outcome_id=str(outcome_id),
            features=merged_features,
            realized_net_usd=net,
            mfe_usd=(mfe_usd if mfe_usd is not None else pending.get("mfe_usd")),
            mae_usd=(mae_usd if mae_usd is not None else pending.get("mae_usd")),
            time_to_green_s=(
                time_to_green_s
                if time_to_green_s is not None else pending.get("time_to_green_s")
            ),
            counterfactual_quotes=(
                counterfactual_quotes
                if counterfactual_quotes
                else pending.get("counterfactual_quotes")
            ),
            counterfactual_geometries=(
                counterfactual_geometries
                if counterfactual_geometries
                else pending.get("counterfactual_geometries")
            ),
            alternative_horizons_s=(
                alternative_horizons_s
                if alternative_horizons_s is not None
                else pending.get("alternative_horizons_s")
            ),
            counterfactual_cost_usd=(
                counterfactual_cost_usd
                if counterfactual_cost_usd else pending.get("counterfactual_cost_usd", 0.0)
            ),
            counterfactual_usd_per_price_unit=(
                counterfactual_usd_per_price_unit
                if counterfactual_usd_per_price_unit != 1.0
                else pending.get("counterfactual_usd_per_price_unit", 1.0)
            ),
            exit_reason=(
                exit_reason
                if exit_reason is not None else pending.get("exit_reason")
            ),
            broker_facts=broker_facts,
            evidence_status="BROKER_CONFIRMED",
        )
        self.pending.pop(str(outcome_id), None)
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

    def import_historical_confirmed_trades(self, source_path: Path) -> dict[str, int]:
        """Import only rows carrying explicit broker-confirmed net PnL."""
        path = Path(source_path)
        try:
            if path.suffix.lower() == ".jsonl":
                rows = [
                    json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
                    if line.strip()
                ]
            else:
                payload = json.loads(path.read_text(encoding="utf-8"))
                rows = (
                    payload.get("trades", payload.get("outcomes", []))
                    if isinstance(payload, Mapping) else payload
                )
        except (OSError, json.JSONDecodeError):
            return {"imported": 0, "skipped": 0, "unavailable": 1}
        if not isinstance(rows, list):
            return {"imported": 0, "skipped": 0, "unavailable": 1}

        imported = skipped = 0
        for item in rows:
            if not isinstance(item, Mapping):
                skipped += 1
                continue
            nested = item.get("broker_facts")
            facts = dict(nested) if isinstance(nested, Mapping) else {}
            explicitly_confirmed = (
                str(item.get("evidence_status") or "") == "BROKER_CONFIRMED"
                or item.get("broker_confirmed") is True
                or facts.get("confirmed") is True
            )
            if not explicitly_confirmed:
                skipped += 1
                continue
            if "realized_net_usd" not in facts and item.get("realized_net_usd") is not None:
                facts["realized_net_usd"] = item.get("realized_net_usd")
            net = _finite(facts.get("realized_net_usd"))
            outcome_id = str(
                item.get("position_id")
                or item.get("position")
                or item.get("ticket")
                or item.get("outcome_id")
                or ""
            ).strip()
            if not outcome_id or net is None:
                skipped += 1
                continue
            facts.setdefault("status", "BROKER_CONFIRMED")
            facts.setdefault("confirmed", True)
            state = item.get("pre_entry_state")
            if not isinstance(state, Mapping):
                state = item.get("features")
            if not isinstance(state, Mapping):
                state = {
                    key: item[key] for key in (
                        "symbol", "side", "mechanism", "horizon_s", "session", "regime",
                    ) if key in item
                }
            result = self.record_confirmed_close(
                outcome_id=outcome_id,
                features=state,
                broker_facts=facts,
                mfe_usd=item.get("mfe_usd"),
                mae_usd=item.get("mae_usd"),
                time_to_green_s=item.get("time_to_green_s"),
            )
            if result.get("evidence_status") == "BROKER_CONFIRMED":
                imported += 1
            else:
                skipped += 1
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
            **self.state_feedback(features),
        }

    def state_feedback(
        self,
        features: Mapping[str, Any],
        *,
        threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    ) -> dict[str, Any]:
        """Return repeated-state reward/penalty without symbol-only learning."""
        query = _normalized_features(features)
        matches = [
            (score, row) for score, row in self.similarity(features)
            if score >= threshold and _same_state_identity(query, row.get("features") or {})
        ]
        loser_count = sum(
            row.get("speed_label") == "FAST_LOSER" for _score, row in matches
        )
        winner_count = sum(
            row.get("speed_label") == "FAST_WINNER" for _score, row in matches
        )
        broker_negative_net_count = sum(
            row.get("evidence_status") == "BROKER_CONFIRMED"
            and (_finite(row.get("realized_net_usd")) or 0.0) < 0.0
            for _score, row in matches
        )
        return {
            "fast_loser_count": loser_count,
            "fast_winner_count": winner_count,
            "loser_penalty": min(1.0, 0.35 * loser_count),
            "winner_bonus": min(1.0, 0.20 * winner_count),
            # Broker net PnL remains useful even when excursion telemetry is
            # unavailable.  This is a score penalty, not a hard blacklist;
            # exact identity prevents one loss from poisoning a symbol.
            "broker_negative_net_count": broker_negative_net_count,
            "broker_negative_net_penalty": min(
                1.0, 0.35 * broker_negative_net_count
            ),
        }

    def should_suppress(
        self,
        features: Mapping[str, Any],
        *,
        threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    ) -> bool:
        return any(
            score >= threshold
            and _same_state_identity(
                _normalized_features(features), row.get("features") or {}
            )
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
        counterfactual_rows = [
            row.get("counterfactuals") or {} for row in self.records
        ]
        counterfactual_available = any(
            any(
                isinstance(value, Mapping) and value.get("status") == "REPLAYED"
                for key, value in payload.items()
                if key.startswith("what_if_") or key == "alternative_horizons"
            )
            for payload in counterfactual_rows
        )
        counterfactual_unavailable = any(
            payload.get("status") == "UNAVAILABLE"
            or any(
                isinstance(value, Mapping) and value.get("status") == "UNAVAILABLE"
                for key, value in payload.items()
                if key.startswith("what_if_") or key == "alternative_horizons"
            )
            for payload in counterfactual_rows
        )
        counterfactual_status = (
            "PARTIAL" if counterfactual_available and counterfactual_unavailable
            else "AVAILABLE" if counterfactual_available
            else "UNAVAILABLE" if counterfactual_unavailable
            else "NONE"
        )
        return {
            "records": len(self.records),
            "pending_closes": len(self.pending),
            "fast_winner_count": sum(row.get("speed_label") == "FAST_WINNER" for row in self.records),
            "fast_loser_count": sum(row.get("speed_label") == "FAST_LOSER" for row in self.records),
            "bad_entry_count": sum(row.get("classification") == "BAD_ENTRY" for row in self.records),
            "good_entry_bad_exit_count": sum(
                row.get("classification") == "GOOD_ENTRY_BAD_EXIT" for row in self.records
            ),
            "counterfactual_status": counterfactual_status,
        }
