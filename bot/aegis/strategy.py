from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import pandas as pd

from aegis.indicators import enrich

Side = Literal["buy", "sell"]

# Heikin-Ashi Level Exhaustion families live in aegis.hale but must route through the
# generic strategy entry points so paper/demo runners can select them by config.
HALE_MODES = frozenset({"hale_fade", "hale_pullback"})


@dataclass
class Signal:
    side: Side
    mode: str  # trend | range
    entry: float
    sl: float
    tp: float | None
    trail_atr_mult: float | None
    time: pd.Timestamp
    reason: str


def in_session(ts: pd.Timestamp, start: int | None, end: int | None) -> bool:
    if start is None or end is None:
        return True
    hour = ts.tz_convert("UTC").hour if getattr(ts, "tzinfo", None) else ts.hour
    if start <= end:
        return start <= hour < end
    return hour >= start or hour < end


def signal_scalper_2h(row: pd.Series, cfg: dict[str, Any]) -> Signal | None:
    """Fast RSI+BB scalper for short play sessions (many signals, tight exits)."""
    if pd.isna(row.get("atr")) or float(row["atr"]) <= 0:
        return None
    if not in_session(row["time"], cfg.get("session_start_utc"), cfg.get("session_end_utc")):
        return None
    if pd.isna(row.get("bb_lower")) or pd.isna(row.get("rsi")):
        return None

    close = float(row["close"])
    atr_v = float(row["atr"])
    rsi_v = float(row["rsi"])
    bb_lower, bb_upper, bb_mid = float(row["bb_lower"]), float(row["bb_upper"]), float(row["bb_mid"])
    sl_m = float(cfg.get("atr_sl_mult", 1.2))
    tp_m = float(cfg.get("atr_tp_mult", 0.9))
    os_ = float(cfg.get("rsi_oversold", 40))
    ob_ = float(cfg.get("rsi_overbought", 60))

    # Long: near lower band or oversold RSI
    if close <= bb_lower or rsi_v <= os_:
        sl = close - max(sl_m * atr_v, atr_v * 0.8)
        tp = close + tp_m * atr_v
        if tp <= close or sl >= close:
            return None
        return Signal("buy", "scalp", close, sl, tp, None, row["time"], "scalper_2h_long")

    # Short: near upper band or overbought RSI
    if close >= bb_upper or rsi_v >= ob_:
        sl = close + max(sl_m * atr_v, atr_v * 0.8)
        tp = close - tp_m * atr_v
        if tp >= close or sl <= close:
            return None
        return Signal("sell", "scalp", close, sl, tp, None, row["time"], "scalper_2h_short")
    return None


