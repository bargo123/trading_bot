"""ML Pipeline for research factory."""
from __future__ import annotations

import json
import hashlib
import joblib
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier, HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    roc_auc_score,
    log_loss,
    brier_score_loss,
)
from sklearn.model_selection import TimeSeriesSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler, RobustScaler
from sklearn.feature_selection import SelectFromModel

try:
    from sklearn.frozen import FrozenEstimator
except ImportError:  # pragma: no cover - depends on installed sklearn version
    FrozenEstimator = None

logger = logging.getLogger(__name__)


LABEL_COLUMNS = frozenset(
    {
        "target",
        "label",
        "target_direction",
        "future_max_high",
        "future_min_low",
        "profit_barrier_first",
        "mfe",
        "mae",
        "time_to_target",
        "no_progress",
        "tail_loss",
        "direction",
        "return_horizon",
    }
)

PROVENANCE_COLUMNS = frozenset(
    {
        "time",
        "source_file",
        "source_kind",
        "source_quality",
        "symbol",
        "timeframe",
    }
)

MIN_ISOTONIC_SAMPLES = 10


def _defined_binary_metrics(
    y_true: pd.Series, y_pred: np.ndarray
) -> Dict[str, float]:
    """Return positive-class metrics only when each ratio is defined."""
    true_values = np.asarray(y_true)
    predicted_values = np.asarray(y_pred)
    true_positives = int(((true_values == 1) & (predicted_values == 1)).sum())
    predicted_positives = int((predicted_values == 1).sum())
    actual_positives = int((true_values == 1).sum())
    f1_denominator = predicted_positives + actual_positives

    metrics: Dict[str, float] = {}
    if predicted_positives:
        metrics["precision"] = true_positives / predicted_positives
    if actual_positives:
        metrics["recall"] = true_positives / actual_positives
    if f1_denominator:
        metrics["f1"] = 2 * true_positives / f1_denominator
    return metrics


@dataclass
class ModelConfig:
    """Configuration for a model."""
    name: str
    model_type: str
    params: Dict[str, Any]
    feature_selector: bool = True
    calibrate: bool = True
    threshold: float = 0.5


DEFAULT_MODEL_CONFIGS = [
    ModelConfig(
        name="logistic",
        model_type="logistic",
        params={"C": 1.0, "max_iter": 1000, "class_weight": "balanced"},
        calibrate=True,
    ),
    ModelConfig(
        name="rf",
        model_type="random_forest",
        params={"n_estimators": 200, "max_depth": 10, "class_weight": "balanced", "n_jobs": -1},
        feature_selector=True,
    ),
    ModelConfig(
        name="gbm",
        model_type="gradient_boosting",
        params={"n_estimators": 200, "max_depth": 5, "learning_rate": 0.05, "subsample": 0.8},
        calibrate=True,
    ),
    ModelConfig(
        name="hist_gbm",
        model_type="hist_gradient_boosting",
        params={"max_iter": 200, "max_depth": 5, "learning_rate": 0.05, "class_weight": "balanced"},
        feature_selector=False,
        calibrate=True,
    ),
]


@dataclass
class TrainedModel:
    """A trained model with metadata."""
    name: str
    model: Any
    feature_names: List[str]
    calibration_threshold: float
    metrics: Dict[str, Any]
    trained_at: str
    feature_hash: str
    config_hash: str

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        """Predict probabilities."""
        missing = [name for name in self.feature_names if name not in X.columns]
        if missing:
            raise ValueError(f"Feature mismatch: missing={missing}")
        features = X.loc[:, self.feature_names].replace(
            [np.inf, -np.inf], np.nan
        ).fillna(0)
        return self.model.predict_proba(features)[:, 1]

    def predict(self, X: pd.DataFrame, threshold: Optional[float] = None) -> np.ndarray:
        """Predict class labels."""
        if threshold is None:
            threshold = self.calibration_threshold
        probs = self.predict_proba(X)
        return (probs >= threshold).astype(int)


