"""Runtime market context for Intelligent Firehose. No research imports."""
from __future__ import annotations

from typing import Any, Mapping

import pandas as pd


def _atr(frame: pd.DataFrame, periods: int = 14) -> float | None:
    """Average True Range from completed bars."""
    if len(frame) < periods + 1:
        return None
    highs = frame["high"].astype(float)
    lows = frame["low"].astype(float)
    closes = frame["close"].astype(float)
    prev_closes = closes.shift(1)
    tr = pd.concat([
        highs - lows,
        (highs - prev_closes).abs(),
        (lows - prev_closes).abs()
    ], axis=1).max(axis=1)
    return round(float(tr.tail(periods).mean()), 8)


def _compression(frame: pd.DataFrame) -> float | None:
    """Body/range compression ratio for completed bars."""
    if frame.empty:
        return None
    last = frame.iloc[-1]
    body = abs(float(last["close"]) - float(last["open"]))
    rng = float(last["high"]) - float(last["low"])
    if rng <= 0:
        return None
    return round(body / rng, 4)


def _structure_full(frame: pd.DataFrame) -> dict[str, Any]:
    """Complete structure with S/R, direction, ATR, compression from completed bars."""
    if len(frame) < 5:
        return {
            "kind": "unavailable",
            "support": None,
            "resistance": None,
            "direction": None,
            "atr": None,
            "compression": None,
        }
    highs = frame["high"].astype(float)
    lows = frame["low"].astype(float)
    closes = frame["close"].astype(float)
    opens = frame["open"].astype(float)
    resistance = float(highs.tail(20).max())
    support = float(lows.tail(20).min())
    close = float(closes.iloc[-1])
    open_ = float(opens.iloc[-1])
    kind = "none"
    if close > resistance * 0.9999:
        kind = "breakout"
    elif close < support * 1.0001:
        kind = "breakout"
    elif abs(close - resistance) / max(resistance, 1e-9) < 0.0003:
        kind = "retest"
    elif abs(close - support) / max(support, 1e-9) < 0.0003:
        kind = "retest"
    direction = "up" if close > open_ else ("down" if close < open_ else "flat")
    atr_val = _atr(frame)
    comp = _compression(frame.tail(1))
    return {
        "kind": kind,
        "support": support,
        "resistance": resistance,
        "direction": direction,
        "atr": atr_val,
        "compression": comp,
    }


def _direction(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "unavailable"
    last = frame.iloc[-1]
    if float(last["close"]) > float(last["open"]):
        return "up"
    if float(last["close"]) < float(last["open"]):
        return "down"
    return "flat"


def _resample(m1: pd.DataFrame, minutes: int) -> pd.DataFrame:
    frame = m1.copy()
    frame["time"] = pd.to_datetime(frame["time"], utc=True)
    frame = frame.set_index("time")
    out = frame.resample(f"{minutes}min", label="right", closed="right").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    )
    out = out.dropna(subset=["close"]).reset_index()
    # Drop the last bar: resample with label="right" always produces a bar for
    # the current incomplete period (right edge = bin end time).
    if len(out) > 0:
        out = out.iloc[:-1]
    return out


def _volatility(m1: pd.DataFrame) -> str:
    ranges = (m1["high"].astype(float) - m1["low"].astype(float)).abs()
    recent = ranges.tail(20)
    prior = ranges.iloc[max(0, len(ranges) - 40) : max(0, len(ranges) - 20)]
    if recent.empty or prior.empty:
        return "unavailable"
    recent_mean = float(recent.mean())
    prior_mean = float(prior.mean())
    if prior_mean <= 0:
        return "unavailable"
    if recent_mean > prior_mean:
        return "expanding"
    if recent_mean < prior_mean:
        return "compressing"
    return "stable"


