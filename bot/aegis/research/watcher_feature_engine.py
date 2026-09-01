"""Point-in-time quote features for the read-only Watcher.

The Watcher receives sparse decision rows, while most of its perspectives are
written in terms of chart, volatility, and microstructure observations.  This
module derives those observations from the quote history that was available at
the decision timestamp.  It is deliberately independent of the production
trader and never consumes outcome fields.

Some concepts cannot be recovered from FX quotes alone.  In particular, tick
activity is labelled as a proxy rather than real traded volume, quote-price
profiles are not volume profiles, and news/validation/trade-management
evidence is left unavailable unless an upstream observer supplied it.
"""
from __future__ import annotations

from bisect import bisect_left
from datetime import datetime, timedelta, timezone
import math
import statistics
from typing import Any, Iterable, Mapping, Sequence


HORIZONS_S = (1, 2, 3, 5, 8, 10, 15, 20, 30, 60)

# These are labels or measurements that are only knowable after the decision.
# ``target`` is intentionally included because the shadow dataset uses it as a
# binary outcome label, not as a target price.
OUTCOME_KEYS = frozenset({
    "target", "label", "outcome", "captured_exit_net_pnl",
    "captured_exit_return", "captured_exit_reason", "terminal_net_pnl",
    "terminal_return", "mfe", "mae", "tail_loss", "immediate_adverse_move",
    "first_green", "never_green", "green_then_loser", "time_to_green_s",
    "time_to_profit_s", "time_to_failure_s", "time_to_mfe_s", "time_in_red_s",
    "winner_giveback", "first_profitable_executable_close",
    "first_profitable_close_net_pnl", "future_path_observed_n", "exit_policy",
    "exit_time_s", "time_to_peak", "captured_win_1s", "captured_win_2s",
    "captured_win_3s", "captured_win_5s", "captured_win_8s", "captured_win_10s",
    "captured_win_15s", "captured_win_20s", "captured_win_30s", "captured_win_45s",
    "exit_capturedexitreplay_net_pnl", "exit_firstmeaningfulgreen_net_pnl",
    "exit_firstmeaningfulgreen_reason", "exit_firstmeaningfulgreen_return",
    "exit_firstmeaningfulgreen_time_s", "exit_mfeprotection_return",
    "exit_noprogress3s_return",
})
_FUTURE_KEYS = frozenset({"future_quotes", "future_ticks", "future_path", "outcomes"})
_PAYLOAD_KEYS = frozenset({
    "quotes", "quote_history", "counterfactual_quotes", "outcome_quotes",
    "post_entry_quotes", "future_quotes", "future_ticks", "future_path",
})


def _finite(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def _timestamp(value: Any) -> float | None:
    numeric = _finite(value)
    if numeric is not None:
        if numeric > 10_000_000_000:
            numeric /= 1000.0
        return numeric
    if isinstance(value, datetime):
        item = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return item.timestamp()
    if isinstance(value, str):
        try:
            item = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
        if item.tzinfo is None:
            item = item.replace(tzinfo=timezone.utc)
        return item.timestamp()
    return None


def _present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (Mapping, list, tuple, set)):
        return bool(value)
    return True


def _clean_value(value: Any, *, row: bool = False) -> Any:
    if isinstance(value, Mapping):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            name = str(key)
            lower = name.lower()
            if lower in _OUTCOME_KEYS_FOR_NESTED or lower in _PAYLOAD_KEYS or lower.startswith("future_"):
                continue
            cleaned[name] = _clean_value(item, row=row)
        return cleaned
    if isinstance(value, list):
        return [_clean_value(item, row=row) for item in value]
    if isinstance(value, tuple):
        return tuple(_clean_value(item, row=row) for item in value)
    return value


_OUTCOME_KEYS_FOR_NESTED = OUTCOME_KEYS | frozenset({"stop", "take_profit"})


def _safe_copy(source: Mapping[str, Any] | None, *, row: bool = False) -> dict[str, Any]:
    if not isinstance(source, Mapping):
        return {}
    result: dict[str, Any] = {}
    for key, value in source.items():
        name = str(key)
        lower = name.lower()
        if lower in _FUTURE_KEYS or lower in _PAYLOAD_KEYS or lower.startswith("future_"):
            continue
        # A state supplied by the caller may contain explicitly supplied
        # geometry.  Raw rows, however, use target/label names for outcomes.
        if row and (lower in OUTCOME_KEYS or lower in {"target", "stop", "take_profit"}):
            continue
        if lower in OUTCOME_KEYS and not (not row and lower == "target"):
            continue
        if _present(value):
            result[name] = _clean_value(value, row=row)
    return result


def _quote(record: Mapping[str, Any]) -> dict[str, float] | None:
    if not isinstance(record, Mapping):
        return None
    bid = _finite(record.get("bid"))
    ask = _finite(record.get("ask"))
    mid = _finite(record.get("mid"))
    if mid is None and bid is not None and ask is not None:
        mid = (bid + ask) / 2.0
    if mid is None or mid <= 0:
        return None
    if bid is None:
        bid = mid
    if ask is None:
        ask = mid
    if bid <= 0 or ask <= 0 or ask < bid:
        return None
    item: dict[str, float] = {
        "mid": mid,
        "bid": bid,
        "ask": ask,
        "spread": max(0.0, ask - bid),
    }
    stamp = _timestamp(record.get("time", record.get("timestamp", record.get("time_utc", record.get("time_msc")))))
    if stamp is not None:
        item["time"] = stamp
    tick_volume = _finite(record.get("tick_volume", record.get("volume")))
    if tick_volume is not None:
        item["tick_volume"] = tick_volume
    for output_key, input_keys in (
        ("bid_size", ("bid_size", "bid_volume")),
        ("ask_size", ("ask_size", "ask_volume")),
        ("signed_order_flow", ("signed_order_flow", "order_flow")),
    ):
        for input_key in input_keys:
            value = _finite(record.get(input_key))
            if value is not None:
                item[output_key] = value
                break
    for input_key in ("transaction_price", "trade_price", "last"):
        transaction_price = _finite(record.get(input_key))
        if transaction_price is not None and transaction_price > 0:
            item["transaction_price"] = transaction_price
            break
    return item


def _point_in_time_quotes(
    history: Iterable[Mapping[str, Any]],
    current_record: Mapping[str, Any] | None,
    current_time: float | None,
) -> tuple[list[dict[str, float]], bool]:
    raw: list[tuple[int, dict[str, float]]] = []
    future_excluded = False
    for order, record in enumerate(history or ()):
        item = _quote(record)
        if item is None:
            continue
        stamp = item.get("time")
        if current_time is not None and stamp is None:
            # Without a timestamp we cannot prove that a historical record
            # preceded the decision, so it is not used for derived features.
            continue
        if current_time is not None and stamp is not None and stamp > current_time + 1e-9:
            future_excluded = True
            continue
        raw.append((order, item))
    if isinstance(current_record, Mapping):
        item = _quote(current_record)
        if item is not None:
            stamp = item.get("time")
            if current_time is None and stamp is not None:
                current_time = stamp
            if current_time is None or stamp is None or stamp <= current_time + 1e-9:
                raw.append((len(raw) + 1, item))
    raw.sort(key=lambda pair: (pair[1].get("time", float("inf")), pair[0]))
    deduped: list[dict[str, float]] = []
    for _, item in raw:
        stamp = item.get("time")
        if stamp is not None and deduped and deduped[-1].get("time") == stamp:
            # The current row is appended last and therefore wins for a
            # duplicate timestamp, without exposing later timestamps.
            deduped[-1] = item
        else:
            deduped.append(item)
    return deduped, future_excluded


def _window(points: Sequence[Mapping[str, float]], now: float, seconds: float) -> list[Mapping[str, float]]:
    return [item for item in points if now - item.get("time", now) <= seconds + 1e-9]


def _mean(values: Iterable[float]) -> float | None:
    items = [value for value in values if math.isfinite(value)]
    return statistics.fmean(items) if items else None


def _std(values: Iterable[float]) -> float | None:
    items = [value for value in values if math.isfinite(value)]
    if len(items) < 2:
        return 0.0 if items else None
    return statistics.pstdev(items)


def _changes(points: Sequence[Mapping[str, float]]) -> list[float]:
    return [b["mid"] - a["mid"] for a, b in zip(points, points[1:])]


def _return_at(points: Sequence[Mapping[str, float]], now: float, seconds: int, current: float) -> float | None:
    target = now - seconds
    candidates = [item for item in points if item.get("time", now) <= target + 1e-9]
    if not candidates:
        return None
    old = candidates[-1].get("mid")
    return current / old - 1.0 if old and old > 0 else None


def _linear_fit(points: Sequence[Mapping[str, float]]) -> tuple[float, float] | None:
    """Fit price on timestamp for a causal, descriptive drift model."""
    if len(points) < 2:
        return None
    origin = points[0].get("time")
    if origin is None:
        return None
    xs = [item.get("time", origin) - origin for item in points]
    ys = [item.get("mid") for item in points]
    if any(value is None or not math.isfinite(value) for value in (*xs, *ys)):
        return None
    mean_x = statistics.fmean(xs)
    mean_y = statistics.fmean(ys)
    denominator = sum((value - mean_x) ** 2 for value in xs)
    if denominator <= 0:
        return None
    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / denominator
    intercept = mean_y - slope * mean_x
    return intercept, slope


def _quote_walk_forward_forecast(
    points: Sequence[Mapping[str, float]],
    now: float,
    horizon_s: float,
    pip: float,
) -> dict[str, Any]:
    """Produce a simple forecast only after causal historical validation.

    Each validation prediction is fit on observations strictly before its
    anchor and scored against a later quote.  The live-as-of forecast is fit
    through the copied current quote; no post-decision observation is used.
    """
    if len(points) < 80 or horizon_s <= 0:
        return {}
    ordered = [
        item for item in points
        if item.get("time") is not None and item.get("mid") is not None
    ]
    if len(ordered) < 80:
        return {}
    window = min(120, len(ordered))
    minimum_train = min(40, window - 5)
    errors: list[float] = []
    for anchor_index in range(minimum_train, len(ordered) - 1):
        anchor_time = ordered[anchor_index].get("time")
        if anchor_time is None:
            continue
        target_time = anchor_time + horizon_s
        target_index = next(
            (index for index in range(anchor_index + 1, len(ordered))
             if ordered[index].get("time", float("inf")) >= target_time),
            None,
        )
        if target_index is None:
            break
        fit_points = ordered[max(0, anchor_index - window):anchor_index]
        fitted = _linear_fit(fit_points)
        if fitted is None:
            continue
        intercept, slope = fitted
        origin = fit_points[0]["time"]
        predicted = intercept + slope * (target_time - origin)
        actual = ordered[target_index]["mid"]
        if actual is not None and math.isfinite(predicted):
            errors.append(actual - predicted)
    if len(errors) < 20:
        return {}
    fitted = _linear_fit(ordered[-window:])
    if fitted is None:
        return {}
    intercept, slope = fitted
    origin = ordered[-window]["time"]
    forecast_price = intercept + slope * (now + horizon_s - origin)
    current_price = ordered[-1]["mid"]
    if not math.isfinite(forecast_price) or current_price is None or not math.isfinite(current_price):
        return {}
    mae = statistics.fmean(abs(error) for error in errors)
    rmse = math.sqrt(statistics.fmean(error * error for error in errors))
    uncertainty = max(mae, pip * 0.25)
    return {
        "forecast_price": forecast_price,
        "forecast_current_price": current_price,
        "forecast_horizon_s": int(horizon_s) if horizon_s.is_integer() else horizon_s,
        "forecast_model": "causal_linear_drift",
        "forecast_oos_status": "WALK_FORWARD",
        "forecast_uncertainty": uncertainty,
        "forecast_oos_n": len(errors),
        "forecast_mae": mae,
        "forecast_rmse": rmse,
        "forecast_training_n": window,
        "forecast_training_last_time": ordered[-1]["time"],
        "forecast_data_provenance": "causal_quote_walk_forward",
    }


def _roc_context(points: Sequence[Mapping[str, float]], now: float, current: float) -> dict[str, Any]:
    """Expose point-in-time quote returns as rate-of-change observations."""
    result: dict[str, Any] = {}
    for seconds in (1, 3, 5, 10, 20):
        value = _return_at(points, now, seconds, current)
        if value is not None:
            result[f"roc_{seconds}s"] = value
    if not result:
        return result
    latest = result.get("roc_5s")
    if latest is None:
        latest = next(iter(result.values()))
    result["roc_state"] = "positive" if latest > 0 else "negative" if latest < 0 else "flat"
    result["roc_direction"] = "up" if latest > 0 else "down" if latest < 0 else "flat"
    result["roc_observation_provenance"] = "point_in_time_quote_return_proxy"
    return result


def _parabolic_sar_context(values: Sequence[float]) -> dict[str, Any]:
    """Calculate a SAR trend on quote mids, explicitly not candle highs/lows."""
    if len(values) < 5:
        return {}
    rising = values[1] >= values[0]
    sar = values[0]
    extreme = values[0]
    acceleration = 0.02
    maximum = 0.20
    for index, current in enumerate(values[1:], 1):
        prior_sar = sar
        sar = prior_sar + acceleration * (extreme - prior_sar)
        if rising:
            if index >= 2:
                sar = min(sar, values[index - 1], values[index - 2])
            else:
                sar = min(sar, values[index - 1])
            if current < sar:
                rising = False
                sar = extreme
                extreme = current
                acceleration = 0.02
            elif current > extreme:
                extreme = current
                acceleration = min(maximum, acceleration + 0.02)
        else:
            if index >= 2:
                sar = max(sar, values[index - 1], values[index - 2])
            else:
                sar = max(sar, values[index - 1])
            if current > sar:
                rising = True
                sar = extreme
                extreme = current
                acceleration = 0.02
            elif current < extreme:
                extreme = current
                acceleration = min(maximum, acceleration + 0.02)
    return {
        "parabolic_sar": sar,
        "sar_state": "bullish" if rising else "bearish",
        "sar_direction": "up" if rising else "down",
        "sar_flip": "flip_up" if rising else "flip_down",
        "sar_observation_n": len(values),
        "sar_data_provenance": "quote_mid_proxy",
    }


def _pip_size(symbol: str) -> float:
    upper = symbol.upper()
    if "XAU" in upper or "XAG" in upper:
        return 0.01
    if "JPY" in upper:
        return 0.01
    return 0.0001


def _trend(value: float | None, scale: float = 0.0) -> str:
    if value is None:
        return "unknown"
    threshold = max(abs(scale) * 0.25, 1e-9)
    if value > threshold:
        return "up"
    if value < -threshold:
        return "down"
    return "range"


def _ema(values: Sequence[float], period: int) -> float | None:
    if not values:
        return None
    alpha = 2.0 / (period + 1.0)
    result = values[0]
    for value in values[1:]:
        result = alpha * value + (1.0 - alpha) * result
    return result


def _rsi(changes: Sequence[float]) -> float | None:
    if not changes:
        return None
    gains = [max(change, 0.0) for change in changes[-14:]]
    losses = [max(-change, 0.0) for change in changes[-14:]]
    gain = _mean(gains) or 0.0
    loss = _mean(losses) or 0.0
    if loss == 0.0:
        return 100.0 if gain > 0 else 50.0
    return 100.0 - 100.0 / (1.0 + gain / loss)


def _stochastic_lines(points: Sequence[Mapping[str, float]], lookback: int = 14, smoothing: int = 3) -> dict[str, float] | None:
    """Derive causal fast/slow stochastic lines from prior quote observations.

    This is explicitly a quote-derived oscillator, not a claim about exchange
    candle or traded-volume data. Each %K value uses only the range preceding
    its observation; the slow line is the trailing mean of those %K values.
    """
    if len(points) < lookback + smoothing + 1:
        return None
    fast_values: list[float] = []
    for index in range(lookback, len(points)):
        prior = [item["mid"] for item in points[index - lookback:index]]
        current = points[index]["mid"]
        high = max(prior)
        low = min(prior)
        if high <= low:
            fast_values.append(50.0)
        else:
            fast_values.append(min(100.0, max(0.0, (current - low) / (high - low) * 100.0)))
    if len(fast_values) < smoothing + 2:
        return None
    slow = _mean(fast_values[-smoothing:])
    previous_slow = _mean(fast_values[-smoothing - 1:-1])
    previous_previous_slow = _mean(fast_values[-smoothing - 2:-2])
    if slow is None or previous_slow is None or previous_previous_slow is None:
        return None
    return {
        "fast": fast_values[-1],
        "slow": slow,
        "fast_previous": fast_values[-2],
        "slow_previous": previous_slow,
        "slow_bottomed": previous_slow <= previous_previous_slow and slow >= previous_slow,
    }


def _bollinger_context(values: Sequence[float], period: int = 20) -> dict[str, Any]:
    """Return quote-observation Bollinger context, never a future candle value."""
    if len(values) < period:
        return {}
    window = list(values[-period:])
    middle = _mean(window)
    deviation = _std(window)
    if middle is None or deviation is None or middle <= 0:
        return {}
    upper = middle + 2.0 * deviation
    lower = middle - 2.0 * deviation
    width = max(upper - lower, 0.0)
    current = window[-1]
    position = (current - lower) / width if width > 0 else 0.5
    if current < lower:
        state = "below_lower"
    elif current > upper:
        state = "above_upper"
    elif position >= 0.5:
        state = "upper_half"
    else:
        state = "lower_half"
    return {
        "bollinger_window_n": period,
        "bollinger_middle": middle,
        "bollinger_upper": upper,
        "bollinger_lower": lower,
        "bollinger_width": width,
        "bollinger_bandwidth": width / middle,
        "bollinger_position": position,
        "bollinger_state": state,
    }


def _macd_context(values: Sequence[float]) -> dict[str, Any]:
    """Calculate MACD from prior quote observations with explicit provenance."""
    if len(values) < 26:
        return {}
    macd_values: list[float] = []
    for end in range(26, len(values) + 1):
        fast = _ema(values[max(0, end - 12):end], 12)
        slow = _ema(values[end - 26:end], 26)
        if fast is not None and slow is not None:
            macd_values.append(fast - slow)
    if len(macd_values) < 9:
        return {}
    line = macd_values[-1]
    signal = _ema(macd_values[-9:], 9)
    if signal is None:
        return {}
    histogram = line - signal
    prior_histogram = None
    if len(macd_values) >= 10:
        prior_signal = _ema(macd_values[-10:-1], 9)
        if prior_signal is not None:
            prior_histogram = macd_values[-2] - prior_signal
    cross = "cross_up" if histogram > 0 and (prior_histogram is None or prior_histogram <= 0) else (
        "cross_down" if histogram < 0 and (prior_histogram is None or prior_histogram >= 0) else "no_cross"
    )
    return {
        "macd_line": line,
        "macd_signal": signal,
        "macd_histogram": histogram,
        "macd_histogram_slope": "up" if prior_histogram is not None and histogram > prior_histogram else (
            "down" if prior_histogram is not None and histogram < prior_histogram else "flat"
        ),
        "macd_state": "bullish" if histogram > 0 else "bearish" if histogram < 0 else "neutral",
        "macd_cross": cross,
        "macd_observation_n": len(values),
    }


def _atr_context(values: Sequence[float], period: int = 14) -> dict[str, Any]:
    """Use absolute quote changes as an explicitly labelled ATR proxy."""
    changes = [abs(value) for value in _changes([{"mid": item} for item in values])]
    if len(changes) < period:
        return {}
    atr = _mean(changes[-period:])
    if atr is None or values[-1] <= 0:
        return {}
    prior = _mean(changes[-2 * period:-period]) if len(changes) >= 2 * period else None
    if prior is None or prior <= 0:
        state = "stable"
    elif atr > prior * 1.2:
        state = "expanding"
    elif atr < prior * 0.8:
        state = "compressed"
    else:
        state = "stable"
    return {
        "atr_14": atr,
        "atr_percent": atr / values[-1],
        "atr_state": state,
        "atr_observation_n": len(values),
    }


def _pivot_context(prior_session: Sequence[Mapping[str, float]], current: float, pip: float) -> dict[str, Any]:
    """Calculate classic pivots only from an observed prior session window."""
    if len(prior_session) < 3:
        return {}
    stamps = [item.get("time") for item in prior_session if item.get("time") is not None]
    if len(stamps) < 3 or max(stamps) - min(stamps) < 1800.0:
        return {}
    high = max(item["mid"] for item in prior_session)
    low = min(item["mid"] for item in prior_session)
    close = prior_session[-1]["mid"]
    pivot = (high + low + close) / 3.0
    relation = "above_pivot" if current > pivot + pip else "below_pivot" if current < pivot - pip else "at_pivot"
    return {
        "previous_session_high": high,
        "previous_session_low": low,
        "previous_session_close": close,
        "pivot": pivot,
        "pivot_r1": 2.0 * pivot - low,
        "pivot_s1": 2.0 * pivot - high,
        "pivot_r2": pivot + (high - low),
        "pivot_s2": pivot - (high - low),
        "pivot_relation": relation,
        "pivot_data_provenance": "observed_prior_session_quote_proxy",
    }


