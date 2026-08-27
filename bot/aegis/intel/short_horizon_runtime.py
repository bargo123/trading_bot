"""Fail-closed local short-horizon model inference for the Firehose runner.

This adapter is deliberately separate from research training.  It loads only a
governed, calibrated ensemble artifact with an explicit short-horizon schema;
missing or incompatible artifacts produce no prediction and never synthetic
confidence.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from aegis.intel.broker_math import BrokerSymbolSpec
from aegis.intel.paths import BOT_ROOT, resolve_bot_path
from aegis.research.short_horizon import point_in_time_features
from aegis.research.short_horizon_artifact import MIN_CAPTURED_EXIT_LOSSES
from aegis.research_factory.ml_pipeline import MLPipeline


SHORT_HORIZON_ARTIFACT_SCHEMA = "short_horizon_ensemble.v1"


def resample_runtime_quotes(frame: pd.DataFrame) -> pd.DataFrame:
    """Match the artifact builder's one-observation-per-second cadence."""
    if frame is None or frame.empty:
        return frame
    required = {"time", "bid", "ask"}
    if not required.issubset(frame.columns):
        raise ValueError("runtime quotes require time, bid, and ask")
    values = frame.loc[:, ["time", "bid", "ask"]].copy()
    values["time"] = pd.to_datetime(values["time"], utc=True, errors="coerce")
    values["bid"] = pd.to_numeric(values["bid"], errors="coerce")
    values["ask"] = pd.to_numeric(values["ask"], errors="coerce")
    values = values.dropna().sort_values("time", kind="stable")
    if values.empty:
        return values
    return (
        values.set_index("time")[["bid", "ask"]]
        .resample("1s")
        .last()
        .dropna()
        .reset_index()
    )


def seed_quote_buffer(quote_buffer: Any, symbol: str, quotes: Any) -> int:
    """Seed local features from valid, read-only broker quote rows."""
    recorder = getattr(quote_buffer, "record", None)
    if not callable(recorder):
        return 0
    added = 0
    for quote in quotes or ():
        try:
            timestamp = float(quote.get("time") or 0.0)
            bid = float(quote.get("bid") or 0.0)
            ask = float(quote.get("ask") or 0.0)
        except (AttributeError, TypeError, ValueError):
            continue
        if timestamp <= 0.0 or bid <= 0.0 or ask <= 0.0 or ask < bid:
            continue
        recorder(str(symbol).upper(), timestamp, bid, ask)
        added += 1
    return added


def _abstain_reason(
    prediction: Mapping[str, Any],
    *,
    min_model_agreement: float,
    max_uncertainty: float,
) -> tuple[str, bool]:
    """Explain an ensemble abstention without relaxing the decision gate."""
    if not bool(prediction.get("abstain", True)):
        return "ensemble_eligible", False

    def scalar(value: Any, default: float) -> float:
        try:
            if not isinstance(value, (str, bytes)) and hasattr(value, "__len__"):
                if len(value) == 1:
                    value = value[0]
            return float(value)
        except (IndexError, TypeError, ValueError):
            return float(default)

    reasons: list[str] = []
    disagreement = scalar(prediction.get("model_agreement"), 0.0) < float(
        min_model_agreement
    )
    uncertain = scalar(prediction.get("uncertainty"), 1.0) > float(max_uncertainty)
    if disagreement:
        reasons.append("model_disagreement")
    if uncertain:
        reasons.append("uncertainty_high")
    return "+".join(reasons) if reasons else "ensemble_abstain", disagreement


def execution_candidate_has_current_promotion_policy(metadata: Mapping[str, Any]) -> bool:
    """Reject legacy execution candidates that lack current downside-evidence proof."""
    if str(metadata.get("execution_status") or "") != "EXECUTION_CANDIDATE":
        return True
    policy = metadata.get("promotion_policy")
    if not isinstance(policy, Mapping):
        return False
    try:
        return (
            int(policy.get("min_captured_exit_losses") or 0) >= MIN_CAPTURED_EXIT_LOSSES
            and policy.get("requires_positive_test_and_sealed_lcb95") is True
        )
    except (TypeError, ValueError):
        return False


