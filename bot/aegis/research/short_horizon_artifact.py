"""Research-only builder for a calibrated seconds-horizon Firehose artifact.

This module consumes completed MT5 quote history and never imports an engine or
places orders.  Features are calculated from observations at or before the
entry timestamp.  Labels use only observations strictly after entry.  An
artifact is publishable only when its chronological OOS slice has positive
cost-aware terminal or first-green harvest expectancy.
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

from aegis.research.short_horizon import DEFAULT_HORIZONS_S, session_features, symbol_features
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
    harvest_mode = str(metadata.get("target_definition") or "terminal_profit").strip().lower() in {"mfe_first", "fast_harvest"}
    reason = (
        "positive chronological test and sealed-OOS first-green harvest returns support a challenger"
        if status == "CHALLENGER" and harvest_mode
        else "positive chronological test and sealed-OOS terminal returns support a challenger"
        if status == "CHALLENGER"
        else "no positive sealed-OOS execution selection; retain shadow-only"
    )
    metrics = {
        "test_n": test.get("n"),
        "test_selected": test.get("selected"),
        "test_positive_rate": test.get("positive_rate"),
        "test_mean_terminal_return": test.get("mean_terminal_return"),
        "test_mean_harvest_return": test.get("mean_harvest_return"),
        "test_harvest_lcb95_return": test.get("harvest_lcb95_return"),
        "test_brier": test.get("brier"),
        "sealed_n": sealed.get("n"),
        "sealed_selected": sealed.get("selected"),
        "sealed_positive_rate": sealed.get("positive_rate"),
        "sealed_mean_terminal_return": sealed.get("mean_terminal_return"),
        "sealed_mean_harvest_return": sealed.get("mean_harvest_return"),
        "sealed_harvest_lcb95_return": sealed.get("harvest_lcb95_return"),
        "sealed_brier": sealed.get("brier"),
        "horizons_s": list(metadata.get("horizons_s") or []),
        "decision_horizon_s": metadata.get("decision_horizon_s"),
        "target_definition": metadata.get("target_definition"),
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
    for name, value in symbol_features(symbol).items():
        values[name] = np.full(len(frame), value, dtype=float)
    hours = frame["time"].dt.hour.to_numpy(dtype=int)
    session_columns = tuple(session_features(0))
    for name in session_columns:
        values[name] = np.asarray(
            [session_features(int(hour))[name] for hour in hours], dtype=float
        )
    spread_series = pd.Series(spread)
    values["spread_percentile"] = (
        spread_series.rolling(60, min_periods=2).rank(pct=True).fillna(1.0).to_numpy(dtype=float)
    )
    returns = pd.Series(mid).pct_change()
    values["micro_volatility"] = returns.rolling(20, min_periods=2).std(ddof=0).fillna(0.0).to_numpy(dtype=float)
    values["realized_vol_60s"] = np.sqrt(
        returns.pow(2).rolling(60, min_periods=2).sum().fillna(0.0).to_numpy(dtype=float)
    )
    relative_spread = np.divide(
        spread, np.maximum(np.abs(mid), 1e-12),
        out=np.zeros_like(spread), where=np.abs(mid) > 0,
    )
    values["spread_to_micro_vol"] = np.divide(
        relative_spread, np.maximum(values["micro_volatility"], 1e-12)
    )
    values["spread_to_realized_vol"] = np.divide(
        relative_spread, np.maximum(values["realized_vol_60s"], 1e-12)
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
    target_mode: str = "mfe_first",
) -> pd.DataFrame:
    """Create point-in-time feature/label rows from completed quotes.

    ``mfe_first`` predicts whether the executable path becomes green at any
    point in the horizon. ``fast_harvest`` requires a realized move of at
    least two observed spreads before treating the path as a harvestable win.
    ``terminal_profit`` predicts whether the executable terminal mark is still
    green at the horizon endpoint. All labels are point-in-time and cost-aware.
    """
    horizon_values = tuple(sorted({int(value) for value in horizons if int(value) > 0}))
    if not horizon_values:
        raise ValueError("at least one positive horizon is required")
    if int(sample_every_s) <= 0:
        raise ValueError("sample_every_s must be positive")
    target_mode = str(target_mode).strip().lower()
    if target_mode not in {"mfe_first", "fast_harvest", "terminal_profit"}:
        raise ValueError("target_mode must be mfe_first, fast_harvest, or terminal_profit")
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
        harvest_threshold = max(float(np.nanmedian(spreads)) * 2.0, 1e-12)
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
                    future_times = features["time"].iloc[index + 1 : end + 1]
                    profitable = np.flatnonzero(signed > 0.0)
                    harvestable = (
                        np.flatnonzero(signed >= harvest_threshold)
                        if target_mode == "fast_harvest"
                        else profitable
                    )
                    failures = np.flatnonzero(signed <= -tail_threshold)
                    time_to_profit = (
                        float((future_times.iloc[int(harvestable[0])] - features.iloc[index]["time"]).total_seconds())
                        if len(harvestable) else None
                    )
                    time_to_failure = (
                        float((future_times.iloc[int(failures[0])] - features.iloc[index]["time"]).total_seconds())
                        if len(failures) else None
                    )
                    harvest = float(signed[int(harvestable[0])]) if len(harvestable) else terminal
                    row = features.iloc[index].to_dict()
                    target = (
                        int(len(harvestable) > 0)
                        if target_mode == "fast_harvest"
                        else int(mfe > 0.0)
                        if target_mode == "mfe_first"
                        else int(terminal > 0.0)
                    )
                    row.update(
                        {
                            "time": features.iloc[index]["time"],
                            "symbol": str(symbol).upper(),
                            "side": side,
                            "side_buy": 1.0 if side == "buy" else 0.0,
                            "horizon_s": float(horizon),
                            # Profit means the executable path became green
                            # within the stated horizon, after spread.
                            "target": target,
                            "terminal_net_pnl": terminal,
                            "terminal_return": terminal / float(mid[index]) if mid[index] > 0 else np.nan,
                            # The first-green harvest proxy is executable-side
                            # and cost-aware: take the first positive mark, or
                            # retain the terminal outcome when no green mark
                            # occurred within the horizon.
                            "harvest_return": harvest / float(mid[index]) if mid[index] > 0 else np.nan,
                            "mfe": mfe,
                            "mae": mae,
                            "tail_loss": int(mae <= -tail_threshold),
                            "time_to_profit_s": time_to_profit,
                            "time_to_failure_s": time_to_failure,
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
        "harvest_return", "time_to_profit_s", "time_to_failure_s",
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
    selected_frame = frame.loc[decision]
    harvest = pd.to_numeric(
        frame.get("harvest_return", frame["terminal_return"]), errors="coerce"
    ).to_numpy(dtype=float)
    selected_harvest = harvest[decision]
    mfe_values = pd.to_numeric(
        frame.get("mfe", pd.Series(np.nan, index=frame.index)), errors="coerce"
    ).to_numpy(dtype=float)
    mid_values = pd.to_numeric(
        frame.get("mid", pd.Series(1.0, index=frame.index)), errors="coerce"
    ).to_numpy(dtype=float)
    mfe_return = np.divide(
        mfe_values,
        mid_values,
        out=np.full(len(frame), np.nan, dtype=float),
        where=np.isfinite(mid_values) & (np.abs(mid_values) > 1e-12),
    )
    selected_mfe_return = mfe_return[decision]
    calibration_bins: list[dict[str, Any]] = []
    calibration_ece = 0.0
    for lower in np.linspace(0.0, 1.0, 11)[:-1]:
        upper = float(lower + 0.1)
        mask = (probability >= float(lower)) & (
            probability <= upper if upper >= 1.0 else probability < upper
        )
        if not mask.any():
            continue
        predicted_mean = float(probability[mask].mean())
        actual_mean = float(actual[mask].mean())
        calibration_ece += float(mask.mean()) * abs(predicted_mean - actual_mean)
        calibration_bins.append(
            {
                "lower": float(lower),
                "upper": min(1.0, upper),
                "n": int(mask.sum()),
                "predicted_mean": predicted_mean,
                "actual_rate": actual_mean,
            }
        )
    confusion = {
        "tp": int((decision & (actual == 1)).sum()),
        "fp": int((decision & (actual == 0)).sum()),
        "tn": int((~decision & (actual == 0)).sum()),
        "fn": int((~decision & (actual == 1)).sum()),
    }
    expectancy_lcb95 = None
    if len(selected) >= 2:
        expectancy_lcb95 = float(
            selected.mean() - 1.96 * selected.std(ddof=1) / np.sqrt(len(selected))
        )
    mfe_lcb95 = None
    finite_selected_mfe = selected_mfe_return[np.isfinite(selected_mfe_return)]
    if len(finite_selected_mfe) >= 2:
        mfe_lcb95 = float(
            finite_selected_mfe.mean()
            - 1.96 * finite_selected_mfe.std(ddof=1) / np.sqrt(len(finite_selected_mfe))
        )
    harvest_lcb95 = None
    finite_selected_harvest = selected_harvest[np.isfinite(selected_harvest)]
    if len(finite_selected_harvest) >= 2:
        harvest_lcb95 = float(
            finite_selected_harvest.mean()
            - 1.96 * finite_selected_harvest.std(ddof=1) / np.sqrt(len(finite_selected_harvest))
        )
    confidence_bands: dict[str, dict[str, Any]] = {}
    for lower, upper in (
        (0.50, 0.60), (0.60, 0.70), (0.70, 0.80), (0.80, 0.90),
        (0.90, 0.95), (0.95, 0.975), (0.975, 0.99), (0.99, 1.000001),
    ):
        mask = (probability >= lower) & (probability < upper)
        band_terminal = terminal[mask]
        band_actual = actual[mask]
        band_losses = band_terminal[band_terminal < 0.0]
        confidence_bands[
            f"{int(round(lower * 100))}-{min(100, int(round(upper * 100)))}%"
        ] = {
            "n": int(mask.sum()),
            "actual_rate": float(band_actual.mean()) if len(band_actual) else None,
            "mean_terminal_return": float(band_terminal.mean()) if len(band_terminal) else None,
            "avg_loss": float(band_losses.mean()) if len(band_losses) else None,
            "tail_loss_rate": float(frame.loc[mask, "tail_loss"].mean()) if mask.any() else None,
        }
    def selected_mean(column: str) -> float | None:
        values = pd.to_numeric(selected_frame[column], errors="coerce").dropna()
        return float(values.mean()) if len(values) else None

    def selected_median(column: str) -> float | None:
        values = pd.to_numeric(selected_frame[column], errors="coerce").dropna()
        return float(values.median()) if len(values) else None

    return {
        "n": int(len(frame)),
        "selected": int(decision.sum()),
        "positive_rate": float(actual.mean()) if len(actual) else None,
        "brier": float(np.mean(np.square(probability - actual))) if len(actual) else None,
        "calibration_ece": float(calibration_ece) if len(actual) else None,
        "calibration_bins": calibration_bins,
        "confusion_matrix": confusion,
        "expectancy_lcb95_return": expectancy_lcb95,
        "mfe_lcb95_return": mfe_lcb95,
        "harvest_lcb95_return": harvest_lcb95,
        "confidence_bands": confidence_bands,
        "precision": float(actual[decision].mean()) if decision.any() else None,
        "mean_terminal_return": float(selected.mean()) if len(selected) else None,
        "net_terminal_return": float(selected.sum()) if len(selected) else None,
        "mean_mfe_return": (
            float(finite_selected_mfe.mean()) if len(finite_selected_mfe) else None
        ),
        "mean_harvest_return": (
            float(finite_selected_harvest.mean())
            if len(finite_selected_harvest) else None
        ),
        "expected_mfe": selected_mean("mfe"),
        "expected_mae": selected_mean("mae"),
        "median_time_to_green_s": selected_median("time_to_profit_s"),
        "median_time_to_failure_s": selected_median("time_to_failure_s"),
        "winner_giveback_rate": (
            float(((selected_frame["mfe"] > 0.0) & (selected_frame["terminal_return"] <= 0.0)).mean())
            if len(selected_frame) else None
        ),
        "tail_loss_rate": float(frame.loc[decision, "tail_loss"].mean()) if decision.any() else None,
        "abstain_rate": float(np.asarray(prediction["abstain"], dtype=bool).mean()) if len(frame) else None,
    }


def _threshold_candidates(probabilities: np.ndarray) -> np.ndarray:
    """Return validation-derived calibrated thresholds, not arbitrary priors."""
    values = np.asarray(probabilities, dtype=float)
    values = np.unique(values[np.isfinite(values)])
    values = values[(values > 0.0) & (values < 1.0)]
    if not len(values):
        return np.asarray([0.5], dtype=float)
    # Exact validation probabilities are affordable for normal slices.  For
    # unusually large slices, quantiles retain the selection-rate frontier
    # without evaluating a threshold for every row.
    if len(values) > 256:
        values = np.unique(np.quantile(values, np.linspace(0.0, 1.0, 257)))
    return values.astype(float, copy=False)


def _threshold_prediction(
    base_prediction: Mapping[str, Any],
    *,
    threshold: float,
    min_model_agreement: float,
    max_uncertainty: float,
) -> dict[str, Any]:
    """Apply a new threshold to cached model probabilities without refitting."""
    matrix = np.asarray(base_prediction["model_probabilities"], dtype=float)
    agreement = np.maximum(
        np.mean(matrix >= float(threshold), axis=0),
        np.mean(matrix < float(threshold), axis=0),
    )
    uncertainty = np.asarray(base_prediction["uncertainty"], dtype=float)
    abstain = (agreement < float(min_model_agreement)) | (
        uncertainty > float(max_uncertainty)
    )
    result = dict(base_prediction)
    result.update(
        {
            "decision": (np.asarray(base_prediction["probability"]) >= float(threshold))
            & ~abstain,
            "abstain": abstain,
            "abstain_reason": np.where(abstain, "ensemble_uncertain", "ensemble_eligible"),
            "model_agreement": agreement,
        }
    )
    return result


def _select_threshold_for_prediction(
    base_prediction: Mapping[str, Any],
    frame: pd.DataFrame,
    *,
    target_definition: str,
    min_selected: int = 20,
    min_model_agreement: float = 0.6,
    max_uncertainty: float = 1.0,
) -> tuple[float, dict[str, Any]]:
    """Select a scope threshold from validation predictions only."""
    target = str(target_definition).strip().lower()
    harvest_mode = target in {"mfe_first", "fast_harvest"}
    mean_key = "mean_harvest_return" if harvest_mode else "mean_terminal_return"
    lcb_key = "harvest_lcb95_return" if harvest_mode else "expectancy_lcb95_return"
    candidates: list[tuple[float, dict[str, Any]]] = []
    for threshold in _threshold_candidates(base_prediction["probability"]):
        prediction = _threshold_prediction(
            base_prediction,
            threshold=float(threshold),
            min_model_agreement=min_model_agreement,
            max_uncertainty=max_uncertainty,
        )
        metrics = _metrics(prediction, frame)
        if int(metrics.get("selected") or 0) >= int(min_selected):
            candidates.append((float(threshold), metrics))
    if not candidates:
        threshold = 0.5
        return threshold, _metrics(
            _threshold_prediction(
                base_prediction,
                threshold=threshold,
                min_model_agreement=min_model_agreement,
                max_uncertainty=max_uncertainty,
            ),
            frame,
        )
    def score(metrics: Mapping[str, Any], key: str, default: float = -float("inf")) -> float:
        value = metrics.get(key)
        return default if value is None else float(value)

    threshold, metrics = max(
        candidates,
        key=lambda item: (
            score(item[1], lcb_key),
            score(item[1], mean_key),
            score(item[1], "precision", 0.0),
            -item[0],
        ),
    )
    return threshold, metrics


def _execution_status(
    *,
    target_definition: str,
    decision_horizon_s: int,
    test_metrics: Mapping[str, Any],
    sealed_metrics: Mapping[str, Any],
    sealed_by_horizon: Mapping[str, Mapping[str, Any]],
) -> tuple[str, str]:
    """Authorize execution only for a costed label the exit can realize."""
    target = str(target_definition).strip().lower()
    if target not in {"terminal_profit", "mfe_first", "fast_harvest"}:
        return "SHADOW_ONLY_NO_POSITIVE_OOS", "execution_requires_supported_harvest_labels"
    harvest_mode = target in {"mfe_first", "fast_harvest"}
    mean_key = "mean_harvest_return" if harvest_mode else "mean_terminal_return"
    lcb_key = "harvest_lcb95_return" if harvest_mode else "expectancy_lcb95_return"

    def positive(metrics: Mapping[str, Any] | None) -> bool:
        if not isinstance(metrics, Mapping):
            return False
        try:
            return float(metrics.get(mean_key)) > 0.0
        except (TypeError, ValueError):
            return False

    def positive_lcb(metrics: Mapping[str, Any] | None) -> bool:
        if not isinstance(metrics, Mapping):
            return False
        try:
            return float(metrics.get(lcb_key)) > 0.0
        except (TypeError, ValueError):
            return False

    if not positive(test_metrics) or not positive(sealed_metrics):
        return "SHADOW_ONLY_NO_POSITIVE_OOS", (
            "test_or_sealed_harvest_oos_not_positive" if harvest_mode
            else "test_or_sealed_oos_not_positive"
        )
    if not positive_lcb(test_metrics) or not positive_lcb(sealed_metrics):
        return "SHADOW_ONLY_NO_POSITIVE_OOS", (
            "harvest_oos_lcb95_not_positive" if harvest_mode else "oos_lcb95_not_positive"
        )
    horizon_metrics = sealed_by_horizon.get(str(int(decision_horizon_s)))
    if not positive(horizon_metrics):
        return "SHADOW_ONLY_NO_POSITIVE_OOS", (
            "decision_horizon_harvest_oos_not_positive" if harvest_mode
            else "decision_horizon_oos_not_positive"
        )
    if not positive_lcb(horizon_metrics):
        return "SHADOW_ONLY_NO_POSITIVE_OOS", (
            "harvest_oos_lcb95_not_positive" if harvest_mode else "oos_lcb95_not_positive"
        )
    return "EXECUTION_CANDIDATE", (
        "positive_test_sealed_decision_horizon_harvest_oos" if harvest_mode
        else "positive_test_sealed_decision_horizon_oos"
    )


def _select_decision_horizon(
    validation_by_horizon: Mapping[str, Mapping[str, Any]],
    *,
    requested_horizon_s: int,
    target_definition: str,
    min_selected: int = 20,
) -> tuple[int, str]:
    """Choose the fastest horizon with positive validation LCB evidence."""
    target = str(target_definition).strip().lower()
    harvest_mode = target in {"mfe_first", "fast_harvest"}
    mean_key = "mean_harvest_return" if harvest_mode else "mean_terminal_return"
    lcb_key = "harvest_lcb95_return" if harvest_mode else "expectancy_lcb95_return"

    def supported(metrics: Mapping[str, Any] | None) -> bool:
        if not isinstance(metrics, Mapping):
            return False
        try:
            return (
                int(metrics.get("selected") or 0) >= int(min_selected)
                and float(metrics.get(mean_key)) > 0.0
                and float(metrics.get(lcb_key)) > 0.0
            )
        except (TypeError, ValueError):
            return False

    supported_horizons = sorted(
        int(horizon) for horizon, metrics in validation_by_horizon.items()
        if supported(metrics)
    )
    if supported_horizons:
        requested = int(requested_horizon_s)
        if requested in supported_horizons:
            return requested, "requested_validation_supported_horizon"
        return supported_horizons[0], "fastest_validation_supported_horizon"
    return int(requested_horizon_s), "requested_horizon_no_positive_validation_support"


def _authorized_symbols(
    *,
    test_by_symbol: Mapping[str, Mapping[str, Any]],
    sealed_by_symbol_horizon: Mapping[str, Mapping[str, Mapping[str, Any]]],
    decision_horizon_s: int,
    target_definition: str,
    min_selected: int = 20,
) -> list[str]:
    """Return only symbols with exact test and sealed horizon evidence."""
    target = str(target_definition).strip().lower()
    if target not in {"terminal_profit", "mfe_first", "fast_harvest"}:
        return []
    harvest_mode = target in {"mfe_first", "fast_harvest"}
    mean_key = "mean_harvest_return" if harvest_mode else "mean_terminal_return"
    lcb_key = "harvest_lcb95_return" if harvest_mode else "expectancy_lcb95_return"

    def positive(metrics: Mapping[str, Any] | None) -> bool:
        if not isinstance(metrics, Mapping):
            return False
        try:
            return (
                int(metrics.get("selected") or 0) >= int(min_selected)
                and float(metrics.get(mean_key)) > 0.0
                and float(metrics.get(lcb_key)) > 0.0
            )
        except (TypeError, ValueError):
            return False

    authorized: list[str] = []
    for symbol, test_metrics in test_by_symbol.items():
        sealed_metrics = (sealed_by_symbol_horizon.get(str(symbol).upper()) or {}).get(
            str(int(decision_horizon_s))
        )
        if positive(test_metrics) and positive(sealed_metrics):
            authorized.append(str(symbol).upper())
    return sorted(set(authorized))


def train_and_publish(
    frame: pd.DataFrame,
    output_path: Path,
    *,
    horizons: Sequence[int] = DEFAULT_HORIZONS_S,
    decision_horizon_s: int = 10,
    target_definition: str = "mfe_first",
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

    # Select the threshold only from chronological validation rows.  A
    # first-green artifact optimizes its realizable harvest proxy; terminal
    # artifacts optimize terminal economics.
    selection_metric = (
        "mean_harvest_return"
        if str(target_definition).strip().lower() in {"mfe_first", "fast_harvest"}
        else "mean_terminal_return"
    )
    validation_prediction = pipeline.get_calibrated_ensemble_prediction(
        _model_frame(slices.validation), threshold=0.5, min_models=2,
        min_model_agreement=0.6, max_uncertainty=1.0,
        include_model_probabilities=True,
    )
    candidates: list[tuple[float, dict[str, Any]]] = []
    min_selected = max(10, int(len(slices.validation) * 0.01))
    for threshold in _threshold_candidates(validation_prediction["probability"]):
        metrics = _metrics(
            _threshold_prediction(
                validation_prediction,
                threshold=float(threshold),
                min_model_agreement=0.6,
                max_uncertainty=1.0,
            ),
            slices.validation,
        )
        if int(metrics["selected"] or 0) >= min_selected:
            candidates.append((float(threshold), metrics))
    if candidates:
        threshold, validation_metrics = max(
            candidates,
            key=lambda item: (
                float(item[1][selection_metric])
                if item[1][selection_metric] is not None else -float("inf"),
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
    validation_by_horizon: dict[str, dict[str, Any]] = {}
    for horizon in sorted({int(value) for value in horizons}):
        subset = slices.validation[slices.validation["horizon_s"] == float(horizon)]
        if not subset.empty:
            validation_by_horizon[str(horizon)] = evaluate(
                subset, threshold=threshold, max_uncertainty=uncertainty_limit
            )
    selected_decision_horizon, horizon_selection_reason = _select_decision_horizon(
        validation_by_horizon,
        requested_horizon_s=decision_horizon_s,
        target_definition=target_definition,
    )
    threshold_by_symbol_horizon: dict[str, dict[str, float]] = {}
    for symbol in sorted(frame["symbol"].astype(str).str.upper().unique()):
        symbol_validation = slices.validation[
            slices.validation["symbol"].astype(str).str.upper() == symbol
        ]
        threshold_by_symbol_horizon[symbol] = {}
        for horizon in sorted({int(value) for value in horizons}):
            validation_subset = symbol_validation[
                symbol_validation["horizon_s"] == float(horizon)
            ]
            if validation_subset.empty:
                continue
            validation_prediction = pipeline.get_calibrated_ensemble_prediction(
                _model_frame(validation_subset), threshold=0.5, min_models=2,
                min_model_agreement=0.6, max_uncertainty=uncertainty_limit,
                include_model_probabilities=True,
            )
            scope_threshold, _ = _select_threshold_for_prediction(
                validation_prediction,
                validation_subset,
                target_definition=target_definition,
                min_selected=20,
                min_model_agreement=0.6,
                max_uncertainty=uncertainty_limit,
            )
            threshold_by_symbol_horizon[symbol][str(horizon)] = float(scope_threshold)
    test_metrics = evaluate(slices.test, threshold=threshold, max_uncertainty=uncertainty_limit)
    sealed_metrics = evaluate(slices.sealed, threshold=threshold, max_uncertainty=uncertainty_limit)
    test_by_symbol: dict[str, dict[str, Any]] = {}
    sealed_by_symbol_horizon: dict[str, dict[str, dict[str, Any]]] = {}
    for symbol in sorted(frame["symbol"].astype(str).str.upper().unique()):
        test_subset = slices.test[
            (slices.test["symbol"].astype(str).str.upper() == symbol)
            & (slices.test["horizon_s"] == float(selected_decision_horizon))
        ]
        if not test_subset.empty:
            scope_threshold = threshold_by_symbol_horizon.get(symbol, {}).get(
                str(selected_decision_horizon), threshold
            )
            test_by_symbol[symbol] = evaluate(
                test_subset, threshold=scope_threshold, max_uncertainty=uncertainty_limit
            )
        sealed_by_symbol_horizon[symbol] = {}
        for horizon in sorted({int(value) for value in horizons}):
            sealed_subset = slices.sealed[
                (slices.sealed["symbol"].astype(str).str.upper() == symbol)
                & (slices.sealed["horizon_s"] == float(horizon))
            ]
            if not sealed_subset.empty:
                scope_threshold = threshold_by_symbol_horizon.get(symbol, {}).get(
                    str(horizon), threshold
                )
                sealed_by_symbol_horizon[symbol][str(horizon)] = evaluate(
                    sealed_subset, threshold=scope_threshold, max_uncertainty=uncertainty_limit
                )
    sealed_by_horizon = {}
    for horizon in sorted({int(value) for value in horizons}):
        subset = slices.sealed[slices.sealed["horizon_s"] == float(horizon)]
        if not subset.empty:
            sealed_by_horizon[str(horizon)] = evaluate(
                subset, threshold=threshold, max_uncertainty=uncertainty_limit
            )
    execution_status, execution_status_reason = _execution_status(
        target_definition=target_definition,
        decision_horizon_s=selected_decision_horizon,
        test_metrics=test_metrics,
        sealed_metrics=sealed_metrics,
        sealed_by_horizon=sealed_by_horizon,
    )
    authorized_symbols = _authorized_symbols(
        test_by_symbol=test_by_symbol,
        sealed_by_symbol_horizon=sealed_by_symbol_horizon,
        decision_horizon_s=selected_decision_horizon,
        target_definition=target_definition,
    )
    if authorized_symbols:
        execution_status = "EXECUTION_CANDIDATE"
        execution_status_reason = "positive_exact_symbol_test_sealed_horizon_oos"
    elif execution_status == "EXECUTION_CANDIDATE":
        execution_status = "SHADOW_ONLY_NO_POSITIVE_OOS"
        execution_status_reason = "no_symbol_scope_positive_oos"

    output_path = Path(output_path)
    pipeline.save(output_path)
    metadata_path = output_path / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata.update(
        {
            "schema": ARTIFACT_SCHEMA,
            "execution_status": execution_status,
            "execution_status_reason": execution_status_reason,
            "dataset_hash": _hash_frame(frame),
            "validation_hash": _hash_frame(slices.validation),
            "horizons_s": [int(value) for value in horizons],
            "decision_horizon_s": int(selected_decision_horizon),
            "decision_horizon_selection": horizon_selection_reason,
            "target_definition": str(target_definition),
            "threshold": float(threshold),
            "threshold_by_symbol_horizon": threshold_by_symbol_horizon,
            "min_model_agreement": 0.6,
            "max_uncertainty": uncertainty_limit,
            "oos": {
                "validation": validation_metrics,
                "validation_by_horizon": validation_by_horizon,
                "test": test_metrics,
                "test_by_symbol": test_by_symbol,
                "sealed": sealed_metrics,
                "sealed_by_horizon": sealed_by_horizon,
                "sealed_by_symbol_horizon": sealed_by_symbol_horizon,
            },
            "trained_at": datetime.now(timezone.utc).isoformat(),
            "cost_evidence": "executable_bid_ask_spread_in_labels; no synthetic slippage",
            "symbols": sorted(frame["symbol"].astype(str).str.upper().unique().tolist()),
            "authorized_symbols": authorized_symbols,
        }
    )
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")
    return metadata
