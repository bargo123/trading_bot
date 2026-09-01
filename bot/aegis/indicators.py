from __future__ import annotations

import numpy as np
import pandas as pd


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    prev = close.shift(1)
    tr = pd.concat([(high - low), (high - prev).abs(), (low - prev).abs()], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return (100 - (100 / (1 + rs))).fillna(50.0)


def bollinger(close: pd.Series, period: int = 20, std_mult: float = 2.0) -> pd.DataFrame:
    mid = close.rolling(period).mean()
    std = close.rolling(period).std(ddof=0)
    return pd.DataFrame(
        {"bb_mid": mid, "bb_upper": mid + std_mult * std, "bb_lower": mid - std_mult * std}
    )


def donchian(high: pd.Series, low: pd.Series, period: int = 55) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "donch_high": high.rolling(period).max().shift(1),
            "donch_low": low.rolling(period).min().shift(1),
        }
    )


def adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    up = high.diff()
    down = -low.diff()
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    tr = atr(high, low, close, 1)
    atr_n = tr.rolling(period).mean()
    plus_di = 100 * pd.Series(plus_dm, index=close.index).rolling(period).mean() / atr_n.replace(0, np.nan)
    minus_di = 100 * pd.Series(minus_dm, index=close.index).rolling(period).mean() / atr_n.replace(0, np.nan)
    dx = (100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)).fillna(0)
    return dx.rolling(period).mean().rename("adx")


def enrich(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    out = df.copy()
    out["ema_fast"] = ema(out["close"], int(cfg["ema_fast"]))
    out["ema_slow"] = ema(out["close"], int(cfg["ema_slow"]))
    out["atr"] = atr(out["high"], out["low"], out["close"], int(cfg["atr_period"]))
    out["rsi"] = rsi(out["close"], int(cfg["rsi_period"]))
    out = pd.concat([out, bollinger(out["close"], int(cfg["bb_period"]), float(cfg["bb_std"]))], axis=1)
    out = pd.concat(
        [out, donchian(out["high"], out["low"], int(cfg["donchian_period"]))], axis=1
    )
    out["adx"] = adx(out["high"], out["low"], out["close"], int(cfg["adx_period"]))
    out["regime"] = np.where(
        (out["adx"] >= float(cfg["adx_trend_threshold"]))
        & (out["ema_fast"] != out["ema_slow"]),
        np.where(out["ema_fast"] > out["ema_slow"], "trend_up", "trend_down"),
        "range",
    )
    return out