def _chart_pattern_context(values: Sequence[float], pip: float) -> dict[str, Any]:
    """Detect simple completed quote-extrema patterns using observations to now."""
    if len(values) < 8:
        return {}
    window = list(values[-60:])
    span = max(max(window) - min(window), pip)
    tolerance = max(3.0 * pip, span * 0.03)
    peaks = [(index, value) for index, value in enumerate(window[1:-1], 1) if value >= window[index - 1] and value >= window[index + 1]]
    troughs = [(index, value) for index, value in enumerate(window[1:-1], 1) if value <= window[index - 1] and value <= window[index + 1]]
    current = window[-1]
    if len(peaks) >= 2 and len(troughs) >= 2:
        first_peak, second_peak = peaks[-2:]
        first_trough, second_trough = troughs[-2:]
        if abs(first_peak[1] - second_peak[1]) <= tolerance and second_trough[1] > first_trough[1] + tolerance * 0.25 and current >= max(first_peak[1], second_peak[1]) - tolerance and current <= max(first_peak[1], second_peak[1]) + tolerance:
            return {
                "chart_pattern": "ascending_triangle",
                "pattern": "ascending_triangle",
                "pattern_state": "observed_quote_pattern",
                "pattern_confirmation": "converging_range",
                "pattern_direction": "up",
                "pattern_detection_provenance": "quote_extrema_proxy",
            }
        if abs(first_trough[1] - second_trough[1]) <= tolerance and second_peak[1] < first_peak[1] - tolerance * 0.25 and current >= min(first_trough[1], second_trough[1]) - tolerance:
            return {
                "chart_pattern": "descending_triangle",
                "pattern": "descending_triangle",
                "pattern_state": "observed_quote_pattern",
                "pattern_confirmation": "converging_range",
                "pattern_direction": "down",
                "pattern_detection_provenance": "quote_extrema_proxy",
            }
    if len(peaks) >= 3:
        left, head, right = peaks[-3:]
        if abs(left[1] - right[1]) <= tolerance and head[1] > max(left[1], right[1]) + tolerance * 0.5:
            return {
                "chart_pattern": "head_and_shoulders",
                "pattern": "head_and_shoulders",
                "pattern_state": "observed_quote_pattern",
                "pattern_confirmation": "right_shoulder_observed",
                "pattern_direction": "down",
                "pattern_detection_provenance": "quote_extrema_proxy",
            }
    if len(troughs) >= 3:
        left, head, right = troughs[-3:]
        if abs(left[1] - right[1]) <= tolerance and head[1] < min(left[1], right[1]) - tolerance * 0.5:
            return {
                "chart_pattern": "inverse_head_and_shoulders",
                "pattern": "inverse_head_and_shoulders",
                "pattern_state": "observed_quote_pattern",
                "pattern_confirmation": "right_shoulder_observed",
                "pattern_direction": "up",
                "pattern_detection_provenance": "quote_extrema_proxy",
            }
    if len(peaks) >= 2:
        first_peak, second_peak = peaks[-2:]
        if second_peak[0] - first_peak[0] >= 2 and abs(first_peak[1] - second_peak[1]) <= tolerance and current < second_peak[1] - tolerance * 0.25:
            return {
                "chart_pattern": "double_top",
                "pattern": "double_top",
                "pattern_state": "completed_quote_pattern",
                "pattern_confirmation": "rejection_observed",
                "pattern_direction": "down",
                "pattern_detection_provenance": "quote_extrema_proxy",
            }
    if len(troughs) >= 2:
        first_trough, second_trough = troughs[-2:]
        if second_trough[0] - first_trough[0] >= 2 and abs(first_trough[1] - second_trough[1]) <= tolerance and current > second_trough[1] + tolerance * 0.25:
            return {
                "chart_pattern": "double_bottom",
                "pattern": "double_bottom",
                "pattern_state": "completed_quote_pattern",
                "pattern_confirmation": "reclaim_observed",
                "pattern_direction": "up",
                "pattern_detection_provenance": "quote_extrema_proxy",
            }
    if len(window) >= 12:
        impulse = window[-12:-6]
        flag = window[-6:]
        impulse_move = impulse[-1] - impulse[0]
        flag_move = flag[-1] - flag[0]
        if impulse_move > tolerance * 2 and -impulse_move * 0.6 <= flag_move <= tolerance:
            return {
                "chart_pattern": "bull_flag",
                "pattern": "bull_flag",
                "pattern_state": "observed_quote_pattern",
                "pattern_confirmation": "pullback_observed",
                "pattern_direction": "up",
                "pattern_detection_provenance": "quote_extrema_proxy",
            }
        if impulse_move < -tolerance * 2 and -tolerance <= flag_move <= -impulse_move * 0.6:
            return {
                "chart_pattern": "bear_flag",
                "pattern": "bear_flag",
                "pattern_state": "observed_quote_pattern",
                "pattern_confirmation": "pullback_observed",
                "pattern_direction": "down",
                "pattern_detection_provenance": "quote_extrema_proxy",
            }
    return {}


def _adx_context(values: Sequence[float], period: int = 14) -> dict[str, Any]:
    """Calculate a directional-strength proxy from sequential quote changes."""
    changes = _changes([{"mid": item} for item in values])
    if len(changes) < period:
        return {}
    observations: list[tuple[float, float, float]] = []
    for end in range(period, len(changes) + 1):
        window = changes[end - period:end]
        total_range = sum(abs(change) for change in window)
        if total_range <= 0:
            continue
        plus = 100.0 * sum(max(change, 0.0) for change in window) / total_range
        minus = 100.0 * sum(max(-change, 0.0) for change in window) / total_range
        denominator = plus + minus
        dx = 100.0 * abs(plus - minus) / denominator if denominator else 0.0
        observations.append((dx, plus, minus))
    if not observations:
        return {}
    adx = _mean(item[0] for item in observations[-period:])
    if adx is None:
        return {}
    _, plus, minus = observations[-1]
    direction = "up" if plus > minus else "down" if minus > plus else "neutral"
    return {
        "adx": adx,
        "di_plus": plus,
        "di_minus": minus,
        "adx_state": "strong" if adx >= 25.0 else "weak",
        "adx_direction": direction,
        "adx_observation_n": len(values),
    }


def _keltner_context(values: Sequence[float], period: int = 20) -> dict[str, Any]:
    """Calculate a quote-observation Keltner proxy using EMA and ATR proxy."""
    changes = _changes([{"mid": item} for item in values])
    if len(values) < period or len(changes) < 14:
        return {}
    middle = _ema(values[-period:], period)
    atr = _mean(abs(change) for change in changes[-14:])
    if middle is None or atr is None or middle <= 0:
        return {}
    upper = middle + 2.0 * atr
    lower = middle - 2.0 * atr
    current = values[-1]
    state = "above_upper" if current > upper else "below_lower" if current < lower else "inside"
    return {
        "keltner_middle": middle,
        "keltner_upper": upper,
        "keltner_lower": lower,
        "keltner_width": upper - lower,
        "keltner_state": state,
        "keltner_observation_n": len(values),
    }


def _prior_channel(values: Sequence[float], lookback: int) -> tuple[float, float, float] | None:
    """Return a prior-observation channel, excluding the current quote."""
    if len(values) <= lookback:
        return None
    prior = list(values[-lookback - 1:-1])
    if len(prior) != lookback:
        return None
    high = max(prior)
    low = min(prior)
    deviation = _std(prior)
    if deviation is None or high <= low:
        return None
    return high, low, deviation


def _squeeze_context(values: Sequence[float], momentum: float | None) -> dict[str, Any]:
    """Derive Carter-style squeeze state from quote-observation proxies."""
    current = _bollinger_context(values)
    keltner = _keltner_context(values)
    if not current or not keltner:
        return {}
    current_on = current["bollinger_width"] <= keltner["keltner_width"]
    previous_on = False
    if len(values) > 1:
        previous_bb = _bollinger_context(values[:-1])
        previous_keltner = _keltner_context(values[:-1])
        if previous_bb and previous_keltner:
            previous_on = previous_bb["bollinger_width"] <= previous_keltner["keltner_width"]
    state = "released" if previous_on and not current_on else "on" if current_on else "off"
    direction = "up" if momentum is not None and momentum > 0 else (
        "down" if momentum is not None and momentum < 0 else "flat"
    )
    return {
        "squeeze_state": state,
        "squeeze_direction": direction,
        "squeeze_momentum": momentum,
        "squeeze_confirmation": "quote_proxy_confirmed" if direction != "flat" else "quote_proxy_unconfirmed",
    }


def _completed_quote_bars(
    points: Sequence[Mapping[str, float]],
    now: float,
    interval_s: float = 15.0,
) -> list[tuple[int, list[Mapping[str, float]]]]:
    """Return completed fixed-time quote buckets, excluding the active one."""
    if not points or interval_s <= 0:
        return []
    current_bucket = math.floor(now / interval_s)
    buckets: dict[int, list[Mapping[str, float]]] = {}
    for point in points:
        stamp = _finite(point.get("time"))
        if stamp is None:
            continue
        bucket = math.floor(stamp / interval_s)
        if bucket < current_bucket:
            buckets.setdefault(bucket, []).append(point)
    return [
        (bucket, sorted(items, key=lambda item: item.get("time", 0.0)))
        for bucket, items in sorted(buckets.items())
        if len(items) >= 2
    ]


def _completed_quote_candle_context(
    points: Sequence[Mapping[str, float]],
    now: float,
    pip: float,
    interval_s: float = 15.0,
) -> dict[str, Any]:
    """Build a candle from a completed fixed-time quote bucket only."""
    completed = _completed_quote_bars(points, now, interval_s)
    if not completed:
        return {}
    bucket, items = completed[-1]
    opening = items[0]["mid"]
    closing = items[-1]["mid"]
    high = max(item["mid"] for item in items)
    low = min(item["mid"] for item in items)
    body = abs(closing - opening)
    upper_wick = max(0.0, high - max(opening, closing))
    lower_wick = max(0.0, min(opening, closing) - low)
    full_range = max(0.0, high - low)
    direction = "bullish" if closing > opening else "bearish" if closing < opening else "doji"
    if full_range == 0 or body <= full_range * 0.1:
        pattern = "doji"
    elif direction == "bullish" and lower_wick >= body * 2.0 and upper_wick <= body:
        pattern = "bullish_hammer"
    elif direction == "bearish" and upper_wick >= body * 2.0 and lower_wick <= body:
        pattern = "bearish_shooting_star"
    else:
        pattern = f"{direction}_quote_bar"
    if len(completed) >= 2:
        prior = completed[-2][1]
        prior_open = prior[0]["mid"]
        prior_close = prior[-1]["mid"]
        if prior_close < prior_open and closing > opening and opening <= prior_close and closing >= prior_open:
            pattern = "bullish_engulfing"
        elif prior_close > prior_open and closing < opening and opening >= prior_close and closing <= prior_open:
            pattern = "bearish_engulfing"
        prior_body = abs(prior_close - prior_open)
        if prior_body > 0:
            if prior_close < prior_open and closing > opening and closing > (prior_open + prior_close) / 2.0 and closing < prior_open:
                pattern = "piercing_line"
            elif prior_close > prior_open and closing < opening and closing < (prior_open + prior_close) / 2.0 and closing > prior_open:
                pattern = "dark_cloud_cover"
            elif min(opening, closing) >= min(prior_open, prior_close) and max(opening, closing) <= max(prior_open, prior_close):
                pattern = "bullish_harami" if prior_close < prior_open and closing > opening else (
                    "bearish_harami" if prior_close > prior_open and closing < opening else pattern
                )
    if len(completed) >= 3:
        shapes = []
        for _, bar in completed[-3:]:
            bar_open = bar[0]["mid"]
            bar_close = bar[-1]["mid"]
            shapes.append({
                "open": bar_open,
                "close": bar_close,
                "body": abs(bar_close - bar_open),
                "direction": "bullish" if bar_close > bar_open else "bearish" if bar_close < bar_open else "doji",
            })
        first, middle, last = shapes
        small_middle = middle["body"] <= max(first["body"], last["body"]) * 0.5
        if (
            first["direction"] == "bearish"
            and small_middle
            and last["direction"] == "bullish"
            and last["close"] > (first["open"] + first["close"]) / 2.0
        ):
            pattern = "morning_star"
        elif (
            first["direction"] == "bullish"
            and small_middle
            and last["direction"] == "bearish"
            and last["close"] < (first["open"] + first["close"]) / 2.0
        ):
            pattern = "evening_star"
        elif all(item["direction"] == "bullish" for item in shapes) and shapes[0]["close"] < shapes[1]["close"] < shapes[2]["close"]:
            pattern = "three_white_soldiers"
        elif all(item["direction"] == "bearish" for item in shapes) and shapes[0]["close"] > shapes[1]["close"] > shapes[2]["close"]:
            pattern = "three_black_crows"
    return {
        "candle": f"{direction}_quote_bar",
        "candle_pattern": pattern,
        "signal_bar": direction,
        "bar_pattern": direction,
        "closed_bar": True,
        "bar_range": full_range,
        "candle_body": body,
        "candle_upper_wick": upper_wick,
        "candle_lower_wick": lower_wick,
        "price_change": "rising" if closing > opening else "falling" if closing < opening else "flat",
        "candle_data_provenance": "completed_quote_bar_proxy",
        "candle_bar_end_time": (bucket + 1) * interval_s,
    }


def _volman_context(
    points: Sequence[Mapping[str, float]],
    now: float,
    dominant: str,
    pip: float,
    interval_s: float = 15.0,
    candidate_side: str | None = None,
) -> dict[str, Any]:
    """Derive conservative Bob Volman setup proxies from completed quote bars.

    Volman's source uses a 70-tick chart and discretionary 20EMA reading.  The
    Watcher has no such native chart, so this adapter uses completed fixed-time
    quote bars and an explicitly labelled 20-period quote EMA.  The active bar
    is excluded; a setup is only visible after its signal bar has completed.
    """
    completed = _completed_quote_bars(points, now, interval_s)
    if len(completed) < 6:
        return {}
    bars: list[dict[str, float | str]] = []
    for _, items in completed:
        opening = float(items[0]["mid"])
        closing = float(items[-1]["mid"])
        high = max(float(item["mid"]) for item in items)
        low = min(float(item["mid"]) for item in items)
        bars.append({
            "open": opening,
            "close": closing,
            "high": high,
            "low": low,
            "body": abs(closing - opening),
            "range": max(0.0, high - low),
            "direction": "bullish" if closing > opening else "bearish" if closing < opening else "doji",
        })
    latest = bars[-1]
    prior = bars[:-1]
    trend = dominant if dominant in {"up", "down", "range"} else "unknown"
    signal = "up" if latest["direction"] == "bullish" else "down" if latest["direction"] == "bearish" else None
    reference = bars[-3:-1]
    if signal is None and reference:
        signal = "up" if float(latest["close"]) > float(reference[-1]["close"]) else (
            "down" if float(latest["close"]) < float(reference[-1]["close"]) else None
        )
    signal_break = bool(reference) and (
        signal == "up" and float(latest["close"]) > max(float(item["high"]) for item in reference)
        or signal == "down" and float(latest["close"]) < min(float(item["low"]) for item in reference)
    )
    prior_ranges = [float(item["range"]) for item in prior if float(item["range"]) > 0]
    median_range = statistics.median(prior_ranges) if prior_ranges else 0.0
    small_limit = max(3.0 * pip, median_range * 0.75)
    ema20 = _ema([float(item["mid"]) for item in points], 20) if len(points) >= 20 else None
    pullback_bars = bars[-4:-1]
    ema_distance = None
    pullback_to_ema = False
    if ema20 is not None and pullback_bars:
        ema_distance = min(abs(float(item["close"]) - ema20) for item in pullback_bars) / max(pip, 1e-12)
        pullback_to_ema = ema_distance <= 3.0
    local = bars[-8:-1]
    if not local:
        local = prior
    local_high = max(float(item["high"]) for item in local)
    local_low = min(float(item["low"]) for item in local)
    local_width = max(0.0, local_high - local_low)
    path_room_pips = local_width / max(pip, 1e-12)
    path_clear = path_room_pips >= 10.0

    def _same_direction(items: Sequence[Mapping[str, float | str]], expected: str) -> bool:
        wanted = "bullish" if expected == "up" else "bearish"
        return bool(items) and all(item["direction"] == wanted for item in items)

    def _opposing_direction(items: Sequence[Mapping[str, float | str]], expected: str) -> bool:
        wanted = "bearish" if expected == "up" else "bullish"
        return bool(items) and all(item["direction"] == wanted for item in items)

    # These extensions translate Volman's discretionary chart checks into
    # conservative, causal proxies.  Only completed bars are used for the
    # structure; the current point is used solely for the executable exit
    # quote and direction-specific barrier comparison.
    candidate_side = str(candidate_side or "").upper()
    pressure_aligned = trend in {"up", "down"} and signal == trend
    market_favorable = pressure_aligned
    left_of_signal = bars[-3:-1]
    left_ranges = [float(item["range"]) for item in left_of_signal]
    left_small_limit = max(3.0 * pip, median_range * 0.85)
    left_overlap = (
        min(float(item["high"]) for item in left_of_signal)
        - max(float(item["low"]) for item in left_of_signal)
        if left_of_signal
        else 0.0
    )
    left_clustered = bool(left_of_signal) and all(
        value <= left_small_limit for value in left_ranges
    ) and left_overlap >= pip

    pullback_style = "unknown"
    pullback_fraction = None
    pullback_move = 0.0
    if len(bars) >= 5 and pullback_bars:
        anchor = bars[-5]
        anchor_close = float(anchor["close"])
        impulse_open = float(bars[0]["open"])
        impulse_move = abs(anchor_close - impulse_open)
        if trend == "up":
            pullback_extreme = min(float(item["low"]) for item in pullback_bars)
            pullback_move = max(0.0, anchor_close - pullback_extreme)
            monotonic_pullback = all(
                float(left["close"]) >= float(right["close"])
                for left, right in zip(pullback_bars, pullback_bars[1:])
            )
        elif trend == "down":
            pullback_extreme = max(float(item["high"]) for item in pullback_bars)
            pullback_move = max(0.0, pullback_extreme - anchor_close)
            monotonic_pullback = all(
                float(left["close"]) <= float(right["close"])
                for left, right in zip(pullback_bars, pullback_bars[1:])
            )
        else:
            pullback_extreme = None
            monotonic_pullback = False
        if impulse_move > 0.0 and pullback_move > 0.0:
            pullback_fraction = pullback_move / impulse_move
        pullback_span = max(float(item["range"]) for item in pullback_bars)
        if (
            trend in {"up", "down"}
            and _opposing_direction(pullback_bars, trend)
            and monotonic_pullback
            and pullback_move >= max(2.0 * pip, median_range * 0.5)
        ):
            pullback_style = "diagonal"
        elif left_clustered:
            pullback_style = "clustering"
        elif pullback_span <= max(3.0 * pip, median_range * 0.75):
            pullback_style = "thin_horizontal"
        elif pullback_move >= max(2.0 * pip, median_range * 0.5):
            pullback_style = "substantial"
        else:
            pullback_style = "horizontal"

    current_quote = points[-1] if points else {}
    current_mid = float(current_quote.get("mid", latest["close"]))
    resistance_blocking = None
    if candidate_side == "BUY":
        distance = local_high - current_mid
        resistance_blocking = 0.0 <= distance <= 10.0 * pip
    elif candidate_side == "SELL":
        distance = current_mid - local_low
        resistance_blocking = 0.0 <= distance <= 10.0 * pip

    setups: list[str] = []
    double_doji = False
    if trend in {"up", "down"} and signal == trend and signal_break and len(bars) >= 3:
        doji_pair = bars[-3:-1]
        double_doji = all(
            float(item["range"]) <= small_limit
            and float(item["body"]) <= max(float(item["range"]) * 0.5, pip)
            for item in doji_pair
        ) and pullback_to_ema
        if double_doji:
            setups.append("double_doji_break")

    burst_move = False
    first_pullback = False
    if trend in {"up", "down"} and len(bars) >= 6:
        impulse = bars[-6:-3]
        pullback = bars[-3:-1]
        impulse_move = abs(float(impulse[-1]["close"]) - float(impulse[0]["open"])) if impulse else 0.0
        burst_move = _same_direction(impulse, trend) and impulse_move >= max(4.0 * pip, median_range)
        first_pullback = _opposing_direction(pullback, trend) and not any(
            item["direction"] == ("bearish" if trend == "up" else "bullish") for item in bars[:-3]
        )
        if burst_move and first_pullback and pullback_to_ema and signal == trend and signal_break:
            setups.append("first_break")

    first_break_failed = False
    if trend in {"up", "down"} and len(bars) >= 6:
        for index in range(2, len(bars) - 2):
            window = bars[max(0, index - 2):index]
            if not window:
                continue
            high = max(float(item["high"]) for item in window)
            low = min(float(item["low"]) for item in window)
            candidate = bars[index]
            reaction = bars[index + 1]
            if trend == "up" and float(candidate["close"]) > high and float(reaction["close"]) <= high:
                first_break_failed = True
                break
            if trend == "down" and float(candidate["close"]) < low and float(reaction["close"]) >= low:
                first_break_failed = True
                break
    second_attempt = first_break_failed and signal == trend and signal_break
    if second_attempt:
        setups.append("second_break")

    block = bars[-5:-1]
    block_ranges = [float(item["range"]) for item in block]
    block_compression = bool(block) and all(
        float(item["range"]) <= max(3.0 * pip, median_range * 0.85) for item in block
    )
    market_pressure = trend if trend in {"up", "down"} else signal or "unknown"
    block_break = block_compression and signal_break and signal == market_pressure
    if block_break:
        setups.append("block_break")

    range_window = bars[-8:-1]
    range_high = max(float(item["high"]) for item in range_window) if range_window else 0.0
    range_low = min(float(item["low"]) for item in range_window) if range_window else 0.0
    range_width = max(0.0, range_high - range_low)
    range_tolerance = max(pip, range_width * 0.08)
    high_touches = sum(abs(float(item["high"]) - range_high) <= range_tolerance for item in range_window)
    low_touches = sum(abs(float(item["low"]) - range_low) <= range_tolerance for item in range_window)
    prebreak_tension = bool(range_window) and len(range_window) >= 4 and median_range > 0 and all(
        float(item["range"]) <= median_range for item in range_window[-2:]
    )
    range_break = (
        len(range_window) >= 4
        and range_width >= 10.0 * pip
        and high_touches >= 2
        and low_touches >= 2
        and signal_break
        and prebreak_tension
    )
    if range_break:
        setups.append("range_break")

    outer = bars[-8:-3]
    inner = bars[-3:-1]
    outer_high = max((float(item["high"]) for item in outer), default=0.0)
    outer_low = min((float(item["low"]) for item in outer), default=0.0)
    outer_width = max(0.0, outer_high - outer_low)
    inner_high = max((float(item["high"]) for item in inner), default=0.0)
    inner_low = min((float(item["low"]) for item in inner), default=0.0)
    inner_width = max(0.0, inner_high - inner_low)
    inner_block = bool(outer and inner) and outer_width >= 10.0 * pip and inner_width <= max(3.0 * pip, outer_width * 0.55) and (
        inner_low >= outer_low and inner_high <= outer_high
    )
    inside_range_break = inner_block and signal_break
    if inside_range_break:
        setups.append("inside_range_break")

    prior_range_break = False
    post_break_retest = False
    prior_break_direction = None
    if len(bars) >= 8:
        for index in range(3, len(bars) - 2):
            base_window = bars[index - 3:index]
            high = max(float(item["high"]) for item in base_window)
            low = min(float(item["low"]) for item in base_window)
            candidate = bars[index]
            if float(candidate["close"]) > high:
                prior_break_direction = "up"
                retest_level = high
            elif float(candidate["close"]) < low:
                prior_break_direction = "down"
                retest_level = low
            else:
                continue
            later = bars[index + 1:-1]
            if prior_break_direction == "up":
                post_break_retest = any(float(item["low"]) <= retest_level + 2.0 * pip for item in later)
            else:
                post_break_retest = any(float(item["high"]) >= retest_level - 2.0 * pip for item in later)
            prior_break = post_break_retest and signal == prior_break_direction and signal_break
            if prior_break:
                prior_range_break = True
                break
    signal_cluster_bars = len(inner) if inner else 0
    advanced_range_break = prior_range_break and post_break_retest and signal_break
    if advanced_range_break:
        setups.append("advanced_range_break")

    result = {
        "volman_setup": setups[0] if setups else "none",
        "volman_setups": setups,
        "volman_trend": trend,
        "volman_signal_direction": signal or "unknown",
        "volman_signal_break": "confirmed" if signal_break else "not_confirmed",
        "volman_signal_confirmation": "confirmed" if signal_break else "not_confirmed",
        "volman_path_clear": path_clear,
        "volman_market_favorable": market_favorable,
        "volman_path_room_pips": path_room_pips,
        "volman_left_clustered": left_clustered,
        "volman_pressure_aligned": pressure_aligned,
        "volman_pullback_style": pullback_style,
        "volman_pullback_fraction": pullback_fraction,
        "volman_data_provenance": "causal_completed_quote_bar_proxy",
        "volman_ema_period": 20,
        "volman_ema_distance_pips": ema_distance,
        "volman_pullback_to_ema": pullback_to_ema,
        "volman_pattern_bars": 2 if double_doji else 0,
        "volman_signal_bar_range_pips": float(latest["range"]) / max(pip, 1e-12),
        "volman_burst_move": burst_move,
        "volman_first_pullback": first_pullback,
        "volman_first_break_failed": first_break_failed,
        "volman_second_attempt": second_attempt,
        "volman_block_bars": len(block),
        "volman_block_compression": block_compression,
        "volman_market_pressure": market_pressure,
        "volman_range_bars": len(range_window),
        "volman_range_width_pips": range_width / max(pip, 1e-12),
        "volman_prebreak_tension": prebreak_tension,
        "volman_inner_block_bars": len(inner),
        "volman_range_room_pips": outer_width / max(pip, 1e-12),
        "volman_prior_range_break": prior_range_break,
        "volman_prior_break_direction": prior_break_direction or "unknown",
        "volman_post_break_retest": post_break_retest,
        "volman_signal_cluster_bars": signal_cluster_bars,
    }
    if candidate_side in {"BUY", "SELL"} and pullback_bars:
        if candidate_side == "BUY":
            result.update({
                "volman_tipping_point_price": min(float(item["low"]) for item in pullback_bars),
                "volman_tipping_point_source": "pullback_low",
                "volman_current_exit_price": float(current_quote.get("bid", current_mid)),
                "volman_tipping_point_activated": bool(signal_break and signal == "up"),
            })
        else:
            result.update({
                "volman_tipping_point_price": max(float(item["high"]) for item in pullback_bars),
                "volman_tipping_point_source": "pullback_high",
                "volman_current_exit_price": float(current_quote.get("ask", current_mid)),
                "volman_tipping_point_activated": bool(signal_break and signal == "down"),
            })
    if resistance_blocking is not None:
        result["volman_resistance_blocking"] = resistance_blocking
    return result


