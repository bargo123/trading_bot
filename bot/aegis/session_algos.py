from __future__ import annotations

from typing import Any, Callable, Optional

import pandas as pd

from aegis.strategy import Signal, in_session

SignalFn = Callable[[pd.Series, dict[str, Any]], Optional[Signal]]


def cost_ok(row: pd.Series, cfg: dict[str, Any], tp_dist: float) -> bool:
    close = float(row["close"])
    bps = float(cfg.get("spread_bps", 1.0)) + float(cfg.get("slippage_bps", 0.5))
    round_trip = close * (bps / 10000.0) * 2
    buffer = float(cfg.get("cost_buffer", 2.0))
    return tp_dist > round_trip * buffer


def sig_hw_range(row: pd.Series, cfg: dict[str, Any]) -> Optional[Signal]:
    """
    BB+RSI mean reversion (high-hit range entries).

    tp_mode:
      - atr (default): ATR take-profit. Books (Tharp/Ponsi): use min_rr / larger TP so E[R]>0;
        tiny high-WR scalps often lose after costs.
      - bb_mid / box: optional Elder-style fade toward BB mid (congestion midpoint).
    """
    if pd.isna(row.get("atr")) or float(row["atr"]) <= 0:
        return None
    if not in_session(row["time"], cfg.get("session_start_utc"), cfg.get("session_end_utc")):
        return None
    if float(row.get("adx") or 0) > float(cfg.get("adx_range_max", 22)):
        return None
    if pd.isna(row.get("bb_lower")) or pd.isna(row.get("bb_mid")):
        return None
    close, atr_v, rsi_v = float(row["close"]), float(row["atr"]), float(row["rsi"])
    bb_mid = float(row["bb_mid"])
    os_, ob_ = float(cfg.get("rsi_oversold", 30)), float(cfg.get("rsi_overbought", 70))
    sl_m, tp_m = float(cfg.get("atr_sl_mult", 2.5)), float(cfg.get("atr_tp_mult", 0.8))
    tp_mode = str(cfg.get("tp_mode", "atr")).lower()
    use_box = tp_mode in {"bb_mid", "box", "bb_box", "mid"}

    if close < float(row["bb_lower"]) and rsi_v < os_:
        sl = close - sl_m * atr_v
        if use_box:
            # Partial/full path to BB mid (box center). frac=1 → full mid.
            frac = float(cfg.get("tp_box_frac", 1.0))
            frac = max(0.05, min(1.0, frac))
            tp = close + frac * (bb_mid - close)
            if tp - close < tp_m * atr_v:
                tp = close + tp_m * atr_v
        else:
            tp = close + tp_m * atr_v
        if tp <= close or not cost_ok(row, cfg, abs(tp - close)):
            return None
        risk = abs(close - sl)
        reward = abs(tp - close)
        if risk <= 0 or reward / risk < float(cfg.get("min_rr", 0.0)):
            return None
        return Signal("buy", "range", close, sl, tp, None, row["time"], "hw_range")
    if close > float(row["bb_upper"]) and rsi_v > ob_:
        sl = close + sl_m * atr_v
        if use_box:
            frac = float(cfg.get("tp_box_frac", 1.0))
            frac = max(0.05, min(1.0, frac))
            tp = close - frac * (close - bb_mid)
            if close - tp < tp_m * atr_v:
                tp = close - tp_m * atr_v
        else:
            tp = close - tp_m * atr_v
        if tp >= close or not cost_ok(row, cfg, abs(close - tp)):
            return None
        risk = abs(close - sl)
        reward = abs(tp - close)
        if risk <= 0 or reward / risk < float(cfg.get("min_rr", 0.0)):
            return None
        return Signal("sell", "range", close, sl, tp, None, row["time"], "hw_range")
    return None


