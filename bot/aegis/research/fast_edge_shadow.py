"""Read-only, multi-market shadow replay for seconds-horizon edge research.

This module deliberately has no broker/execution imports.  Every candidate is
an observed quote entry, and every outcome is replayed sequentially using the
executable opposite-side quote.  The resulting leaderboard is evidence only;
it cannot authorize a Firehose order.
"""
from __future__ import annotations

import hashlib
import warnings
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier, HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import RobustScaler

from aegis.research.short_horizon import _session_name
from aegis.research.short_horizon_artifact import _feature_frame


SHADOW_HORIZONS_S = (1, 2, 3, 5, 8, 10, 15, 20, 30, 45)
SHADOW_THRESHOLDS = (0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.925, 0.95, 0.975, 0.99)

_OUTCOME_COLUMNS = frozenset(
    {
        "target", "terminal_net_pnl", "terminal_return", "mfe", "mae", "tail_loss",
        "harvest_return", "time_to_profit_s", "time_to_failure_s",
        "captured_exit_net_pnl", "captured_exit_return", "captured_exit_reason",
        "first_green", "never_green", "time_to_green_s", "time_to_mfe_s",
        "time_in_red_s", "winner_giveback", "future_path_observed_n",
    }
)


@dataclass(frozen=True)
class ShadowSlices:
    train: pd.DataFrame
    validation: pd.DataFrame
    test: pd.DataFrame
    sealed: pd.DataFrame


def replay_executable_path(
    *,
    entry_time: Any,
    entry_bid: float,
    entry_ask: float,
    future_times: Sequence[Any],
    future_bid: Sequence[float],
    future_ask: Sequence[float],
    side: str,
    horizon_s: int,
) -> dict[str, Any]:
    """Replay a single entry with only the next quote visible at each step."""
    side = str(side).strip().lower()
    if side not in {"buy", "sell"}:
        raise ValueError("side must be buy or sell")
    if int(horizon_s) <= 0:
        raise ValueError("horizon_s must be positive")
    entry_timestamp = pd.Timestamp(entry_time)
    if entry_timestamp.tzinfo is None:
        entry_timestamp = entry_timestamp.tz_localize("UTC")
    else:
        entry_timestamp = entry_timestamp.tz_convert("UTC")
    times = pd.to_datetime(list(future_times), utc=True)
    bid = np.asarray(future_bid, dtype=float)
    ask = np.asarray(future_ask, dtype=float)
    if len(times) != len(bid) or len(times) != len(ask) or not len(times):
        raise ValueError("future quote arrays must be non-empty and aligned")
    entry = float(entry_ask if side == "buy" else entry_bid)
    entry_mid = (float(entry_bid) + float(entry_ask)) / 2.0
    entry_spread = max(float(entry_ask) - float(entry_bid), 1e-12)
    signed = bid - entry if side == "buy" else entry - ask
    harvest_threshold = 2.0 * entry_spread
    abort_threshold = 3.0 * entry_spread
    first_green_index = next((i for i, value in enumerate(signed) if value > 0.0), None)
    mfe_index = int(np.argmax(signed))
    captured = float(signed[-1])
    captured_reason = "timeout"
    captured_index: int | None = None
    time_in_red = 0.0
    prior = entry_timestamp
    for index, value in enumerate(signed):
        current = pd.Timestamp(times[index])
        elapsed = max(0.0, (current - prior).total_seconds())
        if float(value) < 0.0:
            time_in_red += elapsed
        prior = current
        if float(value) >= harvest_threshold:
            captured = float(value)
            captured_reason = "harvest"
            captured_index = index
            break
        if float(value) <= -abort_threshold:
            captured = float(value)
            captured_reason = "abort"
            captured_index = index
            break
    mfe = float(np.max(signed))
    mae = float(np.min(signed))
    first_green = first_green_index is not None
    green_time = (
        float((pd.Timestamp(times[first_green_index]) - entry_timestamp).total_seconds())
        if first_green_index is not None else None
    )
    mfe_time = float((pd.Timestamp(times[mfe_index]) - entry_timestamp).total_seconds())
    return {
        "captured_exit_net_pnl": captured,
        "captured_exit_return": captured / entry_mid if entry_mid > 0 else np.nan,
        "captured_exit_reason": captured_reason,
        "terminal_net_pnl": float(signed[-1]),
        "terminal_return": float(signed[-1]) / entry_mid if entry_mid > 0 else np.nan,
        "mfe": mfe,
        "mae": mae,
        "tail_loss": bool(mae <= -abort_threshold),
        "first_green": bool(first_green),
        "never_green": bool(not first_green),
        "time_to_green_s": green_time,
        "time_to_mfe_s": mfe_time,
        "time_in_red_s": float(time_in_red),
        "winner_giveback": bool(mfe > 0.0 and captured < mfe),
        "future_path_observed_n": int(len(signed) if captured_index is None else captured_index + 1),
        "horizon_s": int(horizon_s),
    }


