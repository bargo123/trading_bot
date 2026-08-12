from __future__ import annotations

import numpy as np
import pandas as pd

from aegis.indicators import adx, atr, bollinger, donchian, ema, rsi


def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(period).mean()


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    ef = ema(close, fast)
    es = ema(close, slow)
    line = ef - es
    sig = ema(line, signal)
    hist = line - sig
    return pd.DataFrame({"macd": line, "macd_signal": sig, "macd_hist": hist})


def stochastic(
    high: pd.Series, low: pd.Series, close: pd.Series, k: int = 14, d: int = 3
) -> pd.DataFrame:
    lowest = low.rolling(k).min()
    highest = high.rolling(k).max()
    k_line = 100 * (close - lowest) / (highest - lowest).replace(0, np.nan)
    d_line = k_line.rolling(d).mean()
    return pd.DataFrame({"stoch_k": k_line.fillna(50), "stoch_d": d_line.fillna(50)})


def enrich_all(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """One feature frame shared by all bake-off strategies."""
    out = df.copy()
    out["ema_fast"] = ema(out["close"], int(cfg.get("ema_fast", 50)))
    out["ema_slow"] = ema(out["close"], int(cfg.get("ema_slow", 200)))
    out["ema_13"] = ema(out["close"], 13)
    out["sma_20"] = sma(out["close"], 20)
    out["atr"] = atr(out["high"], out["low"], out["close"], int(cfg.get("atr_period", 14)))
    out["rsi"] = rsi(out["close"], int(cfg.get("rsi_period", 14)))
    out = pd.concat([out, bollinger(out["close"], int(cfg.get("bb_period", 20)), float(cfg.get("bb_std", 2.0)))], axis=1)
    out = pd.concat([out, donchian(out["high"], out["low"], 55)], axis=1)
    d20 = donchian(out["high"], out["low"], 20)
    out["donch20_high"] = d20["donch_high"]
    out["donch20_low"] = d20["donch_low"]
    out["adx"] = adx(out["high"], out["low"], out["close"], int(cfg.get("adx_period", 14)))
    out = pd.concat([out, macd(out["close"])], axis=1)
    out = pd.concat([out, stochastic(out["high"], out["low"], out["close"])], axis=1)
    out["bb_width"] = (out["bb_upper"] - out["bb_lower"]) / out["bb_mid"].replace(0, np.nan)
    out["bb_width_ma"] = out["bb_width"].rolling(50).mean()
    out["atr_channel_up"] = out["sma_20"] + 2.0 * out["atr"]
    out["atr_channel_dn"] = out["sma_20"] - 2.0 * out["atr"]
    # Volman (Forex Price Action Scalping): 20ema + micro-range / doji structure
    ema20_n = int(cfg.get("volman_ema", 20))
    out["ema_20"] = ema(out["close"], ema20_n)
    body = (out["close"] - out["open"]).abs()
    bar_range = (out["high"] - out["low"]).replace(0, np.nan)
    doji_frac = float(cfg.get("volman_doji_body_frac", 0.35))
    out["volman_doji"] = body <= (doji_frac * bar_range)
    prev_doji = out["volman_doji"].shift(1)
    prev_doji = prev_doji.where(prev_doji.notna(), False).astype(bool)
    out["volman_dd"] = out["volman_doji"].fillna(False).astype(bool) & prev_doji
    # Setup box = last 2 bars high/low (Double Doji / First Break micro-range)
    out["volman_box_high"] = out["high"].rolling(2).max().shift(1)
    out["volman_box_low"] = out["low"].rolling(2).min().shift(1)
    out["regime"] = np.where(
        (out["adx"] >= float(cfg.get("adx_trend_threshold", 25)))
        & (out["ema_fast"] != out["ema_slow"]),
        np.where(out["ema_fast"] > out["ema_slow"], "trend_up", "trend_down"),
        "range",
    )
    from aegis.profile_features import add_aziz_steidl_features, add_fabris_ntz_features

    out = add_aziz_steidl_features(out, cfg)
    out = add_fabris_ntz_features(out, cfg)
    return out