def sig_hw_runner(row: pd.Series, cfg: dict[str, Any]) -> Optional[Signal]:
    """
    100WR-style high-probability BB+RSI entry, but runners:
    - Same entry filter as hw_range (high hit-rate setup)
    - Wide structural stop
    - Far TP + ATR trail so winners can expand beyond tiny 0.1R scalps
    Designed for Thomas-style compounding toward larger equity.
    """
    if pd.isna(row.get("atr")) or float(row["atr"]) <= 0:
        return None
    if not in_session(row["time"], cfg.get("session_start_utc"), cfg.get("session_end_utc")):
        return None
    if float(row.get("adx") or 0) > float(cfg.get("adx_range_max", 24)):
        return None
    if pd.isna(row.get("bb_lower")):
        return None
    close, atr_v, rsi_v = float(row["close"]), float(row["atr"]), float(row["rsi"])
    os_, ob_ = float(cfg.get("rsi_oversold", 35)), float(cfg.get("rsi_overbought", 70))
    sl_m = float(cfg.get("atr_sl_mult", 3.5))
    # Aspiration target (Thomas spirit); trail manages early exit
    tp_r = float(cfg.get("runner_tp_r", cfg.get("min_rr", 5.0)))
    trail = float(cfg.get("atr_trail_mult", 1.2))
    if close < float(row["bb_lower"]) and rsi_v < os_:
        sl = close - sl_m * atr_v
        risk = close - sl
        if risk <= 0:
            return None
        tp = close + tp_r * risk
        if not cost_ok(row, cfg, abs(tp - close) * 0.1):  # allow trail to work; soft cost gate
            return None
        return Signal("buy", "hw_runner", close, sl, tp, trail, row["time"], "hw_runner_up")
    if close > float(row["bb_upper"]) and rsi_v > ob_:
        sl = close + sl_m * atr_v
        risk = sl - close
        if risk <= 0:
            return None
        tp = close - tp_r * risk
        if not cost_ok(row, cfg, abs(close - tp) * 0.1):
            return None
        return Signal("sell", "hw_runner", close, sl, tp, trail, row["time"], "hw_runner_dn")
    return None


def sig_trend_pullback(row: pd.Series, cfg: dict[str, Any]) -> Optional[Signal]:
    if pd.isna(row.get("atr")) or float(row["atr"]) <= 0:
        return None
    if not in_session(row["time"], cfg.get("session_start_utc"), cfg.get("session_end_utc")):
        return None
    if float(row.get("adx") or 0) < float(cfg.get("adx_min", 18)):
        return None
    close, atr_v, rsi_v = float(row["close"]), float(row["atr"]), float(row["rsi"])
    sl_m, tp_m = float(cfg.get("atr_sl_mult", 1.8)), float(cfg.get("atr_tp_mult", 2.2))
    up = float(row["ema_fast"]) > float(row["ema_slow"])
    dn = float(row["ema_fast"]) < float(row["ema_slow"])
    os_, ob_ = float(cfg.get("rsi_oversold", 40)), float(cfg.get("rsi_overbought", 60))
    if up and rsi_v <= os_:
        sl, tp = close - sl_m * atr_v, close + tp_m * atr_v
        if not cost_ok(row, cfg, abs(tp - close)):
            return None
        return Signal("buy", "pullback", close, sl, tp, None, row["time"], "trend_pb")
    if dn and rsi_v >= ob_:
        sl, tp = close + sl_m * atr_v, close - tp_m * atr_v
        if not cost_ok(row, cfg, abs(close - tp)):
            return None
        return Signal("sell", "pullback", close, sl, tp, None, row["time"], "trend_pb")
    return None


def sig_breakout_adx(row: pd.Series, cfg: dict[str, Any]) -> Optional[Signal]:
    if pd.isna(row.get("atr")) or float(row["atr"]) <= 0:
        return None
    if not in_session(row["time"], cfg.get("session_start_utc"), cfg.get("session_end_utc")):
        return None
    if float(row.get("adx") or 0) < float(cfg.get("adx_min", 25)):
        return None
    close, atr_v = float(row["close"]), float(row["atr"])
    dh, dl = row.get("donch20_high"), row.get("donch20_low")
    if pd.isna(dh) or pd.isna(dl):
        return None
    trail = float(cfg.get("atr_trail_mult", 2.5))
    tp_m = float(cfg.get("atr_tp_mult", 3.0))
    if close > float(dh) and float(row["ema_fast"]) > float(row["ema_slow"]):
        if not cost_ok(row, cfg, tp_m * atr_v):
            return None
        return Signal("buy", "trend", close, close - trail * atr_v, close + tp_m * atr_v, None, row["time"], "bo_adx")
    if close < float(dl) and float(row["ema_fast"]) < float(row["ema_slow"]):
        if not cost_ok(row, cfg, tp_m * atr_v):
            return None
        return Signal("sell", "trend", close, close + trail * atr_v, close - tp_m * atr_v, None, row["time"], "bo_adx")
    return None