def build_shadow_dataset(
    quotes_by_symbol: Mapping[str, pd.DataFrame],
    *,
    horizons: Sequence[int] = SHADOW_HORIZONS_S,
    sample_every_s: int = 1,
) -> pd.DataFrame:
    """Build all plausible quote-entry candidates across every supplied symbol."""
    horizon_values = tuple(sorted({int(value) for value in horizons if int(value) > 0}))
    if not horizon_values:
        raise ValueError("at least one positive horizon is required")
    if int(sample_every_s) <= 0:
        raise ValueError("sample_every_s must be positive")
    rows: list[dict[str, Any]] = []
    for raw_symbol, quotes in sorted(quotes_by_symbol.items()):
        symbol = str(raw_symbol).upper()
        try:
            features = _feature_frame(quotes, symbol)
        except ValueError as exc:
            # A malformed or non-varying broker history must not erase the
            # other symbols' evidence.  Keep the omission visible to callers.
            warnings.warn(f"shadow history skipped for {symbol}: {exc}", RuntimeWarning)
            continue
        times = pd.to_datetime(features["time"], utc=True)
        # Use a relative seconds axis so pandas' ns/us resolution is harmless.
        epoch = (times - times.iloc[0]).dt.total_seconds().to_numpy(dtype=float)
        bid = features["bid"].to_numpy(dtype=float)
        ask = features["ask"].to_numpy(dtype=float)
        eligible = np.flatnonzero(epoch <= epoch[-1] - max(horizon_values))
        last_sample: float | None = None
        for index in eligible:
            if last_sample is not None and epoch[index] - last_sample < int(sample_every_s):
                continue
            last_sample = float(epoch[index])
            for horizon in horizon_values:
                end = int(np.searchsorted(epoch, epoch[index] + horizon, side="right") - 1)
                if end <= index:
                    continue
                future_times = times.iloc[index + 1 : end + 1]
                for side in ("buy", "sell"):
                    outcome = replay_executable_path(
                        entry_time=times.iloc[index],
                        entry_bid=bid[index], entry_ask=ask[index],
                        future_times=future_times,
                        future_bid=bid[index + 1 : end + 1],
                        future_ask=ask[index + 1 : end + 1],
                        side=side, horizon_s=horizon,
                    )
                    row = features.iloc[index].to_dict()
                    row.update(outcome)
                    row.update(
                        {
                            "symbol": symbol,
                            "side": side,
                            "side_buy": 1.0 if side == "buy" else 0.0,
                            "horizon_s": float(horizon),
                            "target": int(outcome["captured_exit_net_pnl"] > 0.0),
                            "session": _session_name(int(times.iloc[index].hour)),
                            "candidate_source": "all_quote_entries",
                            "candidate_authority": "SHADOW_ONLY",
                            "regime": "unknown_quote_regime",
                            "structure": "quote_microstructure",
                            "family": "universal_quote_entry",
                        }
                    )
                    rows.append(row)
    if not rows:
        raise ValueError("no matured shadow candidates")
    return pd.DataFrame(rows).sort_values(
        ["time", "symbol", "side", "horizon_s"], kind="stable"
    ).reset_index(drop=True)


