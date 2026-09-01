"""Selective multi-timeframe price-action entries.

Nison candles at D1/H4 levels, with H1 confirmation. Kaufman ER skips chop.
Elder Impulse is a censor, not a holy grail. Edwards/Magee: no pattern is
100% reliable. Tharp: measure expectancy, not winrate.

This is not a 100% or 90% winrate system. The marketing claim is unsourced.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import numpy as np
import pandas as pd

from aegis.chart_read import pa_reversal_side
from aegis.features import (
    pip_size_from_cfg,
    round_above,
    round_below,
    structure_frame,
    touch_counts,
)
from aegis.indicators import ema
from aegis.strategy import Signal, in_session

logger = logging.getLogger(__name__)

_TF_RULES = {
    "h1": "1h",
    "1h": "1h",
    "h4": "4h",
    "4h": "4h",
    "d1": "1D",
    "1d": "1D",
}

_HTF_KEYS = (
    ("d1", "pa_daily_tf", "d1", "pa_daily_lookback_days", 180),
    ("h4", "pa_structure_tf", "h4", "pa_structure_lookback_days", 90),
    ("h1", "pa_confirm_tf", "h1", "pa_confirm_lookback_days", 60),
)


def is_pa_select(cfg: dict[str, Any]) -> bool:
    return str(cfg.get("signal_mode") or cfg.get("algo") or "").lower() in {"pa_select"}


def _bars_to_frame(bars: Any) -> pd.DataFrame:
    rows = []
    for bar in bars:
        if isinstance(bar, dict):
            rows.append(
                {
                    "time": pd.Timestamp(bar["time"]),
                    "open": float(bar["open"]),
                    "high": float(bar["high"]),
                    "low": float(bar["low"]),
                    "close": float(bar["close"]),
                    "volume": float(bar.get("volume", 0) or 0),
                }
            )
            continue
        rows.append(
            {
                "time": pd.Timestamp(bar.time),
                "open": float(bar.open),
                "high": float(bar.high),
                "low": float(bar.low),
                "close": float(bar.close),
                "volume": float(getattr(bar, "volume", 0) or 0),
            }
        )
    return pd.DataFrame(rows)


def fetch_mtf_frames(engine: Any, symbol: str, cfg: dict[str, Any]) -> dict[str, pd.DataFrame]:
    """Pull D1/H4/H1 bars from a connected engine, or return injected test frames.

    Unit tests set cfg['pa_mtf_frames'] so this never needs MetaTrader.
    """
    injected = cfg.get("pa_mtf_frames")
    if injected:
        return {str(key): value.copy() for key, value in injected.items() if value is not None}

    out: dict[str, pd.DataFrame] = {}
    if engine is None or not hasattr(engine, "bars"):
        return out
    for key, tf_cfg, default_tf, days_cfg, default_days in _HTF_KEYS:
        tf = str(cfg.get(tf_cfg, default_tf))
        days = int(cfg.get(days_cfg, default_days))
        try:
            bars = engine.bars(symbol, tf, days)
        except Exception:
            logger.warning("pa_select: could not fetch %s %s", symbol, tf, exc_info=True)
            continue
        if not bars:
            continue
        out[key] = _bars_to_frame(bars)
    return out


def _resample_ohlc(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    bars = df[["time", "open", "high", "low", "close"]].copy()
    bars["time"] = pd.to_datetime(bars["time"], utc=True)
    bars = bars.sort_values("time").set_index("time")
    htf = (
        bars.resample(rule, label="left", closed="left")
        .agg({"open": "first", "high": "max", "low": "min", "close": "last"})
        .dropna()
        .reset_index()
    )
    return htf


def _closed_htf(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or len(df) < 3:
        return pd.DataFrame()
    out = df.copy()
    out["time"] = pd.to_datetime(out["time"], utc=True)
    out = out.sort_values("time").drop_duplicates("time", keep="last").reset_index(drop=True)
    return out.iloc[:-1].copy()


def _frames_for_prepare(entry_df: pd.DataFrame, cfg: dict[str, Any]) -> dict[str, pd.DataFrame]:
    injected = cfg.get("pa_mtf_frames") or {}
    out: dict[str, pd.DataFrame] = {}
    for key, tf_cfg, default_tf, _days_cfg, _default_days in _HTF_KEYS:
        tf = str(cfg.get(tf_cfg, default_tf)).lower()
        raw = injected.get(key)
        if raw is None:
            raw = injected.get(tf)
        if raw is not None and len(raw):
            out[key] = raw
            continue
        rule = _TF_RULES.get(tf)
        if rule:
            out[key] = _resample_ohlc(entry_df, rule)
    return out


def _htf_feature_frame(df: pd.DataFrame, cfg: dict[str, Any], prefix: str, pip: float) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    n = int(cfg.get("pa_swing_n", 3))
    cluster = float(cfg.get("pa_zone_cluster_pips", 15.0)) * pip
    struct = structure_frame(df["high"], df["low"], n, cluster)
    ema_p = int(cfg.get("pa_htf_ema_period", 21))
    ema_s = ema(df["close"], ema_p)
    direction = np.where(df["close"] > ema_s, "up", np.where(df["close"] < ema_s, "down", "range"))
    feat = pd.DataFrame({"time": pd.to_datetime(df["time"], utc=True)})
    feat[f"{prefix}_last_sh"] = struct["last_sh"].to_numpy()
    feat[f"{prefix}_prev_sh"] = struct["prev_sh"].to_numpy()
    feat[f"{prefix}_last_sl"] = struct["last_sl"].to_numpy()
    feat[f"{prefix}_prev_sl"] = struct["prev_sl"].to_numpy()
    feat[f"{prefix}_structure"] = struct["structure"].to_numpy()
    feat[f"{prefix}_ema"] = ema_s.to_numpy()
    feat[f"{prefix}_dir"] = direction
    feat[f"{prefix}_resist_touches"] = touch_counts(struct["swing_high"], struct["last_sh"], cluster)
    feat[f"{prefix}_support_touches"] = touch_counts(struct["swing_low"], struct["last_sl"], cluster)
    return feat


def _empty_htf_cols(prefix: str) -> list[str]:
    return [
        f"{prefix}_last_sh",
        f"{prefix}_prev_sh",
        f"{prefix}_last_sl",
        f"{prefix}_prev_sl",
        f"{prefix}_structure",
        f"{prefix}_ema",
        f"{prefix}_dir",
        f"{prefix}_resist_touches",
        f"{prefix}_support_touches",
    ]


def _merge_htf(entry: pd.DataFrame, feat: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    frame = entry.copy()
    frame["time"] = pd.to_datetime(frame["time"], utc=True)
    for col in cols:
        if col in frame.columns:
            frame = frame.drop(columns=[col])
    if feat is None or feat.empty:
        for col in cols:
            frame[col] = np.nan
        return frame
    use = feat[["time"] + [c for c in cols if c in feat.columns]].copy()
    use["time"] = pd.to_datetime(use["time"], utc=True)
    use = use.sort_values("time").drop_duplicates("time", keep="last")
    frame = frame.sort_values("time")
    return pd.merge_asof(frame, use, on="time", direction="backward")


def _nearest_level(close: np.ndarray, candidates: list[np.ndarray], below: bool) -> np.ndarray:
    arrays = [np.asarray(item, dtype=float) for item in candidates]
    arr = np.column_stack(arrays)
    if below:
        masked = np.where(arr <= close[:, None] + 1e-12, arr, np.nan)
        with np.errstate(all="ignore"):
            out = np.nanmax(masked, axis=1)
    else:
        masked = np.where(arr >= close[:, None] - 1e-12, arr, np.nan)
        with np.errstate(all="ignore"):
            out = np.nanmin(masked, axis=1)
    return out


def _attach_zones(frame: pd.DataFrame, cfg: dict[str, Any], pip: float) -> pd.DataFrame:
    close = pd.to_numeric(frame["close"], errors="coerce").to_numpy(dtype=float)
    step = pip * float(cfg.get("pa_round_pips", 100.0))
    rb = np.array([round_below(float(px), step) if px == px else np.nan for px in close])
    ra = np.array([round_above(float(px), step) if px == px else np.nan for px in close])
    extras_below = [rb]
    extras_above = [ra]
    if bool(cfg.get("pa_round_half", True)) and step > 0:
        half = step / 2.0
        extras_below.append(np.array([round_below(float(px), half) if px == px else np.nan for px in close]))
        extras_above.append(np.array([round_above(float(px), half) if px == px else np.nan for px in close]))

    def _col(name: str) -> np.ndarray:
        if name not in frame.columns:
            return np.full(len(frame), np.nan)
        return pd.to_numeric(frame[name], errors="coerce").to_numpy(dtype=float)

    support_cols = [_col("pa_h4_last_sl"), _col("pa_h4_prev_sl"), _col("pa_d1_last_sl"), _col("pa_d1_prev_sl")]
    resist_cols = [_col("pa_h4_last_sh"), _col("pa_h4_prev_sh"), _col("pa_d1_last_sh"), _col("pa_d1_prev_sh")]
    frame["pa_round_below"] = rb
    frame["pa_round_above"] = ra
    frame["pa_support"] = _nearest_level(close, support_cols + extras_below, below=True)
    frame["pa_resist"] = _nearest_level(close, resist_cols + extras_above, below=False)
    if "pa_h4_support_touches" in frame.columns:
        frame["pa_support_touches"] = pd.to_numeric(frame["pa_h4_support_touches"], errors="coerce")
    else:
        frame["pa_support_touches"] = 0
    if "pa_h4_resist_touches" in frame.columns:
        frame["pa_resist_touches"] = pd.to_numeric(frame["pa_h4_resist_touches"], errors="coerce")
    else:
        frame["pa_resist_touches"] = 0
    return frame


def prepare_pa_select(df: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame:
    from aegis.features import enrich_all

    frame = enrich_all(df, cfg)
    frame["time"] = pd.to_datetime(frame["time"], utc=True)
    frame = frame.sort_values("time").reset_index(drop=True)
    frame["rsi_prev"] = frame["rsi"].shift(1)
    frame["close_prev"] = frame["close"].shift(1)
    frame["high_prev"] = frame["high"].shift(1)
    frame["low_prev"] = frame["low"].shift(1)
    pip = pip_size_from_cfg(cfg)
    frames = _frames_for_prepare(frame, cfg)
    for key, prefix in (("d1", "pa_d1"), ("h4", "pa_h4"), ("h1", "pa_h1")):
        closed = _closed_htf(frames.get(key, pd.DataFrame()))
        feat = _htf_feature_frame(closed, cfg, prefix, pip) if len(closed) else pd.DataFrame()
        cols = list(feat.columns.drop("time")) if len(feat) else _empty_htf_cols(prefix)
        frame = _merge_htf(frame, feat, list(cols))
    frame = _attach_zones(frame, cfg, pip)
    return frame.reset_index(drop=True)


def _daily_bias(row: pd.Series, cfg: dict[str, Any]) -> str:
    mode = str(cfg.get("pa_daily_mode", "ema")).lower()
    if mode == "structure":
        st = str(row.get("pa_d1_structure") or "chop")
        if st == "trend_up":
            return "up"
        if st == "trend_down":
            return "down"
        if st == "range":
            return "range"
        return "chop"
    return str(row.get("pa_d1_dir") or "range")


def _mtf_ok(row: pd.Series, cfg: dict[str, Any], side: str) -> bool:
    """Daily + H4 structure + H1 must agree. Skip chop. Range fades are optional."""
    d1 = _daily_bias(row, cfg)
    h4 = str(row.get("pa_h4_structure") or "chop")
    h1 = str(row.get("pa_h1_dir") or "none")
    require_h1 = bool(cfg.get("pa_require_h1", True))
    allow_range = bool(cfg.get("pa_allow_range", True))
    allow_trend = bool(cfg.get("pa_allow_trend", True))
    if h4 == "chop" or d1 == "chop":
        return False
    if side == "buy":
        if h4 == "trend_up":
            return allow_trend and d1 == "up" and (not require_h1 or h1 == "up")
        if h4 == "range":
            return allow_range and d1 != "down" and (not require_h1 or h1 != "down")
        return False
    if h4 == "trend_down":
        return allow_trend and d1 == "down" and (not require_h1 or h1 == "down")
    if h4 == "range":
        return allow_range and d1 != "up" and (not require_h1 or h1 != "up")
    return False


def _er_ok(row: pd.Series, cfg: dict[str, Any], h4: str) -> bool:
    er = row.get("kaufman_er")
    min_er = float(cfg.get("pa_min_er", 0.30))
    range_min = float(cfg.get("pa_range_min_er", 0.0))
    if h4 in {"trend_up", "trend_down"}:
        if er is None or pd.isna(er) or float(er) < min_er:
            return False
        return True
    if h4 == "range":
        if er is not None and not pd.isna(er) and float(er) < range_min:
            return False
        return True
    return False


def _wick_tags(row: pd.Series, level: Any, pip: float, zone_pips: float, side: str) -> bool:
    if level is None or pd.isna(level):
        return False
    lvl = float(level)
    tol = float(zone_pips) * pip
    lo, hi = float(row["low"]), float(row["high"])
    if abs(lo - lvl) <= tol or abs(hi - lvl) <= tol or (lo <= lvl <= hi):
        if side == "buy":
            return float(row["close"]) >= lvl - tol
        return float(row["close"]) <= lvl + tol
    return False


def _flag(row: pd.Series, key: str) -> bool:
    val = row.get(key)
    try:
        if val is None or pd.isna(val):
            return False
    except (TypeError, ValueError):
        return False
    return bool(val)


def sig_pa_select(row: pd.Series, cfg: dict[str, Any]) -> Optional[Signal]:
    if pd.isna(row.get("close")) or pd.isna(row.get("high")) or pd.isna(row.get("low")):
        return None
    if not in_session(row["time"], cfg.get("session_start_utc"), cfg.get("session_end_utc")):
        return None
    if _flag(row, "inside_bar"):
        return None

    from aegis.session_algos import cost_ok

    pip = pip_size_from_cfg(cfg)
    side = pa_reversal_side(row, cfg)
    if side is None:
        return None
    h4 = str(row.get("pa_h4_structure") or "chop")
    if not _er_ok(row, cfg, h4):
        return None
    if not _mtf_ok(row, cfg, side):
        return None
    if bool(cfg.get("pa_elder_censor", True)):
        if side == "buy" and _flag(row, "impulse_red"):
            return None
        if side == "sell" and _flag(row, "impulse_green"):
            return None

    zone_pips = float(cfg.get("pa_zone_pips", 8.0))
    if side == "buy":
        zone = row.get("pa_support")
        touches = row.get("pa_support_touches")
    else:
        zone = row.get("pa_resist")
        touches = row.get("pa_resist_touches")
    if not _wick_tags(row, zone, pip, zone_pips, side):
        return None
    if bool(cfg.get("pa_require_multi_touch", False)):
        if touches is None or pd.isna(touches) or int(touches) < 2:
            return None

    close = float(row["close"])
    buffer = float(cfg.get("pa_sl_buffer_pips", 1.0)) * pip
    max_sl = float(cfg.get("pa_max_sl_pips", 12.0)) * pip
    min_sl = float(cfg.get("pa_min_sl_pips", 0.0)) * pip
    if side == "buy":
        sl = float(row["low"]) - buffer
        if sl >= close:
            return None
        risk = close - sl
    else:
        sl = float(row["high"]) + buffer
        if sl <= close:
            return None
        risk = sl - close
    if max_sl > 0 and risk > max_sl + 1e-12:
        return None
    if min_sl > 0 and risk + 1e-12 < min_sl:
        return None

    tp_mode = str(cfg.get("pa_tp_mode", "r_multiple")).lower()
    min_rr = float(cfg.get("min_rr", 2.0))
    if tp_mode == "pips":
        tp_dist = float(cfg.get("pa_tp_pips", 20.0)) * pip
    elif tp_mode == "nearest_swing":
        if side == "buy":
            tgt = row.get("pa_resist")
            if tgt is None or pd.isna(tgt) or float(tgt) <= close:
                return None
            tp_dist = float(tgt) - close
        else:
            tgt = row.get("pa_support")
            if tgt is None or pd.isna(tgt) or float(tgt) >= close:
                return None
            tp_dist = close - float(tgt)
    else:
        tp_dist = float(cfg.get("pa_tp_r", 4.0)) * risk
    if tp_dist <= 0 or risk <= 0 or (tp_dist / risk) < min_rr:
        return None
    tp = close + tp_dist if side == "buy" else close - tp_dist
    if not cost_ok(row, cfg, abs(tp - close)):
        return None
    reason = f"pa_select_{side}_{h4}"
    return Signal(side, "pa_select", close, sl, tp, None, row["time"], reason)


__all__ = [
    "fetch_mtf_frames",
    "is_pa_select",
    "prepare_pa_select",
    "sig_pa_select",
]
