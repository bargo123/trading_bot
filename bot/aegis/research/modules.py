"""Independent setup modules with book provenance. Not a blended super-signal."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from aegis.features import add_direction_features, add_intel_regime_features
from aegis.research.profile import tpo_profile


@dataclass(frozen=True)
class Setup:
    source: str
    side: str
    reason: str
    provenance: str


IMPLEMENTED = {
    "brooks_range": "aegis.research.modules.brooks_range_setup",
    "vpa_effort": "aegis.research.modules.vpa_effort_setup",
    "htf_bias": "aegis.research.modules.htf_bias_setup",
    "damir_retest": "aegis.research.modules.damir_retest_setup",
    "profile_excess": "aegis.research.modules.profile_excess_setup",
    "elliott_leg": "aegis.research.modules.elliott_leg_setup",
    "chan_bb_fade": "aegis.research.entry_signals.sig_chan_bb_fade",
}

MODULE_LABELS = {
    "brooks_range": "research_proxy",
    "vpa_effort": "research_proxy",
    "htf_bias": "research_proxy",
    "damir_retest": "research_proxy",
    "profile_excess": "research_proxy",
    "elliott_leg": "research_proxy",
    "chan_bb_fade": "research_proxy",
    "prado_purged_cv": "research_proxy",
    "gann_cycles": "research_proxy",
    "johnson_spread_gate": "research_proxy",
    "prado_meta_label": "research_proxy",
    "six_book_stack": "research_proxy",
    "jansen_ml": "unavailable",
    "harris_jump_live": "research_proxy",
}


def _last_body_side(df: pd.DataFrame) -> str | None:
    if df.empty:
        return None
    o = float(df["open"].iloc[-1])
    c = float(df["close"].iloc[-1])
    if c > o:
        return "buy"
    if c < o:
        return "sell"
    return None


def _signal_bar_ok(df: pd.DataFrame) -> bool:
    """Brooks: the last completed bar must be a signal bar, not a doji."""
    rng = float(df["high"].iloc[-1] - df["low"].iloc[-1])
    if rng <= 0:
        return False
    body = abs(float(df["close"].iloc[-1]) - float(df["open"].iloc[-1]))
    return body >= 0.35 * rng


def brooks_range_setup(*, m5: pd.DataFrame, regime: str) -> Setup | None:
    """Brooks ranges on completed 5-minute bars: location, signal bar, failed break.

    Does not use M1. Barbwire overlapping dojis are a no-trade.
    """
    if regime != "range" or len(m5) < 8 or not _signal_bar_ok(m5):
        return None
    feat = add_intel_regime_features(add_direction_features(m5, {}), {})
    last = feat.iloc[-1]
    if bool(last.get("brooks_barbwire")):
        return None
    loc = last.get("range_loc")
    side = _last_body_side(m5)
    if side is None or loc is None or pd.isna(loc):
        return None
    loc_f = float(loc)
    if bool(last.get("brooks_failed_bo_up")) and side == "sell":
        return Setup("brooks_range", "sell", "failed_breakout_up", "brooks:5m-failed-break")
    if bool(last.get("brooks_failed_bo_dn")) and side == "buy":
        return Setup("brooks_range", "buy", "failed_breakout_dn", "brooks:5m-failed-break")
    if loc_f >= 0.7 and side == "sell":
        return Setup("brooks_range", "sell", "range_high_sell", "brooks:5m-range-location")
    if loc_f <= 0.3 and side == "buy":
        return Setup("brooks_range", "buy", "range_low_buy", "brooks:5m-range-location")
    return None


def vpa_effort_setup(*, m5: pd.DataFrame) -> Setup | None:
    """Coulling effort vs result on completed 5m using broker tick-volume proxy.

    Spot FX has no centralized volume (Coulling). Absorption is a no-chase.
    """
    if len(m5) < 6:
        return None
    vol = m5["volume"].astype(float)
    rng = (m5["high"] - m5["low"]).astype(float)
    if float(rng.iloc[-1]) <= 0:
        return None
    vol_z = float(vol.iloc[-1] / max(float(vol.tail(6).mean()), 1e-9))
    rng_z = float(rng.iloc[-1] / max(float(rng.tail(6).mean()), 1e-9))
    side = _last_body_side(m5)
    if side is not None and vol_z >= 1.2 and rng_z >= 1.1:
        return Setup("vpa_effort", side, "effort_with_result", "coulling:tick-volume-proxy")
    if len(m5) < 20:
        return None
    feat = add_direction_features(m5, {})
    last = feat.iloc[-1]
    if bool(last.get("vpa_absorption")):
        return None
    if bool(last.get("vpa_effort_up")):
        return Setup("vpa_effort", "buy", "effort_up", "coulling:tick-volume-proxy")
    if bool(last.get("vpa_effort_dn")):
        return Setup("vpa_effort", "sell", "effort_dn", "coulling:tick-volume-proxy")
    return None


def htf_bias_setup(*, h1: pd.DataFrame) -> Setup | None:
    """Elder/Ponsi-style higher-timeframe close vs open as bias only. Uses H1, not M1 EMA."""
    side = _last_body_side(h1)
    if side is None:
        return None
    return Setup("htf_bias", side, f"h1_{side}", "ponsi-elder:htf-bias")


def _h4_value(h4: pd.DataFrame) -> tuple[float, float] | None:
    if len(h4) < 8:
        return None
    tp = (h4["high"] + h4["low"] + h4["close"]) / 3.0
    window = tp.tail(12)
    return float(window.quantile(0.25)), float(window.quantile(0.75))


def damir_retest_setup(*, h4: pd.DataFrame, m15: pd.DataFrame) -> Setup | None:
    """Damir H4 value with M15 rejection/retest. Never an M1 range percentile."""
    if h4.empty or len(m15) < 4:
        return None
    value = _h4_value(h4)
    if value is None:
        return None
    va_lo, va_hi = value
    last = m15.iloc[-1]
    rng = float(last["high"] - last["low"])
    if rng <= 0:
        return None
    close = float(last["close"])
    wick_lo = float(last["low"])
    wick_hi = float(last["high"])
    if wick_lo < va_lo <= close:
        return Setup("damir_retest", "buy", "m15_reject_h4_value_low", "damir:h4-value-m15-retest")
    if wick_hi > va_hi >= close:
        return Setup("damir_retest", "sell", "m15_reject_h4_value_high", "damir:h4-value-m15-retest")
    return None


def profile_excess_setup(*, m1: pd.DataFrame, m30: pd.DataFrame) -> Setup | None:
    """Steidlmayer TPO excess from completed M30 of the UTC day. Not order flow."""
    del m30  # profile rebuilds M30 from the session's M1
    prof = tpo_profile(m1)
    if not prof.get("ok"):
        return None
    c = float(m1["close"].iloc[-1])
    if bool(prof.get("excess_high")) and c >= float(prof["va_high"]):
        return Setup("profile_excess", "sell", "excess_high", "steidlmayer:tpo-proxy-not-pit-ib")
    if bool(prof.get("excess_low")) and c <= float(prof["va_low"]):
        return Setup("profile_excess", "buy", "excess_low", "steidlmayer:tpo-proxy-not-pit-ib")
    return None


def elliott_leg_setup(*, m5: pd.DataFrame) -> Setup | None:
    """Alternating swing-leg phase 3 proxy. Not subjective Elliott wave labeling."""
    from aegis.research.elliott import add_elliott_legs

    if len(m5) < 12:
        return None
    feat = add_elliott_legs(m5)
    last = feat.iloc[-1]
    try:
        phase = int(last.get("elliott_phase") or 0)
    except (TypeError, ValueError):
        return None
    if phase != 3:
        return None
    side = "buy" if float(last.get("elliott_up_leg") or 0) >= 0.5 else "sell"
    return Setup("elliott_leg", side, f"leg3_{side}", "frost-prechter:objective-leg-proxy")


def collect_setups(
    *,
    m5: pd.DataFrame,
    h1: pd.DataFrame,
    regime: str,
    m1: pd.DataFrame | None = None,
    m15: pd.DataFrame | None = None,
    m30: pd.DataFrame | None = None,
    h4: pd.DataFrame | None = None,
) -> list[Setup]:
    raw = [
        htf_bias_setup(h1=h1),
        brooks_range_setup(m5=m5, regime=regime),
        vpa_effort_setup(m5=m5),
        elliott_leg_setup(m5=m5),
    ]
    if h4 is not None and m15 is not None:
        raw.append(damir_retest_setup(h4=h4, m15=m15))
    if m1 is not None:
        raw.append(profile_excess_setup(m1=m1, m30=m30 if m30 is not None else m5))
    out = [s for s in raw if s is not None]
    if not out:
        return []
    sides = {s.side for s in out}
    if len(sides) != 1:
        return []
    return out
