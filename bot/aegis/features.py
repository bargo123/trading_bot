from __future__ import annotations

import math
from typing import Any

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
    keep = [c for c in ("time", "open", "high", "low", "close", "volume") if c in df.columns]
    out = df[keep].copy()
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
    # Kaufman efficiency ratio: displacement / path. Chop prints low ER.
    er_n = max(2, int(cfg.get("er_period", 10)))
    path = out["close"].diff().abs().rolling(er_n).sum()
    disp = (out["close"] - out["close"].shift(er_n)).abs()
    out["kaufman_er"] = disp / path.replace(0, np.nan)
    # Elder triple-screen stand-in: slower EMA on the same M1 series (~20 bars on M5).
    out["htf_ema"] = ema(out["close"], int(cfg.get("htf_ema_period", 100)))
    # Elder Impulse: 13-EMA slope + MACD-Histogram slope (green/red censor).
    ema_imp = out["ema_13"]
    macd_h = out["macd_hist"]
    out["impulse_green"] = ((ema_imp > ema_imp.shift(1)) & (macd_h > macd_h.shift(1))).fillna(False).astype(bool)
    out["impulse_red"] = ((ema_imp < ema_imp.shift(1)) & (macd_h < macd_h.shift(1))).fillna(False).astype(bool)
    out["regime"] = np.where(
        (out["adx"] >= float(cfg.get("adx_trend_threshold", 25)))
        & (out["ema_fast"] != out["ema_slow"]),
        np.where(out["ema_fast"] > out["ema_slow"], "trend_up", "trend_down"),
        "range",
    )
    from aegis.profile_features import add_aziz_steidl_features, add_fabris_ntz_features

    out = add_aziz_steidl_features(out, cfg)
    out = add_fabris_ntz_features(out, cfg)
    from aegis.chart_read import add_chart_features

    out = add_chart_features(out, cfg)
    out = add_direction_features(out, cfg)
    out = add_jansen_harris_features(out, cfg)
    out = add_intel_regime_features(out, cfg)
    return out