def sig_rsi_cross(row: pd.Series, cfg: dict[str, Any]) -> Optional[Signal]:
    if pd.isna(row.get("atr")) or float(row["atr"]) <= 0 or pd.isna(row.get("rsi_prev")):
        return None
    if not in_session(row["time"], cfg.get("session_start_utc"), cfg.get("session_end_utc")):
        return None
    close, atr_v = float(row["close"]), float(row["atr"])
    rsi_v, prev = float(row["rsi"]), float(row["rsi_prev"])
    os_, ob_ = float(cfg.get("rsi_oversold", 30)), float(cfg.get("rsi_overbought", 70))
    sl_m, tp_m = float(cfg.get("atr_sl_mult", 2.0)), float(cfg.get("atr_tp_mult", 1.5))
    if prev < os_ and rsi_v >= os_:
        sl, tp = close - sl_m * atr_v, close + tp_m * atr_v
        if not cost_ok(row, cfg, abs(tp - close)):
            return None
        return Signal("buy", "rsi_x", close, sl, tp, None, row["time"], "rsi_cross")
    if prev > ob_ and rsi_v <= ob_:
        sl, tp = close + sl_m * atr_v, close - tp_m * atr_v
        if not cost_ok(row, cfg, abs(close - tp)):
            return None
        return Signal("sell", "rsi_x", close, sl, tp, None, row["time"], "rsi_cross")
    return None


def sig_inside_bar_break(row: pd.Series, cfg: dict[str, Any]) -> Optional[Signal]:
    if pd.isna(row.get("atr")) or float(row["atr"]) <= 0:
        return None
    if not in_session(row["time"], cfg.get("session_start_utc"), cfg.get("session_end_utc")):
        return None
    if pd.isna(row.get("bb_width_ma")):
        return None
    if float(row["bb_width"]) > float(row["bb_width_ma"]) * float(cfg.get("squeeze_frac", 0.85)):
        return None
    close, atr_v = float(row["close"]), float(row["atr"])
    sl_m, tp_m = float(cfg.get("atr_sl_mult", 1.5)), float(cfg.get("atr_tp_mult", 2.5))
    if close > float(row["bb_upper"]):
        if not cost_ok(row, cfg, tp_m * atr_v):
            return None
        return Signal("buy", "squeeze", close, close - sl_m * atr_v, close + tp_m * atr_v, None, row["time"], "squeeze_bo")
    if close < float(row["bb_lower"]):
        if not cost_ok(row, cfg, tp_m * atr_v):
            return None
        return Signal("sell", "squeeze", close, close + sl_m * atr_v, close - tp_m * atr_v, None, row["time"], "squeeze_bo")
    return None


def _rr_ok(entry: float, sl: float, tp: float, min_rr: float) -> bool:
    risk = abs(entry - sl)
    reward = abs(tp - entry)
    if risk <= 0:
        return False
    return (reward / risk) >= min_rr


def sig_aziz_orb(row: pd.Series, cfg: dict[str, Any]) -> Optional[Signal]:
    """Aziz Opening Range Breakout — break OR with VWAP-side stop, ≥2:1 R:R."""
    if pd.isna(row.get("atr")) or float(row["atr"]) <= 0:
        return None
    if not in_session(row["time"], cfg.get("session_start_utc"), cfg.get("session_end_utc")):
        return None
    if not bool(row.get("orb_ready")):
        return None
    if pd.isna(row.get("orb_high")) or pd.isna(row.get("vwap")):
        return None
    close, atr_v = float(row["close"]), float(row["atr"])
    min_rr = float(cfg.get("min_rr", 2.0))
    # Avoid crazy OR width
    orb_w = float(row["orb_high"]) - float(row["orb_low"])
    if orb_w > float(cfg.get("orb_max_atr", 2.5)) * atr_v:
        return None
    if bool(row.get("orb_break_up")):
        sl = float(row["vwap"])  # Aziz: stop related to VWAP invalidation
        if sl >= close:
            sl = close - max(1.0 * atr_v, orb_w * 0.5)
        tp = close + min_rr * abs(close - sl)
        if not cost_ok(row, cfg, abs(tp - close)) or not _rr_ok(close, sl, tp, min_rr):
            return None
        return Signal("buy", "aziz_orb", close, sl, tp, None, row["time"], "aziz_orb")
    if bool(row.get("orb_break_dn")):
        sl = float(row["vwap"])
        if sl <= close:
            sl = close + max(1.0 * atr_v, orb_w * 0.5)
        tp = close - min_rr * abs(sl - close)
        if not cost_ok(row, cfg, abs(close - tp)) or not _rr_ok(close, sl, tp, min_rr):
            return None
        return Signal("sell", "aziz_orb", close, sl, tp, None, row["time"], "aziz_orb")
    return None


