"""Point-in-time short-horizon research labels and quote features.

This module is research-only.  It consumes completed quote/tick history and
never places orders.  Labels are built only from observations strictly after
the entry timestamp; features are built only from observations at or before
the requested timestamp.
"""
from __future__ import annotations

from collections.abc import Sequence
import hashlib
from typing import Any

import numpy as np
import pandas as pd

from aegis.research.dataset import assert_no_lookahead


DEFAULT_HORIZONS_S = (3, 5, 8, 10, 15, 20, 30, 45)
SYMBOL_FEATURE_BUCKETS = 32
SHORT_HORIZON_LABEL_COLUMNS = (
    "entry_time",
    "side",
    "horizon_s",
    "entry_price",
    "terminal_net_pnl",
    "mfe",
    "mae",
    "net_profitable_after_cost",
    "adverse_move",
    "tail_loss",
    "time_to_profit_s",
    "time_to_failure_s",
)


def symbol_features(symbol: str | None) -> dict[str, float]:
    """Return a stable one-hot identity encoding for a market symbol.

    The digest avoids Python's process-randomized ``hash()`` so research and
    runtime rows use the same representation across processes.  Empty symbols
    remain all-zero and therefore cannot create synthetic identity evidence.
    """
    features = {f"symbol_bucket_{index:02d}": 0.0 for index in range(SYMBOL_FEATURE_BUCKETS)}
    normalized = str(symbol or "").strip().upper()
    if not normalized:
        return features
    bucket = int.from_bytes(hashlib.sha256(normalized.encode("utf-8")).digest()[:4], "big")
    features[f"symbol_bucket_{bucket % SYMBOL_FEATURE_BUCKETS:02d}"] = 1.0
    return features


def session_features(hour_utc: int | float) -> dict[str, float]:
    """Return a numeric one-hot encoding of the point-in-time UTC session."""
    session = _session_name(int(float(hour_utc)) % 24)
    return {
        "session_asia_or_off": 1.0 if session == "asia_or_off" else 0.0,
        "session_london": 1.0 if session == "london" else 0.0,
        "session_new_york": 1.0 if session == "new_york" else 0.0,
        "session_overlap": 1.0 if session == "overlap" else 0.0,
    }


def _normalise_quotes(quotes: pd.DataFrame) -> pd.DataFrame:
    if quotes is None or quotes.empty:
        raise ValueError("quotes must not be empty")
    out = quotes.copy()
    time_col = "time" if "time" in out.columns else "timestamp" if "timestamp" in out.columns else None
    if time_col is None:
        raise ValueError("quotes require a time or timestamp column")
    out["_time"] = pd.to_datetime(out[time_col], utc=True, errors="coerce")
    if out["_time"].isna().any():
        raise ValueError("quotes contain invalid timestamps")
    if "mid" in out.columns:
        mid = pd.to_numeric(out["mid"], errors="coerce")
    elif "price" in out.columns:
        mid = pd.to_numeric(out["price"], errors="coerce")
    else:
        mid = pd.Series(np.nan, index=out.index, dtype=float)
    if "bid" not in out.columns and "ask" not in out.columns and mid.notna().any():
        out["bid"] = mid
        out["ask"] = mid
    elif "bid" not in out.columns or "ask" not in out.columns:
        raise ValueError("quotes require bid and ask, or a mid/price column")
    out["_bid"] = pd.to_numeric(out["bid"], errors="coerce")
    out["_ask"] = pd.to_numeric(out["ask"], errors="coerce")
    out["_mid"] = (out["_bid"] + out["_ask"]) / 2.0
    out["_spread"] = out["_ask"] - out["_bid"]
    if out[["_bid", "_ask", "_mid", "_spread"]].isna().any().any():
        raise ValueError("quotes contain invalid bid/ask values")
    if (out["_spread"] < 0).any():
        raise ValueError("quotes contain negative spreads")
    return out.sort_values("_time", kind="stable").reset_index(drop=True)


