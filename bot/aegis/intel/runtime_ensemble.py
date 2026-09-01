"""Runtime-only calibrated ensemble loader.

This module intentionally knows nothing about the research factory or any
research orchestrator.  It loads raw sklearn estimators emitted alongside a
validated artifact and exposes only the inference contract used by Firehose.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import joblib
import numpy as np
import pandas as pd

from aegis.intel.short_horizon_policy import validate_feature_provenance


RUNTIME_FUTURE_FEATURE_PREFIXES = (
    "pnl_", "green_", "captured_", "exit_", "future_", "time_to_",
    "terminal_", "label_",
)
RUNTIME_FUTURE_FEATURE_NAMES = frozenset(
    {
        "first_green", "first_profitable_executable_close",
        "first_profitable_close_net_pnl", "immediate_adverse_move",
        "winner_giveback", "never_green", "time_in_red_s",
        "future_path_observed_n", "exit_policy", "exit_time_s",
    }
)


def future_feature_aliases(feature_names: Sequence[str]) -> list[str]:
    """Return feature names that can only be known after the entry point."""
    aliases: list[str] = []
    for raw_name in feature_names:
        name = str(raw_name).strip()
        lowered = name.lower()
        if lowered in RUNTIME_FUTURE_FEATURE_NAMES or lowered.startswith(
            RUNTIME_FUTURE_FEATURE_PREFIXES
        ):
            aliases.append(name)
    return aliases


class RuntimeModel:
    """One raw estimator plus the immutable metadata needed for inference."""

    def __init__(
        self,
        *,
        name: str,
        estimator: Any,
        feature_names: Sequence[str],
        threshold: float,
        metrics: Mapping[str, Any],
    ) -> None:
        self.name = str(name)
        self.model = estimator
        self.feature_names = [str(value) for value in feature_names]
        self.calibration_threshold = float(threshold)
        self.metrics = dict(metrics)

    def predict_proba(self, frame: pd.DataFrame) -> np.ndarray:
        missing = [name for name in self.feature_names if name not in frame.columns]
        if missing:
            raise ValueError(f"Feature mismatch: missing={missing}")
        features = frame.loc[:, self.feature_names].replace(
            [np.inf, -np.inf], np.nan
        ).fillna(0)
        probabilities = np.asarray(self.model.predict_proba(features), dtype=float)
        if probabilities.ndim != 2 or probabilities.shape[1] < 2:
            raise ValueError("runtime estimator must expose binary probabilities")
        return probabilities[:, 1]


class RuntimeMLPipeline:
    """A calibrated ensemble with a research-independent artifact loader."""

    def __init__(self, models: Sequence[RuntimeModel] = ()) -> None:
        self.models = list(models)

    @classmethod
    def load(cls, path: Path) -> "RuntimeMLPipeline":
        root = Path(path)
        metadata_path = root / "metadata.json"
        if not metadata_path.is_file():
            raise FileNotFoundError(f"No metadata at {root}")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if not isinstance(metadata, Mapping):
            raise ValueError("runtime metadata must be a mapping")
        feature_names = metadata.get("feature_names")
        if not isinstance(feature_names, list) or not feature_names:
            raise ValueError("runtime metadata feature_names missing")
        leaked = future_feature_aliases(feature_names)
        if leaked:
            raise ValueError(
                "runtime feature set contains future outcome alias: "
                + ",".join(leaked[:5])
            )
        validate_feature_provenance(metadata.get("feature_provenance"), feature_names)
        model_rows = metadata.get("models")
        if not isinstance(model_rows, list):
            raise ValueError("runtime metadata models missing")
        models: list[RuntimeModel] = []
        for row in model_rows:
            if not isinstance(row, Mapping):
                raise ValueError("runtime model metadata must be a mapping")
            name = str(row.get("name") or "").strip()
            if not name:
                raise ValueError("runtime model name missing")
            runtime_file = str(row.get("runtime_model_file") or f"{name}.runtime.joblib")
            runtime_path = root / runtime_file
            if Path(runtime_file).name != runtime_file or not runtime_path.is_file():
                raise FileNotFoundError(f"runtime model missing: {runtime_file}")
            estimator = joblib.load(runtime_path)
            module_name = str(type(estimator).__module__)
            if module_name.startswith(("aegis.research_factory", "ai_council")):
                raise ValueError("runtime estimator has excluded provenance")
            row_features = row.get("feature_names") or feature_names
            metrics = row.get("metrics")
            if not isinstance(row_features, list) or not isinstance(metrics, Mapping):
                raise ValueError(f"runtime metadata incomplete: {name}")
            leaked = future_feature_aliases(row_features)
            if leaked:
                raise ValueError(
                    f"runtime feature set contains future outcome alias: {','.join(leaked[:5])}"
                )
            validate_feature_provenance(metadata.get("feature_provenance"), row_features)
            try:
                threshold = float(row.get("threshold", 0.5))
            except (TypeError, ValueError):
                raise ValueError(f"runtime threshold invalid: {name}") from None
            models.append(
                RuntimeModel(
                    name=name,
                    estimator=estimator,
                    feature_names=row_features,
                    threshold=threshold,
                    metrics=metrics,
                )
            )
        return cls(models)

    def get_calibrated_ensemble_prediction(
        self,
        frame: pd.DataFrame,
        *,
        threshold: float = 0.5,
        min_models: int = 2,
        min_model_agreement: float = 0.6,
        max_uncertainty: float = 0.2,
        include_model_probabilities: bool = False,
    ) -> dict[str, Any]:
        if not 0 < float(threshold) < 1:
            raise ValueError("threshold must be between 0 and 1")
        if int(min_models) < 1:
            raise ValueError("min_models must be positive")
        if not 0 <= float(min_model_agreement) <= 1:
            raise ValueError("min_model_agreement must be between 0 and 1")
        if float(max_uncertainty) < 0:
            raise ValueError("max_uncertainty must be non-negative")

        probabilities = [model.predict_proba(frame) for model in self.models]
        n_rows = len(frame)
        if probabilities:
            matrix = np.vstack(probabilities)
            dispersion = np.std(matrix, axis=0)
            agreement = np.maximum(
                np.mean(matrix >= float(threshold), axis=0),
                np.mean(matrix < float(threshold), axis=0),
            )
        else:
            matrix = np.empty((0, n_rows), dtype=float)
            dispersion = np.full(n_rows, np.inf, dtype=float)
            agreement = np.zeros(n_rows, dtype=float)

        calibrated = bool(self.models) and all(
            str(model.metrics.get("calibration_status", "")).startswith("calibrated")
            for model in self.models
        )
        weights: dict[str, float] = {}
        if calibrated and len(self.models) >= int(min_models):
            raw_weights = []
            for model in self.models:
                try:
                    brier = float(model.metrics.get("brier"))
                except (TypeError, ValueError):
                    brier = float("nan")
                raw_weights.append(1.0 / max(brier, 1e-6) if np.isfinite(brier) else 1.0)
            normalizer = float(np.sum(raw_weights)) or 1.0
            weights = {
                model.name: float(weight / normalizer)
                for model, weight in zip(self.models, raw_weights)
            }
            probability = np.average(matrix, axis=0, weights=raw_weights)
            abstain = (agreement < float(min_model_agreement)) | (
                dispersion > float(max_uncertainty)
            )
            reason = np.where(abstain, "ensemble_uncertain", "ensemble_eligible")
            calibration_status = "calibrated"
        else:
            probability = np.mean(matrix, axis=0) if self.models else np.zeros(n_rows, dtype=float)
            abstain = np.ones(n_rows, dtype=bool)
            reason_value = "not_calibrated" if not calibrated else "insufficient_models"
            reason = np.full(n_rows, reason_value, dtype=object)
            calibration_status = reason_value

        result: dict[str, Any] = {
            "probability": np.asarray(probability, dtype=float),
            "decision": (np.asarray(probability) >= float(threshold)) & ~abstain,
            "abstain": np.asarray(abstain, dtype=bool),
            "abstain_reason": np.asarray(reason, dtype=object),
            "model_agreement": np.asarray(agreement, dtype=float),
            "uncertainty": np.asarray(dispersion, dtype=float),
            "weights": weights,
            "model_count": len(self.models),
            "calibration_status": calibration_status,
        }
        if include_model_probabilities:
            result["model_probabilities"] = np.asarray(matrix, dtype=float)
        return result


__all__ = [
    "RuntimeMLPipeline", "RuntimeModel", "future_feature_aliases",
]