def signal_from_row(row: pd.Series, cfg: dict[str, Any]) -> Signal | None:
    mode = str(cfg.get("signal_mode") or cfg.get("algo") or "").lower()
    if mode in {"scalper_2h", "scalp_2h", "2h"}:
        return signal_scalper_2h(row, cfg)
    if mode in HALE_MODES:
        from aegis.hale import sig_hale_fade, sig_hale_pullback

        return (sig_hale_fade if mode == "hale_fade" else sig_hale_pullback)(row, cfg)
    if mode in {"hw_range", "trend_pullback", "breakout_adx", "rsi_cross", "squeeze_bo",
                "aziz_orb", "aziz_vwap", "steidl_ib_break", "steidl_ib_fade", "fabris_ntz",
                "book_optimal", "hw_runner", "thomas_10r", "volman_scalp", "chan_bb_scalp",
                "firehose", "cafb", "pulse_scalp", "ensemble", "ensemble_optimal", "all_books",
                "pa_select"}:
        from aegis.session_algos import ALGOS

        return ALGOS[mode](row, cfg)

    if pd.isna(row.get("atr")) or float(row["atr"]) <= 0:
        return None
    if not in_session(row["time"], cfg.get("session_start_utc"), cfg.get("session_end_utc")):
        return None

    close = float(row["close"])
    atr_v = float(row["atr"])
    min_atr_pct = float(cfg.get("min_atr_pct", 0.0))
    if min_atr_pct > 0 and (atr_v / close) < min_atr_pct:
        return None

    adx_v = float(row["adx"]) if not pd.isna(row.get("adx")) else 0.0
    regime = str(row.get("regime") or "range")
    trend_th = float(cfg.get("adx_trend_threshold", 25))
    range_max = float(cfg.get("adx_range_max", 18))

    # TREND MODE — only when ADX confirms trend strength
    if regime in {"trend_up", "trend_down"} and adx_v >= trend_th:
        dh, dl = row.get("donch_high"), row.get("donch_low")
        if pd.isna(dh) or pd.isna(dl):
            return None
        trail = float(cfg["atr_trail_mult"])
        if regime == "trend_up" and close > float(dh):
            sl = close - trail * atr_v
            return Signal("buy", "trend", close, sl, None, trail, row["time"], "donchian_breakout_up")
        if regime == "trend_down" and close < float(dl):
            sl = close + trail * atr_v
            return Signal("sell", "trend", close, sl, None, trail, row["time"], "donchian_breakout_down")
        return None

    # RANGE MODE — only when ADX is clearly weak (avoid transition chop)
    if adx_v > range_max:
        return None
    if pd.isna(row.get("bb_lower")):
        return None
    rsi_v = float(row["rsi"])
    bb_lower, bb_upper, bb_mid = float(row["bb_lower"]), float(row["bb_upper"]), float(row["bb_mid"])
    sl_m = float(cfg["atr_sl_mult"])
    tp_m = float(cfg["atr_tp_mult"])

    if close < bb_lower and rsi_v < float(cfg["rsi_oversold"]):
        sl = close - max(sl_m * atr_v, atr_v)  # floor stop to >= 1 ATR
        tp = min(bb_mid, close + tp_m * atr_v)
        if tp <= close or sl >= close:
            return None
        return Signal("buy", "range", close, sl, tp, None, row["time"], "bb_rsi_long")

    if close > bb_upper and rsi_v > float(cfg["rsi_overbought"]):
        sl = close + max(sl_m * atr_v, atr_v)
        tp = max(bb_mid, close - tp_m * atr_v)
        if tp >= close or sl <= close:
            return None
        return Signal("sell", "range", close, sl, tp, None, row["time"], "bb_rsi_short")

    return None


def latest_signal(df: pd.DataFrame, cfg: dict[str, Any]) -> Signal | None:
    frame = prepare(df, cfg)
    if len(frame) < 3:
        return None
    return signal_from_row(frame.iloc[-2], cfg)  # last closed bar


def prepare(df: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame:
    mode = str(cfg.get("signal_mode") or cfg.get("algo") or "").lower()
    if mode in {"hw_range", "trend_pullback", "breakout_adx", "rsi_cross", "squeeze_bo", "scalper_2h", "scalp_2h", "2h",
                "aziz_orb", "aziz_vwap", "steidl_ib_break", "steidl_ib_fade", "fabris_ntz", "book_optimal",
                "volman_scalp", "chan_bb_scalp", "firehose", "hw_runner", "thomas_10r", "ensemble", "ensemble_optimal", "all_books"}:
        from aegis.features import enrich_all

        frame = enrich_all(df, cfg)
        frame["rsi_prev"] = frame["rsi"].shift(1)
        frame["close_prev"] = frame["close"].shift(1)
        frame["high_prev"] = frame["high"].shift(1)
        frame["low_prev"] = frame["low"].shift(1)
        return frame
    if mode == "cafb":
        from aegis.cafb import prepare_cafb

        return prepare_cafb(df, cfg)
    if mode == "pulse_scalp":
        from aegis.pulse import prepare_pulse

        return prepare_pulse(df, cfg)
    if mode == "pa_select":
        from aegis.pa_select import prepare_pa_select

        return prepare_pa_select(df, cfg)
    if mode in HALE_MODES:
        from aegis.hale import prepare_hale

        return prepare_hale(df, cfg)
    return enrich(df, cfg)