def sig_aziz_vwap(row: pd.Series, cfg: dict[str, Any]) -> Optional[Signal]:
    """Aziz VWAP reclaim / reject with ≥2:1 R:R."""
    if pd.isna(row.get("atr")) or float(row["atr"]) <= 0:
        return None
    if not in_session(row["time"], cfg.get("session_start_utc"), cfg.get("session_end_utc")):
        return None
    if pd.isna(row.get("vwap")):
        return None
    close, atr_v, vwap = float(row["close"]), float(row["atr"]), float(row["vwap"])
    min_rr = float(cfg.get("min_rr", 2.0))
    sl_m = float(cfg.get("atr_sl_mult", 1.2))
    if bool(row.get("vwap_reclaim")):
        sl = vwap - sl_m * atr_v
        tp = close + min_rr * abs(close - sl)
        if not cost_ok(row, cfg, abs(tp - close)) or not _rr_ok(close, sl, tp, min_rr):
            return None
        return Signal("buy", "aziz_vwap", close, sl, tp, None, row["time"], "aziz_vwap")
    if bool(row.get("vwap_reject")):
        sl = vwap + sl_m * atr_v
        tp = close - min_rr * abs(sl - close)
        if not cost_ok(row, cfg, abs(close - tp)) or not _rr_ok(close, sl, tp, min_rr):
            return None
        return Signal("sell", "aziz_vwap", close, sl, tp, None, row["time"], "aziz_vwap")
    return None


def sig_steidl_ib_break(row: pd.Series, cfg: dict[str, Any]) -> Optional[Signal]:
    """Steidlmayer-inspired IB breakout (go-with), prefer initiating vs prior VA."""
    if pd.isna(row.get("atr")) or float(row["atr"]) <= 0:
        return None
    if not in_session(row["time"], cfg.get("session_start_utc"), cfg.get("session_end_utc")):
        return None
    if not bool(row.get("ib_ready")):
        return None
    if pd.isna(row.get("ib_high")):
        return None
    close, atr_v = float(row["close"]), float(row["atr"])
    # Skip extremely wide IB (already extended day)
    if float(row.get("ib_width_atr") or 0) > float(cfg.get("ib_max_atr", 3.0)):
        return None
    min_rr = float(cfg.get("min_rr", 1.5))
    # Target ~1x IB width (normal-variation style projection)
    ib_w = float(row["ib_width"])
    if bool(row.get("ib_break_up")):
        # Prefer initiating buy (above prior VA) when available
        if not pd.isna(row.get("prior_va_hi")) and close < float(row["prior_va_hi"]):
            if not bool(cfg.get("allow_responsive_ib", False)):
                return None
        sl = float(row["ib_mid"])
        if sl >= close:
            sl = close - 1.0 * atr_v
        tp = close + max(ib_w, min_rr * abs(close - sl))
        if not cost_ok(row, cfg, abs(tp - close)):
            return None
        return Signal("buy", "steidl_ib", close, sl, tp, None, row["time"], "steidl_ib_break")
    if bool(row.get("ib_break_dn")):
        if not pd.isna(row.get("prior_va_lo")) and close > float(row["prior_va_lo"]):
            if not bool(cfg.get("allow_responsive_ib", False)):
                return None
        sl = float(row["ib_mid"])
        if sl <= close:
            sl = close + 1.0 * atr_v
        tp = close - max(ib_w, min_rr * abs(sl - close))
        if not cost_ok(row, cfg, abs(close - tp)):
            return None
        return Signal("sell", "steidl_ib", close, sl, tp, None, row["time"], "steidl_ib_break")
    return None


