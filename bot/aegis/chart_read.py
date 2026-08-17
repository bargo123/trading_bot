"""OHLC chart reading (Nison candles + Volman box + inside bar).

Nison: hammer / shooting star / engulfing are reversal clues, not certainties.
Steidlmayer/Brooks: inside bars are compression — wait for the break.
This module scores structure. It does not claim 100% accuracy.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def add_chart_features(df: pd.DataFrame, cfg: dict[str, Any] | None = None) -> pd.DataFrame:
    out = df.copy()
    o, h, l, c = out["open"], out["high"], out["low"], out["close"]
    body = (c - o).abs()
    rng = (h - l).replace(0, np.nan)
    upper = h - np.maximum(c, o)
    lower = np.minimum(c, o) - l
    po, pc, ph, pl = o.shift(1), c.shift(1), h.shift(1), l.shift(1)
    declined = pc < c.shift(3)
    rallied = pc > c.shift(3)

    out["nison_hammer"] = (
        (lower >= 2.0 * body)
        & (upper <= body)
        & (body / rng <= 0.4)
        & declined
    ).fillna(False)
    out["nison_shooting_star"] = (
        (upper >= 2.0 * body)
        & (lower <= body)
        & (body / rng <= 0.4)
        & rallied
    ).fillna(False)
    out["nison_bull_engulf"] = ((c > o) & (pc < po) & (o <= pc) & (c >= po)).fillna(False)
    out["nison_bear_engulf"] = ((c < o) & (pc > po) & (o >= pc) & (c <= po)).fillna(False)
    out["inside_bar"] = ((h < ph) & (l > pl)).fillna(False)
    out["pin_bull"] = ((lower >= 2.0 * body) & (c >= (l + 0.6 * rng))).fillna(False)
    out["pin_bear"] = ((upper >= 2.0 * body) & (c <= (l + 0.4 * rng))).fillna(False)
    if "volman_box_high" in out.columns:
        out["volman_box_break_up"] = (c > out["volman_box_high"]).fillna(False)
        out["volman_box_break_dn"] = (c < out["volman_box_low"]).fillna(False)
    else:
        out["volman_box_break_up"] = False
        out["volman_box_break_dn"] = False
    out["prior_high_break"] = (c > ph).fillna(False)
    out["prior_low_break"] = (c < pl).fillna(False)
    # Break of the bar-before-last extreme, then retest that level (not a certainty).
    brk_up_lvl = ph.shift(1)
    brk_dn_lvl = pl.shift(1)
    out["break_retest_bull"] = ((pc > brk_up_lvl) & (l <= brk_up_lvl) & (c > brk_up_lvl)).fillna(False)
    out["break_retest_bear"] = ((pc < brk_dn_lvl) & (h >= brk_dn_lvl) & (c < brk_dn_lvl)).fillna(False)
    return out


def _flag(row: pd.Series, key: str) -> bool:
    val = row.get(key)
    try:
        if val is None or pd.isna(val):
            return False
    except (TypeError, ValueError):
        return False
    return bool(val)


def chart_confirms(row: pd.Series, cfg: dict[str, Any], side: str) -> bool:
    """True if candle/structure agrees with side. False on inside bar or opposing Nison pattern."""
    if not bool(cfg.get("firehose_chart_read", True)):
        return True
    if _flag(row, "inside_bar"):
        return False
    if side == "buy":
        if _flag(row, "nison_shooting_star") or _flag(row, "nison_bear_engulf") or _flag(row, "pin_bear"):
            return False
        score = sum(
            [
                _flag(row, "nison_hammer"),
                _flag(row, "nison_bull_engulf"),
                _flag(row, "pin_bull"),
                _flag(row, "volman_box_break_up"),
                _flag(row, "prior_high_break"),
            ]
        )
    else:
        if _flag(row, "nison_hammer") or _flag(row, "nison_bull_engulf") or _flag(row, "pin_bull"):
            return False
        score = sum(
            [
                _flag(row, "nison_shooting_star"),
                _flag(row, "nison_bear_engulf"),
                _flag(row, "pin_bear"),
                _flag(row, "volman_box_break_dn"),
                _flag(row, "prior_low_break"),
            ]
        )
    return score >= int(cfg.get("firehose_min_chart_score", 1))


def pa_reversal_side(row: pd.Series, cfg: dict[str, Any] | None = None) -> str | None:
    """Nison pin/engulf or break-retest on the entry bar. Edwards/Magee: not 100% reliable."""
    cfg = cfg or {}
    if _flag(row, "inside_bar"):
        return None
    bull = False
    bear = False
    if bool(cfg.get("pa_allow_pin", True)):
        bull = bull or _flag(row, "pin_bull") or _flag(row, "nison_hammer")
        bear = bear or _flag(row, "pin_bear") or _flag(row, "nison_shooting_star")
    if bool(cfg.get("pa_allow_engulf", True)):
        bull = bull or _flag(row, "nison_bull_engulf")
        bear = bear or _flag(row, "nison_bear_engulf")
    if bool(cfg.get("pa_allow_retest", True)):
        bull = bull or _flag(row, "break_retest_bull")
        bear = bear or _flag(row, "break_retest_bear")
    if bull and not bear:
        return "buy"
    if bear and not bull:
        return "sell"
    return None