def add_direction_features(df: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame:
    """Coulling relative volume, Brooks range location, Damir HH/HL structure.

    Tick volume is a proxy. Coulling 2013: spot FX has no centralized volume.
    """
    out = df.copy()
    h, l, c, o = out["high"], out["low"], out["close"], out["open"]
    rng = (h - l).replace(0, np.nan)
    if "volume" not in out.columns:
        out["volume"] = np.nan
    vol = pd.to_numeric(out["volume"], errors="coerce")
    vol_n = max(2, int(cfg.get("vpa_vol_period", 20)))
    min_p = max(3, vol_n // 2)
    out["vol_sma"] = vol.rolling(vol_n, min_periods=min_p).mean()
    out["vol_rel"] = vol / out["vol_sma"].replace(0, np.nan)
    rng_sma = rng.rolling(vol_n, min_periods=min_p).mean()
    wide_mult = float(cfg.get("vpa_wide_mult", 1.2))
    narrow_mult = float(cfg.get("vpa_narrow_mult", 0.6))
    high_vol = float(cfg.get("vpa_high_vol", 1.5))
    low_vol = float(cfg.get("vpa_low_vol", 0.65))
    out["vpa_wide"] = (rng >= (wide_mult * rng_sma)).fillna(False).astype(bool)
    out["vpa_narrow"] = (rng <= (narrow_mult * rng_sma)).fillna(False).astype(bool)
    out["vpa_high_vol"] = (out["vol_rel"] >= high_vol).fillna(False).astype(bool)
    out["vpa_low_vol"] = (out["vol_rel"] <= low_vol).fillna(False).astype(bool)
    out["close_loc"] = ((c - l) / rng).clip(0.0, 1.0)
    out["vpa_absorption"] = (out["vpa_narrow"] & out["vpa_high_vol"]).astype(bool)
    out["vpa_no_demand"] = ((c > o) & out["vpa_wide"] & out["vpa_low_vol"]).fillna(False).astype(bool)
    out["vpa_no_supply"] = ((c < o) & out["vpa_wide"] & out["vpa_low_vol"]).fillna(False).astype(bool)
    out["vpa_effort_up"] = (
        (c > o) & out["vpa_wide"] & out["vpa_high_vol"] & (out["close_loc"] >= 0.66)
    ).fillna(False).astype(bool)
    out["vpa_effort_dn"] = (
        (c < o) & out["vpa_wide"] & out["vpa_high_vol"] & (out["close_loc"] <= 0.34)
    ).fillna(False).astype(bool)

    look = max(8, int(cfg.get("brooks_range_bars", 20)))
    prior_high = h.rolling(look).max().shift(1)
    prior_low = l.rolling(look).min().shift(1)
    width = (prior_high - prior_low).replace(0, np.nan)
    out["range_loc"] = ((c - prior_low) / width).clip(-0.5, 1.5)
    hp, lp = h.shift(1), l.shift(1)
    overlap = (np.minimum(h, hp) - np.maximum(l, lp)).clip(lower=0) / rng
    ov_n = max(4, int(cfg.get("brooks_overlap_bars", 8)))
    ov_min = float(cfg.get("brooks_overlap_min", 0.40))
    out["brooks_overlap"] = overlap.rolling(ov_n, min_periods=ov_n).mean()
    out["brooks_in_range"] = (out["brooks_overlap"] >= ov_min).fillna(False).astype(bool)
    out["brooks_failed_bo_up"] = ((h > prior_high) & (c < prior_high)).fillna(False).astype(bool)
    out["brooks_failed_bo_dn"] = ((l < prior_low) & (c > prior_low)).fillna(False).astype(bool)

    pip = float(cfg.get("volman_pip_size", cfg.get("firehose_pip_size", 0.0001)))
    cluster = pip * float(cfg.get("pa_cluster_pips", 3.0))
    swing_n = int(cfg.get("pa_swing_n", 3))
    sf = structure_frame(h, l, swing_n, cluster)
    out["structure"] = sf["structure"]
    return out


def add_jansen_harris_features(df: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame:
    """Lagged alpha factors (Jansen) + jump flag (Harris). No future bars."""
    out = df.copy()
    c = out["close"]
    out["ret_1"] = c.pct_change(1)
    out["ret_5"] = c.pct_change(5)
    out["ret_10"] = c.pct_change(10)
    z_n = max(20, int(cfg.get("jansen_z_bars", 50)))
    mu = out["ret_5"].rolling(z_n, min_periods=20).mean()
    sd = out["ret_5"].rolling(z_n, min_periods=20).std().replace(0, np.nan)
    out["jansen_mom_z"] = ((out["ret_5"] - mu) / sd).clip(-3.0, 3.0)
    rsi = out["rsi"] if "rsi" in out.columns else pd.Series(50.0, index=out.index)
    out["jansen_rsi_z"] = ((rsi - 50.0) / 50.0).clip(-1.0, 1.0)
    er = out["kaufman_er"] if "kaufman_er" in out.columns else pd.Series(0.0, index=out.index)
    out["jansen_er_z"] = ((er.fillna(0.0) - 0.25) * 4.0).clip(-1.0, 1.0)
    out["jansen_score"] = (
        0.50 * out["jansen_mom_z"].fillna(0.0)
        + 0.30 * out["jansen_rsi_z"].fillna(0.0)
        + 0.20 * out["jansen_er_z"].fillna(0.0)
    )
    rng = (out["high"] - out["low"])
    atr_s = out["atr"] if "atr" in out.columns else rng
    jump_k = float(cfg.get("harris_jump_atr", 1.8) or 1.8)
    out["harris_jump"] = (rng >= (jump_k * atr_s.replace(0, np.nan))).fillna(False).astype(bool)
    return out


def add_intel_regime_features(df: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame:
    """Pre-entry regime flags. Closed bars only — no future data.

    Brooks barbwire: 3+ overlapping bars with a doji — 'don't touch'.
    EMA-side streak: how long close has been on the same side of ema_20 (lag/exhaustion).
    atr_expand: current ATR vs its SMA (vol about to eat a 30-pip stop).
    """
    out = df.copy()
    h, l, c, o = out["high"], out["low"], out["close"], out["open"]
    hmin = np.minimum(np.minimum(h, h.shift(1)), h.shift(2))
    lmax = np.maximum(np.maximum(l, l.shift(1)), l.shift(2))
    inter = (hmin - lmax).clip(lower=0)
    rng3 = ((h - l) + (h.shift(1) - l.shift(1)) + (h.shift(2) - l.shift(2))) / 3.0
    out["barbwire_overlap"] = inter / rng3.replace(0, np.nan)
    doji = out["volman_doji"] if "volman_doji" in out.columns else (c - o).abs() <= 0.35 * (h - l).replace(0, np.nan)
    any_doji = (
        doji.fillna(False).astype(bool)
        | doji.shift(1).fillna(False).astype(bool)
        | doji.shift(2).fillna(False).astype(bool)
    )
    bw_min = float(cfg.get("intel_barbwire_overlap", 0.50) or 0.50)
    out["brooks_barbwire"] = ((out["barbwire_overlap"] >= bw_min) & any_doji).fillna(False).astype(bool)

    if "ema_20" in out.columns:
        above = c >= out["ema_20"]
        grp = above.ne(above.shift(1)).cumsum()
        out["ema_side_streak"] = above.groupby(grp).cumcount() + 1
        pip = float(cfg.get("volman_pip_size", cfg.get("firehose_pip_size", 0.0001)))
        out["close_ema_pips"] = (c - out["ema_20"]) / max(pip, 1e-12)
    else:
        out["ema_side_streak"] = 0
        out["close_ema_pips"] = 0.0

    atr_s = out["atr"] if "atr" in out.columns else (h - l)
    atr_sma = atr_s.rolling(20, min_periods=10).mean()
    out["atr_expand"] = atr_s / atr_sma.replace(0, np.nan)
    pip = float(cfg.get("volman_pip_size", cfg.get("firehose_pip_size", 0.0001)))
    out["ret3_pips"] = (c - c.shift(3)) / max(pip, 1e-12)
    return out


def pip_size_from_cfg(cfg: dict[str, Any], symbol: str | None = None) -> float:
    from aegis.config import pip_size_for

    sym = symbol or str(cfg.get("symbol") or "")
    if sym:
        return pip_size_for(sym, cfg)
    return float(cfg.get("firehose_pip_size", cfg.get("volman_pip_size", 0.0001)))


def round_below(price: float, step: float) -> float:
    if step <= 0:
        return float(price)
    return math.floor(float(price) / step + 1e-12) * step


def round_above(price: float, step: float) -> float:
    if step <= 0:
        return float(price)
    val = math.ceil(float(price) / step - 1e-12) * step
    if val <= float(price) + 1e-12:
        val += step
    return val


def confirmed_swings(high: pd.Series, low: pd.Series, n: int = 3) -> pd.DataFrame:
    """Pivots confirmed after `n` bars on the right. Window is fully in the past."""
    n = max(1, int(n))
    win = 2 * n + 1
    roll_h = high.rolling(win, min_periods=win).max()
    roll_l = low.rolling(win, min_periods=win).min()
    cand_h = high.shift(n)
    cand_l = low.shift(n)
    return pd.DataFrame(
        {
            "swing_high": cand_h.where(cand_h >= roll_h - 1e-12),
            "swing_low": cand_l.where(cand_l <= roll_l + 1e-12),
        },
        index=high.index,
    )


def last_two_swings(series: pd.Series) -> tuple[pd.Series, pd.Series]:
    marked = series.dropna()
    last = series.ffill()
    prev = marked.shift(1).reindex(series.index).ffill()
    return last, prev


def classify_structure(
    last_sh: Any,
    prev_sh: Any,
    last_sl: Any,
    prev_sl: Any,
    cluster: float,
) -> str:
    """HH/HL vs LH/LL vs clustered range vs mixed chop. Edwards/Magee: not 100%."""
    vals = (last_sh, prev_sh, last_sl, prev_sl)
    if any(v is None or pd.isna(v) for v in vals):
        return "chop"
    last_sh_f, prev_sh_f, last_sl_f, prev_sl_f = (float(v) for v in vals)
    cl_h = abs(last_sh_f - prev_sh_f) <= cluster
    cl_l = abs(last_sl_f - prev_sl_f) <= cluster
    if cl_h and cl_l:
        return "range"
    hh = last_sh_f > prev_sh_f + 1e-12
    hl = last_sl_f > prev_sl_f + 1e-12
    lh = last_sh_f < prev_sh_f - 1e-12
    ll = last_sl_f < prev_sl_f - 1e-12
    if hh and hl:
        return "trend_up"
    if lh and ll:
        return "trend_down"
    return "chop"


def structure_frame(high: pd.Series, low: pd.Series, n: int, cluster: float) -> pd.DataFrame:
    sw = confirmed_swings(high, low, n)
    last_sh, prev_sh = last_two_swings(sw["swing_high"])
    last_sl, prev_sl = last_two_swings(sw["swing_low"])
    structure = [
        classify_structure(a, b, c, d, cluster)
        for a, b, c, d in zip(last_sh, prev_sh, last_sl, prev_sl)
    ]
    return pd.DataFrame(
        {
            "last_sh": last_sh,
            "prev_sh": prev_sh,
            "last_sl": last_sl,
            "prev_sl": prev_sl,
            "structure": structure,
            "swing_high": sw["swing_high"],
            "swing_low": sw["swing_low"],
        },
        index=high.index,
    )


def touch_counts(swing: pd.Series, last_level: pd.Series, tol: float, last_n: int = 8) -> list[int]:
    hist: list[float] = []
    out: list[int] = []
    cap = max(2, int(last_n))
    for raw_v, raw_lvl in zip(swing.to_numpy(), last_level.to_numpy()):
        if raw_v == raw_v:
            hist.append(float(raw_v))
        if raw_lvl != raw_lvl or not hist:
            out.append(0)
            continue
        lvl = float(raw_lvl)
        out.append(sum(abs(x - lvl) <= tol for x in hist[-cap:]))
    return out