def sig_steidl_ib_fade(row: pd.Series, cfg: dict[str, Any]) -> Optional[Signal]:
    """Fade first IB extension on narrow IB (neutral/development day heuristic)."""
    if pd.isna(row.get("atr")) or float(row["atr"]) <= 0:
        return None
    if not in_session(row["time"], cfg.get("session_start_utc"), cfg.get("session_end_utc")):
        return None
    if not bool(row.get("ib_ready")):
        return None
    # Only fade when IB is relatively narrow
    if float(row.get("ib_width_atr") or 99) > float(cfg.get("fade_ib_max_atr", 1.2)):
        return None
    close, atr_v = float(row["close"]), float(row["atr"])
    min_rr = float(cfg.get("min_rr", 1.5))
    # Small extension past IB then fade back to mid
    if bool(row.get("ib_break_up")):
        sl = close + 0.8 * atr_v
        tp = float(row["ib_mid"])
        if tp >= close or not _rr_ok(close, sl, tp, min_rr):
            return None
        if not cost_ok(row, cfg, abs(close - tp)):
            return None
        return Signal("sell", "steidl_fade", close, sl, tp, None, row["time"], "steidl_ib_fade")
    if bool(row.get("ib_break_dn")):
        sl = close - 0.8 * atr_v
        tp = float(row["ib_mid"])
        if tp <= close or not _rr_ok(close, sl, tp, min_rr):
            return None
        if not cost_ok(row, cfg, abs(tp - close)):
            return None
        return Signal("buy", "steidl_fade", close, sl, tp, None, row["time"], "steidl_ib_fade")
    return None


def sig_fabris_ntz(row: pd.Series, cfg: dict[str, Any]) -> Optional[Signal]:
    """
    Fabris NTZ breakout (Price in Time).
    SL = opposite NTZ extreme; TP = ntz_tp_mult × NTZ width (Model 3 default = 2).
    Skip flatten window and Asia-already-trending days.
    """
    if pd.isna(row.get("atr")) or float(row["atr"]) <= 0:
        return None
    if not in_session(row["time"], cfg.get("session_start_utc"), cfg.get("session_end_utc")):
        return None
    if bool(row.get("ntz_flatten")):
        return None
    if not bool(row.get("ntz_ready")) or not bool(row.get("ntz_width_ok")):
        return None
    if not bool(row.get("ntz_asia_ok", True)):
        return None
    if pd.isna(row.get("ntz_high")) or pd.isna(row.get("ntz_width")):
        return None

    close = float(row["close"])
    w = float(row["ntz_width"])
    if w <= 0:
        return None
    tp_mult = float(cfg.get("ntz_tp_mult", 2.0))  # Model 3: aim ~TP2
    buf = float(cfg.get("ntz_buffer", 0.0))

    if bool(row.get("ntz_break_up")):
        sl = float(row["ntz_low"]) - buf
        if sl >= close:
            return None
        tp = close + tp_mult * w
        if not cost_ok(row, cfg, abs(tp - close)):
            return None
        return Signal("buy", "fabris_ntz", close, sl, tp, None, row["time"], "fabris_ntz")
    if bool(row.get("ntz_break_dn")):
        sl = float(row["ntz_high"]) + buf
        if sl <= close:
            return None
        tp = close - tp_mult * w
        if not cost_ok(row, cfg, abs(close - tp)):
            return None
        return Signal("sell", "fabris_ntz", close, sl, tp, None, row["time"], "fabris_ntz")
    return None


def _htf_trend(row: pd.Series) -> str:
    """Ponsi/Damir/DraKoln: EMA stack + close side."""
    if pd.isna(row.get("ema_fast")) or pd.isna(row.get("ema_slow")):
        return "none"
    ef, es, c = float(row["ema_fast"]), float(row["ema_slow"]), float(row["close"])
    if ef > es and c > ef:
        return "up"
    if ef < es and c < ef:
        return "down"
    return "none"