def _vpa_context(
    points: Sequence[Mapping[str, float]],
    now: float,
    dominant: str,
    pip: float,
    interval_s: float = 15.0,
) -> dict[str, Any]:
    """Derive conservative Coulling VPA proxies from completed quote bars.

    The source material reasons about traded volume.  The Watcher does not
    receive exchange volume for these FX quotes, so this adapter uses only
    broker tick-volume values when present, otherwise quote-count activity,
    and labels both cases as a tick-activity proxy.  It never represents the
    proxy as real traded volume and never reads the active bar.
    """
    completed = _completed_quote_bars(points, now, interval_s)
    if len(completed) < 3:
        return {}

    bars: list[dict[str, float | str | bool | None]] = []
    for bucket, items in completed:
        opening = float(items[0]["mid"])
        closing = float(items[-1]["mid"])
        high = max(float(item["mid"]) for item in items)
        low = min(float(item["mid"]) for item in items)
        full_range = max(0.0, high - low)
        body = abs(closing - opening)
        upper_wick = max(0.0, high - max(opening, closing))
        lower_wick = max(0.0, min(opening, closing) - low)
        activity_values = [
            _finite(item.get("tick_volume"))
            for item in items
        ]
        numeric_activity = [value for value in activity_values if value is not None and value >= 0]
        activity = sum(numeric_activity) if numeric_activity else float(len(items))
        direction = "up" if closing > opening else "down" if closing < opening else "unknown"
        bars.append({
            "bucket": bucket,
            "open": opening,
            "close": closing,
            "high": high,
            "low": low,
            "range": full_range,
            "body": body,
            "body_fraction": body / full_range if full_range > 0 else 0.0,
            "upper_wick_ratio": upper_wick / max(body, pip),
            "lower_wick_ratio": lower_wick / max(body, pip),
            "close_location": (
                "upper_half" if full_range > 0 and closing >= low + full_range * 0.5
                else "lower_half" if full_range > 0 and closing <= low + full_range * 0.5
                else "middle"
            ),
            "direction": direction,
            "activity": activity,
        })

    # Each bar's ratio is based only on bars before it.  This keeps the
    # comparison causal and avoids using the current event as its own baseline.
    for index, bar in enumerate(bars):
        prior_activity = [
            float(item["activity"])
            for item in bars[:index]
            if float(item["activity"]) > 0
        ]
        baseline = statistics.median(prior_activity) if prior_activity else None
        bar["volume_ratio"] = (
            float(bar["activity"]) / baseline
            if baseline is not None and baseline > 0
            else None
        )

    latest = bars[-1]
    prior = bars[:-1]
    prior_ranges = [float(item["range"]) for item in prior if float(item["range"]) > 0]
    average_range = statistics.median(prior_ranges) if prior_ranges else None
    latest_range = float(latest["range"])
    latest_volume_ratio = latest["volume_ratio"]
    latest_range_pips = latest_range / max(pip, 1e-12)
    average_range_pips = (
        average_range / max(pip, 1e-12) if average_range is not None else None
    )
    latest_volume_ratio_number = (
        float(latest_volume_ratio) if latest_volume_ratio is not None else None
    )
    setups: list[str] = []

    long_legged_doji = (
        average_range is not None
        and latest_range_pips >= max(10.0, average_range_pips * 1.5)
        and float(latest["body_fraction"]) <= 0.2
        and latest_volume_ratio_number is not None
        and latest_volume_ratio_number <= 0.8
    )
    if long_legged_doji:
        setups.append("long_legged_doji")

    narrow_spread_high_volume = (
        average_range is not None
        and latest_range <= average_range * 0.75
        and latest_volume_ratio_number is not None
        and latest_volume_ratio_number >= 1.5
        and latest["direction"] in {"up", "down"}
    )
    if narrow_spread_high_volume:
        setups.append("narrow_spread_high_volume")

    lower_wick_sequence = [
        item for item in bars[-4:-1]
        if float(item["lower_wick_ratio"]) >= 2.0
        and item["volume_ratio"] is not None
        and float(item["volume_ratio"]) >= 1.2
    ]
    stopping_volume = (
        dominant == "down"
        and len(lower_wick_sequence) >= 2
        and latest["direction"] == "up"
        and float(latest["lower_wick_ratio"]) >= 2.0
        and latest["close_location"] == "upper_half"
        and latest_volume_ratio_number is not None
        and latest_volume_ratio_number >= 1.2
    )
    if stopping_volume:
        setups.append("stopping_volume")

    upper_wick_sequence = [
        item for item in bars[-4:-1]
        if float(item["upper_wick_ratio"]) >= 2.0
        and item["volume_ratio"] is not None
        and float(item["volume_ratio"]) >= 1.2
    ]
    spread_contraction = (
        average_range is not None
        and latest_range < average_range
    )
    topping_out_volume = (
        dominant == "up"
        and len(upper_wick_sequence) >= 2
        and latest["direction"] == "down"
        and float(latest["upper_wick_ratio"]) >= 2.0
        and spread_contraction
        and latest_volume_ratio_number is not None
        and latest_volume_ratio_number >= 1.2
    )
    if topping_out_volume:
        setups.append("topping_out_volume")

    breakout_direction = "not_applicable"
    clear_water = False
    breakout_volume_ratio = latest_volume_ratio_number
    retest_volume_ratio: float | None = None
    breakout_confirmation = "not_confirmed"
    range_window = bars[-5:-1]
    if len(range_window) >= 4:
        range_high = max(float(item["high"]) for item in range_window)
        range_low = min(float(item["low"]) for item in range_window)
        if float(latest["close"]) > range_high + pip:
            breakout_direction = "up"
            clear_water = True
            boundary = range_high
            retest_candidates = [
                item for item in range_window
                if float(item["low"]) <= boundary + 2.0 * pip
            ]
        elif float(latest["close"]) < range_low - pip:
            breakout_direction = "down"
            clear_water = True
            boundary = range_low
            retest_candidates = [
                item for item in range_window
                if float(item["high"]) >= boundary - 2.0 * pip
            ]
        else:
            boundary = None
            retest_candidates = []
        if clear_water and retest_candidates:
            candidate = retest_candidates[-1]
            candidate_ratio = candidate["volume_ratio"]
            if candidate_ratio is not None:
                retest_volume_ratio = float(candidate_ratio)
        if (
            clear_water
            and breakout_volume_ratio is not None
            and breakout_volume_ratio >= 1.2
            and retest_volume_ratio is not None
            and retest_volume_ratio <= 1.0
        ):
            breakout_confirmation = "quote_bar_proxy_confirmed"
            setups.append("breakout_volume_validation")

    confirmation = "quote_bar_proxy_confirmed" if stopping_volume or topping_out_volume else "not_confirmed"
    sequence_bars = max(len(lower_wick_sequence), len(upper_wick_sequence))
    return {
        "vpa_setup": setups[0] if setups else "none",
        "vpa_setups": setups,
        "vpa_volume_provenance": "tick_activity_proxy",
        "vpa_data_provenance": "causal_completed_bar_tick_activity_proxy",
        "vpa_candle_range_pips": latest_range_pips,
        "vpa_candle_body_fraction": float(latest["body_fraction"]),
        "vpa_volume_ratio": (
            latest_volume_ratio_number
            if latest_volume_ratio_number is not None else "not_applicable"
        ),
        "vpa_price_direction": (
            latest["direction"] if latest["direction"] != "unknown" else "not_applicable"
        ),
        "vpa_average_spread_pips": (
            average_range_pips if average_range_pips is not None else "not_applicable"
        ),
        "vpa_spread_pips": latest_range_pips,
        "vpa_confirmation": confirmation,
        "vpa_trend": dominant if dominant in {"up", "down", "range"} else "not_applicable",
        "vpa_lower_wick_ratio": float(latest["lower_wick_ratio"]),
        "vpa_close_location": latest["close_location"],
        "vpa_sequence_bars": sequence_bars,
        "vpa_upper_wick_ratio": float(latest["upper_wick_ratio"]),
        "vpa_spread_contraction": spread_contraction,
        "vpa_breakout_direction": breakout_direction,
        "vpa_breakout_confirmation": breakout_confirmation,
        "vpa_clear_water": clear_water,
        "vpa_breakout_volume_ratio": (
            breakout_volume_ratio if breakout_volume_ratio is not None else "not_applicable"
        ),
        # Keep the field present so a normal non-breakout state is
        # NOT_APPLICABLE rather than a generic missing-data failure.  A
        # breakout setup is never emitted unless this is a measured number.
        "vpa_retest_volume_ratio": (
            retest_volume_ratio if retest_volume_ratio is not None else "not_applicable"
        ),
    }


def _edwards_magee_context(
    points: Sequence[Mapping[str, float]],
    now: float,
    dominant: str,
    pip: float,
    interval_s: float = 15.0,
) -> dict[str, Any]:
    """Derive conservative Edwards-Magee chart-pattern proxies.

    These rules are intentionally expressed on completed quote bars.  The
    source book uses exchange price/volume charts; FX has no consolidated
    volume here, so volume fields are labelled tick-activity proxies and are
    never treated as source-quality traded volume.
    """
    completed = _completed_quote_bars(points, now, interval_s)
    if len(completed) < 5:
        return {}

    bars: list[dict[str, float | str]] = []
    for bucket, items in completed:
        opening = float(items[0]["mid"])
        closing = float(items[-1]["mid"])
        high = max(float(item["mid"]) for item in items)
        low = min(float(item["mid"]) for item in items)
        full_range = max(0.0, high - low)
        body = abs(closing - opening)
        numeric_activity = [
            _finite(item.get("tick_volume"))
            for item in items
        ]
        activity_values = [value for value in numeric_activity if value is not None and value >= 0]
        activity = sum(activity_values) if activity_values else float(len(items))
        bars.append({
            "bucket": float(bucket),
            "open": opening,
            "close": closing,
            "high": high,
            "low": low,
            "range": full_range,
            "body": body,
            "upper_wick": max(0.0, high - max(opening, closing)),
            "lower_wick": max(0.0, min(opening, closing) - low),
            "direction": "up" if closing > opening else "down" if closing < opening else "flat",
            "activity": activity,
        })
    for index, bar in enumerate(bars):
        prior_activity = [
            float(item["activity"])
            for item in bars[:index]
            if float(item["activity"]) > 0
        ]
        baseline = statistics.median(prior_activity) if prior_activity else None
        bar["volume_ratio"] = (
            float(bar["activity"]) / baseline
            if baseline is not None and baseline > 0 else "not_applicable"
        )

    latest = bars[-1]
    prior = bars[:-1]
    latest_ratio = latest["volume_ratio"]
    latest_ratio_number = latest_ratio if isinstance(latest_ratio, float) else None
    output: dict[str, Any] = {
        "em_setup": "none",
        "em_setups": [],
        "em_data_provenance": "causal_completed_quote_bar_proxy",
        "em_volume_provenance": "tick_activity_proxy",
        "em_breakout_direction": "not_applicable",
        "em_breakout_confirmation": "not_confirmed",
        "em_volume_pattern": "not_applicable",
        "em_neckline_break_pips": 0.0,
        "em_triangle_stage": "not_applicable",
        "em_breakout_volume_ratio": latest_ratio_number if latest_ratio_number is not None else "not_applicable",
        "em_gap_type": "not_applicable",
        "em_gap_direction": "not_applicable",
        "em_gap_confirmation": "not_confirmed",
        "em_gap_size_pips": 0.0,
        "em_sr_role": "not_applicable",
        "em_sr_retest": "not_applicable",
        "em_sr_confirmation": "not_confirmed",
        "em_sr_break_margin_pips": 0.0,
        "em_channel_direction": dominant if dominant in {"up", "down"} else "not_applicable",
        "em_channel_state": "not_applicable",
        "em_channel_confirmation": "not_confirmed",
        "em_channel_break_margin_pips": 0.0,
    }

    def set_setup(name: str) -> None:
        output["em_setups"].append(name)
        if output["em_setup"] == "none":
            output["em_setup"] = name

    # The six-bar shape is the smallest conservative proxy for the required
    # left shoulder, valley, head, valley, right shoulder, and confirmation.
    if len(bars) >= 6:
        left, valley_one, head, valley_two, right, break_bar = bars[-6:]
        neckline = (float(valley_one["low"]) + float(valley_two["low"])) / 2.0
        top_shape = (
            dominant == "up"
            and float(head["high"]) > float(left["high"]) + pip
            and float(right["high"]) < float(head["high"]) - pip
            and float(right["high"]) <= float(left["high"]) + 2.0 * pip
        )
        bottom_shape = (
            dominant == "down"
            and float(head["low"]) < float(left["low"]) - pip
            and float(right["low"]) > float(head["low"]) + pip
            and float(right["low"]) >= float(left["low"]) - 2.0 * pip
        )
        if top_shape or bottom_shape:
            setup = "head_shoulders_top" if top_shape else "head_shoulders_bottom"
            set_setup(setup)
            if top_shape:
                confirmed = float(break_bar["close"]) < neckline - pip
                margin = (neckline - float(break_bar["close"])) / max(pip, 1e-12)
                expected_break = "down"
            else:
                confirmed = float(break_bar["close"]) > neckline + pip
                margin = (float(break_bar["close"]) - neckline) / max(pip, 1e-12)
                expected_break = "up"
            output["em_breakout_direction"] = expected_break if confirmed else "not_applicable"
            output["em_breakout_confirmation"] = "confirmed" if confirmed else "not_confirmed"
            output["em_neckline_break_pips"] = max(0.0, margin)
            shoulder_activity = float(right["activity"])
            comparison = statistics.median([float(left["activity"]), float(head["activity"])])
            output["em_volume_pattern"] = (
                "right_shoulder_lower_volume"
                if shoulder_activity < comparison else "right_shoulder_volume_not_lower"
            )

    # A triangle needs four established reversals.  The final bar is kept out
    # of the boundaries and is used only as the possible breakout bar.
    if output["em_setup"] == "none" and len(prior) >= 4:
        triangle = prior[-4:]
        highs = [float(item["high"]) for item in triangle]
        lows = [float(item["low"]) for item in triangle]
        widths = [float(item["range"]) for item in triangle]
        descending_highs = all(a > b + 0.25 * pip for a, b in zip(highs, highs[1:]))
        rising_lows = all(a < b - 0.25 * pip for a, b in zip(lows, lows[1:]))
        horizontal_high = max(highs) - min(highs) <= 2.0 * pip
        horizontal_low = max(lows) - min(lows) <= 2.0 * pip
        contracting = all(a > b for a, b in zip(widths, widths[1:]))
        if contracting and ((descending_highs and rising_lows) or (horizontal_high and rising_lows) or (descending_highs and horizontal_low)):
            if horizontal_high and rising_lows:
                setup = "ascending_triangle"
            elif descending_highs and horizontal_low:
                setup = "descending_triangle"
            else:
                setup = "symmetrical_triangle"
            set_setup(setup)
            initial_width = max(widths[0], pip)
            progress = 1.0 - min(1.0, widths[-1] / initial_width)
            output["em_triangle_stage"] = (
                "early" if progress < 0.25
                else "half_to_three_quarters" if progress <= 0.75
                else "apex"
            )
            if float(latest["close"]) > highs[-1] + pip:
                output["em_breakout_direction"] = "up"
                output["em_breakout_confirmation"] = "confirmed"
            elif float(latest["close"]) < lows[-1] - pip:
                output["em_breakout_direction"] = "down"
                output["em_breakout_confirmation"] = "confirmed"
            output["em_breakout_volume_ratio"] = latest_ratio_number if latest_ratio_number is not None else "not_applicable"

    # Classify only the latest completed inter-bar gap.  A continuous FX feed
    # often has no such event; "not_applicable" is an honest result.
    gap_index = None
    gap_value = 0.0
    for index in range(1, len(bars)):
        value = float(bars[index]["open"]) - float(bars[index - 1]["close"])
        if abs(value) >= 2.0 * pip:
            gap_index = index
            gap_value = value
    if gap_index is not None:
        gap_bar = bars[gap_index]
        gap_direction = "up" if gap_value > 0 else "down"
        context = bars[max(0, gap_index - 4):gap_index]
        context_high = max((float(item["high"]) for item in context), default=float(gap_bar["open"]))
        context_low = min((float(item["low"]) for item in context), default=float(gap_bar["open"]))
        if (gap_direction == "up" and float(gap_bar["open"]) > context_high + pip) or (
            gap_direction == "down" and float(gap_bar["open"]) < context_low - pip
        ):
            gap_type = "breakaway"
        elif dominant in {"up", "down"} and gap_direction == dominant and gap_index >= 2:
            gap_type = "runaway"
        elif dominant in {"up", "down"} and gap_direction != dominant:
            gap_type = "exhaustion"
        else:
            gap_type = "area"
        output.update({
            "em_gap_type": gap_type,
            "em_gap_direction": gap_direction,
            "em_gap_size_pips": abs(gap_value) / max(pip, 1e-12),
        })
        if gap_type in {"breakaway", "runaway"}:
            held = (
                float(latest["close"]) > float(gap_bar["open"]) if gap_direction == "up"
                else float(latest["close"]) < float(gap_bar["open"])
            )
        elif gap_type == "exhaustion":
            held = (
                float(latest["close"]) < float(gap_bar["open"]) if gap_direction == "up"
                else float(latest["close"]) > float(gap_bar["open"])
            )
        else:
            held = False
        output["em_gap_confirmation"] = "confirmed" if held else "not_confirmed"

    # Role reversal: a decisive break, a retest of the old boundary, then a
    # close back in the new direction.
    if len(bars) >= 5:
        base_bars, break_bar, retest, confirm = bars[-5:-3], bars[-3], bars[-2], bars[-1]
        resistance = max(float(item["high"]) for item in base_bars)
        support = min(float(item["low"]) for item in base_bars)
        up_break = float(break_bar["close"]) > resistance + pip
        up_hold = float(retest["low"]) <= resistance + 2.0 * pip and float(confirm["close"]) > resistance + pip
        down_break = float(break_bar["close"]) < support - pip
        down_hold = float(retest["high"]) >= support - 2.0 * pip and float(confirm["close"]) < support - pip
        if up_break and up_hold:
            output.update({
                "em_sr_role": "resistance_to_support",
                "em_sr_retest": "held",
                "em_sr_confirmation": "confirmed",
                "em_sr_break_margin_pips": (float(break_bar["close"]) - resistance) / max(pip, 1e-12),
            })
        elif down_break and down_hold:
            output.update({
                "em_sr_role": "support_to_resistance",
                "em_sr_retest": "held",
                "em_sr_confirmation": "confirmed",
                "em_sr_break_margin_pips": (support - float(break_bar["close"])) / max(pip, 1e-12),
            })

    if dominant in {"up", "down"} and len(prior) >= 4:
        channel = prior[-4:]
        channel_direction = dominant
        if channel_direction == "up":
            lower_slope = (float(channel[-1]["low"]) - float(channel[0]["low"])) / 3.0
            projected_lower = float(channel[-1]["low"]) + lower_slope
            broken = float(latest["close"]) < projected_lower - pip
            failed_return = not broken and float(latest["high"]) < float(channel[-1]["high"]) - pip
            margin = (projected_lower - float(latest["close"])) / max(pip, 1e-12)
        else:
            upper_slope = (float(channel[-1]["high"]) - float(channel[0]["high"])) / 3.0
            projected_upper = float(channel[-1]["high"]) + upper_slope
            broken = float(latest["close"]) > projected_upper + pip
            failed_return = not broken and float(latest["low"]) > float(channel[-1]["low"]) + pip
            margin = (float(latest["close"]) - projected_upper) / max(pip, 1e-12)
        output.update({
            "em_channel_direction": channel_direction,
            "em_channel_state": "basic_line_broken" if broken else "return_line_failure" if failed_return else "established",
            "em_channel_confirmation": "confirmed" if broken else "not_confirmed",
            "em_channel_break_margin_pips": max(0.0, margin),
        })

    return output


def _chan_statistical_context(
    points: Sequence[Mapping[str, float]],
) -> dict[str, Any]:
    """Derive Chan's half-life prerequisite from prior log-quote levels.

    The source distinguishes descriptive stationarity diagnostics from a
    trading result.  This adapter therefore exposes only a causal regression
    half-life.  It does not invent ADF critical values or significance for
    Hurst/variance-ratio tests that require a separately calibrated test.
    """
    levels = [
        math.log(float(item["mid"]))
        for item in points
        if _finite(item.get("mid")) is not None and float(item["mid"]) > 0
    ]
    if len(levels) < 20:
        return {}
    x = levels[:-1]
    y = [current - previous for previous, current in zip(levels, levels[1:])]
    mean_x = statistics.fmean(x)
    mean_y = statistics.fmean(y)
    denominator = sum((value - mean_x) ** 2 for value in x)
    if denominator <= 0:
        return {}
    coefficient = sum((left - mean_x) * (right - mean_y) for left, right in zip(x, y)) / denominator
    intercept = mean_y - coefficient * mean_x
    residuals = [right - (intercept + coefficient * left) for left, right in zip(x, y)]
    degrees = len(x) - 2
    standard_error = math.sqrt(sum(value * value for value in residuals) / degrees / denominator) if degrees > 0 else 0.0
    result: dict[str, Any] = {
        "chan_mean_reversion_coefficient": coefficient,
        "chan_adf_coefficient": coefficient,
        "chan_adf_sample_n": len(x),
        "chan_adf_data_provenance": "observed_causal_log_quote_series",
        "chan_half_life_data_provenance": "observed_causal_log_quote_series",
    }
    if standard_error > 0:
        result["chan_adf_t_statistic"] = coefficient / standard_error
    if coefficient < 0:
        result["chan_mean_reversion_half_life"] = -math.log(2.0) / coefficient
    return result