def _structure(m15: pd.DataFrame) -> dict[str, Any]:
    if len(m15) < 5:
        return {"kind": "unavailable", "support": None, "resistance": None}
    highs = m15["high"].astype(float)
    lows = m15["low"].astype(float)
    resistance = float(highs.tail(20).max())
    support = float(lows.tail(20).min())
    close = float(m15["close"].iloc[-1])
    kind = "none"
    if close > resistance * 0.9999:
        kind = "breakout"
    elif close < support * 1.0001:
        kind = "breakout"
    elif abs(close - resistance) / max(resistance, 1e-9) < 0.0003:
        kind = "retest"
    elif abs(close - support) / max(support, 1e-9) < 0.0003:
        kind = "retest"
    return {"kind": kind, "support": support, "resistance": resistance}


def build_runtime_state(*, symbol: str, m1: pd.DataFrame) -> dict[str, Any]:
    """Minimal completed-bar state for demo brain and analogue signatures."""
    source = m1.copy()
    source["time"] = pd.to_datetime(source["time"], utc=True)
    source = source.sort_values("time").reset_index(drop=True)
    m5 = _resample(source, 5)
    m15 = _resample(source, 15)
    h1 = _resample(source, 60)
    h1_dir = _direction(h1)
    m5_dir = _direction(m5)
    if h1_dir in {"up", "down"} and m5_dir in {"up", "down"}:
        regime = "trend" if h1_dir == m5_dir else "range"
    else:
        regime = "unknown"
    m15_struct = _structure_full(m15)
    m5_struct = _structure_full(m5)
    return {
        "schema": "runtime_state.v1",
        "symbol": str(symbol).upper(),
        "observed_at": str(source["time"].iloc[-1]),
        "regime": {"label": regime},
        "structure": {
            "M15": {
                "kind": m15_struct["kind"],
                "support": m15_struct["support"],
                "resistance": m15_struct["resistance"],
                "direction": m15_struct["direction"],
                "atr": m15_struct["atr"],
            },
            "M5": {
                "kind": m5_struct["kind"],
                "support": m5_struct["support"],
                "resistance": m5_struct["resistance"],
                "direction": m5_struct["direction"],
                "atr": m5_struct["atr"],
                "compression": m5_struct["compression"],
            },
        },
        "multi_timeframe": {
            "M5": {"direction": m5_struct["direction"]},  # genuine M5 direction from completed bars
            "M15": {"direction": m15_struct["direction"]},  # genuine M15 direction from completed bars
            "H1": {"direction": h1_dir},
        },
        "volatility": {"phase": _volatility(source)},
        "session": _session(source["time"].iloc[-1]),
    }


def _session(ts: pd.Timestamp) -> str:
    """Session label. Must match aegis.research.dataplane.session_label so runtime
    signatures line up with the analogue index and validated-state allowlists.
    """
    stamp = pd.Timestamp(ts)
    if stamp.tzinfo is None:
        stamp = stamp.tz_localize("UTC")
    else:
        stamp = stamp.tz_convert("UTC")
    hour = stamp.hour
    if 7 <= hour < 13:
        return "london"
    if 13 <= hour < 21:
        return "newyork"
    return "asia"


def runtime_signature(state: Mapping[str, Any], *, side: str, setup: str) -> dict[str, str]:
    mtf = state.get("multi_timeframe") if isinstance(state.get("multi_timeframe"), Mapping) else {}
    structure = state.get("structure") if isinstance(state.get("structure"), Mapping) else {}
    m15 = structure.get("M15") if isinstance(structure.get("M15"), Mapping) else {}
    regime = state.get("regime") if isinstance(state.get("regime"), Mapping) else {}
    vol = state.get("volatility") if isinstance(state.get("volatility"), Mapping) else {}
    return {
        "symbol": str(state.get("symbol") or ""),
        "side": str(side).lower(),
        "setup": str(setup or "unknown"),
        "regime": str(regime.get("label") or "unknown"),
        "structure": str(m15.get("kind") or "none"),
        "volatility": str(vol.get("phase") or "unknown"),
        "session": str(state.get("session") or "unknown"),
        "h1_direction": str((mtf.get("H1") or {}).get("direction") or "unavailable"),
        "m5_direction": str((mtf.get("M5") or {}).get("direction") or "unavailable"),
    }