def sig_book_optimal(row: pd.Series, cfg: dict[str, Any]) -> Optional[Signal]:
    """
    Book-synthesized confluence engine (all digests):
    Silvani/Fabris session · Ponsi/Damir HTF trend · ADX gate ·
    trigger = NTZ or ORB or squeeze or EMA pullback · min R:R · cost filter ·
    ATR/structure stop · Damir/Thomas asymmetric target.
    Not a holy grail — measured in backtests only.
    """
    if pd.isna(row.get("atr")) or float(row["atr"]) <= 0:
        return None
    if not in_session(row["time"], cfg.get("session_start_utc"), cfg.get("session_end_utc")):
        return None
    if bool(row.get("ntz_flatten", False)):
        return None

    close = float(row["close"])
    atr_v = float(row["atr"])
    adx_v = float(row.get("adx") or 0)
    adx_min = float(cfg.get("adx_min", 20))
    adx_max = float(cfg.get("book_adx_max", 45))  # skip blow-off
    if adx_v < adx_min or adx_v > adx_max:
        return None

    trend = _htf_trend(row)
    if trend == "none":
        return None

    min_rr = float(cfg.get("min_rr", 2.0))
    sl_atr = float(cfg.get("atr_sl_mult", 1.5))
    need = int(cfg.get("book_min_triggers", 1))

    # --- Triggers (book menu) ---
    ntz_up = bool(row.get("ntz_break_up")) and bool(row.get("ntz_width_ok", False))
    ntz_dn = bool(row.get("ntz_break_dn")) and bool(row.get("ntz_width_ok", False))
    orb_up = bool(row.get("orb_break_up"))
    orb_dn = bool(row.get("orb_break_dn"))
    squeeze = False
    if not pd.isna(row.get("bb_width")) and not pd.isna(row.get("bb_width_ma")):
        squeeze = float(row["bb_width"]) <= float(row["bb_width_ma"]) * float(
            cfg.get("squeeze_frac", 0.85)
        )
    sq_up = squeeze and (not pd.isna(row.get("bb_upper"))) and close > float(row["bb_upper"])
    sq_dn = squeeze and (not pd.isna(row.get("bb_lower"))) and close < float(row["bb_lower"])

    # Ponsi pullback: near fast EMA + RSI turning with trend
    near_ema = abs(close - float(row["ema_fast"])) <= 0.5 * atr_v
    rsi_v = float(row["rsi"]) if not pd.isna(row.get("rsi")) else 50.0
    rsi_prev = float(row["rsi_prev"]) if not pd.isna(row.get("rsi_prev")) else rsi_v
    pb_up = near_ema and rsi_prev < float(cfg.get("rsi_pullback", 45)) and rsi_v >= rsi_prev
    pb_dn = near_ema and rsi_prev > float(cfg.get("rsi_pullback_hi", 55)) and rsi_v <= rsi_prev

    # VWAP side confirmation (Aziz)
    vwap_ok_up = True
    vwap_ok_dn = True
    if cfg.get("book_require_vwap", True) and not pd.isna(row.get("vwap")):
        vwap_ok_up = close >= float(row["vwap"])
        vwap_ok_dn = close <= float(row["vwap"])

    if trend == "up":
        triggers = sum([ntz_up, orb_up, sq_up, pb_up])
        if triggers < need or not vwap_ok_up:
            return None
        # Prefer structure stop when NTZ/ORB available
        if ntz_up and not pd.isna(row.get("ntz_low")):
            sl = float(row["ntz_low"])
        elif orb_up and not pd.isna(row.get("orb_low")):
            sl = float(row["orb_low"])
        else:
            sl = close - sl_atr * atr_v
        if sl >= close:
            sl = close - sl_atr * atr_v
        risk = close - sl
        tp = close + min_rr * risk
        if not cost_ok(row, cfg, abs(tp - close)) or not _rr_ok(close, sl, tp, min_rr):
            return None
        reason = f"book_opt_up_t{triggers}"
        return Signal("buy", "book_optimal", close, sl, tp, None, row["time"], reason)

    # trend == down
    triggers = sum([ntz_dn, orb_dn, sq_dn, pb_dn])
    if triggers < need or not vwap_ok_dn:
        return None
    if ntz_dn and not pd.isna(row.get("ntz_high")):
        sl = float(row["ntz_high"])
    elif orb_dn and not pd.isna(row.get("orb_high")):
        sl = float(row["orb_high"])
    else:
        sl = close + sl_atr * atr_v
    if sl <= close:
        sl = close + sl_atr * atr_v
    risk = sl - close
    tp = close - min_rr * risk
    if not cost_ok(row, cfg, abs(close - tp)) or not _rr_ok(close, sl, tp, min_rr):
        return None
    reason = f"book_opt_dn_t{triggers}"
    return Signal("sell", "book_optimal", close, sl, tp, None, row["time"], reason)


