from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

import pandas as pd

from aegis.features import enrich_all
from aegis.strategy import Signal, in_session

SignalFn = Callable[[pd.Series, dict[str, Any]], Optional[Signal]]


def _base_ok(row: pd.Series, cfg: dict[str, Any]) -> bool:
    if pd.isna(row.get("atr")) or float(row["atr"]) <= 0:
        return False
    if not in_session(row["time"], cfg.get("session_start_utc"), cfg.get("session_end_utc")):
        return False
    close = float(row["close"])
    atr_v = float(row["atr"])
    min_atr_pct = float(cfg.get("min_atr_pct", 0.0004))
    if min_atr_pct > 0 and (atr_v / close) < min_atr_pct:
        return False
    return True


def sig_aegis_range_hw(row: pd.Series, cfg: dict[str, Any]) -> Signal | None:
    """High-win-rate BB+RSI range scalper (optimized profile)."""
    if not _base_ok(row, cfg):
        return None
    if float(row.get("adx") or 0) > 22:
        return None
    if pd.isna(row.get("bb_lower")):
        return None
    close, atr_v, rsi_v = float(row["close"]), float(row["atr"]), float(row["rsi"])
    bb_lower, bb_upper, bb_mid = float(row["bb_lower"]), float(row["bb_upper"]), float(row["bb_mid"])
    if close < bb_lower and rsi_v < 30:
        sl = close - 3.0 * atr_v
        tp = min(bb_mid, close + 0.6 * atr_v)
        if tp <= close:
            return None
        return Signal("buy", "range", close, sl, tp, None, row["time"], "aegis_range_hw")
    if close > bb_upper and rsi_v > 75:
        sl = close + 3.0 * atr_v
        tp = max(bb_mid, close - 0.6 * atr_v)
        if tp >= close:
            return None
        return Signal("sell", "range", close, sl, tp, None, row["time"], "aegis_range_hw")
    return None


def sig_donchian55_trend(row: pd.Series, cfg: dict[str, Any]) -> Signal | None:
    """Clenow/Turtle-style 55 Donchian breakout + ATR trail."""
    if not _base_ok(row, cfg):
        return None
    if float(row.get("adx") or 0) < 20:
        return None
    close, atr_v = float(row["close"]), float(row["atr"])
    dh, dl = row.get("donch_high"), row.get("donch_low")
    if pd.isna(dh) or pd.isna(dl):
        return None
    if close > float(dh) and row["ema_fast"] > row["ema_slow"]:
        return Signal("buy", "trend", close, close - 3 * atr_v, None, 3.0, row["time"], "donch55")
    if close < float(dl) and row["ema_fast"] < row["ema_slow"]:
        return Signal("sell", "trend", close, close + 3 * atr_v, None, 3.0, row["time"], "donch55")
    return None


def sig_donchian20_turtle(row: pd.Series, cfg: dict[str, Any]) -> Signal | None:
    """Shorter Donchian 20 breakout."""
    if not _base_ok(row, cfg):
        return None
    close, atr_v = float(row["close"]), float(row["atr"])
    dh, dl = row.get("donch20_high"), row.get("donch20_low")
    if pd.isna(dh) or pd.isna(dl):
        return None
    if close > float(dh):
        return Signal("buy", "trend", close, close - 2.5 * atr_v, None, 2.5, row["time"], "donch20")
    if close < float(dl):
        return Signal("sell", "trend", close, close + 2.5 * atr_v, None, 2.5, row["time"], "donch20")
    return None


def sig_ema_cross(row: pd.Series, cfg: dict[str, Any]) -> Signal | None:
    """Classic EMA 50/200 cross (Edwards/Magee trend spirit)."""
    if not _base_ok(row, cfg):
        return None
    # need previous values — encoded as columns set in prepare
    if pd.isna(row.get("ema_fast_prev")):
        return None
    close, atr_v = float(row["close"]), float(row["atr"])
    f, s = float(row["ema_fast"]), float(row["ema_slow"])
    fp, sp = float(row["ema_fast_prev"]), float(row["ema_slow_prev"])
    if fp <= sp and f > s:
        return Signal("buy", "trend", close, close - 3 * atr_v, None, 3.0, row["time"], "ema_cross")
    if fp >= sp and f < s:
        return Signal("sell", "trend", close, close + 3 * atr_v, None, 3.0, row["time"], "ema_cross")
    return None


