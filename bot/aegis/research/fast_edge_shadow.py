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
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import RobustScaler

from aegis.research.short_horizon import _session_name
from aegis.research.short_horizon_artifact import _feature_frame


SHADOW_HORIZONS_S = (1, 2, 3, 5, 8, 10, 15, 20, 30, 45)
SHADOW_THRESHOLDS = (0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.925, 0.95, 0.975, 0.99)
SHADOW_EXIT_POLICIES = (
    "captured_exit_replay", "first_meaningful_green", "mfe_protection", "no_progress_3s",
)
SHADOW_PROBABILITY_TARGETS = {
    "P_GREEN_1S": "green_within_1s",
    "P_GREEN_2S": "green_within_2s",
    "P_GREEN_3S": "green_within_3s",
    "P_GREEN_5S": "green_within_5s",
    "P_GREEN_8S": "green_within_8s",
    "P_GREEN_10S": "green_within_10s",
    "P_CAPTURED_WIN_3S": "captured_win_3s",
    "P_CAPTURED_WIN_5S": "captured_win_5s",
    "P_CAPTURED_WIN_10S": "captured_win_10s",
    "P_CAPTURED_WIN_20S": "captured_win_20s",
    "P_IMMEDIATE_ADVERSE_MOVE": "immediate_adverse_move",
    "P_NEVER_GREEN": "never_green",
    "P_TAIL_LOSS": "tail_loss",
    "P_WINNER_GIVEBACK": "winner_giveback",
}
SHADOW_REGRESSION_TARGETS = {
    "EXPECTED_NET_PNL": "captured_exit_return",
    "EXPECTED_MFE": "mfe",
    "EXPECTED_MAE": "mae",
    "EXPECTED_TIME_TO_GREEN": "time_to_green_s",
    "EXPECTED_TIME_TO_FAILURE": "time_to_failure_s",
}

_OUTCOME_COLUMNS = frozenset(
    {
        "target", "terminal_net_pnl", "terminal_return", "mfe", "mae", "tail_loss",
        "harvest_return", "time_to_profit_s", "time_to_failure_s",
        "captured_exit_net_pnl", "captured_exit_return", "captured_exit_reason",
        "first_green", "never_green", "time_to_green_s", "time_to_mfe_s",
        "time_in_red_s", "winner_giveback", "future_path_observed_n",
        "first_profitable_executable_close", "first_profitable_close_net_pnl",
        "immediate_adverse_move",
    }
)


@dataclass(frozen=True)
class ShadowSlices:
    train: pd.DataFrame
    validation: pd.DataFrame
    test: pd.DataFrame
    sealed: pd.DataFrame


