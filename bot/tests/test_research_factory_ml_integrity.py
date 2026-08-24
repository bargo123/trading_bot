from __future__ import annotations

import inspect
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest
from sklearn.calibration import CalibratedClassifierCV
from sklearn.frozen import FrozenEstimator
from sklearn.pipeline import Pipeline

import aegis.research_factory.ml_pipeline as ml_pipeline_module
from aegis.research_factory.ml_pipeline import (
    DEFAULT_MODEL_CONFIGS,
    MLPipeline,
    ModelConfig,
)


def small_logistic_config(*, calibrate: bool = False) -> ModelConfig:
    return ModelConfig(
        name="logistic",
        model_type="logistic",
        params={"C": 1.0, "max_iter": 100},
        feature_selector=False,
        calibrate=calibrate,
    )


def small_random_forest_config() -> ModelConfig:
    return ModelConfig(
        name="rf",
        model_type="random_forest",
        params={"n_estimators": 8, "max_depth": 3, "n_jobs": 1},
        feature_selector=True,
        calibrate=False,
    )


def labeled_frame(rows: int = 80) -> pd.DataFrame:
    target = np.tile([0, 1], rows // 2 + 1)[:rows]
    return pd.DataFrame(
        {
            "time": pd.date_range("2026-01-01", periods=rows, freq="min", tz="UTC"),
            "source_file": ["fixture.csv"] * rows,
            "source_kind": ["test"] * rows,
            "source_quality": ["observed"] * rows,
            "symbol": ["EURUSD"] * rows,
            "timeframe": ["1m"] * rows,
            "signal": target + np.linspace(-0.2, 0.2, rows),
            "profit_barrier_first": target,
            "target_direction": 1 - target,
            "direction": target,
            "return_horizon": target / 100,
            "mfe": target + 0.1,
            "mae": 1.1 - target,
            "time_to_target": np.ones(rows),
            "no_progress": 1 - target,
            "tail_loss": 1 - target,
        }
    )


def test_prepare_features_requires_explicit_target() -> None:
    pipeline = MLPipeline(configs=[small_logistic_config()])

    with pytest.raises(ValueError, match="profit_barrier_first"):
        pipeline.train(pd.DataFrame({"feature": [0.0, 1.0]}))


def test_prepare_features_excludes_all_labels_and_provenance() -> None:
    pipeline = MLPipeline(configs=[small_logistic_config()])
    frame = labeled_frame()

    pipeline.train(frame.iloc[:60], frame.iloc[60:])

    assert pipeline.feature_names == ["signal"]


def test_training_drops_non_finite_supervised_rows_and_records_counts() -> None:
    train = labeled_frame(60)
    validation = labeled_frame(20)
    train.loc[train.index[:2], "signal"] = [np.nan, np.inf]
    validation.loc[validation.index[:2], "signal"] = [np.nan, -np.inf]
    expected_center = np.median(train.loc[train["signal"].notna() & np.isfinite(train["signal"]), "signal"])

    trained = MLPipeline(configs=[small_logistic_config()]).train(
        train, validation
    )[0]

    assert trained.metrics["dropped_non_finite_train_rows"] == 2
    assert trained.metrics["dropped_non_finite_validation_rows"] == 2
    assert trained.model.named_steps["scaler"].center_[0] == pytest.approx(
        expected_center
    )


def test_training_fails_if_non_finite_row_removal_leaves_one_class() -> None:
    frame = labeled_frame(20)
    frame.loc[frame["profit_barrier_first"] == 1, "signal"] = np.nan
    pipeline = MLPipeline(configs=[small_logistic_config()])

    with pytest.raises(ValueError, match="two classes.*non-finite"):
        pipeline.train(frame)

    assert pipeline.models == []


def test_predict_proba_uses_the_fitted_pipeline_once_without_double_preprocessing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pipeline = MLPipeline(configs=[small_logistic_config()])
    frame = labeled_frame()
    trained = pipeline.train(frame.iloc[:60], frame.iloc[60:])[0]
    inference_frame = frame.iloc[60:].copy()
    inference_frame.loc[inference_frame.index[0], "signal"] = np.inf
    inference_frame.loc[inference_frame.index[1], "signal"] = np.nan
    normalized = inference_frame[["signal"]].replace(
        [np.inf, -np.inf], np.nan
    ).fillna(0)

    assert isinstance(trained.model, Pipeline)
    expected = trained.model.predict_proba(normalized)[:, 1]
    original_predict_proba = trained.model.predict_proba
    calls = 0

    def counting_predict_proba(features: pd.DataFrame) -> np.ndarray:
        nonlocal calls
        calls += 1
        return original_predict_proba(features)

    monkeypatch.setattr(trained.model, "predict_proba", counting_predict_proba)
    actual = trained.predict_proba(inference_frame)

    np.testing.assert_allclose(actual, expected)
    assert np.isfinite(actual).all()
    assert len(actual) == len(inference_frame)
    assert calls == 1


def test_pipeline_predict_reuses_one_probability_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frame = labeled_frame()
    pipeline = MLPipeline(configs=[small_logistic_config()])
    trained = pipeline.train(frame.iloc[:60], frame.iloc[60:])[0]
    original_predict_proba = trained.predict_proba
    calls = 0

    def counting_predict_proba(features: pd.DataFrame) -> np.ndarray:
        nonlocal calls
        calls += 1
        return original_predict_proba(features)

    monkeypatch.setattr(trained, "predict_proba", counting_predict_proba)
    result = pipeline.predict(frame.iloc[60:])["logistic"]

    np.testing.assert_array_equal(
        result["pred"],
        (result["proba"] >= trained.calibration_threshold).astype(int),
    )
    assert calls == 1


def test_null_target_fails_explicitly() -> None:
    frame = labeled_frame(20)
    frame.loc[frame.index[3], "profit_barrier_first"] = np.nan

    with pytest.raises(ValueError, match="target.*null|Target.*null"):
        MLPipeline(configs=[small_logistic_config()]).train(frame)


def test_single_class_training_target_fails_explicitly() -> None:
    frame = labeled_frame(20)
    frame["profit_barrier_first"] = 1

    with pytest.raises(ValueError, match="two classes"):
        MLPipeline(configs=[small_logistic_config()]).train(frame)


@pytest.mark.parametrize(
    "invalid_target",
    [
        pytest.param([0, 0.5] * 10, id="fractional"),
        pytest.param([1, 2] * 10, id="non_binary_two_class"),
    ],
)
def test_target_rejects_values_outside_binary_membership(
    invalid_target: list[float],
) -> None:
    frame = labeled_frame(20)
    frame["profit_barrier_first"] = invalid_target

    with pytest.raises(
        ValueError, match="profit_barrier_first.*binary.*0.*1"
    ):
        MLPipeline(configs=[small_logistic_config()]).train(frame)


def test_no_numeric_model_features_fails_explicitly() -> None:
    frame = labeled_frame(20).drop(columns="signal")

    with pytest.raises(ValueError, match="No numeric model features"):
        MLPipeline(configs=[small_logistic_config()]).train(frame)


def test_validation_feature_mismatch_fails_explicitly() -> None:
    train = labeled_frame(40)
    validation = labeled_frame(20)
    validation["unexpected_numeric"] = np.arange(len(validation))

    with pytest.raises(ValueError, match="Feature mismatch.*unexpected_numeric"):
        MLPipeline(configs=[small_logistic_config()]).train(train, validation)


def test_validation_metrics_use_the_tuned_threshold() -> None:
    train = labeled_frame(60)
    train["signal"] = train["profit_barrier_first"]
    validation = labeled_frame(20)
    validation["signal"] = validation["profit_barrier_first"] - 0.8
    trained = MLPipeline(configs=[small_logistic_config()]).train(
        train, validation
    )[0]

    probabilities = trained.predict_proba(validation)
    predictions = (probabilities >= trained.calibration_threshold).astype(int)

    assert trained.calibration_threshold != 0.5
    assert trained.metrics["accuracy"] == pytest.approx(
        np.mean(predictions == validation["profit_barrier_first"].to_numpy())
    )
    assert trained.metrics["f1"] == pytest.approx(1.0)


def test_one_class_validation_omits_undefined_roc_auc() -> None:
    train = labeled_frame(60)
    validation = labeled_frame(10)
    validation["profit_barrier_first"] = 0

    trained = MLPipeline(configs=[small_logistic_config()]).train(
        train, validation
    )[0]

    assert "roc_auc" not in trained.metrics
    assert trained.metrics["validation_classes"] == 1


def test_all_negative_validation_omits_undefined_metrics_and_skips_threshold_tuning() -> None:
    train = labeled_frame(60)
    validation = labeled_frame(10)
    validation["profit_barrier_first"] = 0
    validation["signal"] = -100.0

    trained = MLPipeline(configs=[small_logistic_config()]).train(
        train, validation
    )[0]

    assert trained.calibration_threshold == 0.5
    for metric in ("precision", "recall", "f1"):
        assert metric not in trained.metrics


def test_all_positive_validation_reports_defined_positive_class_metrics() -> None:
    train = labeled_frame(60)
    validation = labeled_frame(10)
    validation["profit_barrier_first"] = 1
    validation["signal"] = 100.0

    trained = MLPipeline(configs=[small_logistic_config()]).train(
        train, validation
    )[0]

    for metric in ("precision", "recall", "f1"):
        assert trained.metrics[metric] == pytest.approx(1.0)


def test_no_positive_predictions_omit_only_undefined_precision() -> None:
    train = labeled_frame(60)
    validation = labeled_frame(10)
    validation["signal"] = -100.0

    trained = MLPipeline(configs=[small_logistic_config()]).train(
        train, validation
    )[0]

    assert "precision" not in trained.metrics
    assert trained.metrics["recall"] == pytest.approx(0.0)
    assert trained.metrics["f1"] == pytest.approx(0.0)


def test_training_interface_does_not_accept_or_report_test_data() -> None:
    assert "test_df" not in inspect.signature(MLPipeline.train).parameters
    frame = labeled_frame(80)
    pipeline = MLPipeline(configs=[small_logistic_config()])

    with pytest.raises(TypeError):
        pipeline.train(frame.iloc[:50], frame.iloc[50:65], frame.iloc[65:])


def test_small_validation_set_skips_isotonic_calibration_with_status() -> None:
    train = labeled_frame(60)
    validation = labeled_frame(4)

    trained = MLPipeline(configs=[small_logistic_config(calibrate=True)]).train(
        train, validation
    )[0]

    assert trained.metrics["calibration_status"] == "skipped_insufficient_samples"
    assert np.isfinite(trained.predict_proba(validation)).all()


def test_isotonic_calibration_wraps_the_fitted_preprocessing_pipeline() -> None:
    frame = labeled_frame(80)

    trained = MLPipeline(
        configs=[small_logistic_config(calibrate=True)]
    ).train(frame.iloc[:60], frame.iloc[60:])[0]

    assert isinstance(trained.model, Pipeline)
    assert trained.metrics["calibration_status"] == "calibrated_isotonic"
    calibrated = trained.model.named_steps["calibrated_model"]
    assert isinstance(calibrated, CalibratedClassifierCV)
    assert isinstance(calibrated.estimator, FrozenEstimator)
    frozen_pipeline = calibrated.estimator.estimator
    assert isinstance(frozen_pipeline, Pipeline)
    assert list(frozen_pipeline.named_steps) == ["scaler", "model"]
    assert np.isfinite(trained.predict_proba(frame.iloc[60:])).all()


def test_calibration_fails_explicitly_when_frozen_estimator_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frame = labeled_frame(80)
    monkeypatch.setattr(ml_pipeline_module, "FrozenEstimator", None)

    with pytest.raises(RuntimeError, match="scikit-learn.*FrozenEstimator"):
        MLPipeline(configs=[small_logistic_config(calibrate=True)]).train(
            frame.iloc[:60], frame.iloc[60:]
        )


def test_every_default_model_configuration_fits_with_reduced_cost() -> None:
    frame = labeled_frame(80)

    for default in DEFAULT_MODEL_CONFIGS:
        params = dict(default.params)
        if "n_estimators" in params:
            params["n_estimators"] = 8
        if "max_iter" in params:
            params["max_iter"] = 20
        if "n_jobs" in params:
            params["n_jobs"] = 1
        config = replace(default, params=params)

        trained = MLPipeline(configs=[config]).train(
            frame.iloc[:60], frame.iloc[60:]
        )[0]

        assert trained.name == default.name
        assert np.isfinite(trained.predict_proba(frame.iloc[60:])).all()


def test_training_failure_does_not_publish_partially_built_models() -> None:
    frame = labeled_frame(80)
    invalid = ModelConfig(
        name="invalid",
        model_type="unsupported",
        params={},
        feature_selector=False,
        calibrate=False,
    )
    pipeline = MLPipeline(configs=[small_logistic_config(), invalid])

    with pytest.raises(ValueError, match="Unknown model type"):
        pipeline.train(frame.iloc[:60], frame.iloc[60:])

    assert pipeline.models == []


def test_real_models_fit_predict_and_repeated_training_resets_state() -> None:
    frame = labeled_frame(80)
    pipeline = MLPipeline(
        configs=[small_logistic_config(), small_random_forest_config()]
    )

    first_models = pipeline.train(frame.iloc[:60], frame.iloc[60:])
    second_models = pipeline.train(frame.iloc[:60], frame.iloc[60:])

    assert len(first_models) == 2
    assert len(second_models) == 2
    assert len(pipeline.models) == 2
    assert [model.name for model in second_models] == ["logistic", "rf"]
    for model in second_models:
        probabilities = model.predict_proba(frame.iloc[60:])
        assert len(probabilities) == 20
        assert np.isfinite(probabilities).all()


def test_calibrated_ensemble_exposes_agreement_uncertainty_and_abstention() -> None:
    frame = labeled_frame(80)
    configs = [
        small_logistic_config(calibrate=True),
        ModelConfig(
            name="logistic_2",
            model_type="logistic",
            params={"C": 0.5, "max_iter": 100},
            feature_selector=False,
            calibrate=True,
        ),
    ]
    pipeline_obj = MLPipeline(configs=configs)
    pipeline_obj.train(frame.iloc[:60], frame.iloc[60:])

    result = pipeline_obj.get_calibrated_ensemble_prediction(frame.iloc[60:])

    assert result["model_count"] == 2
    assert len(result["probability"]) == 20
    assert len(result["model_agreement"]) == 20
    assert len(result["uncertainty"]) == 20
    assert result["weights"]
    assert sum(result["weights"].values()) == pytest.approx(1.0)
    assert result["calibration_status"] == "calibrated"


def test_calibrated_ensemble_abstains_when_calibration_or_model_count_is_missing() -> None:
    frame = labeled_frame(80)
    pipeline = MLPipeline(configs=[small_logistic_config(calibrate=False)])
    pipeline.train(frame.iloc[:60], frame.iloc[60:])

    result = pipeline.get_calibrated_ensemble_prediction(frame.iloc[60:])

    assert result["calibration_status"] == "not_calibrated"
    assert result["abstain"].all()