def sig_thomas_10r(row: pd.Series, cfg: dict[str, Any]) -> Optional[Signal]:
    """
    LR Thomas 10XROI spirit: trend + pullback, stop beyond structure/ATR, target ~10R.
    """
    if pd.isna(row.get("atr")) or float(row["atr"]) <= 0:
        return None
    if not in_session(row["time"], cfg.get("session_start_utc"), cfg.get("session_end_utc")):
        return None
    close = float(row["close"])
    atr_v = float(row["atr"])
    ema_f = float(row["ema_fast"])
    ema_s = float(row["ema_slow"])
    adx_v = float(row.get("adx") or 0)
    if adx_v < float(cfg.get("adx_min", 18)):
        return None
    rr = float(cfg.get("thomas_rr", cfg.get("min_rr", 10.0)))
    sl_atr = float(cfg.get("atr_sl_mult", 1.5))
    up = ema_f > ema_s and close > ema_f
    dn = ema_f < ema_s and close < ema_f
    rsi_v = float(row["rsi"]) if not pd.isna(row.get("rsi")) else 50.0
    rsi_prev = float(row["rsi_prev"]) if not pd.isna(row.get("rsi_prev")) else rsi_v
    near = abs(close - ema_f) <= float(cfg.get("thomas_near_atr", 0.75)) * atr_v
    if up and near and rsi_prev <= float(cfg.get("rsi_pullback", 45)) and rsi_v >= rsi_prev:
        sl = close - sl_atr * atr_v
        risk = close - sl
        if risk <= 0:
            return None
        tp = close + rr * risk
        if not cost_ok(row, cfg, abs(tp - close)):
            return None
        return Signal("buy", "thomas_10r", close, sl, tp, None, row["time"], "thomas_10r_up")
    if dn and near and rsi_prev >= float(cfg.get("rsi_pullback_hi", 55)) and rsi_v <= rsi_prev:
        sl = close + sl_atr * atr_v
        risk = sl - close
        if risk <= 0:
            return None
        tp = close - rr * risk
        if not cost_ok(row, cfg, abs(close - tp)):
            return None
        return Signal("sell", "thomas_10r", close, sl, tp, None, row["time"], "thomas_10r_dn")
    return None


def sig_ensemble(row: pd.Series, cfg: dict[str, Any]) -> Optional[Signal]:
    """
    Combine multiple book strategies — trade only when enough engines agree on side.
    Strictest stop among voters; median TP distance.
    """
    import numpy as np

    members = cfg.get("ensemble_members") or [
        "book_optimal",
        "thomas_10r",
        "breakout_adx",
        "trend_pullback",
        "hw_range",
        "aziz_vwap",
        "steidl_ib_break",
        "fabris_ntz",
    ]
    need = int(cfg.get("ensemble_min_votes", 2))
    skip = {"ensemble", "ensemble_optimal", "all_books"}
    votes: list[Signal] = []
    for name in members:
        if name in skip:
            continue
        fn = _ALGO_TABLE.get(name)
        if fn is None:
            continue
        try:
            sig = fn(row, cfg)
        except Exception:
            sig = None
        if sig is not None:
            votes.append(sig)

    if len(votes) < need:
        return None
    buys = [s for s in votes if s.side == "buy"]
    sells = [s for s in votes if s.side == "sell"]
    if len(buys) >= need and len(buys) >= len(sells):
        chosen, side = buys, "buy"
    elif len(sells) >= need:
        chosen, side = sells, "sell"
    else:
        return None

    close = float(row["close"])
    if side == "buy":
        sl = min(float(s.sl) for s in chosen)
        if sl >= close:
            return None
        tp_dists = [abs(float(s.tp) - float(s.entry)) for s in chosen if s.tp is not None]
        if not tp_dists:
            return None
        tp = close + float(np.median(tp_dists))
    else:
        sl = max(float(s.sl) for s in chosen)
        if sl <= close:
            return None
        tp_dists = [abs(float(s.entry) - float(s.tp)) for s in chosen if s.tp is not None]
        if not tp_dists:
            return None
        tp = close - float(np.median(tp_dists))

    trail_vals = [s.trail_atr_mult for s in chosen if s.trail_atr_mult]
    trail = max(trail_vals) if trail_vals else None
    if not cost_ok(row, cfg, abs(tp - close)):
        return None
    reason = f"ensemble_{side}_v{len(chosen)}"
    return Signal(side, "ensemble", close, sl, tp, trail, row["time"], reason)