def shadow_model_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Return the numeric point-in-time feature matrix plus the target."""
    if "target" not in frame:
        raise ValueError("shadow frame requires target")
    excluded = _OUTCOME_COLUMNS | frozenset(
        {"time", "symbol", "side", "session", "regime", "structure", "family", "candidate_source", "candidate_authority"}
    )
    columns = [
        column for column in frame.columns
        if column not in excluded and pd.api.types.is_numeric_dtype(frame[column])
    ]
    result = frame.loc[:, columns].copy()
    result["target"] = frame["target"].astype(int).to_numpy()
    return result.replace([np.inf, -np.inf], np.nan).fillna(0.0)


def chronological_shadow_slices(frame: pd.DataFrame) -> ShadowSlices:
    if frame.empty or "time" not in frame:
        raise ValueError("shadow frame requires time")
    ordered = frame.sort_values("time", kind="stable").reset_index(drop=True)
    unique_times = ordered["time"].drop_duplicates().sort_values().to_numpy()
    if len(unique_times) < 20:
        raise ValueError("insufficient distinct timestamps for chronological OOS")
    train_end = unique_times[max(0, int(len(unique_times) * 0.60) - 1)]
    validation_end = unique_times[max(0, int(len(unique_times) * 0.80) - 1)]
    test_end = unique_times[max(0, int(len(unique_times) * 0.90) - 1)]
    parts = (
        ordered[ordered["time"] <= train_end].copy(),
        ordered[(ordered["time"] > train_end) & (ordered["time"] <= validation_end)].copy(),
        ordered[(ordered["time"] > validation_end) & (ordered["time"] <= test_end)].copy(),
        ordered[ordered["time"] > test_end].copy(),
    )
    if min(map(len, parts)) == 0:
        raise ValueError("chronological shadow slices must all be non-empty")
    return ShadowSlices(*parts)


def _calibration_ece(probability: np.ndarray, actual: np.ndarray) -> float | None:
    if not len(probability):
        return None
    ece = 0.0
    for lower in np.linspace(0.0, 1.0, 11)[:-1]:
        upper = lower + 0.1
        mask = (probability >= lower) & (probability < upper if upper < 1 else probability <= 1)
        if mask.any():
            ece += float(mask.mean()) * abs(float(probability[mask].mean()) - float(actual[mask].mean()))
    return float(ece)


def _metrics(frame: pd.DataFrame, probability: np.ndarray, threshold: float) -> dict[str, Any]:
    probability = np.asarray(probability, dtype=float)
    actual = frame["target"].to_numpy(dtype=int)
    selected = probability >= float(threshold)
    captured = pd.to_numeric(frame["captured_exit_return"], errors="coerce").to_numpy(dtype=float)
    selected_values = captured[selected]
    wins = selected_values[selected_values > 0.0]
    losses = selected_values[selected_values < 0.0]
    return {
        "n": int(len(frame)),
        "selected": int(selected.sum()),
        "precision": float(actual[selected].mean()) if selected.any() else None,
        "captured_exit_expectancy": float(selected_values.mean()) if len(selected_values) else None,
        "captured_exit_pf": float(wins.sum() / abs(losses.sum())) if len(wins) and len(losses) else None,
        "p95_loss": float(np.quantile(losses, 0.05)) if len(losses) else None,
        "p99_loss": float(np.quantile(losses, 0.01)) if len(losses) else None,
        "calibration_ece": _calibration_ece(probability, actual),
        "abstain_rate": float((~selected).mean()) if len(selected) else None,
    }


def evaluate_shadow_leaderboard(
    frame: pd.DataFrame,
    model_probabilities: Mapping[str, Sequence[float]],
    *,
    thresholds: Sequence[float] = SHADOW_THRESHOLDS,
    min_samples: int = 20,
) -> list[dict[str, Any]]:
    """Evaluate pooled model probabilities by universal market segment."""
    required = {"symbol", "side", "session", "regime", "structure", "family", "horizon_s"}
    if not required.issubset(frame.columns):
        raise ValueError(f"shadow frame missing segment columns: {sorted(required - set(frame.columns))}")
    work = frame.reset_index(drop=True)
    rows: list[dict[str, Any]] = []
    group_columns = ["symbol", "side", "session", "regime", "structure", "family", "horizon_s"]
    for model_name, values in model_probabilities.items():
        probabilities = np.asarray(values, dtype=float)
        if len(probabilities) != len(frame):
            raise ValueError(f"probability length mismatch for {model_name}")
        for threshold in dict.fromkeys(float(value) for value in thresholds):
            for keys, group in work.groupby(group_columns, sort=False, dropna=False):
                indexes = group.index.to_numpy()
                metrics = _metrics(group, probabilities[indexes], float(threshold))
                if int(metrics["selected"]) < int(min_samples):
                    continue
                row = dict(zip(group_columns, keys))
                row.update({"model": str(model_name), "threshold": float(threshold), **metrics})
                rows.append(row)
    rows.sort(
        key=lambda row: (
            row["captured_exit_expectancy"] is None,
            -(row["captured_exit_expectancy"] or -float("inf")),
            -(row["selected"] or 0),
        )
    )
    return rows


def dataset_hash(frame: pd.DataFrame) -> str:
    raw = frame.sort_values(["time", "symbol", "side", "horizon_s"], kind="stable").to_json(
        orient="records", date_format="iso", double_precision=15
    ).encode()
    return hashlib.sha256(raw).hexdigest()


def fit_shadow_model_space(
    frame: pd.DataFrame,
    *,
    min_samples: int = 20,
) -> dict[str, Any]:
    """Fit local shadow-only model candidates on train and score sealed OOS."""
    slices = chronological_shadow_slices(frame)
    train, validation, sealed = slices.train, slices.validation, slices.sealed
    x_train = shadow_model_frame(train).drop(columns=["target"])
    x_validation = shadow_model_frame(validation).drop(columns=["target"])
    x_sealed = shadow_model_frame(sealed).drop(columns=["target"])
    y_train = train["target"].astype(int).to_numpy()
    if len(np.unique(y_train)) < 2:
        raise ValueError("shadow train target must contain both classes")
    factories = {
        "logistic": LogisticRegression(C=1.0, max_iter=1000, class_weight="balanced", random_state=42),
        "regularized_logistic": LogisticRegression(C=0.1, max_iter=1000, class_weight="balanced", random_state=42),
        "hist_gradient_boosting": HistGradientBoostingClassifier(max_iter=100, max_depth=5, learning_rate=0.05, random_state=42),
        "gradient_boosting": GradientBoostingClassifier(n_estimators=80, max_depth=3, learning_rate=0.05, random_state=42),
        "random_forest": RandomForestClassifier(n_estimators=80, max_depth=8, class_weight="balanced", n_jobs=-1, random_state=42),
    }
    probabilities: dict[str, np.ndarray] = {}
    selected_thresholds: dict[str, float] = {}
    model_errors: dict[str, str] = {}
    oos_metrics: dict[str, dict[str, Any]] = {}
    for name, estimator in factories.items():
        try:
            model = Pipeline([("scale", RobustScaler()), ("model", estimator)])
            model.fit(x_train, y_train)
            validation_probability = model.predict_proba(x_validation)[:, 1]
            candidates: list[tuple[float, float]] = []
            validation_captured = validation["captured_exit_return"].to_numpy(dtype=float)
            for threshold in SHADOW_THRESHOLDS:
                chosen = validation_probability >= threshold
                if int(chosen.sum()) >= int(min_samples):
                    candidates.append((float(validation_captured[chosen].mean()), float(threshold)))
            selected_thresholds[name] = max(candidates, default=(0.0, 0.5))[1]
            test_probability = model.predict_proba(
                shadow_model_frame(slices.test).drop(columns=["target"])
            )[:, 1]
            probabilities[name] = model.predict_proba(x_sealed)[:, 1]
            oos_metrics[name] = {
                "test": _metrics(slices.test, test_probability, selected_thresholds[name]),
                "sealed": _metrics(slices.sealed, probabilities[name], selected_thresholds[name]),
            }
        except Exception as exc:  # one model failure must not erase other evidence
            model_errors[name] = f"{type(exc).__name__}: {exc}"
    leaderboard = evaluate_shadow_leaderboard(
        sealed,
        probabilities,
        thresholds=tuple(selected_thresholds.values()) or (0.5,),
        min_samples=min_samples,
    )
    primary_model = max(
        oos_metrics,
        key=lambda name: (
            oos_metrics[name]["sealed"].get("captured_exit_expectancy")
            if oos_metrics[name]["sealed"].get("captured_exit_expectancy") is not None
            else -float("inf")
        ),
        default=None,
    )
    return {
        "dataset_hash": dataset_hash(frame),
        "validation_hash": dataset_hash(validation),
        "feature_names": list(x_train.columns),
        "model_names": sorted(probabilities),
        "model_count": len(probabilities),
        "selected_thresholds": selected_thresholds,
        "model_errors": model_errors,
        "oos_metrics": oos_metrics,
        "primary_model": primary_model,
        "oos": {
            "train_n": len(train),
            "validation_n": len(validation),
            "test_n": len(slices.test),
            "sealed_n": len(sealed),
        },
        "leaderboard": leaderboard[:50],
    }
