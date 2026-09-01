"""EMA/ATR pullback-confirmation scalp for higher trade frequency."""
from __future__ import annotations

from typing import Any, Optional

import pandas as pd

from aegis.cafb import _cost_ok, _excluded_hour, _higher_timeframe_context
from aegis.features import enrich_all
from aegis.strategy import Signal, in_session


def prepare_pulse(df: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame:
    frame = enrich_all(df, cfg).sort_values("time").reset_index(drop=True)
    frame["pulse_close_prev"] = frame["close"].shift(1)
    context = _higher_timeframe_context(frame, cfg)
    frame["time"] = pd.to_datetime(frame["time"], utc=True)
    frame = pd.merge_asof(
        frame.sort_values("time"),
        context.sort_values("time"),
        on="time",
        direction="backward",
    )
    return frame.reset_index(drop=True)


def sig_pulse(row: pd.Series, cfg: dict[str, Any]) -> Optional[Signal]:
    required = ["time", "close", "pulse_close_prev", "ema_20", "atr", "rsi", "cafb_htf_regime"]
    if any(pd.isna(row.get(k)) for k in required):
        return None
    ts = pd.Timestamp(row["time"])
    if not in_session(ts, cfg.get("session_start_utc"), cfg.get("session_end_utc")):
        return None
    if _excluded_hour(ts, cfg):
        return None
    close = float(row["close"])
    prev = float(row["pulse_close_prev"])
    ema20 = float(row["ema_20"])
    atr_v = float(row["atr"])
    rsi_v = float(row["rsi"])
    if atr_v <= 0:
        return None

    regime = str(row.get("cafb_htf_regime") or "range")
    mode = str(cfg.get("pulse_regime_mode", "both")).lower()
    z = max(0.0, float(cfg.get("pulse_z_atr", 0.5)))
    edge = float(cfg.get("pulse_rsi_edge", 40.0))
    near = max(0.0, float(cfg.get("pulse_trend_near_atr", 0.75)))
    pullback_rsi = float(cfg.get("pulse_trend_rsi", 55.0))
    dist = (close - ema20) / atr_v
    turned_up = close > prev
    turned_down = close < prev

    range_long = mode in {"range", "both"} and regime == "range" and dist <= -z and rsi_v <= edge and turned_up
    range_short = mode in {"range", "both"} and regime == "range" and dist >= z and rsi_v >= 100.0 - edge and turned_down
    trend_long = (
        mode in {"trend", "both"}
        and regime == "trend_up"
        and close <= ema20 + near * atr_v
        and rsi_v <= pullback_rsi
        and turned_up
    )
    trend_short = (
        mode in {"trend", "both"}
        and regime == "trend_down"
        and close >= ema20 - near * atr_v
        and rsi_v >= 100.0 - pullback_rsi
        and turned_down
    )
    if not (range_long or range_short or trend_long or trend_short):
        return None

    if cfg.get("pulse_tp_pips") is not None:
        pip = float(cfg.get("pulse_pip_size", 0.0001))
        reward = max(0.01, float(cfg["pulse_tp_pips"])) * pip
        stop_distance = max(0.01, float(cfg.get("pulse_sl_pips", 10.0))) * pip
    else:
        sl_atr = max(0.05, float(cfg.get("pulse_sl_atr", 3.0)))
        tp_atr = max(0.01, float(cfg.get("pulse_tp_atr", 0.5)))
        reward = tp_atr * atr_v
        stop_distance = sl_atr * atr_v
    if not _cost_ok(close, reward, cfg):
        return None
    if range_long or trend_long:
        branch = "range" if range_long else "trend"
        return Signal(
            "buy",
            f"pulse_{branch}",
            close,
            close - stop_distance,
            close + reward,
            None,
            ts,
            f"pulse_{branch}_long",
        )
    branch = "range" if range_short else "trend"
    return Signal(
        "sell",
        f"pulse_{branch}",
        close,
        close + stop_distance,
        close - reward,
        None,
        ts,
        f"pulse_{branch}_short",
    )