def _entry_price(row: pd.Series, side: str) -> float:
    return float(row["_ask"] if side == "buy" else row["_bid"])


def build_short_horizon_labels(
    quotes: pd.DataFrame,
    *,
    sides: Sequence[str] = ("buy", "sell"),
    horizons: Sequence[int] = DEFAULT_HORIZONS_S,
    cost: float = 0.0,
    tail_loss_threshold: float | None = None,
    failure_threshold: float | None = None,
) -> pd.DataFrame:
    """Build realized, cost-aware labels from a completed quote history.

    Each row is an entry-side/horizon observation.  A row is emitted only when
    the history contains at least one quote at or beyond the horizon endpoint.
    ``mfe`` and ``mae`` are signed price moves from the executable entry price
    using the executable opposite-side quote for the future observations.
    """
    frame = _normalise_quotes(quotes)
    normal_sides = tuple(str(side).lower() for side in sides)
    if any(side not in {"buy", "sell"} for side in normal_sides):
        raise ValueError("sides must contain only buy or sell")
    horizon_values = tuple(int(h) for h in horizons)
    if any(h <= 0 for h in horizon_values):
        raise ValueError("horizons must be positive seconds")
    cost_value = float(cost)
    if cost_value < 0:
        raise ValueError("cost must be non-negative")
    rows: list[dict[str, Any]] = []
    last_time = frame["_time"].iloc[-1]
    for idx, entry in frame.iterrows():
        entry_time = entry["_time"]
        for horizon in horizon_values:
            end_time = entry_time + pd.Timedelta(seconds=horizon)
            if last_time < end_time:
                continue
            future = frame[(frame["_time"] > entry_time) & (frame["_time"] <= end_time)]
            if future.empty:
                continue
            for side in normal_sides:
                entry_price = _entry_price(entry, side)
                if side == "buy":
                    signed = future["_bid"] - entry_price
                else:
                    signed = entry_price - future["_ask"]
                signed_values = signed.to_numpy(dtype=float)
                mfe = float(np.max(signed_values))
                mae = float(np.min(signed_values))
                terminal = float(signed_values[-1])
                profitable = signed_values > cost_value
                failure_limit = failure_threshold
                profit_time = None
                failure_time = None
                if profitable.any():
                    first = int(np.flatnonzero(profitable)[0])
                    profit_time = float((future["_time"].iloc[first] - entry_time).total_seconds())
                if failure_limit is not None and float(failure_limit) > 0:
                    failed = signed_values <= -abs(float(failure_limit))
                    if failed.any():
                        first = int(np.flatnonzero(failed)[0])
                        failure_time = float((future["_time"].iloc[first] - entry_time).total_seconds())
                rows.append(
                    {
                        "entry_time": entry_time,
                        "side": side,
                        "horizon_s": horizon,
                        "entry_price": entry_price,
                        "terminal_net_pnl": terminal - cost_value,
                        "mfe": mfe,
                        "mae": mae,
                        "net_profitable_after_cost": bool(mfe > cost_value),
                        "adverse_move": bool(mae < 0.0),
                        "tail_loss": bool(
                            tail_loss_threshold is not None
                            and mae <= -abs(float(tail_loss_threshold))
                        ),
                        "time_to_profit_s": profit_time,
                        "time_to_failure_s": failure_time,
                    }
                )
    return pd.DataFrame(rows, columns=SHORT_HORIZON_LABEL_COLUMNS)