def _dejong_roll_context(
    points: Sequence[Mapping[str, float]],
) -> dict[str, Any]:
    """Estimate Roll's spread only from observed, causal transaction prices.

    Bid/ask midpoints are deliberately not substituted: Roll's result is a
    transaction-price diagnostic, and a quote-only tape cannot supply it.
    """
    prices = [
        float(item["transaction_price"])
        for item in points
        if _finite(item.get("transaction_price")) is not None
        and float(item["transaction_price"]) > 0
    ]
    changes = [current - previous for previous, current in zip(prices, prices[1:])]
    if len(changes) < 3:
        return {}
    left = changes[:-1]
    right = changes[1:]
    mean_left = statistics.fmean(left)
    mean_right = statistics.fmean(right)
    autocovariance = statistics.fmean(
        (first - mean_left) * (second - mean_right)
        for first, second in zip(left, right)
    )
    result: dict[str, Any] = {
        "dejong_roll_autocovariance": autocovariance,
        "dejong_roll_sample_n": len(changes),
        "dejong_roll_data_provenance": "observed_causal_transaction_prices",
    }
    if autocovariance < 0:
        result["dejong_roll_spread_estimate"] = 2.0 * math.sqrt(-autocovariance)
    return result


def _chan_context(
    points: Sequence[Mapping[str, float]],
    now: float,
    pip: float,
    interval_s: float = 15.0,
) -> dict[str, Any]:
    """Derive only Chan observations recoverable from the copied quote tape.

    The book's event calendar, exchange trade flow, and level-two sizes are
    not inferred from FX mid prices.  Gap and stop-cascade fields are emitted
    only when completed quote bars provide the required causal observations;
    event/order-flow fields remain absent unless an upstream observer supplied
    them.
    """
    completed = _completed_quote_bars(points, now, interval_s)
    output: dict[str, Any] = {}
    if len(completed) >= 2:
        bars: list[dict[str, float]] = []
        for _, items in completed:
            bars.append({
                "open": float(items[0]["mid"]),
                "close": float(items[-1]["mid"]),
                "high": max(float(item["mid"]) for item in items),
                "low": min(float(item["mid"]) for item in items),
            })
        latest = bars[-1]
        prior = bars[:-1]
        gap = latest["open"] - prior[-1]["close"]
        returns = [
            current["open"] / previous["close"] - 1.0
            for previous, current in zip(bars, bars[1:])
            if previous["close"] > 0 and current["open"] > 0
        ]
        reference_volatility = _std(returns)
        if abs(gap) >= 2.0 * pip and reference_volatility is not None and reference_volatility > 0:
            output.update({
                "chan_gap_open_price": latest["open"],
                "chan_gap_prior_high": max(item["high"] for item in prior),
                "chan_gap_prior_low": min(item["low"] for item in prior),
                "chan_gap_reference_volatility": reference_volatility,
                "chan_gap_entry_zscore": 0.1,
                "chan_gap_data_provenance": "causal_completed_quote_bar_gap_proxy",
            })

    prior_points = [item for item in points if _finite(item.get("time")) is not None and item.get("time", now) < now]
    statistical = _chan_statistical_context(prior_points)
    if statistical:
        output.update(statistical)
    roll = _dejong_roll_context(points)
    if roll:
        output.update(roll)
    recent = _window(prior_points, now, 60.0)
    current = points[-1] if points else None
    current_mid = _finite(current.get("mid")) if isinstance(current, Mapping) else None
    if len(recent) >= 4 and current_mid is not None and current_mid > 0:
        high = max(float(item["mid"]) for item in recent)
        low = min(float(item["mid"]) for item in recent)
        if current_mid > high + pip:
            role = "resistance"
            confirmed = True
        elif current_mid < low - pip:
            role = "support"
            confirmed = True
        else:
            role = "resistance" if current_mid >= (high + low) / 2.0 else "support"
            confirmed = False
        output.update({
            "chan_stop_level": high if role == "resistance" else low,
            "chan_stop_price": current_mid,
            "chan_stop_level_role": role,
            "chan_stop_break_confirmed": confirmed,
            "chan_stop_data_provenance": "causal_quote_range_stop_proxy",
        })

    if isinstance(current, Mapping):
        bid_size = _finite(current.get("bid_size"))
        ask_size = _finite(current.get("ask_size"))
        if bid_size is not None and ask_size is not None and bid_size > 0 and ask_size > 0:
            output.update({
                "chan_bid_size": bid_size,
                "chan_ask_size": ask_size,
                "chan_imbalance_min_ratio": 2.0,
                "chan_imbalance_data_provenance": "observed_timestamped_level_two_quote",
            })
    signed_flow = [
        _finite(item.get("signed_order_flow"))
        for item in points[-20:]
        if _finite(item.get("signed_order_flow")) is not None
    ]
    if len(signed_flow) >= 2:
        total = sum(signed_flow)
        output.update({
            "chan_order_flow_value": total,
            "chan_order_flow_min_abs": max(1.0, statistics.fmean(abs(value) for value in signed_flow)),
            "chan_order_flow_lookback": len(signed_flow),
            "chan_order_flow_source": "real_transaction_signed_volume",
            "chan_order_flow_data_provenance": "observed_timestamped_signed_trade_flow",
        })
    return output


def _ponsi_context(
    points: Sequence[Mapping[str, float]],
    now: float,
    dominant: str,
    pip: float,
    *,
    session: Any = None,
    round_number_step: float | None = None,
    interval_s: float = 15.0,
) -> dict[str, Any]:
    """Derive causal proxies for distinct Ponsi setup rules.

    The source describes chart patterns and session behavior rather than an
    FX tick schema. This adapter uses completed quote bars only, labels tick
    observations as proxies, and leaves market-specific measurements absent
    when the copied state did not supply them.
    """
    completed = _completed_quote_bars(points, now, interval_s)
    if len(completed) < 5:
        return {}
    bars: list[dict[str, float | str]] = []
    for bucket, items in completed:
        opening = float(items[0]["mid"])
        closing = float(items[-1]["mid"])
        high = max(float(item["mid"]) for item in items)
        low = min(float(item["mid"]) for item in items)
        bars.append({
            "bucket": float(bucket),
            "open": opening,
            "close": closing,
            "high": high,
            "low": low,
            "range": max(0.0, high - low),
            "spread": max(float(item.get("spread", 0.0)) for item in items),
            "direction": "up" if closing > opening else "down" if closing < opening else "flat",
        })

    session_text = str(session or "").strip().lower().replace("_", " ")
    hour = datetime.fromtimestamp(now, tz=timezone.utc).hour
    if session_text:
        dead_zone = any(token in session_text for token in ("dead zone", "late asia", "low liquidity", "quiet"))
        high_liquidity = any(token in session_text for token in ("london", "new york", "high liquidity", "high volume", "overlap"))
        if dead_zone:
            session_quality = "dead_zone_low_liquidity"
        elif high_liquidity:
            session_quality = "high_liquidity"
        else:
            session_quality = "unclassified"
    else:
        dead_zone = hour >= 22 or hour < 2
        high_liquidity = 7 <= hour < 17
        session_quality = "dead_zone_low_liquidity" if dead_zone else "high_liquidity" if high_liquidity else "unclassified"

    output: dict[str, Any] = {
        "ponsi_data_provenance": "causal_completed_quote_bar_proxy",
        "ponsi_pattern": "not_applicable",
        "ponsi_flagpole_direction": "not_applicable",
        "ponsi_flagpole_impulse": False,
        "ponsi_consolidation_contracting": False,
        "ponsi_consolidation_bars": 0,
        "ponsi_breakout_direction": "not_applicable",
        "ponsi_breakout_confirmation": "not_confirmed",
        "ponsi_triangle_type": "not_applicable",
        "ponsi_prior_trend": dominant if dominant in {"up", "down"} else "not_applicable",
        "ponsi_session_quality": session_quality,
        "ponsi_dead_zone": dead_zone,
        "ponsi_time_remaining_s": "not_applicable",
        "ponsi_level_type": "not_applicable",
        "ponsi_first_bounce": False,
        "ponsi_reversal_direction": "not_applicable",
        "ponsi_entry_confirmation": "not_confirmed",
        "ponsi_round_number_test": "not_applicable",
        "ponsi_extension_from_ma_pips": "not_applicable",
        "ponsi_open_retest": False,
        "ponsi_reversal_confirmation": "not_confirmed",
        "ponsi_price_level": "not_applicable",
        "ponsi_approach_speed": "not_applicable",
        "ponsi_price_action": "not_observed",
        "ponsi_entry_order_location": "not_applicable",
        "ponsi_level_test_count": 0,
        "ponsi_round_trip_level": "not_applicable",
        "ponsi_round_trip_extension_pips": "not_applicable",
        "ponsi_round_trip_bounce_count": 0,
        "ponsi_round_trip_reversal_direction": "not_applicable",
        "ponsi_round_trip_spread_pips": "not_applicable",
    }

    prior = bars[:-1]
    latest = bars[-1]
    latest_close = float(latest["close"])
    if len(prior) >= 4:
        triangle = prior[-4:]
        highs = [float(item["high"]) for item in triangle]
        lows = [float(item["low"]) for item in triangle]
        widths = [float(item["range"]) for item in triangle]
        descending_highs = all(a > b + 0.25 * pip for a, b in zip(highs, highs[1:]))
        rising_lows = all(a < b - 0.25 * pip for a, b in zip(lows, lows[1:]))
        horizontal_high = max(highs) - min(highs) <= 2.0 * pip
        horizontal_low = max(lows) - min(lows) <= 2.0 * pip
        contracting = all(a > b for a, b in zip(widths, widths[1:]))
        if contracting and ((horizontal_high and rising_lows) or (descending_highs and horizontal_low) or (descending_highs and rising_lows)):
            output["ponsi_triangle_type"] = (
                "ascending_triangle" if horizontal_high and rising_lows
                else "descending_triangle" if descending_highs and horizontal_low
                else "symmetrical_triangle"
            )
            upper = max(highs)
            lower = min(lows)
            if latest_close > upper + pip:
                output["ponsi_breakout_direction"] = "up"
                output["ponsi_breakout_confirmation"] = "confirmed"
            elif latest_close < lower - pip:
                output["ponsi_breakout_direction"] = "down"
                output["ponsi_breakout_confirmation"] = "confirmed"

    if len(bars) >= 5:
        flagpole = bars[-5:-3]
        pause = bars[-3:-1]
        impulse = float(flagpole[-1]["close"]) - float(flagpole[0]["open"])
        pause_ranges = [float(item["range"]) for item in pause]
        contraction = len(pause_ranges) == 2 and pause_ranges[0] > pause_ranges[1] > 0
        pause_high = max(float(item["high"]) for item in pause)
        pause_low = min(float(item["low"]) for item in pause)
        flagpole_direction = "up" if impulse > 0 else "down" if impulse < 0 else "not_applicable"
        impulse_large = abs(impulse) >= max(2.0 * max(pause_ranges or [pip]), 2.0 * pip)
        breakout_direction = (
            "up" if latest_close > pause_high + pip
            else "down" if latest_close < pause_low - pip
            else "not_applicable"
        )
        if flagpole_direction in {"up", "down"} and impulse_large:
            output["ponsi_flagpole_direction"] = flagpole_direction
            output["ponsi_flagpole_impulse"] = True
        if contraction:
            output["ponsi_consolidation_contracting"] = True
            output["ponsi_consolidation_bars"] = len(pause)
        if (
            output["ponsi_flagpole_impulse"]
            and output["ponsi_consolidation_contracting"]
            and breakout_direction == flagpole_direction
        ):
            output["ponsi_pattern"] = "pennant"
            output["ponsi_breakout_direction"] = breakout_direction
            output["ponsi_breakout_confirmation"] = "confirmed"

    if len(prior) >= 3:
        support = min(float(item["low"]) for item in prior[-3:])
        resistance = max(float(item["high"]) for item in prior[-3:])
        tolerance = max(2.0 * pip, (resistance - support) * 0.05)
        prior_support_touches = sum(float(item["low"]) <= support + tolerance for item in prior[:-1])
        prior_resistance_touches = sum(float(item["high"]) >= resistance - tolerance for item in prior[:-1])
        prior_ranges = [float(item["range"]) for item in prior if float(item["range"]) > 0]
        typical_range = statistics.median(prior_ranges) if prior_ranges else None
        if float(latest["low"]) <= support + tolerance and latest_close > float(latest["open"]) and latest_close > support + pip:
            output.update({
                "ponsi_level_type": "support",
                "ponsi_first_bounce": prior_support_touches == 0,
                "ponsi_reversal_direction": "up",
                "ponsi_entry_confirmation": "confirmed",
                "ponsi_price_level": "support",
                "ponsi_price_action": "rejection",
                "ponsi_entry_order_location": "above support",
                "ponsi_level_test_count": prior_support_touches + 1,
            })
            approach_distance = abs(float(prior[-1]["close"]) - float(latest["low"]))
            output["ponsi_approach_speed"] = "fast" if typical_range and approach_distance > 1.5 * typical_range else "measured"
        elif float(latest["high"]) >= resistance - tolerance and latest_close < float(latest["open"]) and latest_close < resistance - pip:
            output.update({
                "ponsi_level_type": "resistance",
                "ponsi_first_bounce": prior_resistance_touches == 0,
                "ponsi_reversal_direction": "down",
                "ponsi_entry_confirmation": "confirmed",
                "ponsi_price_level": "resistance",
                "ponsi_price_action": "rejection",
                "ponsi_entry_order_location": "below resistance",
                "ponsi_level_test_count": prior_resistance_touches + 1,
            })
            approach_distance = abs(float(prior[-1]["close"]) - float(latest["high"]))
            output["ponsi_approach_speed"] = "fast" if typical_range and approach_distance > 1.5 * typical_range else "measured"

    if round_number_step is not None and round_number_step > 0:
        moving_average = statistics.mean(float(item["close"]) for item in prior[-20:])
        level = round(latest_close / round_number_step) * round_number_step
        if abs(latest_close - level) <= max(2.0 * pip, round_number_step * 0.1):
            extension = abs(latest_close - moving_average) / max(pip, 1e-12)
            if extension >= 20.0:
                output["ponsi_round_number_test"] = "support" if latest_close >= moving_average else "resistance"
                output["ponsi_extension_from_ma_pips"] = extension
                round_level = output["ponsi_round_number_test"]
                reversal = "up" if latest_close > float(latest["open"]) else "down" if latest_close < float(latest["open"]) else "not_applicable"
                prior_round_tests = sum(
                    1
                    for item in prior
                    if abs(float(item["high"]) - level) <= max(2.0 * pip, round_number_step * 0.1)
                    or abs(float(item["low"]) - level) <= max(2.0 * pip, round_number_step * 0.1)
                )
                output.update({
                    "ponsi_round_trip_level": round_level,
                    "ponsi_round_trip_extension_pips": extension,
                    "ponsi_round_trip_bounce_count": max(1, prior_round_tests + 1),
                    "ponsi_round_trip_reversal_direction": reversal,
                    "ponsi_round_trip_spread_pips": max(0.0, float(latest.get("spread", 0.0))) / max(pip, 1e-12),
                })

    if dead_zone and output["ponsi_breakout_direction"] in {"up", "down"}:
        output["ponsi_reversal_confirmation"] = "confirmed" if output["ponsi_pattern"] != "not_applicable" else "not_confirmed"
        output["ponsi_open_retest"] = output["ponsi_reversal_confirmation"] == "confirmed"

    return output


def _nison_context(
    points: Sequence[Mapping[str, float]],
    now: float,
    pip: float,
    interval_s: float = 15.0,
) -> dict[str, Any]:
    """Build a causal three-line-break proxy from completed quote-bar closes."""
    completed = _completed_quote_bars(points, now, interval_s)
    if len(completed) < 4:
        return {}
    closes = [float(items[-1]["mid"]) for _, items in completed]
    line_values = [closes[0]]
    line_directions: list[str] = []
    direction: str | None = None
    for price in closes[1:]:
        if direction is None:
            if price == line_values[-1]:
                continue
            direction = "up" if price > line_values[-1] else "down"
            line_values.append(price)
            line_directions.append(direction)
            continue
        if direction == "up" and price > line_values[-1]:
            line_values.append(price)
            line_directions.append("up")
        elif direction == "down" and price < line_values[-1]:
            line_values.append(price)
            line_directions.append("down")
        elif direction == "up" and len(line_values) >= 4 and price < min(line_values[-3:]):
            direction = "down"
            line_values.append(price)
            line_directions.append("down")
        elif direction == "down" and len(line_values) >= 4 and price > max(line_values[-3:]):
            direction = "up"
            line_values.append(price)
            line_directions.append("up")
    trailing = 0
    if line_directions:
        latest_direction = line_directions[-1]
        for item in reversed(line_directions):
            if item != latest_direction:
                break
            trailing += 1
    else:
        latest_direction = "not_applicable"
    return {
        "nison_three_line_direction": latest_direction,
        "nison_three_line_consecutive": trailing,
        "nison_three_line_confirmation": "confirmed" if trailing >= 3 else "not_confirmed",
        "nison_data_provenance": "causal_price_filtered_quote_bar_proxy",
    }