def sig_rsi_pure(row: pd.Series, cfg: dict[str, Any]) -> Signal | None:
    """Pure RSI mean reversion (Schwager oscillator chapter spirit)."""
    if not _base_ok(row, cfg):
        return None
    close, atr_v, rsi_v = float(row["close"]), float(row["atr"]), float(row["rsi"])
    if rsi_v < 25:
        return Signal("buy", "range", close, close - 2.5 * atr_v, close + 0.8 * atr_v, None, row["time"], "rsi_pure")
    if rsi_v > 75:
        return Signal("sell", "range", close, close + 2.5 * atr_v, close - 0.8 * atr_v, None, row["time"], "rsi_pure")
    return None


def sig_bb_mr(row: pd.Series, cfg: dict[str, Any]) -> Signal | None:
    """Bollinger band fade without RSI filter."""
    if not _base_ok(row, cfg):
        return None
    if pd.isna(row.get("bb_lower")):
        return None
    close, atr_v = float(row["close"]), float(row["atr"])
    if close < float(row["bb_lower"]):
        tp = min(float(row["bb_mid"]), close + 0.7 * atr_v)
        return Signal("buy", "range", close, close - 2.5 * atr_v, tp, None, row["time"], "bb_mr")
    if close > float(row["bb_upper"]):
        tp = max(float(row["bb_mid"]), close - 0.7 * atr_v)
        return Signal("sell", "range", close, close + 2.5 * atr_v, tp, None, row["time"], "bb_mr")
    return None


def sig_macd_cross(row: pd.Series, cfg: dict[str, Any]) -> Signal | None:
    """MACD line/signal cross."""
    if not _base_ok(row, cfg):
        return None
    if pd.isna(row.get("macd_prev")):
        return None
    close, atr_v = float(row["close"]), float(row["atr"])
    m, s = float(row["macd"]), float(row["macd_signal"])
    mp, sp = float(row["macd_prev"]), float(row["macd_signal_prev"])
    if mp <= sp and m > s:
        return Signal("buy", "trend", close, close - 2.5 * atr_v, None, 2.5, row["time"], "macd_cross")
    if mp >= sp and m < s:
        return Signal("sell", "trend", close, close + 2.5 * atr_v, None, 2.5, row["time"], "macd_cross")
    return None


def sig_stoch_mr(row: pd.Series, cfg: dict[str, Any]) -> Signal | None:
    """Stochastic mean reversion."""
    if not _base_ok(row, cfg):
        return None
    close, atr_v = float(row["close"]), float(row["atr"])
    k, d = float(row["stoch_k"]), float(row["stoch_d"])
    if k < 20 and d < 25:
        return Signal("buy", "range", close, close - 2.5 * atr_v, close + 0.7 * atr_v, None, row["time"], "stoch_mr")
    if k > 80 and d > 75:
        return Signal("sell", "range", close, close + 2.5 * atr_v, close - 0.7 * atr_v, None, row["time"], "stoch_mr")
    return None


def sig_atr_breakout(row: pd.Series, cfg: dict[str, Any]) -> Signal | None:
    """ATR channel breakout around SMA20."""
    if not _base_ok(row, cfg):
        return None
    if pd.isna(row.get("atr_channel_up")):
        return None
    close, atr_v = float(row["close"]), float(row["atr"])
    if close > float(row["atr_channel_up"]):
        return Signal("buy", "trend", close, close - 2.5 * atr_v, None, 2.5, row["time"], "atr_breakout")
    if close < float(row["atr_channel_dn"]):
        return Signal("sell", "trend", close, close + 2.5 * atr_v, None, 2.5, row["time"], "atr_breakout")
    return None