class ShortHorizonPredictor:
    """Runtime-only wrapper around a validated local calibrated ensemble."""

    def __init__(self, artifact_path: Path) -> None:
        self.artifact_path = Path(artifact_path)
        self.pipeline: MLPipeline | None = None
        self.metadata: dict[str, Any] = {}
        self.status = "missing_artifact"
        self.reason = "artifact_not_found"
        self.execution_status = "NO_ARTIFACT"
        self._load()

    @classmethod
    def from_config(cls, cfg: Mapping[str, Any]) -> "ShortHorizonPredictor":
        path = resolve_bot_path(
            cfg.get("short_horizon_model_path"),
            BOT_ROOT / "intel" / "short_horizon_model",
        )
        return cls(path)

    def _load(self) -> None:
        metadata_path = self.artifact_path / "metadata.json"
        if not metadata_path.is_file():
            return
        try:
            import json

            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            if not isinstance(metadata, dict):
                self.status, self.reason = "invalid_artifact", "metadata_not_mapping"
                return
            self.metadata = metadata
            self.execution_status = str(metadata.get("execution_status") or "SHADOW_ONLY_NO_POSITIVE_OOS")
            if metadata.get("schema") != SHORT_HORIZON_ARTIFACT_SCHEMA:
                self.status, self.reason = "invalid_artifact", "schema_mismatch"
                return
            required = ("dataset_hash", "validation_hash", "horizons_s", "oos")
            missing = [key for key in required if not metadata.get(key)]
            if missing:
                self.status, self.reason = "invalid_artifact", "missing:" + ",".join(missing)
                return
            if (
                self.execution_status == "EXECUTION_CANDIDATE"
                and str(metadata.get("target_definition") or "").strip().lower()
                != "captured_exit_replay"
            ):
                self.status, self.reason = (
                    "invalid_artifact",
                    "execution_requires_captured_exit_replay",
                )
                return
            if not execution_candidate_has_current_promotion_policy(metadata):
                self.status, self.reason = (
                    "invalid_artifact",
                    "execution_candidate_missing_current_promotion_policy",
                )
                return
            if self.execution_status == "EXECUTION_CANDIDATE":
                authorized_values = metadata.get("authorized_symbols")
                authorized = (
                    [str(value).upper() for value in authorized_values if str(value).strip()]
                    if isinstance(authorized_values, list)
                    else []
                )
                if not authorized:
                    self.status, self.reason = (
                        "invalid_artifact",
                        "execution_requires_authorized_symbols",
                    )
                    return
                decision_horizon = str(int(metadata.get("decision_horizon_s", 0) or 0))
                scoped_oos = (metadata.get("oos") or {}).get("sealed_by_symbol_horizon") or {}
                if not decision_horizon or any(
                    not isinstance((scoped_oos.get(symbol) or {}).get(decision_horizon), Mapping)
                    for symbol in authorized
                ):
                    self.status, self.reason = (
                        "invalid_artifact",
                        "execution_requires_exact_symbol_horizon_oos",
                    )
                    return
            self.pipeline = MLPipeline.load(self.artifact_path)
            if len(self.pipeline.models) < 2:
                self.status, self.reason = "invalid_artifact", "insufficient_models"
                self.pipeline = None
                return
            if not all(
                str(model.metrics.get("calibration_status") or "").startswith("calibrated")
                for model in self.pipeline.models
            ):
                self.status, self.reason = "not_calibrated", "model_calibration_incomplete"
                self.pipeline = None
                return
            self.status = (
                "ready" if self.execution_status == "EXECUTION_CANDIDATE" else "shadow_only"
            )
            self.reason = (
                "validated_calibrated_ensemble"
                if self.status == "ready" else self.execution_status.lower()
            )
        except Exception as exc:  # fail closed on corrupt/incompatible artifacts
            self.pipeline = None
            self.status, self.reason = "invalid_artifact", type(exc).__name__

    def snapshot(self) -> dict[str, Any]:
        proof = self.metadata.get("runtime_proof")
        if not isinstance(proof, dict):
            proof = {}
        return {
            "status": self.status,
            "reason": self.reason,
            "artifact_path": str(self.artifact_path),
            "dataset_hash": self.metadata.get("dataset_hash"),
            "validation_hash": self.metadata.get("validation_hash"),
            "model_version": self.metadata.get("model_version"),
            "horizons_s": self.metadata.get("horizons_s"),
            "model_count": len(self.pipeline.models) if self.pipeline is not None else 0,
            "execution_status": self.execution_status,
            "target_definition": self.metadata.get("target_definition"),
            "authorized_symbols": self.metadata.get("authorized_symbols") or [],
            "decision_horizon_s": self.metadata.get("decision_horizon_s"),
            "runtime_proof": proof,
        }

    def _fail_closed_prediction(self, reason: str) -> dict[str, Any]:
        return {
            "probability": 0.0,
            "decision": False,
            "abstain": True,
            "calibration_status": "unavailable",
            "model_agreement": 0.0,
            "uncertainty": 1.0,
            "model_count": len(self.pipeline.models) if self.pipeline is not None else 0,
            "threshold": float(self.metadata.get("threshold", 0.5) or 0.5),
            "abstain_reason": str(reason),
            "model_disagreement": False,
            "expected_net_pnl": 0.0,
            "prediction_reason": str(reason),
            "artifact_status": self.status,
            "execution_status": self.execution_status,
            "dataset_hash": self.metadata.get("dataset_hash"),
            "validation_hash": self.metadata.get("validation_hash"),
            "artifact_path": str(self.artifact_path),
            "model_version": self.metadata.get("model_version"),
        }

    @staticmethod
    def _side_is_executable(prediction: Mapping[str, Any] | None) -> bool:
        """Return whether one side has enough runtime evidence to be ranked.

        Side comparison is deliberately stricter than merely receiving a model
        score.  A side must be calibrated, non-abstaining, positively predicted,
        and have positive executable EV (including its lower bound when the
        artifact provides one).  Otherwise it remains an abstention candidate.
        """
        if not isinstance(prediction, Mapping):
            return False
        if str(prediction.get("calibration_status") or "") != "calibrated":
            return False
        if bool(prediction.get("abstain", True)) or not bool(prediction.get("decision", False)):
            return False
        try:
            expected = float(prediction.get("expected_net_pnl"))
            if expected != expected or expected <= 0.0:
                return False
            if "expected_net_pnl_lcb95" in prediction:
                lower = float(prediction.get("expected_net_pnl_lcb95"))
                if lower != lower or lower <= 0.0:
                    return False
        except (TypeError, ValueError):
            return False
        return True

    def predict_sides(
        self,
        *,
        symbol: str,
        quote_buffer: Any,
        now_ts: float,
        notional_usd: float | None = None,
        broker_spec: Mapping[str, Any] | None = None,
        quantity: float | None = None,
        horizon_s: int | None = None,
    ) -> dict[str, Any]:
        """Evaluate BUY and SELL independently, then select or abstain.

        The returned mapping is itself a normal prediction for the selected
        side, augmented with the complete side comparison.  If neither side
        is executable, it is an explicit fail-closed abstention carrying both
        side results for diagnosis.
        """
        predictions: dict[str, dict[str, Any]] = {}
        for candidate_side in ("buy", "sell"):
            try:
                result = self.predict(
                    symbol=symbol,
                    quote_buffer=quote_buffer,
                    now_ts=now_ts,
                    side=candidate_side,
                    notional_usd=notional_usd,
                    broker_spec=broker_spec,
                    quantity=quantity,
                    horizon_s=horizon_s,
                )
            except Exception:
                result = self._fail_closed_prediction("prediction_error")
            predictions[candidate_side] = dict(result or self._fail_closed_prediction("prediction_missing"))

        eligible = [
            side for side, prediction in predictions.items()
            if self._side_is_executable(prediction)
        ]
        ranking = sorted(
            eligible,
            key=lambda side: (
                float(predictions[side].get("expected_net_pnl") or 0.0),
                float(predictions[side].get("probability") or 0.0),
                -float(predictions[side].get("uncertainty") or 1.0),
            ),
            reverse=True,
        )
        comparison = {
            "selected_side": ranking[0] if ranking else None,
            "ranking": ranking,
            "predictions": predictions,
        }
        if not ranking:
            reasons = [
                str(prediction.get("prediction_reason") or prediction.get("abstain_reason") or "prediction_unavailable")
                for prediction in predictions.values()
            ]
            reason = reasons[0] if reasons and len(set(reasons)) == 1 else "no_eligible_side"
            result = self._fail_closed_prediction(reason)
            result["selected_side"] = None
            result["side_comparison"] = comparison
            result["side_predictions"] = predictions
            return result

        selected = dict(predictions[ranking[0]])
        selected["selected_side"] = ranking[0]
        selected["side_comparison"] = comparison
        selected["side_predictions"] = predictions
        return selected

    def predict(
        self,
        *,
        symbol: str,
        quote_buffer: Any,
        now_ts: float,
        side: str = "buy",
        notional_usd: float | None = None,
        broker_spec: Mapping[str, Any] | None = None,
        quantity: float | None = None,
        horizon_s: int | None = None,
    ) -> dict[str, Any] | None:
        normalized_symbol = str(symbol).upper()
        normalized_side = str(side).strip().lower()
        if normalized_side not in {"buy", "sell"}:
            return self._fail_closed_prediction("side_invalid")
        if (
            self.execution_status == "EXECUTION_CANDIDATE"
            and str(self.metadata.get("target_definition") or "").strip().lower()
            != "captured_exit_replay"
        ):
            return self._fail_closed_prediction("execution_requires_captured_exit_replay")
        authorized_values = self.metadata.get("authorized_symbols")
        authorized = (
            {str(value).upper() for value in authorized_values if str(value).strip()}
            if isinstance(authorized_values, (list, tuple, set))
            else set()
        )
        if self.execution_status == "EXECUTION_CANDIDATE":
            if not authorized or normalized_symbol not in authorized:
                return self._fail_closed_prediction("symbol_not_authorized")
        elif authorized and normalized_symbol not in authorized:
            return self._fail_closed_prediction("symbol_not_authorized")
        if self.pipeline is None:
            return self._fail_closed_prediction(self.reason or "artifact_unavailable")
        if self.status != "ready":
            return self._fail_closed_prediction("artifact_shadow_only")
        buffer = getattr(quote_buffer, "buffers", {}).get(normalized_symbol)
        if buffer is None:
            return self._fail_closed_prediction("quote_history_missing")
        points = [point for point in getattr(buffer, "points", ()) if point.timestamp <= float(now_ts)]
        if len(points) < 2:
            return self._fail_closed_prediction("quote_history_insufficient")
        frame = pd.DataFrame(
            [
                {
                    "time": pd.Timestamp.fromtimestamp(point.timestamp, tz="UTC"),
                    "bid": point.bid,
                    "ask": point.ask,
                }
                for point in points
            ]
        )
        try:
            frame = resample_runtime_quotes(frame)
            if len(frame) < 2:
                return self._fail_closed_prediction("quote_history_insufficient")
            features = point_in_time_features(
                frame,
                at=frame["time"].iloc[-1],
                symbol=str(symbol).upper(),
            )
            by_horizon: dict[str, dict[str, Any]] = {}
            configured_horizons = tuple(self.metadata.get("horizons_s") or ())
            if horizon_s is not None:
                try:
                    requested_horizon = int(horizon_s)
                except (TypeError, ValueError):
                    return self._fail_closed_prediction("decision_horizon_invalid")
                configured_horizons = tuple(
                    horizon for horizon in configured_horizons
                    if int(horizon) == requested_horizon
                )
                if not configured_horizons:
                    return self._fail_closed_prediction("decision_horizon_unavailable")
            for horizon in configured_horizons:
                horizon_key = str(int(horizon))
                scope_thresholds = (
                    self.metadata.get("threshold_by_symbol_horizon") or {}
                ).get(normalized_symbol) or {}
                horizon_threshold = float(
                    scope_thresholds.get(
                        horizon_key,
                        self.metadata.get("threshold", 0.5) or 0.5,
                    )
                )
                row = pd.DataFrame([{
                    **features,
                    "side_buy": 1.0 if normalized_side == "buy" else 0.0,
                    "horizon_s": float(horizon),
                }])
                min_model_agreement = float(
                    self.metadata.get("min_model_agreement", 0.6) or 0.6
                )
                max_uncertainty = float(
                    self.metadata.get("max_uncertainty", 0.2) or 0.2
                )
                result = self.pipeline.get_calibrated_ensemble_prediction(
                    row,
                    threshold=horizon_threshold,
                    min_models=2,
                    min_model_agreement=min_model_agreement,
                    max_uncertainty=max_uncertainty,
                )
                abstain_reason, model_disagreement = _abstain_reason(
                    result,
                    min_model_agreement=min_model_agreement,
                    max_uncertainty=max_uncertainty,
                )
                by_horizon[horizon_key] = {
                    "probability": float(result["probability"][0]),
                    "decision": bool(result["decision"][0]),
                    "abstain": bool(result["abstain"][0]),
                    "model_agreement": float(result["model_agreement"][0]),
                    "uncertainty": float(result["uncertainty"][0]),
                    "threshold": horizon_threshold,
                    "abstain_reason": abstain_reason,
                    "model_disagreement": model_disagreement,
                }
            if not by_horizon:
                return self._fail_closed_prediction("decision_horizon_missing")
            oos = self.metadata.get("oos") or {}
            target_definition = str(
                self.metadata.get("target_definition") or "terminal_profit"
            ).strip().lower()
            harvest_mode = target_definition in {"mfe_first", "fast_harvest"}
            captured_exit_mode = target_definition == "captured_exit_replay"

            def horizon_oos(horizon_key: str) -> Mapping[str, Any]:
                if self.execution_status == "EXECUTION_CANDIDATE":
                    scoped = (
                        (oos.get("sealed_by_symbol_horizon") or {})
                        .get(normalized_symbol) or {}
                    )
                    value = scoped.get(horizon_key) or {}
                else:
                    value = (oos.get("sealed_by_horizon") or {}).get(horizon_key) or {}
                return value if isinstance(value, Mapping) else {}

            def horizon_returns(metrics: Mapping[str, Any]) -> tuple[Any, Any]:
                return (
                    metrics.get("mean_captured_exit_return") if captured_exit_mode
                    else metrics.get("mean_harvest_return") if harvest_mode
                    else metrics.get("mean_terminal_return"),
                    metrics.get("captured_exit_lcb95_return") if captured_exit_mode
                    else metrics.get("harvest_lcb95_return") if harvest_mode
                    else metrics.get("expectancy_lcb95_return"),
                )

            money_spec = None
            lots = None
            if broker_spec is not None or quantity is not None:
                if broker_spec is None or quantity is None:
                    return self._fail_closed_prediction("broker_money_evidence_incomplete")
                money_spec = BrokerSymbolSpec.from_mapping(broker_spec)
                lots = float(quantity)
                if lots <= 0:
                    return self._fail_closed_prediction("broker_quantity_invalid")
            mid = float(features["mid"])
            for horizon_key, horizon_prediction in by_horizon.items():
                metrics = horizon_oos(horizon_key)
                expected_return, expected_lcb_return = horizon_returns(metrics)
                if money_spec is not None and lots is not None:
                    horizon_net = (
                        money_spec.price_units_to_usd(float(expected_return) * mid, lots)
                        if expected_return is not None else 0.0
                    )
                    horizon_net_lcb95 = (
                        money_spec.price_units_to_usd(float(expected_lcb_return) * mid, lots)
                        if expected_lcb_return is not None else 0.0
                    )
                elif notional_usd is not None:
                    horizon_net = (
                        float(expected_return) * mid * float(notional_usd)
                        if expected_return is not None else 0.0
                    )
                    horizon_net_lcb95 = (
                        float(expected_lcb_return) * mid * float(notional_usd)
                        if expected_lcb_return is not None else 0.0
                    )
                else:
                    # A horizon without broker money context cannot authorize
                    # executable Firehose activity.
                    horizon_net = 0.0
                    horizon_net_lcb95 = 0.0
                horizon_prediction.update({
                    "horizon_s": int(horizon_key),
                    "calibration_status": "calibrated",
                    "expected_net_pnl": horizon_net,
                    "expected_net_pnl_lcb95": horizon_net_lcb95,
                    "expected_captured_exit_return": (
                        expected_return if captured_exit_mode else None
                    ),
                    "expected_captured_exit_return_lcb95": (
                        expected_lcb_return if captured_exit_mode else None
                    ),
                    "expected_harvest_return": expected_return if harvest_mode else None,
                    "expected_harvest_return_lcb95": expected_lcb_return if harvest_mode else None,
                    "prediction_reason": horizon_prediction.get(
                        "abstain_reason", "ensemble_eligible"
                    ),
                })

            executable_horizons = [
                (key, value) for key, value in by_horizon.items()
                if bool(value.get("decision"))
                and not bool(value.get("abstain"))
                and float(value.get("expected_net_pnl") or 0.0) > 0.0
                and float(value.get("expected_net_pnl_lcb95") or 0.0) > 0.0
            ]
            selected_horizon = str(int(self.metadata.get("decision_horizon_s", 10) or 10))
            if executable_horizons:
                selected_horizon = max(
                    executable_horizons,
                    key=lambda item: (
                        float(item[1].get("expected_net_pnl") or 0.0),
                        float(item[1].get("probability") or 0.0),
                    ),
                )[0]
            selected = by_horizon.get(selected_horizon) or next(iter(by_horizon.values()))
            selected_oos = horizon_oos(selected_horizon)
            if self.execution_status == "EXECUTION_CANDIDATE" and not selected_oos:
                return self._fail_closed_prediction("symbol_horizon_oos_missing")
            expected_return = (
                selected_oos.get("mean_captured_exit_return") if captured_exit_mode
                else selected_oos.get("mean_harvest_return") if harvest_mode
                else selected_oos.get("mean_terminal_return")
            )
            expected_lcb_return = (
                selected_oos.get("captured_exit_lcb95_return") if captured_exit_mode
                else selected_oos.get("harvest_lcb95_return") if harvest_mode
                else selected_oos.get("expectancy_lcb95_return")
            )
            expected_net = None
            expected_net_lcb95 = None
            if broker_spec is not None or quantity is not None:
                # Production money math uses broker-native USD tick value so
                # JPY/CHF/CAD and other non-USD quote currencies are not
                # accidentally reported as USD. The artifact return is a
                # relative price return, so convert it back to price units
                # before applying the broker's USD-per-price-unit value.
                if money_spec is None or lots is None:
                    return self._fail_closed_prediction("broker_money_evidence_incomplete")
                expected_net = (
                    money_spec.price_units_to_usd(float(expected_return) * mid, lots)
                    if expected_return is not None else 0.0
                )
                expected_net_lcb95 = (
                    money_spec.price_units_to_usd(float(expected_lcb_return) * mid, lots)
                    if expected_lcb_return is not None else 0.0
                )
            elif notional_usd is not None:
                # Backward-compatible research/test fallback. Production calls
                # should supply broker_spec + quantity for true USD money math.
                expected_net = (
                    float(expected_return) * float(features["mid"]) * float(notional_usd)
                    if expected_return is not None else 0.0
                )
                expected_net_lcb95 = (
                    float(expected_lcb_return) * float(features["mid"]) * float(notional_usd)
                    if expected_lcb_return is not None else 0.0
                )
            return {
                "probability": selected["probability"],
                "net_profit_probability": selected["probability"],
                "decision": selected["decision"],
                "abstain": selected["abstain"],
                "calibration_status": "calibrated",
                "model_agreement": selected["model_agreement"],
                "uncertainty": selected["uncertainty"],
                "abstain_reason": selected.get("abstain_reason", "ensemble_eligible"),
                "model_disagreement": bool(selected.get("model_disagreement", False)),
                "model_count": len(self.pipeline.models),
                "horizons_s": self.metadata.get("horizons_s"),
                "decision_horizon_s": int(selected_horizon),
                "threshold": float(selected.get("threshold", self.metadata.get("threshold", 0.5)) or 0.5),
                "by_horizon": by_horizon,
                "expected_net_pnl": expected_net,
                "expected_net_pnl_lcb95": expected_net_lcb95,
                "harvest_mode": (
                    "captured_exit_replay" if captured_exit_mode
                    else "first_green" if harvest_mode
                    else "terminal_horizon"
                ),
                "expected_harvest_return": expected_return if harvest_mode else None,
                "expected_harvest_return_lcb95": expected_lcb_return if harvest_mode else None,
                "expected_captured_exit_return": expected_return if captured_exit_mode else None,
                "expected_captured_exit_return_lcb95": expected_lcb_return if captured_exit_mode else None,
                "tail_loss_probability": selected_oos.get("tail_loss_rate"),
                "expected_mfe": selected_oos.get("expected_mfe"),
                "expected_mae": selected_oos.get("expected_mae"),
                "expected_time_to_green_s": selected_oos.get("median_time_to_green_s"),
                "expected_time_to_failure_s": selected_oos.get("median_time_to_failure_s"),
                "winner_giveback_rate": selected_oos.get("winner_giveback_rate"),
                "calibration_ece": selected_oos.get("calibration_ece"),
                "feature_snapshot": dict(features),
                "artifact_status": self.status,
                "execution_status": self.execution_status,
                "dataset_hash": self.metadata.get("dataset_hash"),
                "validation_hash": self.metadata.get("validation_hash"),
                "artifact_path": str(self.artifact_path),
                "model_version": self.metadata.get("model_version"),
            }
        except Exception:
            return self._fail_closed_prediction("prediction_error")
