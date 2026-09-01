"""Pure completed-bar market-state semantics shared by runtime and research."""
from __future__ import annotations

from typing import Any

import pandas as pd

from aegis.completed_bars import TF_MINUTES, resample_completed


def session_label(ts: Any) -> str:
    stamp = pd.Timestamp(ts)
    stamp = stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")
    if 7 <= stamp.hour < 13:
        return "london"
    if 13 <= stamp.hour < 21:
        return "newyork"
    return "asia"


def direction(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "unavailable"
    last = frame.iloc[-1]
    if float(last["close"]) > float(last["open"]):
        return "up"
    if float(last["close"]) < float(last["open"]):
        return "down"
    return "flat"


def volatility(m1: pd.DataFrame) -> dict[str, Any]:
    ranges = (m1["high"].astype(float) - m1["low"].astype(float)).abs()
    recent = ranges.tail(20)
    prior = ranges.iloc[max(0, len(ranges) - 40) : max(0, len(ranges) - 20)]
    recent_mean = float(recent.mean()) if len(recent) else None
    prior_mean = float(prior.mean()) if len(prior) else None
    if recent_mean is None or prior_mean is None or prior_mean <= 0:
        phase = "unavailable"
    elif recent_mean > prior_mean:
        phase = "expanding"
    elif recent_mean < prior_mean:
        phase = "compressing"
    else:
        phase = "stable"
    return {
        "range_mean_20": recent_mean,
        "range_mean_prior_20": prior_mean,
        "phase": phase,
        "source": "completed_m1_ranges",
    }


def confirmed_pivots(
    frame: pd.DataFrame, *, left: int = 1, right: int = 1
) -> list[dict[str, Any]]:
    """Return pivots only after all bars required to confirm them have closed."""
    if len(frame) < left + right + 1:
        return []
    high = frame["high"].astype(float)
    low = frame["low"].astype(float)
    pivots: list[dict[str, Any]] = []
    for index in range(left, len(frame) - right):
        window_high = high.iloc[index - left : index + right + 1]
        window_low = low.iloc[index - left : index + right + 1]
        if float(high.iloc[index]) >= float(window_high.max()) and float(high.iloc[index]) > float(high.iloc[index - 1]):
            pivots.append({"kind": "high", "bar_index": index, "decided_at": index + right, "price": float(high.iloc[index])})
        if float(low.iloc[index]) <= float(window_low.min()) and float(low.iloc[index]) < float(low.iloc[index - 1]):
            pivots.append({"kind": "low", "bar_index": index, "decided_at": index + right, "price": float(low.iloc[index])})
    return pivots


def structure_event(frame: pd.DataFrame) -> dict[str, Any]:
    pivots = confirmed_pivots(frame)
    last_close = float(frame["close"].iloc[-1])
    highs = [pivot for pivot in pivots if pivot["kind"] == "high"]
    lows = [pivot for pivot in pivots if pivot["kind"] == "low"]
    resistance = max((pivot["price"] for pivot in highs), default=None)
    support = min((pivot["price"] for pivot in lows), default=None)
    kind = "none"
    if resistance is not None and last_close > resistance:
        kind = "breakout"
        if len(frame) >= 2 and float(frame["high"].iloc[-2]) > resistance and last_close < resistance:
            kind = "failure"
    elif support is not None and last_close < support:
        kind = "breakout"
        if len(frame) >= 2 and float(frame["low"].iloc[-2]) < support and last_close > support:
            kind = "failure"
    elif resistance is not None and abs(last_close - resistance) / max(resistance, 1e-9) < 0.0003:
        kind = "retest"
    elif support is not None and abs(last_close - support) / max(support, 1e-9) < 0.0003:
        kind = "retest"
    return {
        "kind": kind,
        "lookahead": False,
        "support": support,
        "resistance": resistance,
        "n_pivots": len(pivots),
        "label": "research_proxy",
    }


def classify_regime(m1: pd.DataFrame) -> dict[str, Any]:
    frames = {timeframe: resample_completed(m1, timeframe) for timeframe in TF_MINUTES}
    h1 = frames["H1"]
    m5 = frames["M5"]
    used = [timeframe for timeframe in ("M5", "M15", "H1", "H4") if not frames[timeframe].empty]
    label = "no_trade"
    if not h1.empty and not m5.empty:
        h1_up = float(h1["close"].iloc[-1]) >= float(h1["open"].iloc[-1])
        m5_up = float(m5["close"].iloc[-1]) >= float(m5["open"].iloc[-1])
        label = "trend" if h1_up == m5_up else "range"
        if abs(float(m5["close"].iloc[-1]) - float(m5["open"].iloc[-1])) <= 0:
            label = "noise"
    return {
        "schema": "regime.v1",
        "label": label,
        "used_tfs": used,
        "lookahead": False,
        "source": "resampled_completed_bars",
    }


def atr(frame: pd.DataFrame, periods: int = 14) -> float | None:
    if len(frame) < periods + 1:
        return None
    highs = frame["high"].astype(float)
    lows = frame["low"].astype(float)
    closes = frame["close"].astype(float)
    previous_close = closes.shift(1)
    true_range = pd.concat(
        [highs - lows, (highs - previous_close).abs(), (lows - previous_close).abs()], axis=1
    ).max(axis=1)
    return round(float(true_range.tail(periods).mean()), 8)


def compression(frame: pd.DataFrame) -> float | None:
    if frame.empty:
        return None
    last = frame.iloc[-1]
    body = abs(float(last["close"]) - float(last["open"]))
    price_range = float(last["high"]) - float(last["low"])
    if price_range <= 0:
        return None
    return round(body / price_range, 4)
