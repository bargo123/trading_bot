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
            self.status, self.reason = "ready", "validated_calibrated_ensemble"
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
        }

    def predict(
        self,
        *,
        symbol: str,
        quote_buffer: Any,
        now_ts: float,
    ) -> dict[str, Any] | None:
        if self.pipeline is None or self.status != "ready":
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
            row = pd.DataFrame([features])
            result = self.pipeline.get_calibrated_ensemble_prediction(
                row,
                threshold=float(self.metadata.get("threshold", 0.5) or 0.5),
                min_models=2,
                min_model_agreement=float(self.metadata.get("min_model_agreement", 0.6) or 0.6),
                max_uncertainty=float(self.metadata.get("max_uncertainty", 0.2) or 0.2),
            )
            return {
                "probability": float(result["probability"][0]),
                "decision": bool(result["decision"][0]),
                "abstain": bool(result["abstain"][0]),
                "calibration_status": str(result["calibration_status"]),
                "model_agreement": float(result["model_agreement"][0]),
                "uncertainty": float(result["uncertainty"][0]),
                "model_count": int(result["model_count"]),
                "horizons_s": self.metadata.get("horizons_s"),
            }
        except Exception:
            return None
