"""Research-only builder for a calibrated seconds-horizon Firehose artifact.

This module consumes completed MT5 quote history and never imports an engine or
places orders.  Features are calculated from observations at or before the
entry timestamp.  Labels use only observations strictly after entry.  An
artifact is execution-authorizing only when its chronological OOS slice has
positive cost-aware captured-exit replay expectancy. Older targets remain
research-only labels.
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

from aegis.research.short_horizon import (
    DEFAULT_HORIZONS_S,
    mechanism_features,
    session_features,
    symbol_features,
)
from aegis.research.registry import DuplicateExperimentError, ExperimentRegistry
from aegis.research_factory.evaluation import record_outcome
from aegis.research_factory.ml_pipeline import MLPipeline, ModelConfig
from aegis.intel.analogue_store import is_executable_capture_provenance
from aegis.intel.trade_controller import TradeController
from aegis.intel.trade_economics import wilson_lower_bound


ARTIFACT_SCHEMA = "short_horizon_ensemble.v1"
MIN_CAPTURED_EXIT_LOSSES = 5  # align with the repo's sampled-loss promotion standard
MIN_CAPTURED_EXIT_WIN_LCB95 = 0.95
FAST_GREEN_CEILING_S = 3


@dataclass(frozen=True)
class ChronologicalSlices:
    train: pd.DataFrame
    validation: pd.DataFrame
    test: pd.DataFrame
    sealed: pd.DataFrame


def _hash_frame(frame: pd.DataFrame) -> str:
    order = [
        column for column in ("time", "symbol", "side", "mechanism", "horizon_s")
        if column in frame.columns
    ]
    payload = frame.sort_values(order, kind="stable") if order else frame
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
    target = str(metadata.get("target_definition") or "terminal_profit").strip().lower()
    status = (
        "CHALLENGER"
        if (
            str(metadata.get("execution_status") or "") == "EXECUTION_CANDIDATE"
            and target == "captured_exit_replay"
        )
        else "NO_EVIDENCE"
    )
    harvest_mode = target in {"mfe_first", "fast_harvest"}
    reason = (
        "positive chronological test and sealed-OOS first-green harvest returns support a challenger"
        if status == "CHALLENGER" and harvest_mode
        else "positive chronological test and sealed-OOS captured-exit replay returns support a challenger"
        if status == "CHALLENGER" and target == "captured_exit_replay"
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
        "test_mean_captured_exit_return": test.get("mean_captured_exit_return"),
        "test_harvest_lcb95_return": test.get("harvest_lcb95_return"),
        "test_brier": test.get("brier"),
        "sealed_n": sealed.get("n"),
        "sealed_selected": sealed.get("selected"),
        "sealed_positive_rate": sealed.get("positive_rate"),
        "sealed_mean_terminal_return": sealed.get("mean_terminal_return"),
        "sealed_mean_harvest_return": sealed.get("mean_harvest_return"),
        "sealed_mean_captured_exit_return": sealed.get("mean_captured_exit_return"),
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


def _feature_frame(
    quotes: pd.DataFrame,
    symbol: str,
    *,
    minimum_history_rows: int | None = None,
) -> pd.DataFrame:
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
    minimum_rows = max(DEFAULT_HORIZONS_S) + 20 if minimum_history_rows is None else int(minimum_history_rows)
    if len(frame) < max(minimum_rows, 2):
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
    for window in (1, 2, 3, 5, 8, 10, 15, 30, 60):
        starts = _asof_index(times, window)
        valid = starts >= 0
        result = np.full(len(mid), np.nan, dtype=float)
        result[valid] = mid[valid] / mid[starts[valid]] - 1.0
        values[f"return_{window}s"] = result
    velocity_series = pd.Series(velocity)
    spread_change = values["spread_change"]
    values["spread_acceleration"] = np.concatenate(([0.0], np.diff(spread_change)))
    prior_velocity = velocity_series.shift(1).fillna(0.0).to_numpy(dtype=float)
    values["micro_reversal"] = np.where(
        (velocity * prior_velocity) < 0.0,
        np.abs(velocity - prior_velocity),
        0.0,
    )
    values["momentum_persistence"] = (
        np.sign(velocity_series).rolling(10, min_periods=2).mean().fillna(0.0).to_numpy(dtype=float)
    )
    rolling_abs_velocity = (
        velocity_series.abs().rolling(20, min_periods=2).mean().fillna(0.0).to_numpy(dtype=float)
    )
    values["momentum_decay"] = np.divide(
        np.abs(velocity), np.maximum(rolling_abs_velocity, 1e-12)
    )
    mid_series = pd.Series(mid)
    values["distance_to_micro_high"] = mid - mid_series.rolling(30, min_periods=2).max().to_numpy(dtype=float)
    values["distance_to_micro_low"] = mid - mid_series.rolling(30, min_periods=2).min().to_numpy(dtype=float)
    volatility_series = pd.Series(values["micro_volatility"])
    baseline_volatility = (
        volatility_series.rolling(60, min_periods=2).mean().fillna(0.0).to_numpy(dtype=float)
    )
    values["volatility_expansion"] = np.divide(
        values["micro_volatility"], np.maximum(baseline_volatility, 1e-12)
    )
    values["cost_to_movement"] = np.divide(
        spread, np.maximum(np.abs(velocity), 1e-12)
    )
    return pd.DataFrame(values)


def build_quote_training_frame(
    quotes_by_symbol: Mapping[str, pd.DataFrame],
    *,
    horizons: Sequence[int] = DEFAULT_HORIZONS_S,
    sample_every_s: int = 5,
    target_mode: str = "captured_exit_replay",
    slippage_bps: float = 0.0,
    commission_round_trip_usd: float = 0.0,
    usd_per_price_unit_by_symbol: Mapping[str, float] | None = None,
    mechanism: str = "quote_microstructure_v1",
    provenance: str = "unknown",
) -> pd.DataFrame:
    """Create point-in-time feature/label rows from completed quotes.

    ``mfe_first`` predicts whether the executable path becomes green at any
    point in the horizon. ``fast_harvest`` requires a realized move of at
    least two observed spreads before treating the path as a harvestable win.
    ``terminal_profit`` predicts whether the executable terminal mark is still
    green at the horizon endpoint. ``captured_exit_replay`` sequentially
    applies the capture/abort/timeout policy to future executable BID/ASK
    quotes. All labels are point-in-time and cost-aware.
    """
    horizon_values = tuple(sorted({int(value) for value in horizons if int(value) > 0}))
    if not horizon_values:
        raise ValueError("at least one positive horizon is required")
    if int(sample_every_s) <= 0:
        raise ValueError("sample_every_s must be positive")
    mechanism = str(mechanism or "").strip()
    provenance = str(provenance or "").strip()
    if not mechanism:
        raise ValueError("mechanism must not be empty")
    if not provenance:
        raise ValueError("provenance must not be empty")
    target_mode = str(target_mode).strip().lower()
    if target_mode not in {"mfe_first", "fast_harvest", "terminal_profit", "captured_exit_replay"}:
        raise ValueError(
            "target_mode must be mfe_first, fast_harvest, terminal_profit, or captured_exit_replay"
        )
    try:
        slippage_bps = float(slippage_bps)
    except (TypeError, ValueError) as exc:
        raise ValueError("slippage_bps must be a finite non-negative number") from exc
    if not np.isfinite(slippage_bps) or slippage_bps < 0.0:
        raise ValueError("slippage_bps must be a finite non-negative number")
    try:
        commission_round_trip_usd = float(commission_round_trip_usd)
    except (TypeError, ValueError) as exc:
        raise ValueError("commission_round_trip_usd must be finite and non-negative") from exc
    if not np.isfinite(commission_round_trip_usd) or commission_round_trip_usd < 0.0:
        raise ValueError("commission_round_trip_usd must be finite and non-negative")
    rows: list[dict[str, Any]] = []
    for symbol, quotes in sorted(quotes_by_symbol.items()):
        features = _feature_frame(
            quotes,
            symbol,
            minimum_history_rows=max(horizon_values) + 1,
        )
        times = _epoch_seconds(features["time"])
        bid = features["bid"].to_numpy(dtype=float)
        ask = features["ask"].to_numpy(dtype=float)
        mid = features["mid"].to_numpy(dtype=float)
        spreads = features["spread"].to_numpy(dtype=float)
        # The executable entry/exit sides already include the observed spread.
        # Configured slippage is charged separately on both sides of the round
        # trip, matching the runner's round-trip-notional cost convention.
        tail_threshold = max(float(np.nanmedian(spreads)) * 3.0, 1e-12)
        harvest_threshold = max(float(np.nanmedian(spreads)) * 2.0, 1e-12)
        replay_controller = TradeController()
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
                slippage_price = 2.0 * (slippage_bps / 10_000.0) * float(mid[index])
                for side, raw_signed in (
                    ("buy", future_bid - ask[index]),
                    ("sell", bid[index] - future_ask),
                ):
                    signed = np.asarray(raw_signed, dtype=float) - slippage_price
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
                    captured = terminal
                    captured_reason = "timeout"
                    captured_index: int | None = None
                    shared_replay: dict[str, Any] | None = None
                    if target_mode == "captured_exit_replay":
                        replay_quotes = [
                            {"time": float(times[quote_index]), "bid": float(bid[quote_index]), "ask": float(ask[quote_index])}
                            for quote_index in range(index, end + 1)
                        ]
                        entry = float(ask[index] if side == "buy" else bid[index])
                        sign = 1.0 if side == "buy" else -1.0
                        target_price = entry + sign * harvest_threshold
                        stop_price = entry - sign * tail_threshold
                        shared_replay = replay_controller.replay_quote_path(
                            quotes=replay_quotes,
                            side=side,
                            horizon_s=horizon,
                            target_price=target_price,
                            stop_price=stop_price,
                            pip_size=max(float(spreads[index]), 1e-12),
                            slippage_price=slippage_price,
                            commission_usd=commission_round_trip_usd,
                            usd_per_price_unit=float(
                                (usd_per_price_unit_by_symbol or {}).get(str(symbol).upper(), 1.0)
                            ),
                        )
                        if shared_replay.get("status") != "REPLAYED":
                            continue
                        captured = float(shared_replay["captured_exit_net_pnl"])
                        captured_reason = str(shared_replay["captured_exit_reason"])
                        if captured_reason == "harvest":
                            matching = [
                                offset for offset, action in enumerate(shared_replay.get("actions") or [])
                                if action.get("action") == "HARVEST"
                            ]
                            captured_index = matching[0] if matching else None
                    harvest = float(signed[int(harvestable[0])]) if len(harvestable) else terminal
                    if target_mode == "captured_exit_replay":
                        harvest = captured
                        time_to_profit = (
                            float(
                                (
                                    future_times.iloc[captured_index]
                                    - features.iloc[index]["time"]
                                ).total_seconds()
                            )
                            if captured_reason == "harvest" and captured_index is not None
                            else None
                        )
                        terminal = float(shared_replay["terminal_net_pnl"])
                        mfe = float(shared_replay["mfe_net_pnl"])
                        mae = float(shared_replay["mae_net_pnl"])
                        time_to_profit = shared_replay.get("time_to_green_s")
                    row = features.iloc[index].to_dict()
                    target = (
                        int(len(harvestable) > 0)
                        if target_mode == "fast_harvest"
                        else int(mfe > 0.0)
                        if target_mode == "mfe_first"
                        else int(captured > 0.0)
                        if target_mode == "captured_exit_replay"
                        else int(terminal > 0.0)
                    )
                    row.update(
                        {
                            "time": features.iloc[index]["time"],
                            "symbol": str(symbol).upper(),
                            "mechanism": mechanism,
                            "label_provenance": provenance,
                            "evidence_provenance": provenance,
                            "label_target": (
                                "captured_exit_net_pnl > 0"
                                if target_mode == "captured_exit_replay"
                                else f"{target_mode}_auxiliary"
                            ),
                            "label_identity": "|".join(
                                (str(symbol).upper(), side, mechanism, str(int(horizon)))
                            ),
                            "side": side,
                            "side_buy": 1.0 if side == "buy" else 0.0,
                            "entry_price": float(ask[index] if side == "buy" else bid[index]),
                            "entry_bid": float(bid[index]),
                            "entry_ask": float(ask[index]),
                            "horizon_s": float(horizon),
                            **mechanism_features(mechanism),
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
                            "captured_exit_net_pnl": captured,
                            "captured_exit_return": captured / float(mid[index]) if mid[index] > 0 else np.nan,
                            "captured_exit_reason": captured_reason,
                            "captured_exit_action": (
                                shared_replay.get("captured_exit_action")
                                if shared_replay is not None else None
                            ),
                            "captured_net_win": bool(captured > 0.0),
                            "captured_win_label": (
                                int(captured > 0.0)
                                if target_mode == "captured_exit_replay" else None
                            ),
                            "net_pnl": (
                                captured if target_mode == "captured_exit_replay" else None
                            ),
                            "assumed_slippage_bps": slippage_bps,
                            "assumed_commission_round_trip_usd": commission_round_trip_usd,
                            "spread_price": float(ask[index] - bid[index]),
                            "entry_spread_price": float(ask[index] - bid[index]),
                            "commission_usd": float(commission_round_trip_usd),
                            "commission": float(commission_round_trip_usd),
                            "slippage_price": float(slippage_price),
                            "slippage": float(slippage_price),
                            "slippage_bps": float(slippage_bps),
                            "expected_initial_friction_price": (
                                shared_replay.get("entry_spread_price")
                                if shared_replay is not None else None
                            ),
                            "mfe": mfe,
                            "mae": mae,
                            "maximum_favorable_executable_move": mfe,
                            "maximum_adverse_executable_move": mae,
                            "time_to_peak_s": (
                                shared_replay.get("time_to_peak_s")
                                if shared_replay is not None
                                else (future_times.iloc[int(np.argmax(signed))] - features.iloc[index]["time"]).total_seconds()
                            ),
                            "time_to_first_net_green_s": time_to_profit,
                            "time_to_first_net_green": time_to_profit,
                            "never_green": bool(
                                shared_replay.get("never_green")
                                if shared_replay is not None
                                else not len(profitable)
                            ),
                            "green_then_loser": bool(
                                shared_replay.get("green_then_loser")
                                if shared_replay is not None
                                else bool(len(profitable) and captured <= 0.0)
                            ),
                            "capture_ratio": (
                                shared_replay.get("capture_ratio")
                                if shared_replay is not None else None
                            ),
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
        "time", "symbol", "side", "mechanism", "label_provenance",
        "evidence_provenance", "label_target", "label_identity",
        "target", "terminal_net_pnl",
        "terminal_return", "mfe", "mae", "tail_loss",
        "harvest_return", "time_to_profit_s", "time_to_failure_s",
        "captured_exit_net_pnl", "captured_exit_return", "captured_exit_reason",
        "captured_exit_action",
        "captured_net_win", "never_green", "green_then_loser", "capture_ratio",
        "maximum_favorable_executable_move", "maximum_adverse_executable_move",
        "time_to_peak_s",
        "net_pnl", "captured_win_label", "spread_price", "commission_usd",
        "slippage_price", "slippage_bps", "time_to_first_net_green_s",
        "assumed_slippage_bps",
    }
    columns = [column for column in frame.columns if column not in excluded]
    result = frame.loc[:, columns].copy()
    result["profit_barrier_first"] = frame["target"].astype(int)
    return result


def captured_win_calibration_metrics(
    predicted_probability: Sequence[float],
    captured_net_pnl: Sequence[float],
    *,
    bins: int = 10,
) -> dict[str, Any]:
    """Measure calibration against the executable captured-net winner label.

    A positive MFE, temporary green mark, or terminal mark is deliberately not
    used here.  The binary target is the result of the sequential live-exit
    replay after executable spread, slippage, and commission.
    """
    probabilities = np.asarray(tuple(predicted_probability), dtype=float)
    net_pnl = np.asarray(tuple(captured_net_pnl), dtype=float)
    if len(probabilities) != len(net_pnl):
        raise ValueError("predicted_probability and captured_net_pnl must have equal length")
    if not np.isfinite(probabilities).all() or (
        (probabilities < 0.0) | (probabilities > 1.0)
    ).any():
        raise ValueError("predicted_probability must be finite and between 0 and 1")
    if not np.isfinite(net_pnl).all():
        raise ValueError("captured_net_pnl must be finite")
    actual = (net_pnl > 0.0).astype(float)
    calibration_bins: list[dict[str, Any]] = []
    calibration_ece = 0.0
    bin_count = max(1, int(bins))
    for index in range(bin_count):
        lower = float(index / bin_count)
        upper = float((index + 1) / bin_count)
        mask = (probabilities >= lower) & (
            probabilities <= upper if index == bin_count - 1 else probabilities < upper
        )
        if not mask.any():
            continue
        predicted_mean = float(probabilities[mask].mean())
        actual_mean = float(actual[mask].mean())
        calibration_ece += float(mask.mean()) * abs(predicted_mean - actual_mean)
        calibration_bins.append({
            "lower": lower,
            "upper": min(1.0, upper),
            "n": int(mask.sum()),
            "predicted_mean": predicted_mean,
            "actual_rate": actual_mean,
        })
    return {
        "target": "captured_exit_net_pnl > 0",
        "n": int(len(actual)),
        "captured_win_count": int(actual.sum()),
        "captured_win_rate": float(actual.mean()) if len(actual) else None,
        "brier_score": float(np.mean(np.square(probabilities - actual))) if len(actual) else None,
        "calibration_ece": float(calibration_ece) if len(actual) else None,
        "calibration_bins": calibration_bins,
    }


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
    captured = pd.to_numeric(
        frame.get("captured_exit_return", frame["terminal_return"]), errors="coerce"
    ).to_numpy(dtype=float)
    if "net_pnl" in frame:
        captured_source = frame["net_pnl"]
    elif "captured_exit_net_pnl" in frame:
        captured_source = frame["captured_exit_net_pnl"]
    elif "terminal_net_pnl" in frame:
        captured_source = frame["terminal_net_pnl"]
    else:
        captured_source = frame["terminal_return"]
    captured_net = pd.to_numeric(captured_source, errors="coerce").to_numpy(dtype=float)
    if len(captured_net) != len(frame) or not np.isfinite(captured_net).all():
        fallback_source = (
            frame["captured_exit_net_pnl"]
            if "captured_exit_net_pnl" in frame
            else frame["terminal_net_pnl"]
            if "terminal_net_pnl" in frame
            else frame["terminal_return"]
        )
        captured_net = pd.to_numeric(fallback_source, errors="coerce").to_numpy(dtype=float)
    captured_calibration = captured_win_calibration_metrics(
        probability,
        captured_net,
    )
    selected_captured = captured[decision]
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
    captured_lcb95 = None
    finite_selected_captured = selected_captured[np.isfinite(selected_captured)]
    if len(finite_selected_captured) >= 2:
        captured_lcb95 = float(
            finite_selected_captured.mean()
            - 1.96 * finite_selected_captured.std(ddof=1) / np.sqrt(len(finite_selected_captured))
        )
    captured_wins = finite_selected_captured[finite_selected_captured > 0.0]
    captured_losses = finite_selected_captured[finite_selected_captured < 0.0]
    captured_profit_factor = (
        float(captured_wins.sum() / abs(captured_losses.sum()))
        if len(captured_losses) and len(captured_wins) else None
    )
    p95_loss = float(np.quantile(captured_losses, 0.05)) if len(captured_losses) else None
    p99_loss = float(np.quantile(captured_losses, 0.01)) if len(captured_losses) else None
    captured_win_count = int(len(captured_wins))
    captured_observation_count = int(len(finite_selected_captured))
    captured_win_lcb95 = wilson_lower_bound(
        wins=captured_win_count, n=captured_observation_count
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
        if column not in selected_frame.columns:
            return None
        values = pd.to_numeric(selected_frame[column], errors="coerce").dropna()
        return float(values.median()) if len(values) else None

    def selected_rate(column: str) -> float | None:
        if column not in selected_frame.columns or selected_frame.empty:
            return None
        return float(selected_frame[column].astype(bool).mean())

    def selected_numeric_mean(column: str) -> float | None:
        if column not in selected_frame.columns or selected_frame.empty:
            return None
        values = pd.to_numeric(selected_frame[column], errors="coerce").dropna()
        return float(values.mean()) if len(values) else None

    time_to_green = pd.to_numeric(
        selected_frame.get("time_to_profit_s", pd.Series(dtype=float)), errors="coerce"
    ).dropna()

    return {
        "n": int(len(frame)),
        "selected": int(decision.sum()),
        "positive_rate": float(actual.mean()) if len(actual) else None,
        "brier": float(np.mean(np.square(probability - actual))) if len(actual) else None,
        "calibration_ece": float(calibration_ece) if len(actual) else None,
        "captured_win_brier": captured_calibration["brier_score"],
        "captured_win_calibration_ece": captured_calibration["calibration_ece"],
        "captured_win_calibration": captured_calibration,
        "calibration_bins": calibration_bins,
        "confusion_matrix": confusion,
        "expectancy_lcb95_return": expectancy_lcb95,
        "mfe_lcb95_return": mfe_lcb95,
        "harvest_lcb95_return": harvest_lcb95,
        "captured_exit_lcb95_return": captured_lcb95,
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
        "mean_captured_exit_return": (
            float(finite_selected_captured.mean())
            if len(finite_selected_captured) else None
        ),
        "captured_exit_profit_factor": captured_profit_factor,
        "captured_exit_win_count": captured_win_count,
        "captured_exit_win_rate": (
            float(captured_win_count / captured_observation_count)
            if captured_observation_count else None
        ),
        "captured_exit_win_lcb95": captured_win_lcb95,
        "captured_exit_loss_count": int(len(captured_losses)),
        "p95_loss_return": p95_loss,
        "p99_loss_return": p99_loss,
        "expected_mfe": selected_mean("mfe"),
        "expected_mae": selected_mean("mae"),
        "median_time_to_green_s": selected_median("time_to_profit_s"),
        "median_time_to_peak_s": selected_median("time_to_peak_s"),
        "median_time_to_failure_s": selected_median("time_to_failure_s"),
        "never_green_rate": selected_rate("never_green"),
        "fast_green_rate": (
            float((time_to_green <= FAST_GREEN_CEILING_S).mean())
            if len(time_to_green) else None
        ),
        "green_then_loser_rate": selected_rate("green_then_loser"),
        "capture_ratio": selected_numeric_mean("capture_ratio"),
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
    if target == "captured_exit_replay":
        mean_key = "mean_captured_exit_return"
        lcb_key = "captured_exit_lcb95_return"
    else:
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
    if target != "captured_exit_replay":
        if target in {"mfe_first", "fast_harvest"}:
            return "SHADOW_ONLY_AUXILIARY_TARGET", f"{target}_auxiliary_only"
        if target == "terminal_profit":
            return "SHADOW_ONLY_NO_POSITIVE_OOS", "execution_requires_captured_exit_replay"
        return "SHADOW_ONLY_NO_POSITIVE_OOS", "execution_requires_supported_harvest_labels"
    mean_key = "mean_captured_exit_return"
    lcb_key = "captured_exit_lcb95_return"

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

    def enough_losses(metrics: Mapping[str, Any] | None) -> bool:
        if not isinstance(metrics, Mapping):
            return False
        try:
            return int(metrics.get("captured_exit_loss_count") or 0) >= MIN_CAPTURED_EXIT_LOSSES
        except (TypeError, ValueError):
            return False

    def meets_win_rate_target(metrics: Mapping[str, Any] | None) -> bool:
        if not isinstance(metrics, Mapping):
            return False
        try:
            return float(metrics.get("captured_exit_win_lcb95")) >= MIN_CAPTURED_EXIT_WIN_LCB95
        except (TypeError, ValueError):
            return False

    if not positive(test_metrics) or not positive(sealed_metrics):
        return "SHADOW_ONLY_NO_POSITIVE_OOS", (
            "test_or_sealed_captured_exit_oos_not_positive"
        )
    if not positive_lcb(test_metrics) or not positive_lcb(sealed_metrics):
        return "SHADOW_ONLY_NO_POSITIVE_OOS", (
            "captured_exit_oos_lcb95_not_positive"
        )
    if not enough_losses(test_metrics) or not enough_losses(sealed_metrics):
        return "SHADOW_ONLY_NO_POSITIVE_OOS", (
            "insufficient_captured_exit_loss_evidence"
        )
    if not meets_win_rate_target(test_metrics) or not meets_win_rate_target(sealed_metrics):
        return "SHADOW_ONLY_NO_POSITIVE_OOS", (
            "captured_exit_win_rate_lcb95_below_target"
        )
    horizon_metrics = sealed_by_horizon.get(str(int(decision_horizon_s)))
    if not positive(horizon_metrics):
        return "SHADOW_ONLY_NO_POSITIVE_OOS", (
            "decision_horizon_captured_exit_oos_not_positive"
        )
    if not positive_lcb(horizon_metrics):
        return "SHADOW_ONLY_NO_POSITIVE_OOS", (
            "captured_exit_oos_lcb95_not_positive"
        )
    if not enough_losses(horizon_metrics):
        return "SHADOW_ONLY_NO_POSITIVE_OOS", (
            "insufficient_captured_exit_loss_evidence"
        )
    if not meets_win_rate_target(horizon_metrics):
        return "SHADOW_ONLY_NO_POSITIVE_OOS", (
            "captured_exit_win_rate_lcb95_below_target"
        )
    return "EXECUTION_CANDIDATE", (
        "positive_test_sealed_decision_horizon_captured_exit_oos"
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
    if target == "captured_exit_replay":
        mean_key = "mean_captured_exit_return"
        lcb_key = "captured_exit_lcb95_return"
    else:
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
    if target not in {"terminal_profit", "mfe_first", "fast_harvest", "captured_exit_replay"}:
        return []
    if target != "captured_exit_replay":
        return []
    mean_key = "mean_captured_exit_return"
    lcb_key = "captured_exit_lcb95_return"

    def positive(metrics: Mapping[str, Any] | None) -> bool:
        if not isinstance(metrics, Mapping):
            return False
        try:
            return (
                int(metrics.get("selected") or 0) >= int(min_selected)
                and int(metrics.get("captured_exit_loss_count") or 0) >= MIN_CAPTURED_EXIT_LOSSES
                and float(metrics.get("captured_exit_win_lcb95")) >= MIN_CAPTURED_EXIT_WIN_LCB95
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
    target_definition: str = "captured_exit_replay",
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
        "mean_captured_exit_return"
        if str(target_definition).strip().lower() == "captured_exit_replay"
        else "mean_harvest_return"
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
    provenance_values = sorted(
        {
            str(value).strip().lower()
            for value in frame.get("label_provenance", pd.Series(["unknown"])).dropna()
            if str(value).strip()
        }
    )
    if (
        execution_status == "EXECUTION_CANDIDATE"
        and (
            str(target_definition).strip().lower() != "captured_exit_replay"
            or not provenance_values
            or not all(is_executable_capture_provenance(value) for value in provenance_values)
        )
    ):
        execution_status = "SHADOW_ONLY_UNMEASURED_LABEL"
        execution_status_reason = "execution_requires_measured_quote_replay_provenance"
    authorized_symbols = _authorized_symbols(
        test_by_symbol=test_by_symbol,
        sealed_by_symbol_horizon=sealed_by_symbol_horizon,
        decision_horizon_s=selected_decision_horizon,
        target_definition=target_definition,
    )
    if authorized_symbols and execution_status == "EXECUTION_CANDIDATE":
        execution_status = "EXECUTION_CANDIDATE"
        execution_status_reason = "positive_exact_symbol_test_sealed_horizon_oos"
    elif execution_status == "EXECUTION_CANDIDATE":
        execution_status = "SHADOW_ONLY_NO_POSITIVE_OOS"
        execution_status_reason = "no_symbol_scope_positive_oos"

    def identity_metrics(part: pd.DataFrame) -> dict[str, dict[str, Any]]:
        if part.empty:
            return {}
        working = part.copy()
        if "mechanism" not in working.columns:
            working["mechanism"] = "legacy_unknown"
        groups = working.groupby(
            ["symbol", "side", "mechanism", "horizon_s"],
            sort=True,
            dropna=False,
        )
        result: dict[str, dict[str, Any]] = {}
        for (symbol, side, mechanism, horizon), subset in groups:
            scope_threshold = threshold_by_symbol_horizon.get(
                str(symbol).upper(), {}
            ).get(str(int(float(horizon))), threshold)
            key = "|".join((
                str(symbol).upper(),
                str(side).lower(),
                str(mechanism).strip().lower(),
                str(int(float(horizon))),
            ))
            result[key] = evaluate(
                subset,
                threshold=float(scope_threshold),
                max_uncertainty=uncertainty_limit,
            )
        return result

    test_by_identity = identity_metrics(slices.test)
    sealed_by_identity = identity_metrics(slices.sealed)

    slippage_values = sorted(
        {
            float(value)
            for value in pd.to_numeric(
                frame.get("assumed_slippage_bps", pd.Series([0.0])), errors="coerce"
            ).dropna()
        }
    )
    if len(slippage_values) > 1:
        raise ValueError("training frame mixes multiple slippage assumptions")
    assumed_slippage_bps = slippage_values[0] if slippage_values else 0.0
    commission_values = sorted(
        {
            float(value)
            for value in pd.to_numeric(
                frame.get("assumed_commission_round_trip_usd", pd.Series([0.0])),
                errors="coerce",
            ).dropna()
        }
    )
    if len(commission_values) > 1:
        raise ValueError("training frame mixes multiple commission assumptions")
    assumed_commission_round_trip_usd = commission_values[0] if commission_values else 0.0

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
            "mechanisms": sorted(
                {
                    str(value).strip().lower()
                    for value in frame.get("mechanism", pd.Series(["legacy_unknown"])).dropna()
                    if str(value).strip()
                }
            ),
            "label_provenance": provenance_values,
            "evidence_identity_fields": ["symbol", "side", "mechanism", "horizon_s"],
            "test_by_identity": test_by_identity,
            "sealed_by_identity": sealed_by_identity,
            "threshold": float(threshold),
            "threshold_by_symbol_horizon": threshold_by_symbol_horizon,
            "min_model_agreement": 0.6,
            "max_uncertainty": uncertainty_limit,
            "oos": {
                "validation": validation_metrics,
                "validation_by_horizon": validation_by_horizon,
                "test": test_metrics,
                "test_by_symbol": test_by_symbol,
                "test_by_identity": test_by_identity,
                "sealed": sealed_metrics,
                "sealed_by_horizon": sealed_by_horizon,
                "sealed_by_symbol_horizon": sealed_by_symbol_horizon,
                "sealed_by_identity": sealed_by_identity,
            },
            "trained_at": datetime.now(timezone.utc).isoformat(),
            "cost_evidence": (
                "executable_bid_ask_spread_in_labels; "
                f"configured_round_trip_slippage_bps={assumed_slippage_bps}; "
                f"commission_round_trip_usd={assumed_commission_round_trip_usd}"
            ),
            "assumed_slippage_bps": assumed_slippage_bps,
            "assumed_commission_round_trip_usd": assumed_commission_round_trip_usd,
            "symbols": sorted(frame["symbol"].astype(str).str.upper().unique().tolist()),
            "authorized_symbols": authorized_symbols,
            "model_count": len(pipeline.models),
            "promotion_policy": {
                "min_captured_exit_losses": MIN_CAPTURED_EXIT_LOSSES,
                "min_captured_exit_win_lcb95": MIN_CAPTURED_EXIT_WIN_LCB95,
                "requires_positive_test_and_sealed_lcb95": True,
                "requires_captured_win_rate_lcb95": True,
            },
            "exit_policy": {
                "name": "captured_exit_replay_v1",
                "entry": "buy=ASK,sell=BID",
                "capture": "first_executable_move_at_or_above_two_observed_spreads",
                "abort": "first_executable_move_at_or_below_three_observed_spreads_loss",
                "timeout": "last_future_quote_at_horizon",
                "costs": (
                    "observed_bid_ask_spread_plus_configured_round_trip_slippage; "
                    f"commission_round_trip_usd={assumed_commission_round_trip_usd}"
                ),
            },
            "runtime_proof": {
                "SHORT_HORIZON_MODEL_STATUS": execution_status,
                "EXECUTION_STATUS": execution_status,
                "TARGET_DEFINITION": str(target_definition),
                "PREDICTION_TARGET": (
                    "captured_exit_net_pnl > 0"
                    if str(target_definition).strip().lower() == "captured_exit_replay"
                    else str(target_definition)
                ),
                "LABEL_PROVENANCE": provenance_values,
                "EVIDENCE_IDENTITY": ["symbol", "side", "mechanism", "horizon_s"],
                "AUTHORIZED_SYMBOLS": authorized_symbols,
                "MODEL_COUNT": len(pipeline.models),
                "DATASET_HASH": _hash_frame(frame),
                "VALIDATION_HASH": _hash_frame(slices.validation),
                "DECISION_HORIZON": int(selected_decision_horizon),
                "OOS_TEST_N": test_metrics.get("n"),
                "OOS_SEALED_N": sealed_metrics.get("n"),
                "OOS_PRECISION": sealed_metrics.get("precision"),
                "OOS_CAPTURED_EXPECTANCY": sealed_metrics.get("mean_captured_exit_return"),
                "OOS_CAPTURED_PF": sealed_metrics.get("captured_exit_profit_factor"),
                "P_CAPTURED_WIN": sealed_metrics.get("captured_exit_win_rate"),
                "P_CAPTURED_WIN_LCB95": sealed_metrics.get("captured_exit_win_lcb95"),
                "P_CAPTURED_WIN_TARGET": "captured_exit_net_pnl > 0",
                "TARGET_CAPTURE_WIN_RATE_LCB95": MIN_CAPTURED_EXIT_WIN_LCB95,
                "OOS_CAPTURED_EV_LCB95": sealed_metrics.get("captured_exit_lcb95_return"),
                "P95_LOSS": sealed_metrics.get("p95_loss_return"),
                "P99_LOSS": sealed_metrics.get("p99_loss_return"),
                "CALIBRATION_ECE": sealed_metrics.get("calibration_ece"),
                "CAPTURED_WIN_CALIBRATION_ECE": sealed_metrics.get(
                    "captured_win_calibration_ece"
                ),
                "ABSTAIN_RATE": sealed_metrics.get("abstain_rate"),
                "SEALED_OOS_TRADES": sealed_metrics.get("selected"),
                "SEALED_OOS_WINS": sealed_metrics.get("captured_exit_win_count"),
                "SEALED_OOS_LOSSES": sealed_metrics.get("captured_exit_loss_count"),
                "SEALED_OOS_WR": sealed_metrics.get("captured_exit_win_rate"),
                "SEALED_OOS_WR_LCB95": sealed_metrics.get("captured_exit_win_lcb95"),
                "SEALED_OOS_EV_LCB95": sealed_metrics.get("captured_exit_lcb95_return"),
                "NEVER_GREEN_RATE": sealed_metrics.get("never_green_rate"),
                "FAST_GREEN_RATE": sealed_metrics.get("fast_green_rate"),
                "GREEN_THEN_LOSER_RATE": sealed_metrics.get("green_then_loser_rate"),
                "CAPTURE_RATIO": sealed_metrics.get("capture_ratio"),
                "TARGET_LOSS_RATE_5_PERCENT_STATUS": (
                    "SUPPORTED_BY_SEALED_OOS"
                    if execution_status == "EXECUTION_CANDIDATE"
                    else "TARGET_95_WR_NOT_PROVEN"
                ),
            },
        }
    )
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")
    return metadata