def evaluate_short_horizon_predictions(
    labels: pd.DataFrame,
    predicted_probability: Sequence[float],
    *,
    predicted_net_pnl: Sequence[float] | None = None,
    threshold: float = 0.5,
) -> dict[str, Any]:
    """Evaluate caller-supplied predictions against realized labels.

    This function does not train, split, or select a model.  The caller must
    provide predictions from its chosen replay/OOS protocol; the report keeps
    that boundary explicit so in-sample scores cannot be mistaken for OOS
    evidence.
    """
    if labels is None or "net_profitable_after_cost" not in labels.columns:
        raise ValueError("labels require net_profitable_after_cost")
    probabilities = np.asarray(tuple(predicted_probability), dtype=float)
    if len(probabilities) != len(labels):
        raise ValueError("predicted_probability length must match labels")
    if not np.isfinite(probabilities).all() or ((probabilities < 0) | (probabilities > 1)).any():
        raise ValueError("predicted_probability must be finite and between 0 and 1")
    if not 0 < float(threshold) < 1:
        raise ValueError("threshold must be between 0 and 1")
    actual_series = labels["net_profitable_after_cost"].astype(bool)
    actual = actual_series.to_numpy(dtype=float)
    predicted = probabilities >= float(threshold)
    report = _prediction_metrics(actual, probabilities, predicted, threshold)
    if predicted_net_pnl is not None:
        expected = np.asarray(tuple(predicted_net_pnl), dtype=float)
        if len(expected) != len(labels) or not np.isfinite(expected).all():
            raise ValueError("predicted_net_pnl must match labels and be finite")
        realized = labels["terminal_net_pnl"].to_numpy(dtype=float)
        report["net_pnl_mae"] = float(np.mean(np.abs(expected - realized)))
        report["net_pnl_rmse"] = float(np.sqrt(np.mean(np.square(expected - realized))))
    by_horizon: dict[str, Any] = {}
    probability_series = pd.Series(probabilities, index=labels.index)
    for horizon, group in labels.groupby("horizon_s", sort=True):
        group_actual = actual_series.loc[group.index].to_numpy(dtype=float)
        group_prob = probability_series.loc[group.index].to_numpy(dtype=float)
        by_horizon[str(int(horizon))] = _prediction_metrics(
            group_actual, group_prob, group_prob >= float(threshold), threshold
        )
    report["by_horizon"] = by_horizon
    report["evaluation_scope"] = "caller_supplied_predictions"
    return report


def _prediction_metrics(
    actual: np.ndarray,
    probabilities: np.ndarray,
    predicted: np.ndarray,
    threshold: float,
) -> dict[str, Any]:
    n = int(len(actual))
    selected = int(predicted.sum())
    true_positive = int((predicted & (actual > 0.5)).sum())
    bins: list[dict[str, Any]] = []
    for low, high in ((0.0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.000001)):
        mask = (probabilities >= low) & (probabilities < high)
        if mask.any():
            bins.append(
                {
                    "lower": low,
                    "upper": min(high, 1.0),
                    "n": int(mask.sum()),
                    "predicted_mean": float(probabilities[mask].mean()),
                    "actual_rate": float(actual[mask].mean()),
                }
            )
    return {
        "n": n,
        "selected": selected,
        "threshold": float(threshold),
        "brier_score": float(np.mean(np.square(probabilities - actual))) if n else None,
        "precision": float(true_positive / selected) if selected else None,
        "actual_positive_rate": float(actual.mean()) if n else None,
        "predicted_probability_mean": float(probabilities.mean()) if n else None,
        "calibration_bins": bins,
    }


def _asof_mid(history: pd.DataFrame, cutoff: pd.Timestamp) -> float | None:
    prior = history[history["_time"] <= cutoff]
    if prior.empty:
        return None
    return float(prior["_mid"].iloc[-1])


def _return_since(history: pd.DataFrame, now: pd.Timestamp, seconds: int) -> float | None:
    current = _asof_mid(history, now)
    prior = _asof_mid(history, now - pd.Timedelta(seconds=seconds))
    if current is None or prior in (None, 0.0):
        return None
    return float(current / prior - 1.0)


