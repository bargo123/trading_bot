"""Cost-Aware Failed-Break Basket signal and features."""
from __future__ import annotations

from typing import Any, Optional

import numpy as np
import pandas as pd

from aegis.features import enrich_all
from aegis.indicators import adx, ema
from aegis.strategy import Signal, in_session


def _higher_timeframe_context(frame: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame:
    """Return lagged, fully closed higher-timeframe features without look-ahead."""
    minutes = max(2, int(cfg.get("cafb_context_minutes", 5)))
    fast = max(2, int(cfg.get("cafb_htf_fast", 8)))
    slow = max(fast + 1, int(cfg.get("cafb_htf_slow", 21)))
    adx_period = max(2, int(cfg.get("cafb_htf_adx_period", 14)))

    bars = frame[["time", "open", "high", "low", "close"]].copy()
    bars["time"] = pd.to_datetime(bars["time"], utc=True)
    bars = bars.sort_values("time").set_index("time")
    rule = f"{minutes}min"
    htf = (
        bars.resample(rule, label="left", closed="left")
        .agg({"open": "first", "high": "max", "low": "min", "close": "last"})
        .dropna()
    )
    htf["cafb_htf_ema_fast"] = ema(htf["close"], fast)
    htf["cafb_htf_ema_slow"] = ema(htf["close"], slow)
    htf["cafb_htf_adx"] = adx(htf["high"], htf["low"], htf["close"], adx_period)
    htf["cafb_htf_fast_prev"] = htf["cafb_htf_ema_fast"].shift(1)

    # Lag one whole bucket. A base bar never sees the still-forming HTF candle.
    cols = [
        "cafb_htf_ema_fast",
        "cafb_htf_ema_slow",
        "cafb_htf_adx",
        "cafb_htf_fast_prev",
    ]
    lagged = htf[cols].shift(1).reset_index()
    lagged["cafb_htf_regime"] = "range"
    adx_min = float(cfg.get("cafb_htf_adx_min", 18.0))
    up = (
        (lagged["cafb_htf_ema_fast"] > lagged["cafb_htf_ema_slow"])
        & (lagged["cafb_htf_ema_fast"] >= lagged["cafb_htf_fast_prev"])
        & (lagged["cafb_htf_adx"] >= adx_min)
    )
    down = (
        (lagged["cafb_htf_ema_fast"] < lagged["cafb_htf_ema_slow"])
        & (lagged["cafb_htf_ema_fast"] <= lagged["cafb_htf_fast_prev"])
        & (lagged["cafb_htf_adx"] >= adx_min)
    )
    lagged.loc[up, "cafb_htf_regime"] = "trend_up"
    lagged.loc[down, "cafb_htf_regime"] = "trend_down"
    return lagged


def prepare_cafb(df: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame:
    """Build CAFB features from raw or previously enriched OHLCV."""
    frame = enrich_all(df, cfg)
    frame = frame.sort_values("time").reset_index(drop=True)
    n = max(2, int(cfg.get("cafb_box_bars", 5)))
    frame["cafb_box_high"] = frame["high"].rolling(n).max().shift(1)
    frame["cafb_box_low"] = frame["low"].rolling(n).min().shift(1)
    frame["cafb_box_mid"] = (frame["cafb_box_high"] + frame["cafb_box_low"]) / 2.0
    width = frame["cafb_box_high"] - frame["cafb_box_low"]
    frame["cafb_box_width_atr"] = width / frame["atr"].replace(0, np.nan)
    min_atr = float(cfg.get("cafb_box_min_atr", 0.25))
    max_atr = float(cfg.get("cafb_box_max_atr", 2.0))
    frame["cafb_compressed"] = frame["cafb_box_width_atr"].between(min_atr, max_atr)
    same_bar_up = (
        frame["cafb_compressed"]
        & (frame["high"] > frame["cafb_box_high"])
        & (frame["close"] < frame["cafb_box_high"])
        & (frame["close"] >= frame["cafb_box_low"])
    )
    same_bar_dn = (
        frame["cafb_compressed"]
        & (frame["low"] < frame["cafb_box_low"])
        & (frame["close"] > frame["cafb_box_low"])
        & (frame["close"] <= frame["cafb_box_high"])
    )
    # Yahoo M1 FX frequently supplies close-only/degenerate bars. Preserve the
    # failed-break idea with an explicit two-bar break then re-entry against a
    # box frozen before the breakout bar.
    re_hi = frame["high"].rolling(n).max().shift(2)
    re_lo = frame["low"].rolling(n).min().shift(2)
    re_mid = (re_hi + re_lo) / 2.0
    re_width_atr = (re_hi - re_lo) / frame["atr"].shift(1).replace(0, np.nan)
    re_compressed = re_width_atr.between(min_atr, max_atr)
    prev_close = frame["close"].shift(1)
    two_bar_up = re_compressed & (prev_close > re_hi) & (frame["close"] < re_hi) & (frame["close"] >= re_lo)
    two_bar_dn = re_compressed & (prev_close < re_lo) & (frame["close"] > re_lo) & (frame["close"] <= re_hi)
    frame["cafb_two_bar_up"] = two_bar_up.fillna(False)
    frame["cafb_two_bar_dn"] = two_bar_dn.fillna(False)
    frame["cafb_failed_up"] = same_bar_up | frame["cafb_two_bar_up"]
    frame["cafb_failed_dn"] = same_bar_dn | frame["cafb_two_bar_dn"]
    frame["cafb_trade_box_high"] = np.where(frame["cafb_two_bar_up"] | frame["cafb_two_bar_dn"], re_hi, frame["cafb_box_high"])
    frame["cafb_trade_box_low"] = np.where(frame["cafb_two_bar_up"] | frame["cafb_two_bar_dn"], re_lo, frame["cafb_box_low"])
    frame["cafb_trade_box_mid"] = np.where(frame["cafb_two_bar_up"] | frame["cafb_two_bar_dn"], re_mid, frame["cafb_box_mid"])
    frame["cafb_prev_high"] = frame["high"].shift(1)
    frame["cafb_prev_low"] = frame["low"].shift(1)

    context = _higher_timeframe_context(frame, cfg)
    frame["time"] = pd.to_datetime(frame["time"], utc=True)
    frame = pd.merge_asof(
        frame.sort_values("time"),
        context.sort_values("time"),
        on="time",
        direction="backward",
    )
    return frame.reset_index(drop=True)


def _cost_ok(close: float, target_distance: float, cfg: dict[str, Any]) -> bool:
    one_way_bps = (
        float(cfg.get("spread_bps", 1.0))
        + float(cfg.get("slippage_bps", 0.5))
        + float(cfg.get("commission_bps", 0.0))
    )
    round_trip = abs(close) * (one_way_bps / 10000.0) * 2.0
    return target_distance > round_trip * float(cfg.get("cost_buffer", 1.5))


def _excluded_hour(ts: pd.Timestamp, cfg: dict[str, Any]) -> bool:
    raw = cfg.get("cafb_exclude_hours_utc", [21, 22])
    if isinstance(raw, str):
        hours = {int(x.strip()) for x in raw.split(",") if x.strip()}
    else:
        hours = {int(x) for x in (raw or [])}
    hour = ts.tz_convert("UTC").hour if getattr(ts, "tzinfo", None) else ts.hour
    return hour in hours


def sig_cafb(row: pd.Series, cfg: dict[str, Any]) -> Optional[Signal]:
    """Trade a failed box break only when regime, R:R, and cost gates agree."""
    required = [
        "time", "close", "high", "low", "atr", "cafb_box_low", "cafb_box_high",
        "cafb_box_mid", "cafb_htf_regime",
    ]
    if any(pd.isna(row.get(k)) for k in required):
        return None
    ts = pd.Timestamp(row["time"])
    if not in_session(ts, cfg.get("session_start_utc"), cfg.get("session_end_utc")):
        return None
    if _excluded_hour(ts, cfg):
        return None
    if not bool(row.get("cafb_compressed", False)):
        return None

    close = float(row["close"])
    atr_v = float(row["atr"])
    if atr_v <= 0:
        return None
    lo = float(row.get("cafb_trade_box_low", row["cafb_box_low"]))
    hi = float(row.get("cafb_trade_box_high", row["cafb_box_high"]))
    mid = float(row.get("cafb_trade_box_mid", row["cafb_box_mid"]))
    regime = str(row.get("cafb_htf_regime") or "range")
    allow_range = bool(cfg.get("cafb_allow_range", True))
    buffer = max(0.0, float(cfg.get("cafb_stop_buffer_atr", 0.15))) * atr_v
    target_mode = str(cfg.get("cafb_target_mode", "opposite")).lower()
    min_rr = max(0.0, float(cfg.get("cafb_min_rr", cfg.get("min_rr", 0.4))))

    if bool(row.get("cafb_failed_dn", False)) and (regime == "trend_up" or (allow_range and regime == "range")):
        prev_low = float(row.get("cafb_prev_low", row["low"]))
        sl = min(float(row["low"]), prev_low, lo) - buffer
        if target_mode == "extension":
            tp = close + float(cfg.get("cafb_target_box_frac", 1.0)) * (hi - lo)
        else:
            tp = hi if target_mode == "opposite" else mid
        risk, reward = close - sl, tp - close
        if risk <= 0 or reward <= 0 or reward / risk < min_rr or not _cost_ok(close, reward, cfg):
            return None
        branch = "trend" if regime == "trend_up" else "range"
        return Signal("buy", f"cafb_{branch}", close, sl, tp, None, ts, f"cafb_failed_dn_{branch}")

    if bool(row.get("cafb_failed_up", False)) and (regime == "trend_down" or (allow_range and regime == "range")):
        prev_high = float(row.get("cafb_prev_high", row["high"]))
        sl = max(float(row["high"]), prev_high, hi) + buffer
        if target_mode == "extension":
            tp = close - float(cfg.get("cafb_target_box_frac", 1.0)) * (hi - lo)
        else:
            tp = lo if target_mode == "opposite" else mid
        risk, reward = sl - close, close - tp
        if risk <= 0 or reward <= 0 or reward / risk < min_rr or not _cost_ok(close, reward, cfg):
            return None
        branch = "trend" if regime == "trend_down" else "range"
        return Signal("sell", f"cafb_{branch}", close, sl, tp, None, ts, f"cafb_failed_up_{branch}")
    return None
