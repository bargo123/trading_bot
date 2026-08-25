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

from aegis.intel.paths import BOT_ROOT, resolve_bot_path
from aegis.research.short_horizon import point_in_time_features
from aegis.research_factory.ml_pipeline import MLPipeline


SHORT_HORIZON_ARTIFACT_SCHEMA = "short_horizon_ensemble.v1"


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
        return {
            "status": self.status,
            "reason": self.reason,
            "artifact_path": str(self.artifact_path),
            "dataset_hash": self.metadata.get("dataset_hash"),
            "validation_hash": self.metadata.get("validation_hash"),
            "horizons_s": self.metadata.get("horizons_s"),
            "model_count": len(self.pipeline.models) if self.pipeline is not None else 0,
            "execution_status": self.execution_status,
        }

    def predict(
        self,
        *,
        symbol: str,
        quote_buffer: Any,
        now_ts: float,
        side: str = "buy",
        notional_usd: float | None = None,
    ) -> dict[str, Any] | None:
        if self.pipeline is None or self.status not in {"ready", "shadow_only"}:
            return None
        buffer = getattr(quote_buffer, "buffers", {}).get(str(symbol).upper())
        points = [point for point in getattr(buffer, "points", ()) if point.timestamp <= float(now_ts)]
        if len(points) < 2:
            return None
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
            features = point_in_time_features(
                frame,
                at=frame["time"].iloc[-1],
                symbol=str(symbol).upper(),
            )
            by_horizon: dict[str, dict[str, Any]] = {}
            for horizon in self.metadata.get("horizons_s") or ():
                row = pd.DataFrame([{
                    **features,
                    "side_buy": 1.0 if str(side).lower() == "buy" else 0.0,
                    "horizon_s": float(horizon),
                }])
                result = self.pipeline.get_calibrated_ensemble_prediction(
                    row,
                    threshold=float(self.metadata.get("threshold", 0.5) or 0.5),
                    min_models=2,
                    min_model_agreement=float(self.metadata.get("min_model_agreement", 0.6) or 0.6),
                    max_uncertainty=float(self.metadata.get("max_uncertainty", 0.2) or 0.2),
                )
                by_horizon[str(int(horizon))] = {
                    "probability": float(result["probability"][0]),
                    "decision": bool(result["decision"][0]),
                    "abstain": bool(result["abstain"][0]),
                    "model_agreement": float(result["model_agreement"][0]),
                    "uncertainty": float(result["uncertainty"][0]),
                }
            if not by_horizon:
                return None
            selected_horizon = str(int(self.metadata.get("decision_horizon_s", 10) or 10))
            selected = by_horizon.get(selected_horizon) or next(iter(by_horizon.values()))
            oos_by_horizon = ((self.metadata.get("oos") or {}).get("sealed_by_horizon") or {})
            selected_oos = oos_by_horizon.get(selected_horizon) or {}
            expected_return = selected_oos.get("mean_terminal_return")
            expected_net = None
            if notional_usd is not None:
                # No selected sealed-OOS rows are an explicit zero-evidence
                # veto, never an omitted field that could bypass the gate.
                expected_net = (
                    float(expected_return) * float(features["mid"]) * float(notional_usd)
                    if expected_return is not None else 0.0
                )
            return {
                "probability": selected["probability"],
                "decision": selected["decision"],
                "abstain": selected["abstain"],
                "calibration_status": "calibrated",
                "model_agreement": selected["model_agreement"],
                "uncertainty": selected["uncertainty"],
                "model_count": len(self.pipeline.models),
                "horizons_s": self.metadata.get("horizons_s"),
                "decision_horizon_s": int(selected_horizon),
                "by_horizon": by_horizon,
                "expected_net_pnl": expected_net,
                "tail_loss_probability": selected_oos.get("tail_loss_rate"),
            }
        except Exception:
            return None
