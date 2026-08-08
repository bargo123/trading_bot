from __future__ import annotations

import numpy as np
import pandas as pd


def _session_key(ts: pd.Series) -> pd.Series:
    t = pd.to_datetime(ts, utc=True)
    return t.dt.floor("D")


def add_fabris_ntz_features(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """
    Fabris *Price in Time* No-Trading-Zone:
    high/low of [ntz_start_utc, ntz_end_utc) GMT, then dual breakout.
    Width gate via ATR multiples (works for FX and BTC); optional absolute bounds.
    """
    out = df.copy()
    t = pd.to_datetime(out["time"], utc=True)
    out["_day"] = t.dt.floor("D")
    hour = t.dt.hour
    start = int(cfg.get("ntz_start_utc", 7))
    end = int(cfg.get("ntz_end_utc", 8))
    in_ntz = (hour >= start) & (hour < end)

    # Per-day NTZ high/low from bars inside the window
    ntz_h = out["high"].where(in_ntz)
    ntz_l = out["low"].where(in_ntz)
    day_hi = ntz_h.groupby(out["_day"]).transform("max")
    day_lo = ntz_l.groupby(out["_day"]).transform("min")

    # Ready once the NTZ window has ended and we have a valid range
    ready = (hour >= end) & day_hi.notna() & day_lo.notna()
    out["ntz_high"] = np.where(ready, day_hi, np.nan)
    out["ntz_low"] = np.where(ready, day_lo, np.nan)
    out["ntz_ready"] = ready
    out["ntz_width"] = out["ntz_high"] - out["ntz_low"]

    atr_v = out["atr"] if "atr" in out.columns else pd.Series(np.nan, index=out.index)
    min_atr = float(cfg.get("ntz_min_atr", 0.5))
    max_atr = float(cfg.get("ntz_max_atr", 3.0))
    width_atr = out["ntz_width"] / atr_v.replace(0, np.nan)
    width_ok = out["ntz_ready"] & width_atr.ge(min_atr) & width_atr.le(max_atr)

    # Optional absolute / pip-style bounds (e.g. FX 10–30 pips as price units)
    min_abs = cfg.get("ntz_min_abs")
    max_abs = cfg.get("ntz_max_abs")
    if min_abs is not None:
        width_ok = width_ok & (out["ntz_width"] >= float(min_abs))
    if max_abs is not None:
        width_ok = width_ok & (out["ntz_width"] <= float(max_abs))
    out["ntz_width_ok"] = width_ok.fillna(False)

    # First cross after ready (Fabris breakout); ntz_high/low frozen once ready
    prev_c = out["close"].shift(1)
    out["ntz_break_up"] = (
        out["ntz_ready"]
        & out["ntz_width_ok"]
        & (out["close"] > out["ntz_high"])
        & (prev_c <= out["ntz_high"])
    )
    out["ntz_break_dn"] = (
        out["ntz_ready"]
        & out["ntz_width_ok"]
        & (out["close"] < out["ntz_low"])
        & (prev_c >= out["ntz_low"])
    )

    flatten_raw = cfg.get("ntz_flatten_utc", 17)
    out["ntz_flatten"] = hour >= int(flatten_raw) if flatten_raw is not None else False

    # Prior-session directional skip (Fabris: skip if Asia already trending)
    # Compare pre-NTZ session range to % of price (ATR×bars would mis-scale on crypto).
    asia = hour < start
    asia_h = out["high"].where(asia)
    asia_l = out["low"].where(asia)
    asia_range = asia_h.groupby(out["_day"]).transform("max") - asia_l.groupby(out["_day"]).transform("min")
    asia_max_pct = float(cfg.get("ntz_asia_max_pct", 0.03))  # 3% default
    out["ntz_asia_ok"] = (asia_range / out["close"].replace(0, np.nan) <= asia_max_pct).fillna(True)
    # Optional ATR gate (disabled unless explicitly set)
    if cfg.get("ntz_asia_max_atr") is not None:
        asia_max = float(cfg["ntz_asia_max_atr"])
        out["ntz_asia_ok"] = out["ntz_asia_ok"] & (
            asia_range / atr_v.replace(0, np.nan) <= asia_max
        ).fillna(True)

    return out.drop(columns=["_day"], errors="ignore")


def add_aziz_steidl_features(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """
    Aziz: session VWAP + Opening Range.
    Steidlmayer: Initial Balance (1st hour), IB width, day-type hints, prior VA proxy.
    Built from OHLCV only (TPO approximated by price recurrence via rolling).
    """
    out = df.copy()
    if "volume" not in out.columns:
        out["volume"] = 1.0
    vol = out["volume"].replace(0, np.nan).fillna(1.0)
    typical = (out["high"] + out["low"] + out["close"]) / 3.0
    sess = _session_key(out["time"])
    sess.name = "_sess"
    out["_sess"] = sess

    # --- Session VWAP (Aziz) ---
    pv = typical * vol
    out["_cum_pv"] = pv.groupby(sess).cumsum()
    out["_cum_v"] = vol.groupby(sess).cumsum()
    out["vwap"] = out["_cum_pv"] / out["_cum_v"].replace(0, np.nan)

    # bar index within session
    out["_bar_i"] = out.groupby(sess).cumcount()

    # Opening range: first N bars (Aziz ORB; default 3 bars on 15m ≈ 45m, on 5m ≈ 15m)
    orb_bars = int(cfg.get("orb_bars", 3))
    ib_bars = int(cfg.get("ib_bars", 12))  # 12x5m = 1h IB; 4x15m = 1h

    def _range_hi(g: pd.DataFrame, n: int, col: str) -> pd.Series:
        # expanding max of first n bars, then freeze
        base = g[col].iloc[:n]
        if base.empty:
            return pd.Series(np.nan, index=g.index)
        hi = base.cummax()
        frozen = float(hi.iloc[-1]) if len(hi) else np.nan
        vals = []
        for i in range(len(g)):
            if i < n:
                vals.append(float(hi.iloc[i]) if i < len(hi) else np.nan)
            else:
                vals.append(frozen)
        return pd.Series(vals, index=g.index)

    def _range_lo(g: pd.DataFrame, n: int, col: str) -> pd.Series:
        base = g[col].iloc[:n]
        if base.empty:
            return pd.Series(np.nan, index=g.index)
        lo = base.cummin()
        frozen = float(lo.iloc[-1]) if len(lo) else np.nan
        vals = []
        for i in range(len(g)):
            if i < n:
                vals.append(float(lo.iloc[i]) if i < len(lo) else np.nan)
            else:
                vals.append(frozen)
        return pd.Series(vals, index=g.index)

    orb_h, orb_l, ib_h, ib_l = [], [], [], []
    for _, g in out.groupby(sess, sort=False):
        orb_h.append(_range_hi(g, orb_bars, "high"))
        orb_l.append(_range_lo(g, orb_bars, "low"))
        ib_h.append(_range_hi(g, ib_bars, "high"))
        ib_l.append(_range_lo(g, ib_bars, "low"))
    out["orb_high"] = pd.concat(orb_h).sort_index()
    out["orb_low"] = pd.concat(orb_l).sort_index()
    out["ib_high"] = pd.concat(ib_h).sort_index()
    out["ib_low"] = pd.concat(ib_l).sort_index()
    out["orb_ready"] = out["_bar_i"] >= orb_bars
    out["ib_ready"] = out["_bar_i"] >= ib_bars
    out["ib_mid"] = (out["ib_high"] + out["ib_low"]) / 2.0
    out["ib_width"] = (out["ib_high"] - out["ib_low"]).abs()
    out["ib_width_atr"] = out["ib_width"] / out["atr"].replace(0, np.nan)

    # Prior session value-area proxy: prior day mid 50% of range (rough 1st SD stand-in)
    day_hi = out.groupby(sess)["high"].transform("max")
    day_lo = out.groupby(sess)["low"].transform("min")
    day_mid = (day_hi + day_lo) / 2.0
    day_va_hi = day_mid + 0.34 * (day_hi - day_lo)  # ~68% band around mid
    day_va_lo = day_mid - 0.34 * (day_hi - day_lo)
    # shift by session: map each session's final VA to next session
    sess_va = (
        out.groupby(sess, sort=True)
        .agg(va_hi=("high", "max"), va_lo=("low", "min"), mid=("close", "last"))
        .reset_index()
    )
    sess_va["prior_va_hi"] = (sess_va["va_hi"] + sess_va["va_lo"]) / 2 + 0.34 * (
        sess_va["va_hi"] - sess_va["va_lo"]
    )
    sess_va["prior_va_lo"] = (sess_va["va_hi"] + sess_va["va_lo"]) / 2 - 0.34 * (
        sess_va["va_hi"] - sess_va["va_lo"]
    )
    sess_va["prior_va_hi"] = sess_va["prior_va_hi"].shift(1)
    sess_va["prior_va_lo"] = sess_va["prior_va_lo"].shift(1)
    out = out.merge(
        sess_va[["_sess", "prior_va_hi", "prior_va_lo"]],
        on="_sess",
        how="left",
    )

    # Steidlmayer day-type hint after IB: narrow IB → more extension potential; wide → caution
    # Extension beyond IB
    out["above_ib"] = out["close"] > out["ib_high"]
    out["below_ib"] = out["close"] < out["ib_low"]
    out["ib_break_up"] = out["ib_ready"] & (out["close"] > out["ib_high"]) & (
        out["close"].shift(1) <= out["ib_high"].shift(1)
    )
    out["ib_break_dn"] = out["ib_ready"] & (out["close"] < out["ib_low"]) & (
        out["close"].shift(1) >= out["ib_low"].shift(1)
    )

    # Aziz ORB break (first cross after ready)
    out["orb_break_up"] = out["orb_ready"] & (out["close"] > out["orb_high"]) & (
        out["close"].shift(1) <= out["orb_high"].shift(1)
    )
    out["orb_break_dn"] = out["orb_ready"] & (out["close"] < out["orb_low"]) & (
        out["close"].shift(1) >= out["orb_low"].shift(1)
    )

    # VWAP reclaim / reject
    out["vwap_prev"] = out["vwap"].shift(1)
    out["close_prev"] = out["close"].shift(1)
    out["vwap_reclaim"] = (out["close_prev"] < out["vwap_prev"]) & (out["close"] >= out["vwap"])
    out["vwap_reject"] = (out["close_prev"] > out["vwap_prev"]) & (out["close"] <= out["vwap"])

    # Initiating vs responsive vs prior VA (Steidlmayer)
    out["init_buy"] = out["close"] > out["prior_va_hi"]
    out["init_sell"] = out["close"] < out["prior_va_lo"]

    drop_cols = [c for c in out.columns if c.startswith("_")]
    return out.drop(columns=drop_cols, errors="ignore")
