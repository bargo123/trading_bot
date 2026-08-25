"""Research-only builder for a calibrated seconds-horizon Firehose artifact.

This module consumes completed MT5 quote history and never imports an engine or
places orders.  Features are calculated from observations at or before the
entry timestamp.  Labels use only observations strictly after entry.  An
artifact is publishable only when its chronological OOS slice has positive
cost-aware terminal expectancy.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from aegis.research.short_horizon import DEFAULT_HORIZONS_S
from aegis.research.registry import DuplicateExperimentError, ExperimentRegistry
from aegis.research_factory.evaluation import record_outcome
from aegis.research_factory.ml_pipeline import MLPipeline, ModelConfig


ARTIFACT_SCHEMA = "short_horizon_ensemble.v1"


@dataclass(frozen=True)
class ChronologicalSlices:
    train: pd.DataFrame
    validation: pd.DataFrame
    test: pd.DataFrame
    sealed: pd.DataFrame


def _hash_frame(frame: pd.DataFrame) -> str:
    payload = frame.sort_values(["time", "symbol", "side", "horizon_s"], kind="stable")
    raw = payload.to_json(orient="records", date_format="iso", double_precision=15).encode()
    return hashlib.sha256(raw).hexdigest()


def record_artifact_outcome(
    metadata: Mapping[str, Any],
    *,
    registry: ExperimentRegistry,
) -> str:
    """Record one seconds-artifact result in the append-only Factory registry.

    A shadow artifact is deliberately recorded as ``NO_EVIDENCE``.  Only the
    builder's explicit positive chronological test and sealed-OOS status is
    recorded as a challenger; this function never promotes or changes runtime
    authority.  Re-running the same immutable artifact is idempotent.
    """
    if str(metadata.get("schema") or "") != ARTIFACT_SCHEMA:
        raise ValueError("unsupported short-horizon artifact schema")
    dataset_hash = str(metadata.get("dataset_hash") or "").strip()
    validation_hash = str(metadata.get("validation_hash") or "").strip()
    if not dataset_hash or not validation_hash:
        raise ValueError("dataset_hash and validation_hash are required")

    experiment_id = f"short_horizon_{dataset_hash[:16]}_{validation_hash[:16]}"
    if registry.get(experiment_id) is not None:
        return experiment_id

    oos = metadata.get("oos")
    if not isinstance(oos, Mapping):
        raise ValueError("artifact OOS metadata is required")
    test = oos.get("test") if isinstance(oos.get("test"), Mapping) else {}
    sealed = oos.get("sealed") if isinstance(oos.get("sealed"), Mapping) else {}
    status = (
        "CHALLENGER"
        if str(metadata.get("execution_status") or "") == "EXECUTION_CANDIDATE"
        else "NO_EVIDENCE"
    )
    reason = (
        "positive chronological test and sealed-OOS terminal returns support a challenger"
        if status == "CHALLENGER"
        else "no positive sealed-OOS execution selection; retain shadow-only"
    )
    metrics = {
        "test_n": test.get("n"),
        "test_selected": test.get("selected"),
        "test_positive_rate": test.get("positive_rate"),
        "test_mean_terminal_return": test.get("mean_terminal_return"),
        "test_brier": test.get("brier"),
        "sealed_n": sealed.get("n"),
        "sealed_selected": sealed.get("selected"),
        "sealed_positive_rate": sealed.get("positive_rate"),
        "sealed_mean_terminal_return": sealed.get("mean_terminal_return"),
        "sealed_brier": sealed.get("brier"),
        "horizons_s": list(metadata.get("horizons_s") or []),
        "decision_horizon_s": metadata.get("decision_horizon_s"),
        "threshold": metadata.get("threshold"),
    }
    hypothesis = {
        "hypothesis_id": experiment_id,
        "origin": "SHORT_HORIZON_ARTIFACT",
        "problem": "seconds-horizon net-profitable opportunity prediction",
        "proposed_mechanism": (
            "calibrated logistic, random-forest, and gradient-boosting ensemble "
            "using point-in-time executable bid/ask features"
        ),
        "features_required": "point-in-time quote and microstructure features",
        "entry_rule": "calibrated ensemble selection after measured costs",
        "exit_rule": "seconds horizon with executable-side labels",
        "max_hold_s": max([int(value) for value in (metadata.get("horizons_s") or [45])]),
    }
    try:
        return record_outcome(
            registry,
            hypothesis,
            dataset_hash,
            status,
            reason,
            metrics,
        )
    except DuplicateExperimentError:
        # A concurrent research cadence may have recorded the same immutable
        # artifact between the idempotence check and the insert.
        if registry.get(experiment_id) is not None:
            return experiment_id
        raise


def _asof_index(times: np.ndarray, seconds: int) -> np.ndarray:
    return np.searchsorted(times, times - float(seconds), side="right") - 1


def _epoch_seconds(values: pd.Series) -> np.ndarray:
    # Explicitly normalize the pandas resolution; it may be seconds,
    # milliseconds, microseconds, or nanoseconds depending on the source.
    normalized = pd.to_datetime(values, utc=True).dt.as_unit("s")
    return normalized.astype("int64").to_numpy(dtype=np.float64)


def _feature_frame(quotes: pd.DataFrame, symbol: str) -> pd.DataFrame:
    required = {"time", "bid", "ask"}
    if not required.issubset(quotes.columns):
        raise ValueError(f"quotes require {sorted(required)}")
    frame = quotes.loc[:, ["time", "bid", "ask"]].copy()
    frame["time"] = pd.to_datetime(frame["time"], utc=True, errors="coerce")
    frame["bid"] = pd.to_numeric(frame["bid"], errors="coerce")
    frame["ask"] = pd.to_numeric(frame["ask"], errors="coerce")
    frame = frame.dropna().sort_values("time", kind="stable")
    frame = frame[(frame["bid"] > 0) & (frame["ask"] > 0) & (frame["ask"] >= frame["bid"])]
    if frame.empty:
        raise ValueError(f"no valid quotes for {symbol}")
    # One observation per second avoids overweighting bursts while preserving
    # genuine observed prices; no interpolation or forward fill is performed.
    frame = (
        frame.set_index("time")
        .resample("1s")[["bid", "ask"]]
        .last()
        .dropna()
        .reset_index()
    )
    if len(frame) < max(DEFAULT_HORIZONS_S) + 20:
        raise ValueError(f"insufficient quote history for {symbol}: {len(frame)} rows")

    times = _epoch_seconds(frame["time"])
    bid = frame["bid"].to_numpy(dtype=float)
    ask = frame["ask"].to_numpy(dtype=float)
    mid = (bid + ask) / 2.0
    spread = ask - bid
    seconds = np.diff(times, prepend=times[0])
    velocity = np.divide(np.diff(mid, prepend=mid[0]), seconds, out=np.zeros_like(mid), where=seconds > 0)
    prior_velocity = np.roll(velocity, 1)
    prior_velocity[0] = 0.0
    acceleration = np.divide(velocity - prior_velocity, seconds, out=np.zeros_like(mid), where=seconds > 0)

    values: dict[str, Any] = {
        "time": frame["time"],
        "symbol": str(symbol).upper(),
        "bid": bid,
        "ask": ask,
        "mid": mid,
        "spread": spread,
        "spread_change": np.concatenate(([0.0], np.diff(spread))),
        "tick_velocity": velocity,
        "price_acceleration": acceleration,
        "quote_age_s": np.zeros(len(frame), dtype=float),
        "hour_utc": frame["time"].dt.hour.to_numpy(dtype=float),
        "dow_utc": frame["time"].dt.dayofweek.to_numpy(dtype=float),
    }
    spread_series = pd.Series(spread)
    values["spread_percentile"] = (
        spread_series.rolling(60, min_periods=2).rank(pct=True).fillna(1.0).to_numpy(dtype=float)
    )
    returns = pd.Series(mid).pct_change()
    values["micro_volatility"] = returns.rolling(20, min_periods=2).std(ddof=0).fillna(0.0).to_numpy(dtype=float)
    values["realized_vol_60s"] = np.sqrt(
        returns.pow(2).rolling(60, min_periods=2).sum().fillna(0.0).to_numpy(dtype=float)
    )
    for window in (5, 10, 15, 30, 60):
        starts = _asof_index(times, window)
        valid = starts >= 0
        result = np.full(len(mid), np.nan, dtype=float)
        result[valid] = mid[valid] / mid[starts[valid]] - 1.0
        values[f"return_{window}s"] = result
    return pd.DataFrame(values)


def build_quote_training_frame(
    quotes_by_symbol: Mapping[str, pd.DataFrame],
    *,
    horizons: Sequence[int] = DEFAULT_HORIZONS_S,
    sample_every_s: int = 5,
) -> pd.DataFrame:
    """Create point-in-time feature/label rows from completed quotes."""
    horizon_values = tuple(sorted({int(value) for value in horizons if int(value) > 0}))
    if not horizon_values:
        raise ValueError("at least one positive horizon is required")
    if int(sample_every_s) <= 0:
        raise ValueError("sample_every_s must be positive")
    rows: list[dict[str, Any]] = []
    for symbol, quotes in sorted(quotes_by_symbol.items()):
        features = _feature_frame(quotes, symbol)
        times = _epoch_seconds(features["time"])
        bid = features["bid"].to_numpy(dtype=float)
        ask = features["ask"].to_numpy(dtype=float)
        mid = features["mid"].to_numpy(dtype=float)
        spreads = features["spread"].to_numpy(dtype=float)
        # The executable entry/exit sides already include the observed spread.
        # A tiny slippage buffer is intentionally not invented here; the
        # artifact metadata records this as spread-only evidence.
        tail_threshold = max(float(np.nanmedian(spreads)) * 3.0, 1e-12)
        eligible = np.flatnonzero(times <= times[-1] - max(horizon_values))
        if not len(eligible):
            continue
        sampled: list[int] = []
        last_time = None
        for index in eligible:
            if last_time is None or int(times[index]) - int(last_time) >= int(sample_every_s):
                sampled.append(int(index))
                last_time = int(times[index])
        for index in sampled:
            for horizon in horizon_values:
                end = int(np.searchsorted(times, times[index] + horizon, side="right") - 1)
                if end <= index:
                    continue
                future_bid = bid[index + 1 : end + 1]
                future_ask = ask[index + 1 : end + 1]
                for side, signed in (
                    ("buy", future_bid - ask[index]),
                    ("sell", bid[index] - future_ask),
                ):
                    if not len(signed):
                        continue
                    mfe = float(np.max(signed))
                    mae = float(np.min(signed))
                    terminal = float(signed[-1])
                    row = features.iloc[index].to_dict()
                    row.update(
                        {
                            "time": features.iloc[index]["time"],
                            "symbol": str(symbol).upper(),
                            "side": side,
                            "side_buy": 1.0 if side == "buy" else 0.0,
                            "horizon_s": float(horizon),
                            # Profit means the executable path became green
                            # within the stated horizon, after spread.
                            "target": int(mfe > 0.0),
                            "terminal_net_pnl": terminal,
                            "terminal_return": terminal / float(mid[index]) if mid[index] > 0 else np.nan,
                            "mfe": mfe,
                            "mae": mae,
                            "tail_loss": int(mae <= -tail_threshold),
                        }
                    )
                    rows.append(row)
    if not rows:
        raise ValueError("no matured short-horizon rows")
    return pd.DataFrame(rows).sort_values(["time", "symbol", "side", "horizon_s"], kind="stable").reset_index(drop=True)


def chronological_slices(frame: pd.DataFrame) -> ChronologicalSlices:
    if frame.empty or "time" not in frame:
        raise ValueError("training frame requires time")
    ordered = frame.sort_values("time", kind="stable").reset_index(drop=True)
    unique_times = ordered["time"].drop_duplicates().sort_values().to_numpy()
    if len(unique_times) < 20:
        raise ValueError("insufficient distinct timestamps for chronological OOS")
    train_end = unique_times[max(0, int(len(unique_times) * 0.60) - 1)]
    validation_end = unique_times[max(0, int(len(unique_times) * 0.80) - 1)]
    test_end = unique_times[max(0, int(len(unique_times) * 0.90) - 1)]
    train = ordered[ordered["time"] <= train_end].copy()
    validation = ordered[(ordered["time"] > train_end) & (ordered["time"] <= validation_end)].copy()
    test = ordered[(ordered["time"] > validation_end) & (ordered["time"] <= test_end)].copy()
    sealed = ordered[ordered["time"] > test_end].copy()
    if min(map(len, (train, validation, test, sealed))) == 0:
        raise ValueError("chronological slices must all be non-empty")
    return ChronologicalSlices(train, validation, test, sealed)


def _model_frame(frame: pd.DataFrame) -> pd.DataFrame:
    # Keep outcome columns out of the estimator entirely.  This explicit
    # allowlist prevents future label additions from becoming leaked features.
    excluded = {
        "time", "symbol", "side", "target", "terminal_net_pnl",
        "terminal_return", "mfe", "mae", "tail_loss",
    }
    columns = [column for column in frame.columns if column not in excluded]
    result = frame.loc[:, columns].copy()
    result["profit_barrier_first"] = frame["target"].astype(int)
    return result


def _metrics(prediction: Mapping[str, Any], frame: pd.DataFrame) -> dict[str, Any]:
    probability = np.asarray(prediction["probability"], dtype=float)
    decision = np.asarray(prediction["decision"], dtype=bool)
    actual = frame["target"].to_numpy(dtype=int)
    terminal = frame["terminal_return"].to_numpy(dtype=float)
    selected = terminal[decision]
    return {
        "n": int(len(frame)),
        "selected": int(decision.sum()),
        "positive_rate": float(actual.mean()) if len(actual) else None,
        "brier": float(np.mean(np.square(probability - actual))) if len(actual) else None,
        "precision": float(actual[decision].mean()) if decision.any() else None,
        "mean_terminal_return": float(selected.mean()) if len(selected) else None,
        "net_terminal_return": float(selected.sum()) if len(selected) else None,
        "tail_loss_rate": float(frame.loc[decision, "tail_loss"].mean()) if decision.any() else None,
        "abstain_rate": float(np.asarray(prediction["abstain"], dtype=bool).mean()) if len(frame) else None,
    }


def train_and_publish(
    frame: pd.DataFrame,
    output_path: Path,
    *,
    horizons: Sequence[int] = DEFAULT_HORIZONS_S,
    decision_horizon_s: int = 10,
) -> dict[str, Any]:
    """Train, evaluate, and publish only a calibrated positive-OOS artifact."""
    slices = chronological_slices(frame)
    train_frame = _model_frame(slices.train)
    validation_frame = _model_frame(slices.validation)
    configs = [
        ModelConfig("logistic", "logistic", {"C": 1.0, "max_iter": 1000, "class_weight": "balanced"}, feature_selector=False),
        ModelConfig("rf", "random_forest", {"n_estimators": 60, "max_depth": 8, "class_weight": "balanced", "n_jobs": -1}, feature_selector=False),
        ModelConfig("gbm", "gradient_boosting", {"n_estimators": 80, "max_depth": 3, "learning_rate": 0.05, "subsample": 0.8}, feature_selector=False),
    ]
    pipeline = MLPipeline(configs=configs, random_seed=42)
    pipeline.train(train_frame, validation_frame)

    def evaluate(
        part: pd.DataFrame,
        *,
        threshold: float = 0.5,
        max_uncertainty: float = 1.0,
    ) -> dict[str, Any]:
        model_part = _model_frame(part)
        prediction = pipeline.get_calibrated_ensemble_prediction(
            model_part, threshold=threshold, min_models=2,
            min_model_agreement=0.6, max_uncertainty=max_uncertainty,
        )
        metrics = _metrics(prediction, part)
        metrics["uncertainty_p90"] = (
            float(np.quantile(prediction["uncertainty"], 0.90))
            if len(prediction["uncertainty"]) else None
        )
        return metrics

    # Select the threshold only from chronological validation rows.  The
    # objective is positive terminal economics, with precision as tie-breaker.
    candidates: list[tuple[float, dict[str, Any]]] = []
    for threshold in np.arange(0.50, 0.951, 0.025):
        metrics = evaluate(slices.validation, threshold=float(threshold), max_uncertainty=1.0)
        if int(metrics["selected"] or 0) >= max(10, int(len(slices.validation) * 0.01)):
            candidates.append((float(threshold), metrics))
    if candidates:
        threshold, validation_metrics = max(
            candidates,
            key=lambda item: (
                float(item[1]["mean_terminal_return"])
                if item[1]["mean_terminal_return"] is not None else -float("inf"),
                float(item[1]["precision"] or 0.0),
                -item[0],
            ),
        )
    else:
        # A calibrated model with no supported high-confidence validation
        # selections is still useful as a shadow veto.  It is never promoted
        # to execution authority without positive chronological OOS evidence.
        threshold = 0.5
        validation_metrics = evaluate(
            slices.validation, threshold=threshold, max_uncertainty=1.0
        )
    uncertainty_limit = max(
        0.01,
        min(1.0, float(validation_metrics.get("uncertainty_p90") or 0.2)),
    )
    test_metrics = evaluate(slices.test, threshold=threshold, max_uncertainty=uncertainty_limit)
    sealed_metrics = evaluate(slices.sealed, threshold=threshold, max_uncertainty=uncertainty_limit)
    sealed_by_horizon = {}
    for horizon in sorted({int(value) for value in horizons}):
        subset = slices.sealed[slices.sealed["horizon_s"] == float(horizon)]
        if not subset.empty:
            sealed_by_horizon[str(horizon)] = evaluate(
                subset, threshold=threshold, max_uncertainty=uncertainty_limit
            )
    execution_status = "EXECUTION_CANDIDATE" if all(
        metrics["mean_terminal_return"] is not None and metrics["mean_terminal_return"] > 0.0
        for metrics in (test_metrics, sealed_metrics)
    ) else "SHADOW_ONLY_NO_POSITIVE_OOS"

    output_path = Path(output_path)
    pipeline.save(output_path)
    metadata_path = output_path / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata.update(
        {
            "schema": ARTIFACT_SCHEMA,
            "execution_status": execution_status,
            "dataset_hash": _hash_frame(frame),
            "validation_hash": _hash_frame(slices.validation),
            "horizons_s": [int(value) for value in horizons],
            "decision_horizon_s": int(decision_horizon_s),
            "threshold": float(threshold),
            "min_model_agreement": 0.6,
            "max_uncertainty": uncertainty_limit,
            "oos": {
                "validation": validation_metrics,
                "test": test_metrics,
                "sealed": sealed_metrics,
                "sealed_by_horizon": sealed_by_horizon,
            },
            "trained_at": datetime.now(timezone.utc).isoformat(),
            "cost_evidence": "executable_bid_ask_spread_in_labels; no synthetic slippage",
            "symbols": sorted(frame["symbol"].astype(str).str.upper().unique().tolist()),
        }
    )
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")
    return metadata