class MLPipeline:
    """ML Pipeline for research factory."""

    def __init__(
        self,
        configs: Optional[List[ModelConfig]] = None,
        n_splits: int = 5,
        test_size: float = 0.2,
        random_seed: int = 42,
    ):
        self.configs = configs or DEFAULT_MODEL_CONFIGS
        self.n_splits = n_splits
        self.test_size = test_size
        self.random_seed = random_seed
        self.models: List[TrainedModel] = []
        self.feature_names: List[str] = []

    def _prepare_features(
        self,
        df: pd.DataFrame,
        expected_features: Optional[List[str]] = None,
        *,
        require_two_classes: bool = True,
    ) -> Tuple[pd.DataFrame, pd.Series, List[str], int]:
        """Extract validated model features and the explicit binary target."""
        target_name = "profit_barrier_first"
        if target_name not in df.columns:
            raise ValueError(f"Missing required target column: {target_name}")
        if df[target_name].isna().any():
            raise ValueError(f"Target column {target_name} contains null values")
        if not df[target_name].isin([0, 1]).all():
            invalid_values = sorted(
                {repr(value) for value in df.loc[
                    ~df[target_name].isin([0, 1]), target_name
                ]}
            )
            raise ValueError(
                f"Target column {target_name} must be binary with values 0 and 1; "
                f"invalid values: {invalid_values}"
            )

        excluded = LABEL_COLUMNS | PROVENANCE_COLUMNS
        feature_names = [
            column
            for column in df.columns
            if column not in excluded
            and (
                pd.api.types.is_numeric_dtype(df[column])
                or pd.api.types.is_bool_dtype(df[column])
            )
        ]
        if not feature_names:
            raise ValueError("No numeric model features remain after exclusions")

        if expected_features is not None and set(feature_names) != set(expected_features):
            missing = [name for name in expected_features if name not in feature_names]
            unexpected = [name for name in feature_names if name not in expected_features]
            raise ValueError(
                "Feature mismatch: "
                f"missing={missing or 'none'}, unexpected={unexpected or 'none'}"
            )
        if expected_features is not None:
            feature_names = list(expected_features)

        X = df.loc[:, feature_names].replace([np.inf, -np.inf], np.nan)
        y = df[target_name].astype(int)
        finite_rows = X.notna().all(axis=1)
        dropped_rows = int((~finite_rows).sum())
        X = X.loc[finite_rows].copy()
        y = y.loc[finite_rows].copy()
        if require_two_classes and y.nunique() < 2:
            raise ValueError(
                f"Target column {target_name} must contain at least two classes "
                "after dropping non-finite supervised rows"
            )
        return X, y, feature_names, dropped_rows

    def _create_model(self, config: ModelConfig) -> Any:
        """Create model from config."""
        if config.model_type == "logistic":
            return LogisticRegression(**config.params, random_state=self.random_seed)
        elif config.model_type == "random_forest":
            return RandomForestClassifier(**config.params, random_state=self.random_seed)
        elif config.model_type == "gradient_boosting":
            return GradientBoostingClassifier(**config.params, random_state=self.random_seed)
        elif config.model_type == "hist_gradient_boosting":
            return HistGradientBoostingClassifier(**config.params, random_state=self.random_seed)
        else:
            raise ValueError(f"Unknown model type: {config.model_type}")

    def train(
        self,
        train_df: pd.DataFrame,
        val_df: Optional[pd.DataFrame] = None,
    ) -> List[TrainedModel]:
        """Train all models."""
        self.models = []
        self.feature_names = []

        # Prepare features
        X_train, y_train, feature_names, dropped_train_rows = self._prepare_features(
            train_df
        )
        self.feature_names = feature_names

        if val_df is not None:
            X_val, y_val, _, dropped_validation_rows = self._prepare_features(
                val_df, expected_features=feature_names, require_two_classes=False
            )
        else:
            X_val, y_val = None, None
            dropped_validation_rows = 0

        models = []

        for config in self.configs:
            logger.info(f"Training {config.name}...")

            # Create pipeline
            steps = []

            # Scaler
            scaler = RobustScaler()
            steps.append(("scaler", scaler))

            # Feature selection
            if config.feature_selector:
                selector_model = self._create_model(config)
                selector_model.set_params(**{k: v for k, v in config.params.items() if k != "n_estimators"})
                steps.append((
                    "selector",
                    SelectFromModel(
                        selector_model, threshold="median", max_features=50
                    ),
                ))

            # Model
            model = self._create_model(config)
            steps.append(("model", model))

            pipeline = Pipeline(steps)

            # Train
            pipeline.fit(X_train, y_train)

            if not config.calibrate:
                calibration_status = "disabled"
            elif val_df is None:
                calibration_status = "skipped_no_validation"
            elif y_val.empty:
                calibration_status = "skipped_no_usable_validation"
            elif y_val.nunique() < 2:
                calibration_status = "skipped_single_class_validation"
            elif len(y_val) < MIN_ISOTONIC_SAMPLES:
                calibration_status = "skipped_insufficient_samples"
            else:
                if FrozenEstimator is None:
                    raise RuntimeError(
                        "Calibration requires a scikit-learn version with "
                        "sklearn.frozen.FrozenEstimator"
                    )
                calibrated_model = CalibratedClassifierCV(
                    FrozenEstimator(pipeline), method="isotonic"
                )
                calibrated_model.fit(X_val, y_val)
                pipeline = Pipeline([("calibrated_model", calibrated_model)])
                calibration_status = "calibrated_isotonic"

            # Determine optimal threshold on validation
            threshold = config.threshold
            y_val_pred = None
            y_val_proba = None
            if val_df is not None and not y_val.empty:
                y_val_proba = pipeline.predict_proba(X_val)[:, 1]
                # Find threshold that maximizes F1
                best_f1 = None
                best_thresh = config.threshold
                candidate_thresholds = [
                    config.threshold,
                    *np.linspace(0.1, 0.9, 17),
                ]
                for thresh in candidate_thresholds:
                    preds = (y_val_proba >= thresh).astype(int)
                    f1 = _defined_binary_metrics(y_val, preds).get("f1")
                    if f1 is not None and (best_f1 is None or f1 > best_f1):
                        best_f1 = f1
                        best_thresh = thresh
                threshold = best_thresh
                y_val_pred = (y_val_proba >= threshold).astype(int)

            # Evaluate
            metrics: Dict[str, Any] = {
                "calibration_status": calibration_status,
                "dropped_non_finite_train_rows": dropped_train_rows,
                "dropped_non_finite_validation_rows": dropped_validation_rows,
            }
            if val_df is not None and not y_val.empty:
                validation_classes = int(y_val.nunique())
                metrics.update(
                    {
                        "validation_classes": validation_classes,
                        "accuracy": accuracy_score(y_val, y_val_pred),
                        "log_loss": log_loss(y_val, y_val_proba, labels=[0, 1]),
                        "brier": brier_score_loss(y_val, y_val_proba),
                    }
                )
                metrics.update(_defined_binary_metrics(y_val, y_val_pred))
                if validation_classes == 2:
                    metrics["roc_auc"] = roc_auc_score(y_val, y_val_proba)

            # Create trained model
            trained = TrainedModel(
                name=config.name,
                model=pipeline,
                feature_names=feature_names,
                calibration_threshold=threshold,
                metrics=metrics,
                trained_at=datetime.now(timezone.utc).isoformat(),
                feature_hash=hashlib.sha256(",".join(feature_names).encode()).hexdigest()[:16],
                config_hash=hashlib.sha256(json.dumps(config.params, sort_keys=True).encode()).hexdigest()[:16],
            )

            models.append(trained)
            logger.info(f"{config.name} trained: {metrics}")

        self.models = models
        return self.models

    def predict(self, df: pd.DataFrame, model_name: Optional[str] = None) -> Dict[str, np.ndarray]:
        """Get predictions from all or specific model."""
        results = {}
        for model in self.models:
            if model_name and model.name != model_name:
                continue
            probabilities = model.predict_proba(df)
            results[model.name] = {
                "proba": probabilities,
                "pred": (
                    probabilities >= model.calibration_threshold
                ).astype(int),
            }
        return results

    def save(self, path: Path) -> None:
        """Save trained models."""
        path.mkdir(parents=True, exist_ok=True)
        for model in self.models:
            model_path = path / f"{model.name}.joblib"
            joblib.dump(model, model_path)

        # Save metadata
        metadata = {
            "feature_names": self.feature_names,
            "models": [
                {
                    "name": m.name,
                    "feature_hash": m.feature_hash,
                    "config_hash": m.config_hash,
                    "threshold": m.calibration_threshold,
                    "metrics": m.metrics,
                    "trained_at": m.trained_at,
                }
                for m in self.models
            ],
        }
        (path / "metadata.json").write_text(json.dumps(metadata, indent=2))

    @classmethod
    def load(cls, path: Path) -> "MLPipeline":
        """Load trained models."""
        pipeline = cls()
        metadata_path = path / "metadata.json"
        if not metadata_path.exists():
            raise FileNotFoundError(f"No metadata at {path}")

        metadata = json.loads(metadata_path.read_text())
        pipeline.feature_names = metadata["feature_names"]

        for model_info in metadata["models"]:
            model_path = path / f"{model_info['name']}.joblib"
            if model_path.exists():
                model = joblib.load(model_path)
                pipeline.models.append(model)

        return pipeline

    def get_ensemble_prediction(
        self,
        df: pd.DataFrame,
        method: str = "average",
        weights: Optional[List[float]] = None,
    ) -> np.ndarray:
        """Get ensemble prediction."""
        preds = {}
        for model in self.models:
            preds[model.name] = model.predict_proba(df)

        if method == "average":
            return np.mean(list(preds.values()), axis=0)
        elif method == "weighted" and weights:
            return np.average(list(preds.values()), axis=0, weights=weights)
        else:
            return np.mean(list(preds.values()), axis=0)