def _aziz_context(
    points: Sequence[Mapping[str, float]],
    now: float,
    pip: float,
    interval_s: float = 60.0,
) -> dict[str, Any]:
    """Derive conservative, point-in-time Aziz playbook proxies.

    The book's setups are stock-day-trading concepts.  This adapter only
    emits a clearly labelled quote-bar/day-range proxy when the required
    structure is observable.  Tick count or broker tick volume never becomes
    real exchange volume; volume-dependent perspectives remain WAIT when no
    volume observation is present.
    """
    completed = _completed_quote_bars(points, now, interval_s)
    if len(completed) < 4 or not points:
        return {}

    bars: list[dict[str, Any]] = []
    for _, items in completed:
        opening = float(items[0]["mid"])
        closing = float(items[-1]["mid"])
        volume_values = [
            _finite(item.get("tick_volume"))
            for item in items
        ]
        volume_values = [value for value in volume_values if value is not None]
        bars.append({
            "open": opening,
            "close": closing,
            "high": max(float(item["mid"]) for item in items),
            "low": min(float(item["mid"]) for item in items),
            "range": max(float(item["mid"]) for item in items) - min(float(item["mid"]) for item in items),
            "direction": "up" if closing > opening else "down" if closing < opening else "flat",
            "volume": sum(volume_values) if volume_values else None,
        })

    current = points[-1]
    current_mid = float(current["mid"])
    result: dict[str, Any] = {}
    source_provenance = "causal_completed_quote_bar_proxy"

    # ABCD: two-bar impulse, a contained C pullback, and a holding bar close
    # near C.  The current quote is used only for the point-in-time entry
    # proximity check.
    if len(bars) >= 4:
        a, b, c, hold = bars[-4:]
        impulse = b["direction"] == "up" and a["direction"] == "up" and b["high"] > a["high"] + pip
        c_support = float(c["low"])
        contained = c_support >= float(a["low"]) - pip and float(hold["close"]) > c_support + pip
        near_c = abs(current_mid - c_support) <= max(3.0 * pip, (float(b["high"]) - float(a["low"])) * 0.25)
        if impulse and contained:
            result.update({
                "aziz_abcd_impulse_direction": "up",
                "aziz_abcd_point_b_confirmed": True,
                "aziz_abcd_point_c_support": c_support,
                "aziz_abcd_c_support_holds": True,
                "aziz_abcd_entry_near_c": near_c,
                "aziz_abcd_stop_defined": True,
                "aziz_abcd_data_provenance": source_provenance,
            })

    # Bull flag: an upward pole, one or two small consolidation bars, and a
    # current-quote break.  Volume confirmation is emitted only when broker
    # tick-volume observations exist; otherwise it is explicitly false.
    if len(bars) >= 5:
        for consolidation_count in (1, 2):
            pole_end = len(bars) - consolidation_count
            pole = bars[pole_end - 3:pole_end]
            flag = bars[pole_end:]
            if len(pole) != 3 or len(flag) != consolidation_count:
                continue
            pole_ranges = [float(item["range"]) for item in pole]
            flag_ranges = [float(item["range"]) for item in flag]
            pole_up = all(item["direction"] == "up" for item in pole) and pole[-1]["high"] > pole[0]["high"] + pip
            flag_tight = max(flag_ranges, default=0.0) <= max(statistics.median(pole_ranges) * 0.75, 2.0 * pip)
            flag_high = max(float(item["high"]) for item in flag)
            breakout = current_mid > flag_high + pip
            if not (pole_up and flag_tight and breakout):
                continue
            flag_volume = [item["volume"] for item in flag if item["volume"] is not None]
            current_volume = _finite(current.get("tick_volume"))
            volume_ok = bool(flag_volume and current_volume is not None and current_volume > statistics.mean(flag_volume) * 1.05)
            result.update({
                "aziz_bull_flag_pole_direction": "up",
                "aziz_bull_flag_consolidation": True,
                "aziz_bull_flag_consolidation_count": consolidation_count,
                "aziz_bull_flag_breakout_confirmation": True,
                "aziz_bull_flag_volume_confirmation": volume_ok,
                "aziz_bull_flag_stop_defined": True,
                "aziz_bull_flag_data_provenance": source_provenance,
            })
            break

    # Previous-close transition: use only the last observed point from the
    # preceding UTC day and today's pre-current observations.
    moment = datetime.fromtimestamp(now, tz=timezone.utc)
    day_start = moment.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    previous_day = [
        item for item in points
        if day_start - 86400.0 <= item.get("time", -math.inf) < day_start
    ]
    today_prior = [
        item for item in points[:-1]
        if day_start <= item.get("time", -math.inf) < now
    ]
    if previous_day and today_prior:
        previous_close = float(previous_day[-1]["mid"])
        prior_mid = float(today_prior[-1]["mid"])
        transition = None
        if prior_mid < previous_close and current_mid > prior_mid and current_mid <= previous_close + pip:
            transition = "red_to_green"
        elif prior_mid > previous_close and current_mid < prior_mid and current_mid >= previous_close - pip:
            transition = "green_to_red"
        if transition:
            prior_volumes = [_finite(item.get("tick_volume")) for item in today_prior[-20:]]
            prior_volumes = [value for value in prior_volumes if value is not None]
            current_volume = _finite(current.get("tick_volume"))
            volume_ok = bool(prior_volumes and current_volume is not None and current_volume > statistics.mean(prior_volumes) * 1.05)
            result.update({
                "aziz_rtg_transition": transition,
                "aziz_rtg_previous_close": previous_close,
                "aziz_rtg_moving_toward_level": True,
                "aziz_rtg_volume_confirmation": volume_ok,
                "aziz_rtg_stop_defined": len(today_prior) >= 3,
                "aziz_rtg_target_defined": True,
                "aziz_rtg_data_provenance": "causal_previous_day_close_quote_proxy",
            })

    # BHOD: the current quote must break a repeated high-of-day level after a
    # pullback.  Count touch episodes rather than every tick at the level.
    if len(today_prior) >= 5:
        high = max(float(item["mid"]) for item in today_prior)
        tolerance = max(2.0 * pip, (high - min(float(item["mid"]) for item in today_prior)) * 0.01)
        touches = 0
        near_previous = False
        for item in today_prior:
            near = abs(float(item["mid"]) - high) <= tolerance
            if near and not near_previous:
                touches += 1
            near_previous = near
        pullback = min(float(item["mid"]) for item in today_prior[-max(5, len(today_prior) // 2):]) < high - 2.0 * pip
        current_volume = _finite(current.get("tick_volume"))
        prior_volumes = [_finite(item.get("tick_volume")) for item in today_prior[-20:]]
        prior_volumes = [value for value in prior_volumes if value is not None]
        volume_ok = bool(prior_volumes and current_volume is not None and current_volume > statistics.mean(prior_volumes) * 1.05)
        if current_mid > high + pip:
            result.update({
                "aziz_bhod_level": high,
                "aziz_bhod_break_direction": "up",
                "aziz_bhod_prior_level_touches": touches,
                "aziz_bhod_break_confirmation": True,
                "aziz_bhod_pullback_quality": "decent" if pullback else "poor",
                "aziz_bhod_volume_confirmation": volume_ok,
                "aziz_bhod_stop_defined": True,
                "aziz_bhod_data_provenance": "causal_quote_day_range_proxy",
            })
    return result


def _price_in_time_context(
    points: Sequence[Mapping[str, float]],
    now: float,
    pip: float,
) -> dict[str, Any]:
    """Derive the European double-open range without using future quotes.

    The source uses the 07:00-08:00 GMT Frankfurt/London overlap as a
    no-trading zone.  This adapter measures that completed UTC window from
    bid/ask observations and treats the Asian-day exclusion as an explicit
    quote-range proxy; it does not claim to observe the author's discretionary
    anomaly classification.
    """
    moment = datetime.fromtimestamp(now, tz=timezone.utc)
    day_start = moment.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    ntz_start = day_start + 7.0 * 3600.0
    ntz_end = day_start + 8.0 * 3600.0
    if now < ntz_end:
        return {}
    ntz = [item for item in points if ntz_start <= item.get("time", -math.inf) < ntz_end]
    if len(ntz) < 2:
        return {}
    ntz = sorted(ntz, key=lambda item: item.get("time", -math.inf))
    high = max(float(item["mid"]) for item in ntz)
    low = min(float(item["mid"]) for item in ntz)
    opening_price = float(ntz[0]["mid"])
    width = max(0.0, high - low) / max(pip, 1e-12)
    ordered_points = sorted(points, key=lambda item: item.get("time", -math.inf))
    current = float(ordered_points[-1]["mid"])
    previous = float(ordered_points[-2]["mid"]) if len(ordered_points) >= 2 else None
    opening_relation = "above" if current > opening_price else "below" if current < opening_price else "at"
    opening_cross = "none"
    if previous is not None:
        if previous <= opening_price < current:
            opening_cross = "up"
        elif previous >= opening_price > current:
            opening_cross = "down"
    if current > high + pip:
        breakout = "up"
        confirmation = "confirmed"
    elif current < low - pip:
        breakout = "down"
        confirmation = "confirmed"
    else:
        breakout = "not_applicable"
        confirmation = "not_confirmed"

    asian_start = day_start - 2.0 * 3600.0
    asian = [item for item in points if asian_start <= item.get("time", -math.inf) < ntz_start]
    anomaly = "not_observed"
    asian_width_pips = None
    if len(asian) >= 2:
        asian_width = max(float(item["mid"]) for item in asian) - min(float(item["mid"]) for item in asian)
        asian_width_pips = asian_width / max(pip, 1e-12)
        anomaly = "anomalous_quote_range_proxy" if asian_width_pips > 40.0 else "not_anomalous_quote_range_proxy"
    if 22 <= moment.hour or moment.hour < 7:
        session_window = "asian"
    elif moment.hour < 8:
        session_window = "frankfurt_ntz"
    elif moment.hour < 13:
        session_window = "london_morning"
    elif moment.hour < 17:
        session_window = "london_new_york_overlap"
    else:
        session_window = "post_london"
    return {
        "pit_session": "london_after_0800_gmt" if 8 <= moment.hour < 17 else "outside_london_window",
        "pit_session_window": session_window,
        "pit_session_data_provenance": "observed GMT session clock",
        "pit_europe_open_price": opening_price,
        "pit_current_price": current,
        "pit_opening_price_relation": opening_relation,
        "pit_opening_cross_direction": opening_cross,
        "pit_opening_data_provenance": "observed causal Frankfurt opening quote",
        "pit_ntz_width_pips": width,
        "pit_breakout_direction": breakout,
        "pit_breakout_confirmation": confirmation,
        "pit_inside_ntz": low <= current <= high,
        "pit_anomalous_day": anomaly,
        "pit_asian_width_pips": asian_width_pips,
        "pit_asian_range_limit_pips": 40.0,
        "pit_anomaly_data_provenance": "observed causal Asian quote range" if asian_width_pips is not None else "not_observed",
        "pit_data_provenance": "causal_session_range_quote_proxy",
    }


def _al_brooks_second_entry_context(
    points: Sequence[Mapping[str, float]],
    now: float,
    dominant: str,
    interval_s: float = 15.0,
) -> dict[str, Any]:
    """Detect a conservative second-entry proxy from completed quote bars.

    A second entry is represented as two separated counter-trend attempts in
    the prevailing direction followed by a signal bar that clears the prior
    pullback bar.  This is an observable quote-bar proxy, not a claim that
    sparse FX quotes reproduce every discretionary Brooks annotation.
    """
    if dominant not in {"up", "down"}:
        return {}
    completed = _completed_quote_bars(points, now, interval_s)
    if len(completed) < 5:
        return {}
    bars: list[dict[str, float | str]] = []
    for _, items in completed:
        opening = items[0]["mid"]
        closing = items[-1]["mid"]
        bars.append({
            "open": opening,
            "close": closing,
            "high": max(item["mid"] for item in items),
            "low": min(item["mid"] for item in items),
            "direction": "bullish" if closing > opening else "bearish" if closing < opening else "doji",
        })
    recent = bars[-5:]
    target = "bullish" if dominant == "up" else "bearish"
    opposing = "bearish" if target == "bullish" else "bullish"
    directions = [str(item["direction"]) for item in recent]
    setup = directions == [target, opposing, target, opposing, target]
    confirmation = False
    if setup:
        signal_bar = recent[-1]
        pullback_bar = recent[-2]
        confirmation = (
            float(signal_bar["close"]) > float(pullback_bar["high"])
            if target == "bullish"
            else float(signal_bar["close"]) < float(pullback_bar["low"])
        )
    return {
        "second_entry_direction": "up" if target == "bullish" else "down",
        "second_entry_number": 2 if setup else 0,
        "second_entry_context": "bullish_pullback" if target == "bullish" else "bearish_pullback",
        "second_entry_confirmation": "quote_bar_proxy_confirmed" if confirmation else "quote_bar_proxy_unconfirmed",
        "second_entry_bar_end_time": (completed[-1][0] + 1) * interval_s,
        "second_entry_data_provenance": "completed_quote_bar_proxy",
    }


def _al_brooks_extended_context(
    points: Sequence[Mapping[str, float]],
    now: float,
    dominant: str,
    pip: float,
    interval_s: float = 15.0,
) -> dict[str, Any]:
    """Derive conservative Brooks structure labels from completed quote bars.

    These are explicit quote-bar proxies, not discretionary annotations.  A
    label is emitted only after its bar sequence and confirmation are visible
    at the copied timestamp; otherwise the corresponding perspective remains
    unavailable.
    """
    completed = _completed_quote_bars(points, now, interval_s)
    if len(completed) < 4:
        return {}
    bars: list[dict[str, float | str]] = []
    for _, items in completed:
        opening = float(items[0]["mid"])
        closing = float(items[-1]["mid"])
        bars.append({
            "open": opening,
            "close": closing,
            "high": max(float(item["mid"]) for item in items),
            "low": min(float(item["mid"]) for item in items),
            "direction": "bullish" if closing > opening else "bearish" if closing < opening else "doji",
        })
    result: dict[str, Any] = {}
    if dominant in {"up", "down"} and len(bars) >= 4:
        target = "bullish" if dominant == "up" else "bearish"
        opposing = "bearish" if target == "bullish" else "bullish"
        latest = bars[-1]
        count = 0
        index = len(bars) - 2
        while index >= 0 and bars[index]["direction"] == opposing and count < 5:
            count += 1
            index -= 1
        prior = bars[: len(bars) - 1 - count] if count else []
        prior_strength = sum(item["direction"] == target for item in prior[-4:]) >= 2
        pullback = bars[len(bars) - 1 - count : -1] if count else []
        if target == "bullish":
            confirmation = bool(pullback) and latest["close"] > max(item["high"] for item in pullback)
        else:
            confirmation = bool(pullback) and latest["close"] < min(item["low"] for item in pullback)
        if 1 <= count <= 4 and prior_strength and latest["direction"] == target and confirmation:
            result.update({
                "bar_count_direction": "up" if target == "bullish" else "down",
                "bar_count": count,
                "bar_count_context": "bullish pullback" if target == "bullish" else "bearish pullback",
                "bar_count_trendline_break": True,
                "bar_count_confirmation": "quote_bar_proxy_confirmed",
            })

    if len(bars) >= 7 and dominant in {"up", "down"}:
        window = bars[-7:]
        before_signal = window[:-1]
        signal_bar = window[-1]
        if dominant == "up":
            pushes = [
                item for index, item in enumerate(before_signal[1:], 1)
                if item["high"] > max(float(prior["high"]) for prior in before_signal[:index]) + pip
            ]
            confirmation = signal_bar["direction"] == "bearish" and signal_bar["close"] < min(item["low"] for item in before_signal[-2:])
            reversal = "SELL"
        else:
            pushes = [
                item for index, item in enumerate(before_signal[1:], 1)
                if item["low"] < min(float(prior["low"]) for prior in before_signal[:index]) - pip
            ]
            confirmation = signal_bar["direction"] == "bullish" and signal_bar["close"] > max(item["high"] for item in before_signal[-2:])
            reversal = "BUY"
        if len(pushes) >= 3 and confirmation:
            increments = []
            for previous, current in zip(pushes, pushes[1:]):
                increments.append(abs(float(current["high"] if reversal == "SELL" else current["low"]) - float(previous["high"] if reversal == "SELL" else previous["low"])))
            if not increments or increments[-1] <= max(increments[0], pip * 2.0):
                result.update({
                    "wedge_reversal_direction": reversal,
                    "wedge_pushes": len(pushes),
                    "wedge_trendline_break": True,
                    "wedge_overshoot": True,
                    "wedge_confirmation": "quote_bar_proxy_confirmed",
                })

    if len(points) >= 12:
        split = max(4, len(points) // 3)
        baseline = points[:split]
        high = max(float(item["mid"]) for item in baseline)
        low = min(float(item["mid"]) for item in baseline)
        tolerance = max((high - low) * 0.02, pip)
        phase = "none"
        for item in points[split:]:
            value = float(item["mid"])
            if phase == "none" and value > high + tolerance:
                phase = "up_break"
            elif phase == "up_break" and value < high - tolerance:
                phase = "up_failed"
            elif phase == "up_failed" and value > high + tolerance:
                result.update({
                    "failed_failure_direction": "BUY",
                    "initial_breakout_failed": True,
                    "failure_of_failure": True,
                    "failed_failure_confirmation": "quote_rebreak_confirmed",
                })
                break
            elif phase == "none" and value < low - tolerance:
                phase = "down_break"
            elif phase == "down_break" and value > low + tolerance:
                phase = "down_failed"
            elif phase == "down_failed" and value < low - tolerance:
                result.update({
                    "failed_failure_direction": "SELL",
                    "initial_breakout_failed": True,
                    "failure_of_failure": True,
                    "failed_failure_confirmation": "quote_rebreak_confirmed",
                })
                break

    if len(bars) >= 7:
        spike_index = len(bars) - 5
        spike = bars[spike_index]
        prior_ranges = [float(item["high"]) - float(item["low"]) for item in bars[max(0, spike_index - 3) : spike_index]]
        median_range = statistics.median(prior_ranges) if prior_ranges else 0.0
        channel = bars[spike_index + 1 : -1]
        spike_direction = spike["direction"]
        if median_range > 0 and float(spike["high"]) - float(spike["low"]) >= 2.0 * median_range and len(channel) >= 2 and all(item["direction"] == spike_direction for item in channel):
            if spike_direction == "bullish":
                held = all(float(item["low"]) >= float(spike["open"]) for item in channel) and bars[-1]["close"] >= channel[-1]["close"]
                signal = "BUY"
            else:
                held = all(float(item["high"]) <= float(spike["open"]) for item in channel) and bars[-1]["close"] <= channel[-1]["close"]
                signal = "SELL"
            if held:
                result.update({
                    "spike_channel_signal": signal,
                    "spike_channel_state": "spike_then_channel",
                    "spike_channel_test": "held",
                    "spike_channel_confirmation": "quote_bar_proxy_confirmed",
                    "spike_channel_provenance": "completed_quote_bar_proxy",
                })

    if len(bars) >= 6:
        first, second = bars[-6], bars[-4]
        ranges = [float(item["high"]) - float(item["low"]) for item in bars[-6:]]
        tolerance = max(pip * 2.0, (statistics.median(ranges) if ranges else pip) * 0.5)
        if dominant == "up" and abs(float(first["low"]) - float(second["low"])) <= tolerance:
            held = all(float(item["low"]) >= float(second["low"]) - tolerance for item in bars[-3:])
            breakout = bars[-1]["close"] > max(float(item["high"]) for item in bars[-3:-1])
            if held and breakout:
                result.update({
                    "double_flag_type": "double_bottom_bull_flag",
                    "double_flag_second_test": "held",
                    "double_flag_confirmation": "quote_bar_proxy_confirmed",
                })
        elif dominant == "down" and abs(float(first["high"]) - float(second["high"])) <= tolerance:
            held = all(float(item["high"]) <= float(second["high"]) + tolerance for item in bars[-3:])
            breakout = bars[-1]["close"] < min(float(item["low"]) for item in bars[-3:-1])
            if held and breakout:
                result.update({
                    "double_flag_type": "double_top_bear_flag",
                    "double_flag_second_test": "held",
                    "double_flag_confirmation": "quote_bar_proxy_confirmed",
                })

    if dominant == "range" and len(points) >= 6:
        prior_points = points[:-1]
        recent = _window(prior_points, now, 300.0)
        if len(recent) >= 4:
            range_high = max(float(item["mid"]) for item in recent)
            range_low = min(float(item["mid"]) for item in recent)
            width = range_high - range_low
            if width >= pip:
                position = (float(points[-1]["mid"]) - range_low) / width
                location = "lower_edge" if position <= 0.2 else "upper_edge" if position >= 0.8 else "middle"
                result.update({
                    "range_state": "range",
                    "range_location": location,
                    "range_location_provenance": "observed_quote_range_proxy",
                    "range_location_confirmation": "observed",
                })
    return result


def _brooks_range_rules_context(
    points: Sequence[Mapping[str, float]],
    now: float,
    pip: float,
    interval_s: float = 15.0,
) -> dict[str, Any]:
    """Derive the newer Brooks range rules from completed quote bars.

    The source terms are discretionary chart descriptions.  The Watcher
    exposes conservative, causal proxies: breakout increments for shrinking
    stairs, a three-bar non-overlap context for a micro-measuring gap, and a
    directional spike/continuation context for always-in mode.  These fields
    are descriptive research inputs only; the individual modules still decide
    whether the observation is supportive or a warning.
    """
    completed = _completed_quote_bars(points, now, interval_s)
    if len(completed) < 3:
        return {}
    bars: list[dict[str, float | str]] = []
    for _, items in completed:
        opening = float(items[0]["mid"])
        closing = float(items[-1]["mid"])
        bars.append({
            "open": opening,
            "close": closing,
            "high": max(float(item["mid"]) for item in items),
            "low": min(float(item["mid"]) for item in items),
            "direction": "up" if closing > opening else "down" if closing < opening else "flat",
        })
    directional = [item for item in bars if item["direction"] in {"up", "down"}]
    if not directional:
        return {}
    up_count = sum(item["direction"] == "up" for item in directional)
    down_count = sum(item["direction"] == "down" for item in directional)
    direction = "up" if up_count > down_count else "down" if down_count > up_count else None
    result: dict[str, Any] = {}

    # A breakout increment is measured against the immediately prior bar in
    # the same direction.  Requiring a real break keeps flat/overlapping bars
    # out of the shrinking-stairs sequence.
    if direction in {"up", "down"}:
        breakout_sizes: list[float] = []
        for previous, current in zip(bars, bars[1:]):
            if direction == "up" and current["high"] > previous["high"] + pip:
                breakout_sizes.append((current["high"] - previous["high"]) / pip)
            elif direction == "down" and current["low"] < previous["low"] - pip:
                breakout_sizes.append((previous["low"] - current["low"]) / pip)
        if len(breakout_sizes) >= 3:
            result.update({
                "brooks_stairs_direction": direction,
                "brooks_stairs_breakout_sizes": breakout_sizes,
                "brooks_stairs_data_provenance": "completed_quote_bar_proxy",
            })

    # Use the most recent complete three-bar window.  The middle bar is the
    # candidate trend bar; its surrounding non-overlap is tested by the
    # dedicated perspective rather than assumed here.
    before, trend, after = bars[-3:]
    trend_range = trend["high"] - trend["low"]
    trend_body = abs(trend["close"] - trend["open"])
    trend_direction = trend["direction"] if trend["direction"] in {"up", "down"} else "flat"
    result.update({
        "brooks_gap_trend_direction": trend_direction,
        "brooks_gap_trend_bar_strength": (
            "strong" if trend_range >= pip and trend_body / max(trend_range, pip) >= 0.65 else "weak"
        ),
        "brooks_gap_before_high": before["high"],
        "brooks_gap_before_low": before["low"],
        "brooks_gap_after_high": after["high"],
        "brooks_gap_after_low": after["low"],
        "brooks_gap_data_provenance": "completed_quote_bar_proxy",
    })

    # Always-in mode is a continuation context only when the last three bars
    # agree.  A spike is observed when any of those bars has a large body and
    # a non-trivial range; no future bar is consulted.
    recent = bars[-3:]
    recent_directions = {str(item["direction"]) for item in recent}
    mode = direction in {"up", "down"} and recent_directions == {direction}
    spike_confirmed = any(
        (item["high"] - item["low"]) >= pip
        and abs(item["close"] - item["open"]) / max(item["high"] - item["low"], pip) >= 0.65
        for item in recent
    )
    result.update({
        "brooks_always_in_mode": mode,
        "brooks_always_in_direction": direction or "unresolved",
        "brooks_always_in_spike_confirmed": spike_confirmed,
        "brooks_always_in_data_provenance": "completed_quote_bar_proxy",
    })
    return result


def _brooks_two_reasons_context(result: Mapping[str, Any], dominant: str | None) -> dict[str, Any]:
    """Build causal inputs for Brooks' two-reasons discipline.

    These are observed quote-bar/chart proxies, not a claim that two
    correlated indicators are independent reasons.  The perspective keeps the
    raw reason labels visible so a later study can audit that assumption.
    """
    candidate_side = str(result.get("side") or "").upper()
    candidate_direction = "up" if candidate_side == "BUY" else "down" if candidate_side == "SELL" else None
    if candidate_direction is None:
        return {}

    confirmed = lambda value: str(value or "").strip().lower() in {
        "confirmed", "quote_bar_proxy_confirmed", "observed", "true",
    }
    second_entry = result.get("second_entry_number") == 2 and confirmed(result.get("second_entry_confirmation"))
    overshoot_reversal = bool(result.get("wedge_overshoot")) and confirmed(result.get("wedge_confirmation"))
    strong_trend = bool(
        result.get("brooks_always_in_mode")
        and result.get("brooks_always_in_direction") == candidate_direction
        and result.get("brooks_always_in_spike_confirmed")
    )
    countertrend = dominant in {"up", "down"} and candidate_direction != dominant
    reasons: list[str] = []
    if second_entry:
        reasons.append("second entry")
    if overshoot_reversal:
        reasons.append("trendline overshoot reversal")
    if strong_trend:
        reasons.append("always-in strong trend")
    if result.get("bar_count_direction") == candidate_direction and confirmed(result.get("bar_count_confirmation")):
        reasons.append("bar-count pullback")
    if result.get("brooks_gap_trend_direction") == candidate_direction and result.get("brooks_gap_trend_bar_strength") == "strong":
        reasons.append("strong breakout context")
    location = result.get("range_location")
    if (candidate_side == "BUY" and location == "lower_edge") or (candidate_side == "SELL" and location == "upper_edge"):
        reasons.append("range-edge test")
    if not reasons:
        reasons.append("no qualifying observed reason")
    return {
        "brooks_entry_reasons": reasons,
        "brooks_strong_trend": strong_trend,
        "brooks_second_entry": second_entry,
        "brooks_trendline_overshoot_reversal": overshoot_reversal,
        "brooks_countertrend": countertrend,
        "brooks_two_reasons_data_provenance": "completed_quote_bar_proxy",
    }


def _ichimoku_context(values: Sequence[float]) -> dict[str, Any]:
    """Calculate Ichimoku lines from quote highs/lows, explicitly as a proxy."""
    if len(values) < 52:
        return {}
    tenkan = (max(values[-9:]) + min(values[-9:])) / 2.0
    kijun = (max(values[-26:]) + min(values[-26:])) / 2.0
    span_a = (tenkan + kijun) / 2.0
    span_b = (max(values[-52:]) + min(values[-52:])) / 2.0
    current = values[-1]
    cloud_high = max(span_a, span_b)
    cloud_low = min(span_a, span_b)
    state = "bullish" if current > cloud_high and tenkan >= kijun else "bearish" if current < cloud_low and tenkan <= kijun else "neutral"
    return {
        "tenkan_sen": tenkan,
        "kijun_sen": kijun,
        "senkou_span_a": span_a,
        "senkou_span_b": span_b,
        "ichimoku_state": state,
        "ichimoku_observation_n": len(values),
    }


def _cci_context(values: Sequence[float], period: int = 20) -> dict[str, Any]:
    if len(values) < period:
        return {}
    window = list(values[-period:])
    mean = _mean(window)
    if mean is None:
        return {}
    deviation = _mean(abs(value - mean) for value in window)
    if deviation is None or deviation <= 0:
        return {}
    cci = (window[-1] - mean) / (0.015 * deviation)
    return {
        "cci": cci,
        "cci_state": "overbought" if cci >= 100.0 else "oversold" if cci <= -100.0 else "neutral",
        "cci_observation_n": len(values),
    }


def _williams_context(values: Sequence[float], period: int = 14) -> dict[str, Any]:
    if len(values) < period:
        return {}
    window = list(values[-period:])
    high = max(window)
    low = min(window)
    width = high - low
    if width <= 0:
        return {}
    williams = -100.0 * (high - window[-1]) / width
    return {
        "williams_r": williams,
        "williams_state": "overbought" if williams >= -20.0 else "oversold" if williams <= -80.0 else "neutral",
        "williams_observation_n": len(values),
    }


def _tick_volume_context(points: Sequence[Mapping[str, float]]) -> dict[str, Any]:
    """Calculate VWAP/OBV-like context only when tick volume is actually present."""
    if len(points) < 3 or any(_finite(item.get("tick_volume")) is None for item in points):
        return {}
    volumes = [max(0.0, _finite(item.get("tick_volume")) or 0.0) for item in points]
    total = sum(volumes)
    if total <= 0:
        return {}
    prices = [item["mid"] for item in points]
    vwap = sum(price * volume for price, volume in zip(prices, volumes)) / total
    current = prices[-1]
    relation = "above_vwap" if current > vwap else "below_vwap" if current < vwap else "at_vwap"
    obv = 0.0
    obv_path: list[float] = []
    for index in range(1, len(prices)):
        if prices[index] > prices[index - 1]:
            obv += volumes[index]
        elif prices[index] < prices[index - 1]:
            obv -= volumes[index]
        obv_path.append(obv)
    if not obv_path:
        return {}
    prior_obv = _mean(obv_path[:-max(1, min(10, len(obv_path)))]) if len(obv_path) > 10 else None
    obv_direction = "up" if prior_obv is not None and obv > prior_obv else "down" if prior_obv is not None and obv < prior_obv else "unresolved"
    return {
        "vwap_proxy": vwap,
        "vwap_relation": relation,
        "vwap_data_provenance": "tick_volume_proxy",
        "obv_proxy": obv,
        "obv_direction": obv_direction,
        "obv_data_provenance": "tick_volume_proxy",
        "volume_observation_n": len(points),
    }


def _correlation(left: Sequence[float], right: Sequence[float]) -> float | None:
    n = min(len(left), len(right))
    if n < 3:
        return None
    a, b = list(left[-n:]), list(right[-n:])
    mean_a, mean_b = statistics.fmean(a), statistics.fmean(b)
    numerator = sum((x - mean_a) * (y - mean_b) for x, y in zip(a, b))
    denominator = math.sqrt(sum((x - mean_a) ** 2 for x in a) * sum((y - mean_b) ** 2 for y in b))
    return numerator / denominator if denominator else 0.0


def _asof_mid(
    points: Sequence[Mapping[str, float]],
    timestamp: float,
    *,
    max_age_s: float,
) -> float | None:
    """Return the latest prior quote without crossing the as-of boundary."""
    latest: Mapping[str, float] | None = None
    for item in points:
        item_time = item.get("time")
        if item_time is None or item_time > timestamp + 1e-9:
            continue
        latest = item
    if latest is None:
        return None
    latest_time = latest.get("time")
    value = latest.get("mid")
    if latest_time is None or value is None or timestamp - latest_time > max_age_s:
        return None
    return value


def _session(timestamp: float) -> str:
    hour = datetime.fromtimestamp(timestamp, tz=timezone.utc).hour
    if 7 <= hour < 12:
        return "london"
    if 12 <= hour < 21:
        return "new_york"
    if 0 <= hour < 7:
        return "asia"
    return "off_session"


def _session_start(timestamp: float) -> float | None:
    """Return the UTC start of the observed FX session containing ``timestamp``."""
    moment = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    session = _session(timestamp)
    start_hour = {
        "asia": 0,
        "london": 7,
        "new_york": 12,
        "off_session": 21,
    }.get(session)
    if start_hour is None:
        return None
    return moment.replace(hour=start_hour, minute=0, second=0, microsecond=0).timestamp()


def _previous_session_points(
    points: Sequence[Mapping[str, float]],
    current_session_start: float,
) -> list[Mapping[str, float]]:
    """Return only the complete immediately preceding observed FX session."""
    current_day = datetime.fromtimestamp(current_session_start, tz=timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    starts = [
        (current_day + timedelta(days=day_offset, hours=hour)).timestamp()
        for day_offset in (-1, 0, 1)
        for hour in (0, 7, 12, 21)
    ]
    prior_starts = [start for start in starts if start < current_session_start]
    if not prior_starts:
        return []
    prior_start = max(prior_starts)
    return [
        item for item in points
        if prior_start <= item.get("time", -math.inf) < current_session_start
    ]


def _seasonality_context(
    points: Sequence[Mapping[str, float]],
    now: float,
) -> dict[str, Any]:
    """Summarize prior same-weekday/hour quote returns without claiming validation."""
    if now <= 0 or len(points) < 30:
        return {}
    current_dt = datetime.fromtimestamp(now, tz=timezone.utc)
    bucket = (current_dt.weekday(), current_dt.hour)
    ordered = [
        item for item in points
        if item.get("time") is not None and item.get("mid") is not None
        and item.get("time", math.inf) < now - 1e-9
        and item.get("mid", 0.0) > 0
    ]
    if len(ordered) < 30:
        return {}
    times = [item["time"] for item in ordered]
    returns: list[float] = []
    seen_days: set[tuple[int, int, int]] = set()
    for index, anchor in enumerate(ordered):
        anchor_time = anchor["time"]
        anchor_dt = datetime.fromtimestamp(anchor_time, tz=timezone.utc)
        if (anchor_dt.weekday(), anchor_dt.hour) != bucket:
            continue
        day_key = (anchor_dt.year, anchor_dt.month, anchor_dt.day)
        if day_key in seen_days:
            continue
        target_index = bisect_left(times, anchor_time + 60.0, lo=index + 1)
        if target_index >= len(ordered):
            continue
        target = ordered[target_index]
        target_time = target["time"]
        if target_time > now + 1e-9 or target_time - anchor_time > 180.0:
            continue
        target_mid = target.get("mid")
        if target_mid is None or target_mid <= 0:
            continue
        returns.append(target_mid / anchor["mid"] - 1.0)
        seen_days.add(day_key)
    if len(returns) < 30:
        return {}
    expectancy = statistics.fmean(returns)
    return {
        "seasonal_state": "descriptive_positive" if expectancy > 0 else "descriptive_negative" if expectancy < 0 else "descriptive_neutral",
        "seasonal_direction": "up" if expectancy > 0 else "down" if expectancy < 0 else "flat",
        "seasonal_expectancy": expectancy,
        "seasonal_sample_n": len(returns),
        "seasonal_period": "weekday_hour_forward_60s",
        "seasonal_validation": "chronological_prior_quote_return_descriptive_not_validated",
        "seasonal_data_provenance": "causal_prior_quote_return_conditioning",
    }


def _fractional_difference_context(points: Sequence[Mapping[str, float]]) -> dict[str, Any]:
    """Calculate a causal fractional difference while leaving validation explicit."""
    prices = [
        item.get("mid") for item in points
        if item.get("mid") is not None and item.get("mid", 0.0) > 0
    ]
    if len(prices) < 70:
        return {}
    logs = [math.log(price) for price in prices]
    d = 0.5
    weights = [1.0]
    for order in range(1, 40):
        weight = -weights[-1] * (d - order + 1.0) / order
        weights.append(weight)
        if order >= 12 and abs(weight) < 1e-5:
            break
    if len(logs) <= len(weights):
        return {}
    differences = [
        sum(weight * logs[index - offset] for offset, weight in enumerate(weights))
        for index in range(len(weights) - 1, len(logs))
    ]
    if len(differences) < 50:
        return {}
    half = len(differences) // 2
    first_variance = statistics.pvariance(differences[:half]) if half > 1 else 0.0
    last_variance = statistics.pvariance(differences[half:]) if len(differences) - half > 1 else 0.0
    variance_ratio = last_variance / first_variance if first_variance > 0 else None
    return {
        "fractional_diff_value": differences[-1],
        "fractional_diff_d": d,
        "fractional_diff_observation_n": len(differences),
        "fractional_diff_stationarity": "descriptive_quote_proxy_not_validated",
        "fractional_diff_variance_ratio": variance_ratio,
        "fractional_diff_data_provenance": "causal_log_quote_fractional_difference",
    }


def _kalman_local_level_context(points: Sequence[Mapping[str, float]]) -> dict[str, Any]:
    """Estimate a causal local price level and residual from quote mids."""
    prices = [
        item.get("mid") for item in points
        if item.get("mid") is not None and item.get("mid", 0.0) > 0
    ]
    if len(prices) < 60:
        return {}
    logs = [math.log(price) for price in prices]
    changes = [b - a for a, b in zip(logs, logs[1:])]
    if len(changes) < 30:
        return {}
    process_noise = max(statistics.pvariance(changes) * 0.1, 1e-12)
    measurement_noise = max(statistics.median(abs(change) for change in changes) ** 2, 1e-12)
    level = logs[0]
    covariance = process_noise
    residuals: list[float] = []
    for observation in logs:
        predicted_covariance = covariance + process_noise
        gain = predicted_covariance / (predicted_covariance + measurement_noise)
        residual = observation - level
        level += gain * residual
        covariance = (1.0 - gain) * predicted_covariance
        residuals.append(residual)
    recent = residuals[-30:]
    scale = statistics.pstdev(recent)
    if scale <= 0:
        return {}
    zscore = recent[-1] / scale
    state = "oversold_reversion" if zscore <= -2.0 else "overbought_reversion" if zscore >= 2.0 else "neutral"
    return {
        "kalman_state": state,
        "kalman_residual": recent[-1],
        "kalman_zscore": zscore,
        "kalman_confirmation": "quote_proxy_unconfirmed",
        "kalman_observation_n": len(logs),
        "kalman_data_provenance": "causal_local_level_quote_filter_proxy",
    }


def _quote_log_returns(points: Sequence[Mapping[str, float]]) -> list[float]:
    prices = [
        item.get("mid") for item in points
        if item.get("mid") is not None and item.get("mid", 0.0) > 0
    ]
    return [math.log(b / a) for a, b in zip(prices, prices[1:]) if a > 0 and b > 0]


def _garch_proxy_context(points: Sequence[Mapping[str, float]]) -> dict[str, Any]:
    """Run a causal fixed-parameter GARCH recursion as a descriptive proxy."""
    returns = _quote_log_returns(points)
    if len(returns) < 120:
        return {}
    alpha, beta = 0.08, 0.90
    unconditional = statistics.pvariance(returns[-120:])
    if unconditional <= 0:
        return {}
    omega = unconditional * (1.0 - alpha - beta)
    variance = unconditional
    for value in returns[-120:]:
        variance = omega + alpha * value * value + beta * variance
    if not math.isfinite(variance) or variance <= 0:
        return {}
    return {
        "garch_forecast": math.sqrt(variance),
        "garch_alpha": alpha,
        "garch_beta": beta,
        "garch_model_status": "descriptive_quote_garch_proxy_not_validated",
        "garch_observation_n": len(returns),
        "garch_data_provenance": "causal_quote_garch_recursion_proxy",
    }


def _stochastic_volatility_proxy_context(points: Sequence[Mapping[str, float]]) -> dict[str, Any]:
    """Track causal log-return variance as a transparent SV-style proxy."""
    returns = _quote_log_returns(points)
    if len(returns) < 120:
        return {}
    log_variance = math.log(max(statistics.pvariance(returns[-120:]), 1e-16))
    persistence = 0.96
    for value in returns[-120:]:
        observed_log_variance = math.log(max(value * value, 1e-16))
        log_variance = persistence * log_variance + (1.0 - persistence) * observed_log_variance
    forecast = math.sqrt(math.exp(log_variance))
    if not math.isfinite(forecast) or forecast <= 0:
        return {}
    return {
        "stochastic_volatility_forecast": forecast,
        "stochastic_volatility_persistence": persistence,
        "stochastic_volatility_status": "descriptive_log_variance_proxy_not_validated",
        "stochastic_volatility_observation_n": len(returns),
        "stochastic_volatility_data_provenance": "causal_log_return_variance_proxy",
    }


def _hawkes_quote_direction_context(points: Sequence[Mapping[str, float]]) -> dict[str, Any]:
    """Estimate decayed quote-direction event intensity without calling it order flow."""
    events: list[tuple[float, int]] = []
    for prior, current in zip(points, points[1:]):
        prior_time = prior.get("time")
        current_time = current.get("time")
        prior_mid = prior.get("mid")
        current_mid = current.get("mid")
        if None in {prior_time, current_time, prior_mid, current_mid} or current_time <= prior_time:
            continue
        if current_mid > prior_mid:
            events.append((current_time, 1))
        elif current_mid < prior_mid:
            events.append((current_time, -1))
    if len(events) < 30:
        return {}
    now = events[-1][0]
    span = max(now - events[0][0], 1.0)
    decay = 5.0
    buy = sum(sign == 1 for _, sign in events) / span
    sell = sum(sign == -1 for _, sign in events) / span
    for event_time, sign in events[-120:]:
        weight = math.exp(-(now - event_time) / decay)
        if sign == 1:
            buy += weight / decay
        else:
            sell += weight / decay
    return {
        "hawkes_buy_intensity": buy,
        "hawkes_sell_intensity": sell,
        "hawkes_model_status": "descriptive_quote_direction_proxy_not_validated",
        "hawkes_confirmation": "quote_direction_proxy_unconfirmed",
        "hawkes_observation_n": len(events),
        "hawkes_data_provenance": "causal_quote_direction_intensity_proxy",
    }


def _break_context(prior: Sequence[Mapping[str, float]], current: Mapping[str, float], pip: float) -> dict[str, Any]:
    """Detect a fresh break, retest, or failed break using prior quotes only."""
    if len(prior) < 6:
        return {}
    split = max(3, len(prior) // 2)
    baseline = prior[:split]
    baseline_high = max(item["mid"] for item in baseline)
    baseline_low = min(item["mid"] for item in baseline)
    width = max(baseline_high - baseline_low, pip)
    tolerance = max(width * 0.02, pip)
    post_break = prior[split:]
    break_up = next((index for index, item in enumerate(post_break) if item["mid"] > baseline_high + tolerance), None)
    break_down = next((index for index, item in enumerate(post_break) if item["mid"] < baseline_low - tolerance), None)
    current_mid = current["mid"]
    result: dict[str, Any] = {
        "break_level_high": baseline_high,
        "break_level_low": baseline_low,
        "break_tolerance": tolerance,
    }
    if break_up is not None and (break_down is None or break_up <= break_down):
        after = post_break[break_up:]
        retested = any(item["mid"] <= baseline_high + tolerance for item in after[1:])
        result["break_direction"] = "up"
        result["break_seen"] = True
        result["break_retested"] = retested
        if current_mid < baseline_high - tolerance:
            result["breakout_state"] = "failed_break_up"
        elif retested:
            result["breakout_state"] = "breakout_up_retest"
            result["retest"] = "retest_confirmed"
        else:
            result["breakout_state"] = "breakout_up_confirmed"
        return result
    if break_down is not None:
        after = post_break[break_down:]
        retested = any(item["mid"] >= baseline_low - tolerance for item in after[1:])
        result["break_direction"] = "down"
        result["break_seen"] = True
        result["break_retested"] = retested
        if current_mid > baseline_low + tolerance:
            result["breakout_state"] = "failed_break_down"
        elif retested:
            result["breakout_state"] = "breakout_down_retest"
            result["retest"] = "retest_confirmed"
        else:
            result["breakout_state"] = "breakout_down_confirmed"
        return result
    return {}


def _pullback_context(prior: Sequence[Mapping[str, float]], current: Mapping[str, float], dominant: str) -> dict[str, str]:
    """Identify a directional pullback followed by a same-direction response."""
    if len(prior) < 5 or dominant not in {"up", "down"}:
        return {}
    window = [*prior[-5:], current]
    changes = _changes(window)
    if len(changes) < 3:
        return {}
    recent = changes[-3:]
    if dominant == "up" and any(change < 0 for change in recent[:-1]) and recent[-1] > 0:
        return {"pullback": "bullish_pullback_reclaimed", "retracement": "shallow_bullish_retracement"}
    if dominant == "down" and any(change > 0 for change in recent[:-1]) and recent[-1] < 0:
        return {"pullback": "bearish_pullback_reclaimed", "retracement": "shallow_bearish_retracement"}
    return {}


def _sweep_context(prior: Sequence[Mapping[str, float]], current: Mapping[str, float], pip: float) -> dict[str, str]:
    """Detect a prior range probe that was rejected/reclaimed by the current quote."""
    if len(prior) < 6:
        return {}
    baseline = prior[:-2]
    if len(baseline) < 4:
        return {}
    high = max(item["mid"] for item in baseline)
    low = min(item["mid"] for item in baseline)
    tolerance = max((high - low) * 0.02, pip)
    probe = prior[-2]
    current_mid = current["mid"]
    if probe["mid"] > high + tolerance and current_mid <= high + tolerance:
        return {
            "liquidity_sweep": "buy_side_sweep_rejected",
            "sweep_state": "buy_side_sweep_rejected",
            "reclaim": "high_rejected",
            "stop_run": "buy_side",
            "wick_rejection": "bearish_rejection",
        }
    if probe["mid"] < low - tolerance and current_mid >= low - tolerance:
        return {
            "liquidity_sweep": "sell_side_sweep_reclaimed",
            "sweep_state": "sell_side_sweep_reclaimed",
            "reclaim": "low_reclaimed",
            "stop_run": "sell_side",
            "wick_rejection": "bullish_rejection",
        }
    return {}


def _point_and_figure_context(values: Sequence[float], pip: float) -> dict[str, Any]:
    """Build a causal point-and-figure proxy from quote mids.

    FX Watcher input has no exchange bar or volume feed, so the construction is
    explicitly quote-price based.  The box scale is estimated from prior
    non-zero quote moves and the current column is built only through the
    copied timestamp.  It is a research perspective, not broker geometry.
    """
    if len(values) < 12 or pip <= 0:
        return {}
    prior_changes = [
        abs(b - a)
        for a, b in zip(values[:-2], values[1:-1])
        if math.isfinite(a) and math.isfinite(b) and abs(b - a) > 0
    ]
    scale = statistics.median(prior_changes) if prior_changes else pip
    box_size = max(pip * 2.0, scale * 2.0)
    if not math.isfinite(box_size) or box_size <= 0:
        return {}

    reversal_boxes = 3
    columns: list[dict[str, Any]] = []
    kind: str | None = None
    high = low = float(values[0])
    for price in values[1:]:
        if not math.isfinite(price):
            continue
        if kind is None:
            move = price - values[0]
            if move >= box_size:
                kind = "X"
                high = values[0] + math.floor(move / box_size) * box_size
            elif move <= -box_size:
                kind = "O"
                low = values[0] - math.floor(-move / box_size) * box_size
            continue
        if kind == "X":
            if price >= high + box_size:
                high += math.floor((price - high) / box_size) * box_size
            elif price <= high - reversal_boxes * box_size:
                columns.append({"kind": kind, "high": high, "low": low})
                kind = "O"
                high -= box_size
                low = high - max(1, math.floor((high - price) / box_size)) * box_size
        else:
            if price <= low - box_size:
                low -= math.floor((low - price) / box_size) * box_size
            elif price >= low + reversal_boxes * box_size:
                columns.append({"kind": kind, "high": high, "low": low})
                kind = "X"
                low += box_size
                high = low + max(1, math.floor((price - low) / box_size)) * box_size
    if kind is not None:
        columns.append({"kind": kind, "high": high, "low": low})
    if not columns:
        return {}

    current = columns[-1]
    same_direction = [item for item in columns[:-1] if item["kind"] == kind]
    pattern = "rising_column" if kind == "X" else "falling_column"
    confirmation = "quote_proxy_unconfirmed"
    if same_direction:
        previous = same_direction[-1]
        if kind == "X" and current["high"] > previous["high"]:
            pattern = "double_top_breakout"
            confirmation = "quote_proxy_confirmed"
        elif kind == "O" and current["low"] < previous["low"]:
            pattern = "double_bottom_breakdown"
            confirmation = "quote_proxy_confirmed"
    return {
        "pnf_pattern": pattern,
        "pnf_direction": "up" if kind == "X" else "down",
        "pnf_confirmation": confirmation,
        "pnf_box_size": box_size,
        "pnf_reversal_boxes": reversal_boxes,
        "pnf_column_count": len(columns),
        "pnf_observation_n": len(values),
        "pnf_data_provenance": "quote_point_and_figure_proxy",
    }


def _exhaustion_context(points: Sequence[Mapping[str, float]], pip: float) -> dict[str, str]:
    """Flag decelerating directional movement at an observed local extreme."""
    if len(points) < 6:
        return {}
    recent = points[-8:]
    changes = _changes(recent)
    if len(changes) < 4:
        return {}
    prior_moves = changes[:-1]
    baseline = statistics.fmean(abs(change) for change in prior_moves) if prior_moves else 0.0
    last = changes[-1]
    threshold = max(baseline * 0.4, pip * 0.1)
    if last > 0 and baseline > 0 and last <= threshold and recent[-1]["mid"] >= max(item["mid"] for item in recent[:-1]):
        return {"exhaustion": "bullish_momentum_exhaustion", "climax": "bullish_climax", "momentum_decay": "decaying"}
    if last < 0 and baseline > 0 and abs(last) <= threshold and recent[-1]["mid"] <= min(item["mid"] for item in recent[:-1]):
        return {"exhaustion": "bearish_momentum_exhaustion", "climax": "bearish_climax", "momentum_decay": "decaying"}
    return {}


def _cycle_context(values: Sequence[float]) -> dict[str, Any]:
    """Estimate a cycle phase from causal quote autocorrelation.

    This is intentionally a descriptive proxy.  The price window is
    detrended before autocorrelation so a persistent trend is not mislabeled
    as a cycle, and the current phase is inferred only from observations up
    to the copied quote.
    """
    if len(values) < 80:
        return {}
    window = [value for value in values[-120:] if math.isfinite(value)]
    if len(window) < 80:
        return {}
    slope = (window[-1] - window[0]) / max(len(window) - 1, 1)
    detrended = [value - (window[0] + slope * index) for index, value in enumerate(window)]
    mean = statistics.fmean(detrended)
    centered = [value - mean for value in detrended]
    variance = sum(value * value for value in centered)
    if variance <= 0:
        return {}
    best_lag: int | None = None
    best_correlation = -1.0
    for lag in range(5, min(60, len(centered) // 3) + 1):
        left = centered[:-lag]
        right = centered[lag:]
        denominator = math.sqrt(sum(value * value for value in left) * sum(value * value for value in right))
        if denominator <= 0:
            continue
        correlation = sum(a * b for a, b in zip(left, right)) / denominator
        if correlation > best_correlation:
            best_lag = lag
            best_correlation = correlation
    if best_lag is None or best_correlation < 0.45:
        return {}
    amplitude = statistics.pstdev(window)
    current = window[-1]
    short_change = window[-1] - window[-2]
    direction = "up" if short_change > 0 else "down" if short_change < 0 else "flat"
    if current <= statistics.fmean(window) - 0.5 * amplitude and direction == "up":
        phase = "trough_rising"
    elif current >= statistics.fmean(window) + 0.5 * amplitude and direction == "down":
        phase = "peak_falling"
    elif direction in {"up", "down"}:
        phase = f"mid_{direction}"
    else:
        phase = "mid_cycle"
    return {
        "cycle_state": phase,
        "cycle_direction": direction,
        "cycle_period": best_lag,
        "cycle_confidence": max(0.0, min(1.0, best_correlation)),
        "cycle_observation_n": len(window),
        "cycle_data_provenance": "causal_quote_autocorrelation_proxy",
    }


def _put(state: dict[str, Any], key: str, value: Any, *, overwrite: bool = False) -> None:
    if value is None:
        return
    if overwrite or not _present(state.get(key)):
        state[key] = value


def _known_trend(value: Any) -> bool:
    return isinstance(value, str) and value in {"up", "down", "range"}


def _placeholder(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return not text or text.startswith(("unknown", "unavailable", "not_observed", "not_available"))


def _put_derived(state: dict[str, Any], key: str, value: Any) -> None:
    if value is not None and (_placeholder(state.get(key)) or key not in state):
        state[key] = value


def _derive_cross_asset(
    state: dict[str, Any],
    symbol: str,
    now: float,
    current_points: Sequence[Mapping[str, float]],
    universe_history: Mapping[str, Iterable[Mapping[str, Any]]] | None,
) -> None:
    if not isinstance(universe_history, Mapping):
        return
    current = current_points[-1].get("mid") if current_points else None
    if current is None:
        return
    left = _window(current_points, now, 300.0)
    if len(left) < 3:
        return
    best: tuple[str, float, float, list[float], list[float]] | None = None
    for other_symbol, other_history in universe_history.items():
        if str(other_symbol).upper() == symbol.upper():
            continue
        other_points, _ = _point_in_time_quotes(other_history, None, now)
        other = _window(other_points, now, 300.0)
        if len(other) < 3:
            continue
        aligned: list[tuple[float, float, float]] = []
        for item in left:
            timestamp = item.get("time")
            left_mid = item.get("mid")
            if timestamp is None or left_mid is None:
                continue
            right_mid = _asof_mid(other, timestamp, max_age_s=15.0)
            if right_mid is not None:
                aligned.append((timestamp, left_mid, right_mid))
        if len(aligned) < 3:
            continue
        l0, r0 = aligned[0][1], aligned[0][2]
        if l0 <= 0 or r0 <= 0:
            continue
        left_norm = [left_mid / l0 - 1.0 for _, left_mid, _ in aligned]
        right_norm = [right_mid / r0 - 1.0 for _, _, right_mid in aligned]
        corr = _correlation(left_norm, right_norm)
        if corr is None:
            continue
        residuals = [a - b for a, b in zip(left_norm, right_norm)]
        spread_mean = statistics.fmean(residuals)
        spread_std = statistics.pstdev(residuals) or 0.0
        zscore = (residuals[-1] - spread_mean) / spread_std if spread_std else 0.0
        best = (str(other_symbol), corr, zscore, left_norm, right_norm)
        break
    if best is None:
        return
    other_symbol, corr, zscore, left_norm, right_norm = best
    state["correlation"] = corr
    state["correlation_state"] = "aligned" if corr >= 0.5 else "divergent"
    state["cross_asset"] = f"quote_return_relationship_{other_symbol}"
    state["intermarket"] = "aligned" if corr >= 0.5 else "unstable"
    state["beta"] = corr
    state["pair"] = f"{symbol}~{other_symbol}"
    state["spread_zscore"] = zscore
    state["relative_value"] = "rich" if zscore > 0 else "cheap" if zscore < 0 else "neutral"
    state["cointegration"] = "quote_return_relationship_proxy_not_validated"
    state["stationarity"] = "not_estimated_from_quotes"
    state["basket_direction"] = _trend(_return_at(current_points, now, 60, current))
    state.setdefault("feature_provenance", {})["cross_asset"] = "quote_return_correlation_proxy"


def _derive_cross_sectional_momentum(
    state: dict[str, Any],
    symbol: str,
    now: float,
    current_points: Sequence[Mapping[str, float]],
    universe_history: Mapping[str, Iterable[Mapping[str, Any]]] | None,
) -> None:
    """Rank one-minute quote returns using only the as-of universe snapshot."""
    if not isinstance(universe_history, Mapping):
        return
    scores: list[tuple[str, float]] = []
    for other_symbol, other_history in universe_history.items():
        name = str(other_symbol)
        if name.upper() == symbol.upper():
            points = list(current_points)
        else:
            points, _ = _point_in_time_quotes(other_history, None, now)
        if len(points) < 2:
            continue
        current = points[-1].get("mid")
        score = _return_at(points, now, 60, current) if current is not None else None
        if score is not None and math.isfinite(score):
            scores.append((name, score))
    if len(scores) < 10:
        return
    current_score = next((score for name, score in scores if name.upper() == symbol.upper()), None)
    if current_score is None:
        return
    lower = sum(score < current_score for _, score in scores)
    equal = sum(score == current_score for _, score in scores)
    percentile = (lower + 0.5 * equal) / len(scores)
    ordered_scores = sorted(score for _, score in scores)
    median_score = statistics.median(ordered_scores)
    # These are as-of cross-sectional research features, not a forecast or a
    # live execution instruction.  Keep the factor signal tied to the same
    # quote-return observation used for the rank so it cannot become a generic
    # or future-informed probability.
    factor_signal = "BUY" if current_score > 0 else "SELL" if current_score < 0 else "FLAT"
    relative_denominator = 1.0 + median_score
    relative_ratio = (
        (1.0 + current_score) / relative_denominator
        if relative_denominator > 0
        else None
    )
    state["momentum_rank_percentile"] = percentile
    state["rank_universe_n"] = len(scores)
    state["momentum_direction"] = "up" if current_score > 0 else "down" if current_score < 0 else "flat"
    state["ranking_as_of"] = datetime.fromtimestamp(now, tz=timezone.utc).isoformat()
    state["factor_signal"] = factor_signal
    state["factor_score"] = current_score
    state["factor_rank_percentile"] = percentile
    state["factor_as_of"] = state["ranking_as_of"]
    state["relative_strength_benchmark"] = "universe_median"
    if relative_ratio is not None and math.isfinite(relative_ratio):
        state["relative_strength_ratio"] = relative_ratio
        state["relative_strength_direction"] = (
            "up" if relative_ratio > 1.0 else "down" if relative_ratio < 1.0 else "flat"
        )
        state["relative_strength_as_of"] = state["ranking_as_of"]
    provenance = state.setdefault("feature_provenance", {})
    provenance["cross_sectional_momentum"] = "asof_quote_return_rank"
    provenance["factor_momentum"] = "asof_quote_return_factor"
    provenance["relative_strength"] = "asof_universe_median"


def enrich_watcher_state(
    state: Mapping[str, Any] | None,
    row: Mapping[str, Any] | None = None,
    *,
    symbol_history: Iterable[Mapping[str, Any]] = (),
    universe_history: Mapping[str, Iterable[Mapping[str, Any]]] | None = None,
    derive: bool = True,
) -> dict[str, Any]:
    """Return a research-only, point-in-time feature state.

    ``row`` is the current observation.  ``symbol_history`` and
    ``universe_history`` must contain observations at or before that row; any
    later timestamp is removed here as a second line of defence against
    look-ahead.  The function is pure and returns a new dictionary.
    """
    result = _safe_copy(state)
    for key, value in _safe_copy(row, row=True).items():
        # ``build_pre_entry_state`` has already normalized fields such as
        # side/horizon.  The current quote itself is allowed to replace an
        # older copy, while descriptive pre-entry fields remain authoritative.
        if key not in result or key in {"bid", "ask", "mid", "time", "timestamp", "time_utc"}:
            result[key] = value
    if "feature_provenance" in result and not isinstance(result["feature_provenance"], Mapping):
        result.pop("feature_provenance", None)
    raw_side = str(result.get("side") or result.get("position_side") or "").strip().lower()
    if raw_side in {"buy", "sell"}:
        result["side"] = raw_side.upper()
    raw_horizon = _finite(result.get("horizon_s"))
    if raw_horizon is not None:
        result["horizon_s"] = int(raw_horizon) if raw_horizon.is_integer() else raw_horizon
    if isinstance(row, Mapping):
        if not _present(result.get("entry")) and _finite(row.get("entry_price")) is not None:
            result["entry"] = _finite(row.get("entry_price"))
    if not derive:
        # Explicit fast path for datasets whose row features were already
        # generated causally.  The row has still passed _safe_copy(row,
        # row=True), so outcome/future payload aliases are removed; skipping
        # derived calculations avoids rebuilding long quote histories for
        # every pre-enriched replay row.
        return result
    symbol = str(result.get("symbol") or (row or {}).get("symbol") or "").strip()
    if symbol:
        result["symbol"] = symbol
    current_time = _timestamp((row or {}).get("time", (row or {}).get("timestamp", result.get("time"))))
    if current_time is None:
        current_time = _timestamp(result.get("time"))
    points, future_excluded = _point_in_time_quotes(symbol_history or (), row, current_time)
    if not points:
        return result
    now = current_time if current_time is not None else points[-1].get("time", 0.0)
    current = points[-1]
    mid = current["mid"]
    pip = _pip_size(symbol)
    raw_provenance = result.get("feature_provenance")
    provenance = dict(raw_provenance) if isinstance(raw_provenance, Mapping) else {}
    provenance.update({
        "quote": "point_in_time_bid_ask_history",
        "returns": "point_in_time_quote_returns",
        "bars": "quote_aggregated_bar_proxy",
        "volume": "tick_activity_proxy",
        "market_profile": "tick_price_profile_proxy",
        "geometry": "watcher_structural_levels_proxy",
    })
    result["feature_provenance"] = provenance
    result["quote_history_n"] = len(points)
    result["quote_history_last_time"] = current.get("time", now)
    result["quote_history_future_excluded"] = future_excluded
    result["bid"] = current["bid"]
    result["ask"] = current["ask"]
    result["mid"] = mid
    result["spread"] = current["spread"]
    result["spread_pips"] = current["spread"] / pip
    result["quote_age_s"] = 0.0
    result["quote_fresh"] = True
    result.setdefault("entry", current["ask"] if str(result.get("side", "")).upper() == "BUY" else current["bid"])

    returns: dict[str, float] = {}
    for horizon in HORIZONS_S:
        value = _return_at(points, now, horizon, mid)
        if value is None:
            value = _finite(result.get(f"return_{horizon}s"))
        if value is not None:
            returns[f"{horizon}s"] = value
            result[f"return_{horizon}"] = value
            result[f"return_{horizon}s"] = value
    if returns:
        result["short_returns"] = returns
    forecast_horizon = _finite(result.get("horizon_s")) or 5.0
    forecast_horizon = min(60.0, max(1.0, forecast_horizon))
    forecast = _quote_walk_forward_forecast(points, now, forecast_horizon, pip)
    if forecast:
        result.update(forecast)
        provenance["time_series_forecasting"] = forecast["forecast_data_provenance"]
    seasonality = _seasonality_context(points, now)
    if seasonality:
        for key, value in seasonality.items():
            _put_derived(result, key, value)
        provenance["seasonality"] = seasonality["seasonal_data_provenance"]
    fractional_difference = _fractional_difference_context(points)
    if fractional_difference:
        for key, value in fractional_difference.items():
            _put_derived(result, key, value)
        provenance["fractional_differentiation"] = fractional_difference["fractional_diff_data_provenance"]
    kalman = _kalman_local_level_context(points)
    if kalman:
        for key, value in kalman.items():
            _put_derived(result, key, value)
        provenance["kalman_filter"] = kalman["kalman_data_provenance"]
    garch = _garch_proxy_context(points)
    if garch:
        for key, value in garch.items():
            _put_derived(result, key, value)
        provenance["garch_volatility"] = garch["garch_data_provenance"]
    stochastic_volatility = _stochastic_volatility_proxy_context(points)
    if stochastic_volatility:
        for key, value in stochastic_volatility.items():
            _put_derived(result, key, value)
        provenance["stochastic_volatility"] = stochastic_volatility["stochastic_volatility_data_provenance"]
    hawkes = _hawkes_quote_direction_context(points)
    if hawkes:
        for key, value in hawkes.items():
            _put_derived(result, key, value)
        provenance["hawkes_order_flow"] = hawkes["hawkes_data_provenance"]
    roc_context = _roc_context(points, now, mid)
    if roc_context:
        result.update(roc_context)
        provenance["rate_of_change"] = roc_context["roc_observation_provenance"]
    latest_changes = _changes(points[-31:])
    recent = _window(points, now, 15.0)
    recent_changes = _changes(recent)
    velocity = None
    prior_velocity = None
    if len(points) >= 2:
        dt = points[-1].get("time", now) - points[-2].get("time", now)
        if dt > 0:
            velocity = (points[-1]["mid"] - points[-2]["mid"]) / dt
    if len(points) >= 3:
        dt = points[-2].get("time", now) - points[-3].get("time", now)
        if dt > 0:
            prior_velocity = (points[-2]["mid"] - points[-3]["mid"]) / dt
    if velocity is not None:
        result["tick_velocity"] = velocity
        result["price_acceleration"] = velocity - prior_velocity if prior_velocity is not None else 0.0
        result["tick_direction"] = "up" if velocity > 0 else "down" if velocity < 0 else "flat"
    signs = [1 if change > 0 else -1 if change < 0 else 0 for change in recent_changes]
    if signs:
        persistence = sum(signs) / len(signs)
        result["tick_persistence"] = persistence
        result["momentum_persistence"] = persistence
        result["imbalance"] = persistence
        result["bid_ask_imbalance"] = persistence
        result["order_flow"] = "buy_pressure" if persistence > 0 else "sell_pressure" if persistence < 0 else "balanced"
    if latest_changes:
        result["momentum"] = sum(latest_changes[-5:]) / max(mid, 1e-12)
        result["momentum_context"] = "rising" if result["momentum"] > 0 else "falling" if result["momentum"] < 0 else "flat"
    micro_returns = [change / max(points[index]["mid"], 1e-12) for index, change in enumerate(latest_changes)]
    micro_vol = _std(micro_returns)
    long_points = _window(points, now, 60.0)
    long_changes = _changes(long_points)
    long_returns = [change / max(long_points[index]["mid"], 1e-12) for index, change in enumerate(long_changes)]
    realized = math.sqrt(sum(value * value for value in long_returns)) if long_returns else None
    if micro_vol is not None:
        result["micro_volatility"] = micro_vol
        result["volatility"] = micro_vol
    if realized is not None:
        result["realized_volatility"] = realized
        result["realized_vol_60s"] = realized
        result["realized_volatility_window_s"] = 60
        result["realized_volatility_observation_n"] = len(long_points)
        provenance["realized_volatility"] = "quote_return_rms_proxy"
    expansion = (micro_vol / ((_std(long_returns) or micro_vol) or 1e-12)) if micro_vol is not None else None
    if expansion is not None:
        result["volatility_expansion"] = expansion
        result["volatility_percentile"] = min(100.0, max(0.0, expansion * 50.0))
        result["volatility_state"] = "expanding" if expansion > 1.2 else "compressed" if expansion < 0.8 else "stable"
    trend_60 = _trend(returns.get("60s"), realized or 0.0)
    trend_300_value = _return_at(points, now, 300, mid)
    trend_900_value = _return_at(points, now, 900, mid)
    trend_3600_value = _return_at(points, now, 3600, mid)
    trend_300 = _trend(trend_300_value, realized or 0.0)
    trend_900 = _trend(trend_900_value, realized or 0.0)
    trend_3600 = _trend(trend_3600_value, realized or 0.0)
    micro_trend = "unknown"
    if len(points) >= 5:
        reference = points[-5]["mid"]
        micro_return = mid / reference - 1.0 if reference else None
        micro_trend = _trend(micro_return, micro_vol or abs(micro_return or 0.0))
    dominant = next((value for value in (trend_300, trend_60, trend_900, trend_3600, micro_trend) if _known_trend(value)), "unknown")
    if _known_trend(dominant):
        _put_derived(result, "trend", dominant)
        _put_derived(result, "regime", "trend" if dominant in {"up", "down"} else "range")
        _put_derived(result, "structure", {
            "up": "bullish higher highs higher lows",
            "down": "bearish lower highs lower lows",
            "range": "balanced range",
        }[dominant])
    if _known_trend(trend_60):
        _put_derived(result, "m1_trend", trend_60)
        result["m1_context"] = {"trend": trend_60, "return": returns.get("60s"), "source": "quote_history"}
    if _known_trend(trend_300):
        _put_derived(result, "m5_trend", trend_300)
        result["m5_context"] = {"trend": trend_300, "return": trend_300_value, "source": "quote_history"}
    if _known_trend(trend_900):
        _put_derived(result, "m15_trend", trend_900)
        result["m15_context"] = {"trend": trend_900, "return": trend_900_value, "source": "quote_history"}
        result["higher_timeframe"] = trend_900
    if _known_trend(trend_3600):
        _put_derived(result, "h1_trend", trend_3600)
        result["h1_context"] = {"trend": trend_3600, "return": trend_3600_value, "source": "quote_history"}

    prior = points[:-1] if len(points) > 1 else []
    prior_60 = _window(prior, now, 60.0)
    prior_300 = _window(prior, now, 300.0)
    level_points = next((candidate for candidate in (prior_300, prior_60, prior) if len(candidate) >= 2), [])
    if level_points:
        range_high = max(item["mid"] for item in level_points)
        range_low = min(item["mid"] for item in level_points)
        width = max(range_high - range_low, pip)
        position = min(1.0, max(0.0, (mid - range_low) / width))
        result.update({
            "range_high": range_high,
            "range_low": range_low,
            "range_width": width,
            "range_position": position,
            "range_state": "range" if dominant == "range" else "trend" if dominant in {"up", "down"} else "observed",
            "balance_state": "balanced" if dominant == "range" else "initiative" if dominant in {"up", "down"} else "unresolved",
            "support": range_low,
            "resistance": range_high,
            "support_level": range_low,
            "resistance_level": range_high,
            "distance_to_support": mid - range_low,
            "distance_to_resistance": range_high - mid,
            "level_state": "observed_quote_levels",
            "level_role": "support_below_resistance",
            "channel_lower": range_low,
            "channel_upper": range_high,
            "channel_position": position,
            "price_position": position,
            "channel_direction": dominant if dominant != "unknown" else "unresolved",
            "channel_state": "ascending" if dominant == "up" else "descending" if dominant == "down" else "range",
            "trend_channel": dominant if dominant != "unknown" else "unresolved",
            "donchian_high": range_high,
            "donchian_low": range_low,
            "donchian_width": width,
            "donchian_data_provenance": "observed_quote_range_proxy",
        })
        if dominant in {"up", "down"}:
            retracement = 1.0 - position if dominant == "up" else position
            fib_levels = (0.236, 0.382, 0.500, 0.618, 0.786)
            nearest = min(fib_levels, key=lambda level: abs(retracement - level))
            zone = "range_edge" if retracement < 0.15 or retracement > 0.85 else f"{nearest:.3f}"
            result.update({
                "fib_retracement": retracement,
                "fib_retracement_zone": zone,
                "fib_direction": dominant,
                "fib_236": range_low + width * 0.236,
                "fib_382": range_low + width * 0.382,
                "fib_500": range_low + width * 0.500,
                "fib_618": range_low + width * 0.618,
                "fib_786": range_low + width * 0.786,
                "fib_data_provenance": "observed_range_retracement_proxy",
            })
            provenance["fibonacci"] = "observed_range_retracement_proxy"
        tolerance = max(width * 0.02, pip)
        break_context = _break_context(prior, current, pip)
        if break_context:
            result.update({key: value for key, value in break_context.items() if key.startswith("break_")})
            breakout = break_context["breakout_state"]
            result["breakout_state"] = breakout
            result["breakout"] = breakout
            result["breakout_confirmation"] = "confirmed_quote_break" if "failed" not in breakout else "failed_quote_break"
            result["range_expansion"] = "up" if break_context.get("break_direction") == "up" else "down"
            if "retest" in break_context:
                result["retest"] = break_context["retest"]
                if break_context.get("break_direction") == "up":
                    result["level_role"] = "resistance turned support"
                elif break_context.get("break_direction") == "down":
                    result["level_role"] = "support turned resistance"
        else:
            broke_up = mid > range_high + tolerance
            broke_down = mid < range_low - tolerance
            breakout = "breakout_up" if broke_up else "breakout_down" if broke_down else "inside_range"
            result["breakout_state"] = breakout
            result["breakout"] = breakout
            result["breakout_confirmation"] = "confirmed_quote_break" if broke_up or broke_down else "not_confirmed"
            result["range_expansion"] = "up" if broke_up else "down" if broke_down else "none"
        result["donchian_state"] = breakout
        result["volatility_transition"] = "compression_expansion" if expansion is not None and expansion > 1.2 else "stable"
        result["expansion"] = "volatility expanding" if expansion is not None and expansion > 1.2 else "none"
        result["compression"] = "compression" if expansion is not None and expansion < 0.8 else "none"
        result["impulse"] = "impulse_up" if dominant == "up" else "impulse_down" if dominant == "down" else "none"
        result["follow_through"] = "present" if dominant in {"up", "down"} else "not_observed"
        result.setdefault("retest", "not_observed")
        result.setdefault("pullback", "pullback_not_confirmed")
        result.setdefault("retracement", "not_observed")
        pullback = _pullback_context(prior, current, dominant)
        result.update(pullback)
        if position < 0.2 and prior and mid > prior[-1]["mid"] and dominant in {"up", "range"}:
            result["range_edge_rejection"] = "lower_edge_reclaimed"
        elif position > 0.8 and prior and mid < prior[-1]["mid"] and dominant in {"down", "range"}:
            result["range_edge_rejection"] = "upper_edge_rejected"
        else:
            result["range_edge_rejection"] = "no_edge_rejection_observed"
        result["rejection"] = result["range_edge_rejection"]
        result["channel_breakout"] = breakout

        sweep = _sweep_context(prior, current, pip)
        result.update(sweep)
        if sweep.get("sweep_state") == "buy_side_sweep_rejected":
            result["level_role"] = "resistance_rejected"
            result["wyckoff_event"] = "upthrust"
            result["wyckoff_confirmation"] = "quote_price_proxy_confirmed"
        elif sweep.get("sweep_state") == "sell_side_sweep_reclaimed":
            result["level_role"] = "support_hold"
            result["wyckoff_event"] = "spring"
            result["wyckoff_confirmation"] = "quote_price_proxy_confirmed"
        if sweep.get("sweep_state") and all(_finite(item.get("tick_volume")) is not None for item in points):
            result["wyckoff_volume_confirmation"] = "quote_volume_proxy_confirmed"
            provenance["wyckoff"] = "quote_sweep_and_tick_volume_proxy"

    exhaustion = _exhaustion_context(points, pip)
    if exhaustion:
        result.update(exhaustion)
    elif len(recent_changes) >= 3:
        result.setdefault("exhaustion", "not_observed")
        result.setdefault("climax", "not_observed")

    candle_context = _completed_quote_candle_context(points, now, pip)
    if candle_context:
        result.update(candle_context)
        candle_pattern = candle_context["candle_pattern"]
        if candle_pattern == "bullish_hammer":
            result.update({
                "tail_direction": "bullish",
                "tail_context": "support",
                "tail_confirmation": "quote_bar_proxy_confirmed",
                "tail_wick_ratio": candle_context["candle_lower_wick"] / max(candle_context["candle_body"], pip),
            })
            provenance["kangaroo_tail"] = "completed_quote_bar_proxy"
        elif candle_pattern == "bearish_shooting_star":
            result.update({
                "tail_direction": "bearish",
                "tail_context": "resistance",
                "tail_confirmation": "quote_bar_proxy_confirmed",
                "tail_wick_ratio": candle_context["candle_upper_wick"] / max(candle_context["candle_body"], pip),
            })
            provenance["kangaroo_tail"] = "completed_quote_bar_proxy"
        named_candle = {
            "bullish_hammer": "hammer",
            "bearish_shooting_star": "shooting_star",
            "bullish_engulfing": "bullish_engulfing",
            "bearish_engulfing": "bearish_engulfing",
            "morning_star": "morning_star",
            "evening_star": "evening_star",
            "piercing_line": "piercing_line",
            "dark_cloud_cover": "dark_cloud_cover",
            "bullish_harami": "bullish_harami",
            "bearish_harami": "bearish_harami",
            "three_white_soldiers": "three_white_soldiers",
            "three_black_crows": "three_black_crows",
        }.get(candle_pattern)
        if named_candle:
            result["candlestick_pattern"] = named_candle
            result["candlestick_confirmation"] = "quote_bar_proxy_confirmed"
            provenance["candlestick_patterns"] = "completed_quote_bar_proxy"
    second_entry = _al_brooks_second_entry_context(points, now, dominant)
    if second_entry:
        result.update(second_entry)
        provenance["second_entry"] = second_entry["second_entry_data_provenance"]
    al_brooks = _al_brooks_extended_context(points, now, dominant, pip)
    if al_brooks:
        result.update(al_brooks)
        provenance["al_brooks"] = "completed_quote_bar_proxy"
    brooks_range_rules = _brooks_range_rules_context(points, now, pip)
    if brooks_range_rules:
        result.update(brooks_range_rules)
        provenance["brooks_range_rules"] = "completed_quote_bar_proxy"
    brooks_two_reasons = _brooks_two_reasons_context(result, dominant)
    if brooks_two_reasons:
        result.update(brooks_two_reasons)
        provenance["brooks_two_reasons"] = brooks_two_reasons["brooks_two_reasons_data_provenance"]
    volman = _volman_context(points, now, dominant, pip, candidate_side=result.get("side"))
    if volman:
        result.update(volman)
        provenance["volman"] = volman["volman_data_provenance"]
    vpa = _vpa_context(points, now, dominant, pip)
    if vpa:
        result.update(vpa)
        provenance["vpa"] = vpa["vpa_data_provenance"]
    edwards_magee = _edwards_magee_context(points, now, dominant, pip)
    if edwards_magee:
        result.update(edwards_magee)
        provenance["edwards_magee"] = edwards_magee["em_data_provenance"]
    chan = _chan_context(points, now, pip)
    if chan:
        for key, value in chan.items():
            _put_derived(result, key, value)
        if "chan_gap_data_provenance" in chan:
            provenance["chan_opening_gap_momentum"] = chan["chan_gap_data_provenance"]
        if "chan_stop_data_provenance" in chan:
            provenance["chan_stop_order_momentum"] = chan["chan_stop_data_provenance"]
        if "chan_order_flow_data_provenance" in chan:
            provenance["chan_order_flow_momentum"] = chan["chan_order_flow_data_provenance"]
        if "chan_imbalance_data_provenance" in chan:
            provenance["chan_bid_ask_imbalance"] = chan["chan_imbalance_data_provenance"]
        if "chan_half_life_data_provenance" in chan:
            provenance["chan_mean_reversion_half_life"] = chan["chan_half_life_data_provenance"]
        if "dejong_roll_data_provenance" in chan:
            provenance["dejong_roll"] = chan["dejong_roll_data_provenance"]
    ponsi = _ponsi_context(
        points,
        now,
        dominant,
        pip,
        session=result.get("session") or result.get("market_session"),
        round_number_step=_finite(result.get("round_number_step")),
    )
    if ponsi:
        result.update(ponsi)
        provenance["ponsi"] = ponsi["ponsi_data_provenance"]
    nison = _nison_context(points, now, pip)
    if nison:
        result.update(nison)
        provenance["nison"] = nison["nison_data_provenance"]
    aziz = _aziz_context(points, now, pip)
    if aziz:
        for key, value in aziz.items():
            _put_derived(result, key, value)
        provenance["aziz"] = "causal_quote_bar_and_day_range_proxy"
    price_in_time = _price_in_time_context(points, now, pip)
    if price_in_time:
        for key, value in price_in_time.items():
            _put_derived(result, key, value)
        provenance["price_in_time"] = price_in_time["pit_data_provenance"]
    if level_points:
        pattern_context = _chart_pattern_context([item["mid"] for item in points], pip)
        if pattern_context:
            result.update(pattern_context)
            provenance["chart_patterns"] = "quote_extrema_proxy"
        else:
            result["chart_pattern"] = "ascending_channel" if dominant == "up" else "descending_channel" if dominant == "down" else "range"
            result["pattern"] = result["chart_pattern"]
            result["pattern_state"] = "quote_pattern_observed"
            result["pattern_confirmation"] = "not_confirmed_from_candles"
        result.setdefault("failure_state", "not_observed")
        result["measured_move"] = width

    changes = _changes(points)
    rsi = _rsi(changes)
    if rsi is not None:
        result["rsi"] = rsi
        result["oscillator"] = "rsi"
        result["rsi_state"] = "overbought" if rsi >= 70 else "oversold" if rsi <= 30 else "neutral"
        result["oscillator_state"] = result["rsi_state"]
        result["overbought"] = rsi >= 70
        result["oversold"] = rsi <= 30
        previous_rsi = _rsi(_changes(points[:-1])) if len(points) > 1 else None
        if previous_rsi is not None:
            _put_derived(result, "link_rsi_current", rsi)
            _put_derived(result, "link_rsi_previous", previous_rsi)
            _put_derived(result, "link_rsi_fifty_line", 50.0)
            _put_derived(result, "link_rsi_oversold", 30.0)
            _put_derived(result, "link_rsi_overbought", 70.0)
            _put_derived(result, "link_rsi_stall_confirmed", False)
            _put_derived(result, "link_rsi_data_provenance", "observed_quote_derived_oscillator")
            _put_derived(result, "link_rsi_extreme_data_provenance", "observed_quote_derived_oscillator")
            provenance["link_rsi_fifty_line_entry"] = "observed_quote_derived_oscillator"
            provenance["link_rsi_extreme_exit"] = "observed_quote_derived_oscillator"
    stochastic_lines = _stochastic_lines(points)
    if stochastic_lines is not None:
        _put_derived(result, "link_stoch_fast", stochastic_lines["fast"])
        _put_derived(result, "link_stoch_slow", stochastic_lines["slow"])
        _put_derived(result, "link_stoch_fast_previous", stochastic_lines["fast_previous"])
        _put_derived(result, "link_stoch_slow_previous", stochastic_lines["slow_previous"])
        _put_derived(result, "link_stoch_slow_bottomed", stochastic_lines["slow_bottomed"])
        _put_derived(result, "link_stoch_oversold", 20.0)
        _put_derived(result, "link_stoch_overbought", 80.0)
        _put_derived(result, "link_stoch_data_provenance", "observed_quote_derived_oscillator")
        provenance["link_stochastic_wave_entry"] = "observed_quote_derived_oscillator"
        provenance["link_stochastic_cross_entry"] = "observed_quote_derived_oscillator"
    if level_points and width > 0:
        result["stochastic"] = position * 100.0
        result["stoch"] = position * 100.0
        result["stochastic_k"] = position * 100.0
        result["stochastic_state"] = "overbought" if position >= 0.8 else "oversold" if position <= 0.2 else "neutral"
    if len(points) >= 8 and rsi is not None:
        result["divergence"] = "no_divergence_detected"
        early_rsi = _rsi(_changes(points[:-4]))
        early_mid = points[-5]["mid"]
        if early_rsi is not None and mid > early_mid and rsi < early_rsi:
            result["divergence"] = "bearish_divergence"
        elif early_rsi is not None and mid < early_mid and rsi > early_rsi:
            result["divergence"] = "bullish_divergence"
    if "divergence" in result:
        result["rsi_divergence"] = result["divergence"]
        result["momentum_divergence"] = result["divergence"]
    primary_screen = next(
        (result.get(key) for key in ("m15_trend", "h1_trend", "m5_trend") if _known_trend(result.get(key))),
        None,
    )
    if primary_screen:
        _put_derived(result, "primary_trend", primary_screen)
        oscillator_state = str(result.get("rsi_state") or result.get("stochastic_state") or "neutral")
        if oscillator_state in {"oversold", "overbought"}:
            intermediate_screen = f"{oscillator_state}_recovery"
        elif "pullback" in str(result.get("pullback") or ""):
            intermediate_screen = "pullback"
        else:
            intermediate_screen = "neutral"
        _put_derived(result, "intermediate_oscillator", intermediate_screen)
        trigger = str(result.get("roc_direction") or result.get("tick_direction") or "").lower()
        trigger = trigger if trigger in {"up", "down"} else "unresolved"
        _put_derived(result, "short_trigger", f"{trigger}_confirmed" if trigger != "unresolved" else trigger)
        provenance["three_screen"] = "quote_observation_proxy"
        result["three_screen_data_provenance"] = "quote_observation_proxy"
    mid_values = [item["mid"] for item in points]
    ten_period = _prior_channel(mid_values, 10)
    if ten_period:
        high_10, low_10, sd_10 = ten_period
        result.update({
            "breakout_lookback": 10,
            "breakout_high_10": high_10,
            "breakout_low_10": low_10,
            "breakout_sd": sd_10,
            "breakout_buffer_sd": 0.5,
            "current_price": mid,
        })
        provenance["breakout_rules"] = "prior_quote_observations"
    turtle_channel = _prior_channel(mid_values, 20)
    if turtle_channel:
        turtle_high, turtle_low, _ = turtle_channel
        turtle_broken = mid > turtle_high or mid < turtle_low
        result.update({
            "turtle_entry_lookback": 20,
            "turtle_exit_lookback": 10,
            "turtle_high": turtle_high,
            "turtle_low": turtle_low,
            "turtle_confirmation": "quote_breakout_confirmed" if turtle_broken else "quote_channel_not_broken",
        })
        provenance["turtle_breakout"] = "prior_quote_observations"
    point_and_figure = _point_and_figure_context(mid_values, pip)
    if point_and_figure:
        result.update(point_and_figure)
        provenance["point_and_figure"] = point_and_figure["pnf_data_provenance"]
    cycle = _cycle_context(mid_values)
    if cycle:
        for key, value in cycle.items():
            _put_derived(result, key, value)
        provenance["cycle_analysis"] = cycle["cycle_data_provenance"]
    sar_context = _parabolic_sar_context(mid_values)
    if sar_context:
        result.update(sar_context)
        provenance["parabolic_sar"] = sar_context["sar_data_provenance"]
    bollinger = _bollinger_context(mid_values)
    if bollinger:
        result.update(bollinger)
        provenance["bollinger"] = "quote_observation_proxy"
    macd = _macd_context(mid_values)
    if macd:
        result.update(macd)
        provenance["macd"] = "quote_observation_proxy"
        _put_derived(result, "link_macd_line", macd["macd_line"])
        _put_derived(result, "link_macd_signal_line", macd["macd_signal"])
        _put_derived(result, "link_macd_data_provenance", "observed_quote_derived_oscillator")
        provenance["link_macd_signal_line_entry"] = "observed_quote_derived_oscillator"
    atr = _atr_context(mid_values)
    if atr:
        result.update(atr)
        provenance["atr"] = "quote_observation_proxy"
    adx = _adx_context(mid_values)
    if adx:
        result.update(adx)
        provenance["adx"] = "quote_observation_proxy"
    keltner = _keltner_context(mid_values)
    if keltner:
        result.update(keltner)
        provenance["keltner"] = "quote_observation_proxy"
    squeeze = _squeeze_context(mid_values, _finite(result.get("momentum")))
    if squeeze:
        result.update(squeeze)
        provenance["ttm_squeeze"] = "quote_observation_proxy"
    ichimoku = _ichimoku_context(mid_values)
    if ichimoku:
        result.update(ichimoku)
        provenance["ichimoku"] = "quote_observation_proxy"
    cci = _cci_context(mid_values)
    if cci:
        result.update(cci)
        provenance["cci"] = "quote_observation_proxy"
    williams = _williams_context(mid_values)
    if williams:
        result.update(williams)
        provenance["williams"] = "quote_observation_proxy"
    fast_values = [item["mid"] for item in points[-12:]]
    slow_values = [item["mid"] for item in points[-26:]]
    fast = _ema(fast_values, min(12, max(2, len(fast_values))))
    slow = _ema(slow_values, min(26, max(2, len(slow_values))))
    if fast is not None and slow is not None:
        prior_fast = _ema(mid_values[-13:-1], 12) if len(mid_values) >= 13 else None
        ema_slope = "up" if prior_fast is not None and fast > prior_fast else (
            "down" if prior_fast is not None and fast < prior_fast else "flat"
        )
        result.update({
            "moving_average_state": "quote_derived",
            "ema_fast": fast,
            "ema_slow": slow,
            "ma_fast": fast,
            "ma_slow": slow,
            "ema_cross": "cross_up" if fast > slow else "cross_down" if fast < slow else "flat",
            "ma_cross": "cross_up" if fast > slow else "cross_down" if fast < slow else "flat",
            "ma_slope": velocity or 0.0,
            "ema_fast_slope": velocity or 0.0,
            "ewma_fast": fast,
            "ewma_slow": slow,
            "ewmac_fast_lookback": 12,
            "ewmac_slow_lookback": 26,
            "ema_slope": ema_slope,
        })
        impulse = "green" if ema_slope == "up" and result.get("macd_histogram_slope") == "up" else (
            "red" if ema_slope == "down" and result.get("macd_histogram_slope") == "down" else "neutral"
        )
        result["impulse_state"] = impulse
        provenance["ewmac"] = "quote_observation_proxy"
        provenance["elder_impulse"] = "quote_observation_proxy"

    tick_count = len(recent)
    baseline_count = len(long_points)
    activity_ratio = tick_count / max(baseline_count / 4.0, 1.0)
    result["tick_activity"] = tick_count
    result["tick_count"] = tick_count
    result["tick_activity_ratio"] = activity_ratio
    result["volume"] = "tick_activity_proxy"
    result["volume_ratio"] = activity_ratio
    result["relative_volume"] = activity_ratio
    result["tick_volume"] = current.get("tick_volume", tick_count)
    tick_volume_context = _tick_volume_context(points)
    if tick_volume_context:
        result.update(tick_volume_context)
        provenance["vwap"] = "tick_volume_proxy"
        provenance["obv"] = "tick_volume_proxy"
    if len(points) >= 2 and all(_finite(item.get("tick_volume")) is not None for item in points):
        previous = points[-2]
        current_volume = _finite(current.get("tick_volume"))
        price_change = current["mid"] - previous["mid"]
        if current_volume is not None:
            force = price_change * current_volume
            force_direction = "up" if force > 0 else "down" if force < 0 else "flat"
            result.update({
                "force_index": force,
                "force_index_direction": force_direction,
                "force_index_confirmation": "quote_proxy_confirmed" if force != 0 else "quote_proxy_unconfirmed",
                "force_index_data_provenance": "tick_volume_proxy",
            })
            provenance["force_index"] = "tick_volume_proxy"
        bar_range = _finite(result.get("bar_range"))
        volume_window = [
            _finite(item.get("tick_volume"))
            for item in points[-21:-1]
        ]
        volume_window = [value for value in volume_window if value is not None and value > 0]
        baseline_volume = _mean(volume_window)
        if bar_range is not None and bar_range > 0 and current_volume is not None and baseline_volume:
            vsa_ratio = current_volume / baseline_volume
            direction_text = str(result.get("price_change") or "")
            if direction_text in {"rising", "falling"}:
                vsa_pattern = "effort_result_up" if direction_text == "rising" else "effort_result_down"
                result.update({
                    "vsa_pattern": vsa_pattern,
                    "vsa_confirmation": "quote_proxy_confirmed" if vsa_ratio >= 1.05 else "quote_proxy_unconfirmed",
                    "vsa_volume_ratio": vsa_ratio,
                    "vsa_bar_spread": bar_range,
                    "vsa_data_provenance": "tick_activity_proxy",
                })
                provenance["volume_spread_analysis"] = "tick_activity_proxy"
    result["effort_result"] = "rising_price_on_tick_activity" if dominant == "up" else "falling_price_on_tick_activity" if dominant == "down" else "balanced_tick_activity"
    result["spread_to_micro_vol"] = current["spread"] / max(micro_vol * mid, 1e-12) if micro_vol is not None else None
    result["spread_to_realized_vol"] = current["spread"] / max(realized * mid, 1e-12) if realized else None
    result["cost_to_movement"] = result.get("spread_to_micro_vol")
    result["volume_context"] = {
        "source": "tick_activity_proxy",
        "is_real_volume": False,
        "tick_count": tick_count,
        "activity_ratio": activity_ratio,
    }
    result["quote_tick_dynamics"] = {
        "source": "point_in_time_quote_history",
        "tick_velocity": velocity,
        "tick_persistence": result.get("tick_persistence"),
        "spread": current["spread"],
    }
    event_times = []
    for item in points:
        event_time = _finite(item.get("time"))
        if event_time is not None and (not event_times or event_time > event_times[-1]):
            event_times.append(event_time)
    if len(event_times) >= 7:
        result["velu_event_times"] = event_times
        result["velu_duration_data_provenance"] = "observed_point_in_time_quote_history"
        provenance["velu_duration_intensity"] = "point_in_time_quote_history"

    # A quote-price profile is useful as an auction context, but it is not a
    # volume profile.  Keep that provenance explicit in the state.
    bins = 12
    profile_counts: dict[int, int] = {}
    if level_points and width > 0:
        for item in level_points:
            bucket = min(bins - 1, int((item["mid"] - range_low) / width * bins))
            profile_counts[bucket] = profile_counts.get(bucket, 0) + 1
        poc_bucket = max(profile_counts, key=profile_counts.get)
        poc = range_low + (poc_bucket + 0.5) * width / bins
        result["market_profile"] = {"source": "tick_price_profile_proxy", "bins": profile_counts}
        result["value_area"] = {"source": "tick_price_profile_proxy", "low": range_low, "high": range_high}
        result["poc"] = poc
        result["auction_state"] = "initiative_up" if dominant == "up" else "initiative_down" if dominant == "down" else "balance"
        result["opening_drive"] = dominant
        result["opening_type"] = "initiative" if dominant in {"up", "down"} else "balance"
        result["balance"] = dominant == "range"
        result["initiative"] = dominant

    if current_time is not None:
        session_name = _session(current_time)
        session_start = _session_start(current_time)
        result.setdefault("session", session_name)
        result.setdefault("session_state", "observed_quote_session")
        result.setdefault("market_state", "quote_observed")
        result.setdefault("market_open", True)
        result.setdefault("liquidity", "observed_quote_activity")
        if session_start is not None:
            result.setdefault("session_open", datetime.fromtimestamp(session_start, tz=timezone.utc).isoformat())
            prior_session = _previous_session_points(points, session_start)
            pivot = _pivot_context(prior_session, mid, pip)
            if pivot:
                result.update(pivot)
                provenance["pivot"] = pivot["pivot_data_provenance"]
            opening_end = session_start + 30.0 * 60.0
            opening_points = [
                item for item in points
                if session_start <= item.get("time", -math.inf) <= opening_end
            ]
            # Do not call an arbitrary recent range an opening range.  A
            # completed opening window must be observed from its own session.
            if session_name in {"asia", "london", "new_york"} and current_time >= opening_end and len(opening_points) >= 3:
                opening_high = max(item["mid"] for item in opening_points)
                opening_low = min(item["mid"] for item in opening_points)
                opening_width = max(opening_high - opening_low, pip)
                opening_direction = _trend(
                    opening_points[-1]["mid"] / opening_points[0]["mid"] - 1.0,
                    opening_width / max(opening_points[0]["mid"], 1e-12),
                )
                result.setdefault("opening_range_state", "complete")
                result.setdefault("initial_balance", {
                    "source": "quote_history",
                    "high": opening_high,
                    "low": opening_low,
                    "range": opening_width,
                })
                if mid > opening_high + max(opening_width * 0.02, pip):
                    opening_breakout = "breakout_up"
                elif mid < opening_low - max(opening_width * 0.02, pip):
                    opening_breakout = "breakout_down"
                else:
                    opening_breakout = "inside_range"
                result.setdefault("opening_range_breakout", opening_breakout)
                result.setdefault("opening_drive", opening_direction)
                result.setdefault("opening_type", "initiative" if opening_direction in {"up", "down"} else "balance")
                if prior_session:
                    result.setdefault("opening_gap", opening_points[0]["mid"] - prior_session[-1]["mid"])
                result.setdefault("initial_balance_high", opening_high)
                result.setdefault("initial_balance_low", opening_low)
                result.setdefault("current_price", mid)
                result.setdefault(
                    "profile_state",
                    f"initiative_{opening_direction}" if opening_direction in {"up", "down"} else "balance",
                )
                result.setdefault("initial_balance_status", "complete")
                provenance["initial_balance"] = "completed_session_quote_window"

    # Research geometry is derived from the observed structural range only;
    # it is never an execution instruction and carries explicit provenance.
    if level_points and not _present(result.get("stop")):
        entry = _finite(result.get("entry")) or mid
        side = str(result.get("side") or "").upper()
        if side == "BUY":
            stop = min(item["mid"] for item in level_points) - pip
            risk = max(entry - stop, pip)
            target = entry + 1.5 * risk
        elif side == "SELL":
            stop = max(item["mid"] for item in level_points) + pip
            risk = max(stop - entry, pip)
            target = entry - 1.5 * risk
        else:
            stop = target = None
        if stop is not None and target is not None:
            result["stop"] = stop
            result.setdefault("target", target)
            result["geometry_provenance"] = "watcher_structural_levels_proxy"

    _derive_cross_asset(result, symbol, now, points, universe_history)
    _derive_cross_sectional_momentum(result, symbol, now, points, universe_history)
    return result


__all__ = ["HORIZONS_S", "OUTCOME_KEYS", "enrich_watcher_state"]