def point_in_time_features(
    quotes: pd.DataFrame,
    *,
    at: Any,
    symbol: str | None = None,
) -> dict[str, Any]:
    """Return quote/microstructure features known at exactly ``at``.

    Future rows are deliberately discarded before every calculation.  Missing
    lookback history is represented by ``None`` rather than backfilled data.
    """
    frame = _normalise_quotes(quotes)
    target = pd.Timestamp(at)
    if target.tzinfo is None:
        target = target.tz_localize("UTC")
    else:
        target = target.tz_convert("UTC")
    history = frame[frame["_time"] <= target].copy()
    if history.empty or history["_time"].iloc[-1] != target:
        raise ValueError("at must be present in quotes")
    current = history.iloc[-1]
    mids = history["_mid"].to_numpy(dtype=float)
    spreads = history["_spread"].to_numpy(dtype=float)
    if len(mids) >= 2:
        dt = (history["_time"].iloc[-1] - history["_time"].iloc[-2]).total_seconds()
        velocity = float((mids[-1] - mids[-2]) / dt) if dt > 0 else None
    else:
        velocity = None
    acceleration = None
    if len(mids) >= 3:
        dt1 = (history["_time"].iloc[-2] - history["_time"].iloc[-3]).total_seconds()
        dt2 = (history["_time"].iloc[-1] - history["_time"].iloc[-2]).total_seconds()
        if dt1 > 0 and dt2 > 0:
            v1 = (mids[-2] - mids[-3]) / dt1
            v2 = (mids[-1] - mids[-2]) / dt2
            acceleration = float((v2 - v1) / dt2)
    returns = np.diff(mids) / mids[:-1] if len(mids) > 1 else np.array([], dtype=float)
    recent_returns = returns[-20:]
    recent_60 = history[history["_time"] > target - pd.Timedelta(seconds=60)]["_mid"].to_numpy(dtype=float)
    realized_returns = (
        np.diff(recent_60) / recent_60[:-1] if len(recent_60) > 1 else np.array([], dtype=float)
    )
    relative_spread = float(current["_spread"]) / max(abs(float(current["_mid"])), 1e-12)
    micro_volatility = float(np.std(recent_returns, ddof=0)) if len(recent_returns) else 0.0
    realized_vol_60s = float(np.sqrt(np.square(realized_returns).sum())) if len(realized_returns) else 0.0
    symbol_value = symbol
    if symbol_value is None and "symbol" in current.index:
        symbol_value = str(current["symbol"])
    # Keep the runtime feature on the same 0..1 percentile scale as the
    # artifact builder's rolling rank.  Returning 0..100 here silently fed a
    # different distribution to the cached models and could suppress every
    # live probability without raising a feature-schema error.
    spread_window = pd.Series(spreads[-60:])
    spread_percentile = float(spread_window.rank(pct=True).iloc[-1]) if len(spread_window) else 1.0
    features = {
        "symbol": symbol_value,
        "bid": float(current["_bid"]),
        "ask": float(current["_ask"]),
        "mid": float(current["_mid"]),
        "spread": float(current["_spread"]),
        "spread_percentile": spread_percentile,
        "spread_change": float(spreads[-1] - spreads[-2]) if len(spreads) >= 2 else None,
        "tick_velocity": velocity,
        "price_acceleration": acceleration,
        "return_5s": _return_since(history, target, 5),
        "return_10s": _return_since(history, target, 10),
        "return_15s": _return_since(history, target, 15),
        "return_30s": _return_since(history, target, 30),
        "return_60s": _return_since(history, target, 60),
        "micro_volatility": micro_volatility if len(recent_returns) else None,
        "realized_vol_60s": realized_vol_60s,
        "spread_to_micro_vol": relative_spread / max(micro_volatility, 1e-12),
        "spread_to_realized_vol": relative_spread / max(realized_vol_60s, 1e-12),
        "quote_age_s": 0.0,
        "hour_utc": float(target.hour),
        "dow_utc": float(target.dayofweek),
        "session": _session_name(target.hour),
    }
    features.update(symbol_features(symbol_value))
    features.update(session_features(target.hour))
    assert_no_lookahead(features)
    return features


def _session_name(hour_utc: int) -> str:
    if 7 <= hour_utc < 13:
        return "london"
    if 13 <= hour_utc < 21:
        return "new_york"
    if hour_utc >= 21 or hour_utc < 7:
        return "asia_or_off"
    return "overlap"