def _add_completed_bar_context(features: pd.DataFrame) -> pd.DataFrame:
    """Attach only completed M1/M5/M15 quote-derived bars as-of each tick."""
    result = features.copy()
    quote = result.loc[:, ["time", "mid"]].sort_values("time", kind="stable")
    quote_indexed = quote.set_index("time")["mid"]
    for minutes in (1, 5, 15):
        bars = quote_indexed.resample(
            f"{minutes}min", label="right", closed="right"
        ).agg(["first", "max", "min", "last"]).dropna()
        bars = bars.rename(
            columns={
                "first": f"m{minutes}_open",
                "max": f"m{minutes}_high",
                "min": f"m{minutes}_low",
                "last": f"m{minutes}_close",
            }
        )
        bars[f"m{minutes}_return"] = bars[f"m{minutes}_close"] / bars[f"m{minutes}_open"] - 1.0
        bars[f"m{minutes}_range"] = bars[f"m{minutes}_high"] - bars[f"m{minutes}_low"]
        bars = bars.reset_index().rename(columns={"time": "bar_time"})
        result = pd.merge_asof(
            result.sort_values("time", kind="stable"),
            bars.sort_values("bar_time", kind="stable"),
            left_on="time", right_on="bar_time", direction="backward",
        ).drop(columns=["bar_time"])
        close = result[f"m{minutes}_close"]
        high = result[f"m{minutes}_high"]
        low = result[f"m{minutes}_low"]
        result[f"m{minutes}_close_location"] = np.divide(
            close - low, np.maximum(high - low, 1e-12)
        )
    m1_high = result["m1_high"].shift(1).rolling(20, min_periods=2).max()
    m1_low = result["m1_low"].shift(1).rolling(20, min_periods=2).min()
    result["structure_context"] = np.select(
        [result["m1_close"] > m1_high, result["m1_close"] < m1_low],
        ["m1_breakout_up", "m1_breakout_down"],
        default="m1_range_or_pullback",
    )
    result["regime_context"] = np.select(
        [result["volatility_expansion"] >= 1.2, result["volatility_expansion"] <= 0.8],
        ["volatility_expansion", "compression"],
        default="normal_volatility",
    )
    return result


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
    exit_policy: str = "captured_exit_replay",
) -> dict[str, Any]:
    """Replay a single entry with only the next quote visible at each step."""
    side = str(side).strip().lower()
    if side not in {"buy", "sell"}:
        raise ValueError("side must be buy or sell")
    if int(horizon_s) <= 0:
        raise ValueError("horizon_s must be positive")
    exit_policy = str(exit_policy).strip().lower()
    valid_policies = {
        "captured_exit_replay", "first_meaningful_green", "mfe_protection",
        "no_progress_3s", "first_green",
    }
    if exit_policy not in valid_policies:
        raise ValueError(f"unsupported exit_policy: {exit_policy}")
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
    first_failure_index = next((i for i, value in enumerate(signed) if value <= -3.0 * entry_spread), None)
    mfe_index = int(np.argmax(signed))
    captured = float(signed[-1])
    captured_reason = "timeout"
    captured_index: int | None = None
    time_in_red = 0.0
    seen_positive = False
    peak_after_green = -float("inf")
    prior = entry_timestamp
    for index, value in enumerate(signed):
        current = pd.Timestamp(times[index])
        elapsed = max(0.0, (current - prior).total_seconds())
        if float(value) < 0.0:
            time_in_red += elapsed
        prior = current
        elapsed_from_entry = max(0.0, (current - entry_timestamp).total_seconds())
        if float(value) > 0.0:
            seen_positive = True
        if float(value) <= -abort_threshold:
            captured = float(value)
            captured_reason = "abort"
            captured_index = index
            break
        if exit_policy == "no_progress_3s" and elapsed_from_entry >= 3.0 and not seen_positive:
            captured = float(value)
            captured_reason = "no_progress"
            captured_index = index
            break
        if exit_policy == "mfe_protection" and seen_positive:
            peak_after_green = max(peak_after_green, float(value))
            if peak_after_green >= harvest_threshold and float(value) <= peak_after_green - entry_spread:
                captured = float(value)
                captured_reason = "giveback"
                captured_index = index
                break
        harvest_now = (
            float(value) > 0.0 if exit_policy == "first_green"
            else float(value) >= harvest_threshold
        )
        if harvest_now and exit_policy != "mfe_protection":
            captured = float(value)
            captured_reason = "harvest"
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
    failure_time = (
        float((pd.Timestamp(times[first_failure_index]) - entry_timestamp).total_seconds())
        if first_failure_index is not None else None
    )
    return {
        "captured_exit_net_pnl": captured,
        "captured_exit_return": captured / entry_mid if entry_mid > 0 else np.nan,
        "captured_exit_reason": captured_reason,
        "terminal_net_pnl": float(signed[-1]),
        "terminal_return": float(signed[-1]) / entry_mid if entry_mid > 0 else np.nan,
        "mfe": mfe,
        "mae": mae,
        "tail_loss": bool(mae <= -abort_threshold),
        "immediate_adverse_move": bool(float(signed[0]) <= -entry_spread),
        "first_green": bool(first_green),
        "never_green": bool(not first_green),
        "time_to_green_s": green_time,
        "time_to_profit_s": green_time,
        "time_to_failure_s": failure_time,
        "time_to_mfe_s": mfe_time,
        "time_in_red_s": float(time_in_red),
        "winner_giveback": bool(mfe > 0.0 and captured < mfe),
        "first_profitable_executable_close": bool(first_green),
        "first_profitable_close_net_pnl": (
            float(signed[first_green_index]) if first_green_index is not None else None
        ),
        "future_path_observed_n": int(len(signed) if captured_index is None else captured_index + 1),
        "exit_policy": exit_policy,
        "exit_time_s": float(
            (pd.Timestamp(times[captured_index]) - entry_timestamp).total_seconds()
            if captured_index is not None else (pd.Timestamp(times[-1]) - entry_timestamp).total_seconds()
        ),
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
        features = _add_completed_bar_context(features)
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
            outcomes_by_side_horizon: dict[str, dict[int, dict[str, Any]]] = {
                "buy": {}, "sell": {}
            }
            for path_horizon in horizon_values:
                path_end = int(
                    np.searchsorted(epoch, epoch[index] + path_horizon, side="right") - 1
                )
                if path_end <= index:
                    continue
                for side in ("buy", "sell"):
                    outcomes_by_side_horizon[side][path_horizon] = replay_executable_path(
                        entry_time=times.iloc[index],
                        entry_bid=bid[index], entry_ask=ask[index],
                        future_times=times.iloc[index + 1 : path_end + 1],
                        future_bid=bid[index + 1 : path_end + 1],
                        future_ask=ask[index + 1 : path_end + 1],
                        side=side, horizon_s=path_horizon,
                    )
            for horizon in horizon_values:
                for side in ("buy", "sell"):
                    outcome = outcomes_by_side_horizon[side].get(horizon)
                    if outcome is None:
                        continue
                    row = features.iloc[index].to_dict()
                    row.update(outcome)
                    row.update(
                        {
                            "symbol": symbol,
                            "side": side,
                            "side_buy": 1.0 if side == "buy" else 0.0,
                            "horizon_s": float(horizon),
                            "entry_price": float(ask[index] if side == "buy" else bid[index]),
                            "entry_spread": float(ask[index] - bid[index]),
                            "cost": float(ask[index] - bid[index]),
                            "target": int(outcome["captured_exit_net_pnl"] > 0.0),
                            "session": _session_name(int(times.iloc[index].hour)),
                            "candidate_source": "all_quote_entries",
                            "candidate_authority": "SHADOW_ONLY",
                            "regime": str(features.iloc[index].get("regime_context") or "unknown_quote_regime"),
                            "structure": str(features.iloc[index].get("structure_context") or "unknown_structure"),
                            "family": "universal_quote_entry",
                            "family_version": "quote_microstructure_v1",
                        }
                    )
                    for policy in SHADOW_EXIT_POLICIES:
                        policy_end = int(
                            np.searchsorted(epoch, epoch[index] + horizon, side="right") - 1
                        )
                        policy_outcome = (
                            outcome if policy == "captured_exit_replay"
                            else replay_executable_path(
                                entry_time=times.iloc[index],
                                entry_bid=bid[index], entry_ask=ask[index],
                                future_times=times.iloc[index + 1 : policy_end + 1],
                                future_bid=bid[index + 1 : policy_end + 1],
                                future_ask=ask[index + 1 : policy_end + 1],
                                side=side, horizon_s=horizon, exit_policy=policy,
                            )
                        )
                        policy_key = policy.replace("_", "")
                        row[f"exit_{policy_key}_net_pnl"] = policy_outcome["captured_exit_net_pnl"]
                        row[f"exit_{policy_key}_return"] = policy_outcome["captured_exit_return"]
                        row[f"exit_{policy_key}_reason"] = policy_outcome["captured_exit_reason"]
                        row[f"exit_{policy_key}_time_s"] = policy_outcome["exit_time_s"]
                    # Carry every requested horizon's executable terminal
                    # path result on the row. These are outcome columns and
                    # never enter shadow_model_frame().
                    for path_horizon, path_outcome in outcomes_by_side_horizon[side].items():
                        row[f"pnl_{path_horizon}s"] = path_outcome["terminal_net_pnl"]
                        row[f"green_within_{path_horizon}s"] = bool(path_outcome["first_green"])
                        row[f"captured_win_{path_horizon}s"] = bool(
                            path_outcome["captured_exit_net_pnl"] > 0.0
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
        {
            "time", "symbol", "side", "session", "regime", "structure", "family",
            "family_version", "structure_context", "regime_context",
            "candidate_source", "candidate_authority",
        }
    )
    columns = [
        column for column in frame.columns
        if column not in excluded
        and not str(column).startswith(("pnl_", "green_within_", "captured_win_", "exit_"))
        and pd.api.types.is_numeric_dtype(frame[column])
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
    ordered_times = pd.to_datetime(frame["time"], utc=True, errors="coerce") if "time" in frame else pd.Series(dtype="datetime64[ns, UTC]")
    duration_hours = (
        max(float((ordered_times.max() - ordered_times.min()).total_seconds()) / 3600.0, 1e-9)
        if len(ordered_times) and ordered_times.notna().all() else None
    )
    return {
        "n": int(len(frame)),
        "selected": int(selected.sum()),
        "precision": float(actual[selected].mean()) if selected.any() else None,
        "captured_exit_expectancy": float(selected_values.mean()) if len(selected_values) else None,
        "captured_exit_pf": float(wins.sum() / abs(losses.sum())) if len(wins) and len(losses) else None,
        "p95_loss": float(np.quantile(losses, 0.05)) if len(losses) else None,
        "p99_loss": float(np.quantile(losses, 0.01)) if len(losses) else None,
        "avg_win": float(wins.mean()) if len(wins) else None,
        "avg_loss": float(losses.mean()) if len(losses) else None,
        "median_time_to_green_s": float(pd.to_numeric(frame.loc[selected, "time_to_green_s"], errors="coerce").median())
        if selected.any() and "time_to_green_s" in frame else None,
        "trades_per_hour": float(selected.sum() / duration_hours) if duration_hours else None,
        "net_per_hour": float(selected_values.sum() / duration_hours) if duration_hours and len(selected_values) else None,
        "exit_policy": "captured_exit_replay",
        "calibration_ece": _calibration_ece(probability, actual),
        "abstain_rate": float((~selected).mean()) if len(selected) else None,
    }


def fit_multi_outcome_models(frame: pd.DataFrame) -> dict[str, Any]:
    """Fit point-in-time pooled probability/regression targets on sealed OOS.

    These are research diagnostics, not execution gates. Each target is fit
    only on the chronological training slice and scored on the sealed slice.
    """
    slices = chronological_shadow_slices(frame)
    train_features = shadow_model_frame(slices.train).drop(columns=["target"])
    sealed_features = shadow_model_frame(slices.sealed).drop(columns=["target"])
    report: dict[str, Any] = {"probability": {}, "regression": {}}
    for label, target_column in SHADOW_PROBABILITY_TARGETS.items():
        if target_column not in slices.train or target_column not in slices.sealed:
            report["probability"][label] = {"status": "missing_target", "target_column": target_column}
            continue
        y_train = pd.to_numeric(slices.train[target_column], errors="coerce").fillna(0.0).astype(int)
        y_sealed = pd.to_numeric(slices.sealed[target_column], errors="coerce").fillna(0.0).astype(int)
        if y_train.nunique() < 2:
            report["probability"][label] = {"status": "single_class_train", "target_column": target_column}
            continue
        model = Pipeline(
            [
                ("scale", RobustScaler()),
                (
                    "model",
                    LogisticRegression(
                        C=0.1, solver="liblinear", max_iter=500,
                        class_weight="balanced", random_state=42,
                    ),
                ),
            ]
        )
        model.fit(train_features, y_train)
        probability = model.predict_proba(sealed_features)[:, 1]
        actual = y_sealed.to_numpy(dtype=int)
        report["probability"][label] = {
            "status": "SEALED_OOS",
            "target_column": target_column,
            "model": "regularized_logistic",
            "oos_n": int(len(actual)),
            "oos_positive_rate": float(actual.mean()) if len(actual) else None,
            "oos_probability_mean": float(probability.mean()) if len(probability) else None,
            "oos_brier": float(np.mean(np.square(probability - actual))) if len(actual) else None,
            "calibration_ece": _calibration_ece(probability, actual),
        }
    for label, target_column in SHADOW_REGRESSION_TARGETS.items():
        if target_column not in slices.train or target_column not in slices.sealed:
            report["regression"][label] = {"status": "missing_target", "target_column": target_column}
            continue
        train_target = pd.to_numeric(slices.train[target_column], errors="coerce")
        sealed_target = pd.to_numeric(slices.sealed[target_column], errors="coerce")
        fill_value = float(train_target.median()) if train_target.notna().any() else 0.0
        y_train = train_target.fillna(fill_value).to_numpy(dtype=float)
        y_sealed = sealed_target.fillna(fill_value).to_numpy(dtype=float)
        model = Pipeline([("scale", RobustScaler()), ("model", Ridge(alpha=1.0, solver="lsqr"))])
        model.fit(train_features, y_train)
        prediction = model.predict(sealed_features)
        report["regression"][label] = {
            "status": "SEALED_OOS",
            "target_column": target_column,
            "model": "ridge",
            "oos_n": int(len(y_sealed)),
            "oos_prediction_mean": float(np.mean(prediction)) if len(prediction) else None,
            "oos_actual_mean": float(np.mean(y_sealed)) if len(y_sealed) else None,
            "oos_mae": float(np.mean(np.abs(prediction - y_sealed))) if len(y_sealed) else None,
        }
    return report


def fit_segmented_logistic_models(
    frame: pd.DataFrame,
    *,
    min_train_samples: int = 200,
    min_validation_samples: int = 20,
    min_sealed_samples: int = 20,
) -> dict[str, Any]:
    """Fit small, chronological logistic challengers by supported dimensions.

    The pooled model remains the hierarchical fallback. Segment models are
    published as research evidence only and are never copied into runtime
    authority automatically.
    """
    slices = chronological_shadow_slices(frame)
    dimensions = ("symbol", "side", "session", "regime", "structure", "family", "horizon_s")
    x_train_all = shadow_model_frame(slices.train).drop(columns=["target"])
    x_validation_all = shadow_model_frame(slices.validation).drop(columns=["target"])
    x_sealed_all = shadow_model_frame(slices.sealed).drop(columns=["target"])
    rows: list[dict[str, Any]] = []
    rejected: dict[str, int] = {}
    for dimension in dimensions:
        values = list(frame[dimension].dropna().unique())
        if len(values) <= 1:
            rejected[f"{dimension}:constant"] = 1
            continue
        for value in values:
            train_mask = slices.train[dimension] == value
            validation_mask = slices.validation[dimension] == value
            sealed_mask = slices.sealed[dimension] == value
            train_part = slices.train.loc[train_mask]
            validation_part = slices.validation.loc[validation_mask]
            sealed_part = slices.sealed.loc[sealed_mask]
            key = f"{dimension}={value}"
            if min(len(train_part), len(validation_part), len(sealed_part)) < min(
                min_train_samples, min_validation_samples, min_sealed_samples
            ):
                rejected[key] = 1
                continue
            y_train = train_part["target"].astype(int)
            if y_train.nunique() < 2:
                rejected[f"{key}:single_class"] = 1
                continue
            model = Pipeline(
                [
                    ("scale", RobustScaler()),
                    (
                        "model",
                        LogisticRegression(
                            C=0.1, solver="liblinear", max_iter=500,
                            class_weight="balanced", random_state=42,
                        ),
                    ),
                ]
            )
            model.fit(x_train_all.loc[train_mask.to_numpy()], y_train)
            validation_probability = model.predict_proba(
                x_validation_all.loc[validation_mask.to_numpy()]
            )[:, 1]
            validation_returns = validation_part["captured_exit_return"].to_numpy(dtype=float)
            candidates = [
                (float(validation_returns[validation_probability >= threshold].mean()), float(threshold))
                for threshold in SHADOW_THRESHOLDS
                if int((validation_probability >= threshold).sum()) >= int(min_validation_samples)
            ]
            threshold = max(candidates, default=(0.0, 0.5))[1]
            sealed_probability = model.predict_proba(x_sealed_all.loc[sealed_mask.to_numpy()])[:, 1]
            metrics = _metrics(sealed_part, sealed_probability, threshold)
            row = {
                "model": f"segmented_regularized_logistic_{dimension}",
                "segment_dimension": dimension,
                "segment_value": str(value),
                "threshold": threshold,
                **metrics,
            }
            for segment_dimension in dimensions:
                row[segment_dimension] = str(value) if segment_dimension == dimension else "ALL"
            rows.append(row)
    rows.sort(
        key=lambda row: (
            row["captured_exit_expectancy"] is None,
            -(row["captured_exit_expectancy"] or -float("inf")),
        )
    )
    return {
        "dimensions": list(dimensions),
        "accepted_model_count": len(rows),
        "rejected_segment_count": len(rejected),
        "rejected_segments": sorted(rejected)[:100],
        "oos_leaderboard": rows[:50],
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


def evaluate_exit_policies(
    frame: pd.DataFrame,
    *,
    policies: Sequence[str] = SHADOW_EXIT_POLICIES,
    min_samples: int = 20,
) -> list[dict[str, Any]]:
    """Compare causal exit policies on the supplied chronological slice."""
    required = {"symbol", "side", "session", "regime", "structure", "family", "horizon_s"}
    if not required.issubset(frame.columns):
        raise ValueError(f"shadow frame missing segment columns: {sorted(required - set(frame.columns))}")
    work = frame.reset_index(drop=True)
    group_columns = ["symbol", "side", "session", "regime", "structure", "family", "horizon_s"]
    rows: list[dict[str, Any]] = []
    for policy in policies:
        policy_key = str(policy).replace("_", "")
        return_column = f"exit_{policy_key}_return"
        time_column = f"exit_{policy_key}_time_s"
        if return_column not in work or time_column not in work:
            raise ValueError(f"shadow frame missing policy outcome columns for {policy}")
        for keys, group in work.groupby(group_columns, sort=False, dropna=False):
            values = pd.to_numeric(group[return_column], errors="coerce").dropna().to_numpy(dtype=float)
            if len(values) < int(min_samples):
                continue
            wins = values[values > 0.0]
            losses = values[values < 0.0]
            row = dict(zip(group_columns, keys))
            group_times = pd.to_datetime(group["time"], utc=True, errors="coerce")
            duration_hours = max(
                float((group_times.max() - group_times.min()).total_seconds()) / 3600.0,
                1e-9,
            )
            row.update(
                {
                    "exit_policy": str(policy),
                    "n": int(len(values)),
                    "win_rate": float((values > 0.0).mean()),
                    "captured_exit_expectancy": float(values.mean()),
                    "captured_exit_pf": float(wins.sum() / abs(losses.sum()))
                    if len(wins) and len(losses) else None,
                    "avg_win": float(wins.mean()) if len(wins) else None,
                    "avg_loss": float(losses.mean()) if len(losses) else None,
                    "p95_loss": float(np.quantile(losses, 0.05)) if len(losses) else None,
                    "p99_loss": float(np.quantile(losses, 0.01)) if len(losses) else None,
                    "median_exit_time_s": float(pd.to_numeric(group[time_column], errors="coerce").median()),
                    "trades_per_hour": float(len(values) / duration_hours),
                    "net_per_hour": float(values.sum() / duration_hours),
                }
            )
            rows.append(row)
    rows.sort(
        key=lambda row: (
            row["captured_exit_expectancy"] is None,
            -(row["captured_exit_expectancy"] or -float("inf")),
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
    test_probabilities: dict[str, np.ndarray] = {}
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
            test_probabilities[name] = test_probability
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
    test_leaderboard = evaluate_shadow_leaderboard(
        slices.test,
        test_probabilities,
        thresholds=tuple(selected_thresholds.values()) or (0.5,),
        min_samples=min_samples,
    )
    test_by_key = {
        tuple(row.get(key) for key in ("symbol", "side", "session", "regime", "structure", "family", "horizon_s", "model", "threshold")): row
        for row in test_leaderboard
    }
    promotion_candidates: list[dict[str, Any]] = []
    for sealed_row in leaderboard:
        key = tuple(
            sealed_row.get(name)
            for name in ("symbol", "side", "session", "regime", "structure", "family", "horizon_s", "model", "threshold")
        )
        test_row = test_by_key.get(key)
        if not test_row:
            continue
        if (
            (sealed_row.get("captured_exit_expectancy") or 0.0) > 0.0
            and (test_row.get("captured_exit_expectancy") or 0.0) > 0.0
            and (sealed_row.get("captured_exit_pf") or 0.0) > 1.0
            and (test_row.get("captured_exit_pf") or 0.0) > 1.0
            and int(sealed_row.get("selected") or 0) >= int(min_samples)
            and int(test_row.get("selected") or 0) >= int(min_samples)
        ):
            promotion_candidates.append(
                {
                    "candidate": sealed_row,
                    "test": test_row,
                    "status": "REQUIRES_CALIBRATION_TAIL_REVIEW",
                }
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
    multi_outcome_models = fit_multi_outcome_models(frame)
    segmented_model_space = fit_segmented_logistic_models(frame)
    sealed_predictions = slices.sealed.loc[
        :, [
            "time", "symbol", "side", "session", "regime", "structure", "family",
            "family_version", "horizon_s", "entry_price", "entry_spread", "cost",
        ]
    ].copy().reset_index(drop=True)
    probability_matrix: list[np.ndarray] = []
    for model_name in sorted(probabilities):
        values = np.asarray(probabilities[model_name], dtype=float)
        probability_matrix.append(values)
        sealed_predictions[f"model_probability_{model_name}"] = values
    if probability_matrix:
        matrix = np.vstack(probability_matrix).T
        sealed_predictions["model_probability_mean"] = matrix.mean(axis=1)
        sealed_predictions["model_disagreement"] = matrix.std(axis=1)
        sealed_predictions["prediction_vector"] = [list(map(float, row)) for row in matrix]
    sealed_predictions["prediction_split"] = "sealed_oos"
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
        "multi_outcome_models": multi_outcome_models,
        "segmented_model_space": segmented_model_space,
        "sealed_predictions": sealed_predictions,
        "oos": {
            "train_n": len(train),
            "validation_n": len(validation),
            "test_n": len(slices.test),
            "sealed_n": len(sealed),
        },
        "leaderboard": leaderboard[:50],
        "test_leaderboard": test_leaderboard[:50],
        "promotion_candidates": promotion_candidates[:50],
    }