def sig_bb_squeeze_breakout(row: pd.Series, cfg: dict[str, Any]) -> Signal | None:
    """Squeeze then breakout (volatility expansion)."""
    if not _base_ok(row, cfg):
        return None
    if pd.isna(row.get("bb_width_ma")) or pd.isna(row.get("bb_upper")):
        return None
    close, atr_v = float(row["close"]), float(row["atr"])
    squeezed = float(row["bb_width"]) < float(row["bb_width_ma"]) * 0.75
    if not squeezed:
        return None
    if close > float(row["bb_upper"]):
        return Signal("buy", "trend", close, close - 2.5 * atr_v, None, 2.5, row["time"], "bb_squeeze")
    if close < float(row["bb_lower"]):
        return Signal("sell", "trend", close, close + 2.5 * atr_v, None, 2.5, row["time"], "bb_squeeze")
    return None


def sig_elder_impulse_proxy(row: pd.Series, cfg: dict[str, Any]) -> Signal | None:
    """Elder-inspired impulse proxy: EMA13 rising + MACD hist rising for longs."""
    if not _base_ok(row, cfg):
        return None
    if pd.isna(row.get("ema_13_prev")) or pd.isna(row.get("macd_hist_prev")):
        return None
    close, atr_v = float(row["close"]), float(row["atr"])
    ema_up = float(row["ema_13"]) > float(row["ema_13_prev"])
    ema_dn = float(row["ema_13"]) < float(row["ema_13_prev"])
    hist_up = float(row["macd_hist"]) > float(row["macd_hist_prev"])
    hist_dn = float(row["macd_hist"]) < float(row["macd_hist_prev"])
    # Enter on fresh alignment
    if ema_up and hist_up and float(row["macd_hist_prev"]) <= 0 <= float(row["macd_hist"]):
        return Signal("buy", "trend", close, close - 2.5 * atr_v, None, 2.5, row["time"], "elder_impulse")
    if ema_dn and hist_dn and float(row["macd_hist_prev"]) >= 0 >= float(row["macd_hist"]):
        return Signal("sell", "trend", close, close + 2.5 * atr_v, None, 2.5, row["time"], "elder_impulse")
    return None


def prepare_bakeoff(df: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame:
    frame = enrich_all(df, cfg)
    frame["ema_fast_prev"] = frame["ema_fast"].shift(1)
    frame["ema_slow_prev"] = frame["ema_slow"].shift(1)
    frame["macd_prev"] = frame["macd"].shift(1)
    frame["macd_signal_prev"] = frame["macd_signal"].shift(1)
    frame["macd_hist_prev"] = frame["macd_hist"].shift(1)
    frame["ema_13_prev"] = frame["ema_13"].shift(1)
    return frame


@dataclass(frozen=True)
class StrategySpec:
    id: str
    name: str
    book_basis: str
    signal_fn: SignalFn


STRATEGIES: list[StrategySpec] = [
    StrategySpec("aegis_range_hw", "Aegis Range HW (BB+RSI)", "Optimized mean reversion / TA oscillators", sig_aegis_range_hw),
    StrategySpec("donch55", "Donchian 55 Trend", "Clenow / Turtle / Carver trend following", sig_donchian55_trend),
    StrategySpec("donch20", "Donchian 20 Breakout", "Shorter-channel breakout (Turtle variant)", sig_donchian20_turtle),
    StrategySpec("ema_cross", "EMA 50/200 Cross", "Edwards & Magee / classic trend", sig_ema_cross),
    StrategySpec("rsi_pure", "RSI Pure MR", "Schwager oscillators / mean reversion", sig_rsi_pure),
    StrategySpec("bb_mr", "Bollinger Fade", "Bollinger mean reversion", sig_bb_mr),
    StrategySpec("macd_cross", "MACD Cross", "Classic momentum cross", sig_macd_cross),
    StrategySpec("stoch_mr", "Stochastic MR", "Stochastic mean reversion", sig_stoch_mr),
    StrategySpec("atr_breakout", "ATR Channel Breakout", "Volatility channel breakout", sig_atr_breakout),
    StrategySpec("bb_squeeze", "BB Squeeze Breakout", "Compression → expansion breakout", sig_bb_squeeze_breakout),
    StrategySpec("elder_impulse", "Elder Impulse Proxy", "Elder impulse / MACD+EMA alignment", sig_elder_impulse_proxy),
]