def sig_volman_scalp(row: pd.Series, cfg: dict[str, Any]) -> Optional[Signal]:
    """
    Bob Volman — Forex Price Action Scalping (approx on OHLC):
    - Setups revolve around 20 EMA
    - Double-doji / micro-range then break (DD / First Break spirit)
    - Tight pip TP/SL (spread must stay tiny — Volman)
    """
    need = ["ema_20", "volman_box_high", "volman_box_low", "close", "high", "low"]
    if any(pd.isna(row.get(k)) for k in need):
        return None
    if not in_session(row["time"], cfg.get("session_start_utc"), cfg.get("session_end_utc")):
        return None
    # Prefer DD; allow FB-style break of prior 2-bar box even without doji if enabled
    require_dd = bool(cfg.get("volman_require_dd", True))
    if require_dd and not bool(row.get("volman_dd")):
        return None

    close = float(row["close"])
    ema20 = float(row["ema_20"])
    box_h, box_l = float(row["volman_box_high"]), float(row["volman_box_low"])
    pip = float(cfg.get("volman_pip_size", 0.0001))
    tp_pips = float(cfg.get("volman_tp_pips", 5.0))
    sl_pips = float(cfg.get("volman_sl_pips", 10.0))
    # Trend filter: only long above 20ema, short below
    if close > box_h and close > ema20:
        sl = close - sl_pips * pip
        tp = close + tp_pips * pip
        if not cost_ok(row, cfg, abs(tp - close)):
            return None
        return Signal("buy", "volman", close, sl, tp, None, row["time"], "volman_dd_break_up")
    if close < box_l and close < ema20:
        sl = close + sl_pips * pip
        tp = close - tp_pips * pip
        if not cost_ok(row, cfg, abs(close - tp)):
            return None
        return Signal("sell", "volman", close, sl, tp, None, row["time"], "volman_dd_break_dn")
    return None


def sig_chan_bb_scalp(row: pd.Series, cfg: dict[str, Any]) -> Optional[Signal]:
    """
    Ernie Chan — Algorithmic Trading (2013): simple Bollinger mean-reversion prototype.
    Time-series MR; basket use = run this on each liquid FX pair (cross-sectional book spirit).
    """
    if pd.isna(row.get("bb_mid")) or pd.isna(row.get("atr")) or float(row["atr"]) <= 0:
        return None
    if not in_session(row["time"], cfg.get("session_start_utc"), cfg.get("session_end_utc")):
        return None
    close = float(row["close"])
    mid, up, lo = float(row["bb_mid"]), float(row["bb_upper"]), float(row["bb_lower"])
    atr_v = float(row["atr"])
    sl_m = float(cfg.get("atr_sl_mult", 1.5))
    # Exit toward mid (Chan BB MR); optional partial atr floor for costs
    if close < lo:
        sl = close - sl_m * atr_v
        tp = mid
        if tp <= close or not cost_ok(row, cfg, abs(tp - close)):
            return None
        risk = abs(close - sl)
        if risk <= 0 or abs(tp - close) / risk < float(cfg.get("min_rr", 0.0)):
            return None
        return Signal("buy", "chan_bb", close, sl, tp, None, row["time"], "chan_bb_long")
    if close > up:
        sl = close + sl_m * atr_v
        tp = mid
        if tp >= close or not cost_ok(row, cfg, abs(close - tp)):
            return None
        risk = abs(close - sl)
        if risk <= 0 or abs(tp - close) / risk < float(cfg.get("min_rr", 0.0)):
            return None
        return Signal("sell", "chan_bb", close, sl, tp, None, row["time"], "chan_bb_short")
    return None


# Registry filled after all sig_* defs; ensemble looks up via _ALGO_TABLE
_ALGO_TABLE: dict[str, SignalFn] = {}

ALGOS: dict[str, SignalFn] = {
    "hw_range": sig_hw_range,
    "hw_runner": sig_hw_runner,
    "trend_pullback": sig_trend_pullback,
    "breakout_adx": sig_breakout_adx,
    "rsi_cross": sig_rsi_cross,
    "squeeze_bo": sig_inside_bar_break,
    "aziz_orb": sig_aziz_orb,
    "aziz_vwap": sig_aziz_vwap,
    "steidl_ib_break": sig_steidl_ib_break,
    "steidl_ib_fade": sig_steidl_ib_fade,
    "fabris_ntz": sig_fabris_ntz,
    "book_optimal": sig_book_optimal,
    "thomas_10r": sig_thomas_10r,
    "volman_scalp": sig_volman_scalp,
    "chan_bb_scalp": sig_chan_bb_scalp,
    "ensemble": sig_ensemble,
    "ensemble_optimal": sig_ensemble,
    "all_books": sig_ensemble,
}
_ALGO_TABLE.update(ALGOS)
