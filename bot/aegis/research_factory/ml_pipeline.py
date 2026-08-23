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
    precision_score,
    recall_score,
    f1_score,
    roc_auc_score,
    log_loss,
    brier_score_loss,
)
from sklearn.model_selection import TimeSeriesSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler, RobustScaler
from sklearn.feature_selection import SelectFromModel

logger = logging.getLogger(__name__)


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
        calibrate=True,
    ),
]


@dataclass
class TrainedModel:
    """A trained model with metadata."""
    name: str
    model: Any
    scaler: Any
    feature_selector: Any
    feature_names: List[str]
    calibration_threshold: float
    metrics: Dict[str, float]
    trained_at: str
    feature_hash: str
    config_hash: str

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        """Predict probabilities."""
        # Ensure features match
        X = X[self.feature_names]
        X_scaled = self.scaler.transform(X)
        if self.feature_selector:
            X_selected = self.feature_selector.transform(X_scaled)
        else:
            X_selected = X_scaled
        return self.model.predict_proba(X_selected)[:, 1]

    def predict(self, X: pd.DataFrame, threshold: Optional[float] = None) -> np.ndarray:
        """Predict class labels."""
        threshold = threshold or self.calibration_threshold
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

    def _prepare_features(self, df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
        """Extract features and labels from dataframe."""
        # Identify feature columns (exclude metadata columns)
        exclude_cols = {
            "time", "source_file", "symbol", "target", "label",
            "future_max_high", "future_min_low", "profit_barrier_first",
            "mfe", "mae", "time_to_target", "no_progress", "tail_loss",
            "profit_barrier_first",
        }

        feature_cols = [c for c in df.columns if c not in exclude_cols and df[c].dtype in [np.float64, np.float32, np.int64, np.int32]]

        X = df[feature_cols].replace([np.inf, -np.inf], np.nan).fillna(0)
        y = df.get("profit_barrier_first", pd.Series(0, index=df.index)).astype(int)

        return X.values, y.values, feature_cols

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
        test_df: Optional[pd.DataFrame] = None,
    ) -> List[TrainedModel]:
        """Train all models."""
        # Prepare features
        X_train, y_train, feature_names = self._prepare_features(train_df)
        self.feature_names = feature_names

        if val_df is not None:
            X_val, y_val, _ = self._prepare_features(val_df)
        else:
            X_val, y_val = None, None

        if test_df is not None:
            X_test, y_test, _ = self._prepare_features(test_df)
        else:
            X_test, y_test = None, None

        trained_models = []

        for config in self.configs:
            logger.info(f"Training {config.name}...")

            # Create base model
            base_model = self._create_model(config)

            # Create pipeline
            steps = []

            # Scaler
            scaler = RobustScaler()
            steps.append(("scaler", scaler))

            # Feature selection
            feature_selector = None
            if config.feature_selector:
                selector_model = self._create_model(config)
                selector_model.set_params(**{k: v for k, v in config.params.items() if k != "n_estimators"})
                feature_selector = SelectFromModel(selector_model, threshold="median", max_features=50)
                steps.append(("selector", feature_selector))

            # Model
            model = self._create_model(config)
            steps.append(("model", model))

            pipeline = Pipeline(steps)

            # Train
            pipeline.fit(X_train, y_train)

            # Calibrate if requested
            if config.calibrate and val_df is not None:
                X_val, y_val, _ = self._prepare_features(val_df)
                X_val = val_df[self.feature_names].replace([np.inf, -np.inf], np.nan).fillna(0)
                pipeline.named_steps["model"] = CalibratedClassifierCV(
                    pipeline.named_steps["model"],
                    method="isotonic",
                    cv="prefit",
                )
                pipeline.named_steps["model"].fit(X_val, y_val)

            # Determine optimal threshold on validation
            threshold = 0.5
            if val_df is not None:
                y_val_pred = pipeline.predict_proba(X_val)[:, 1]
                # Find threshold that maximizes F1
                best_f1 = 0
                best_thresh = 0.5
                for thresh in np.linspace(0.1, 0.9, 17):
                    preds = (y_val_pred >= thresh).astype(int)
                    f1 = f1_score(y_val, preds, zero_division=0)
                    if f1 > best_f1:
                        best_f1 = f1
                        best_thresh = thresh
                threshold = best_thresh

            # Evaluate
            metrics = {}
            if val_df is not None:
                y_pred = pipeline.predict(X_val)
                y_proba = pipeline.predict_proba(X_val)[:, 1]
                metrics = {
                    "accuracy": accuracy_score(y_val, y_pred),
                    "precision": precision_score(y_val, y_pred, zero_division=0),
                    "recall": recall_score(y_val, y_pred, zero_division=0),
                    "f1": f1_score(y_val, y_pred, zero_division=0),
                    "roc_auc": roc_auc_score(y_val, y_proba),
                    "log_loss": log_loss(y_val, y_proba),
                    "brier": brier_score_loss(y_val, y_proba),
                }

            if test_df is not None:
                X_test, y_test, _ = self._prepare_features(test_df)
                y_test_pred = pipeline.predict(X_test)
                y_test_proba = pipeline.predict_proba(X_test)[:, 1]
                metrics.update({
                    "test_accuracy": accuracy_score(y_test, y_test_pred),
                    "test_f1": f1_score(y_test, y_test_pred, zero_division=0),
                    "test_roc_auc": roc_auc_score(y_test, y_test_proba),
                })

            # Create trained model
            trained = TrainedModel(
                name=config.name,
                model=pipeline,
                scaler=scaler,
                feature_selector=feature_selector,
                feature_names=feature_names,
                calibration_threshold=threshold,
                metrics=metrics,
                trained_at=datetime.now(timezone.utc).isoformat(),
                feature_hash=hashlib.sha256(",".join(feature_names).encode()).hexdigest()[:16],
                config_hash=hashlib.sha256(json.dumps(config.params, sort_keys=True).encode()).hexdigest()[:16],
            )

            self.models.append(trained)
            logger.info(f"{config.name} trained: {metrics}")

        return self.models

    def predict(self, df: pd.DataFrame, model_name: Optional[str] = None) -> Dict[str, np.ndarray]:
        """Get predictions from all or specific model."""
        X = df[self.feature_names].replace([np.inf, -np.inf], np.nan).fillna(0)

        results = {}
        for model in self.models:
            if model_name and model.name != model_name:
                continue
            results[model.name] = {
                "proba": model.predict_proba(df),
                "pred": model.predict(df),
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