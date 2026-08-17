"""Coulling VPA + Brooks range fade + Damir 2016 structure.

These are censors on firehose direction. They are not a 100% accuracy claim.
Coulling: spot FX has no true volume — tick volume is a proxy (her 2013 guide).
Brooks *Ranges*: buy low / sell high in a range; skip the middle.
Damir 2016 *Price Action Breakdown*: do not fight HH/HL; do not buy excess above value.
Authors disagree with every-bar EMA spray — each gate is a YAML flag, default off.
"""
from __future__ import annotations

from typing import Any

import pandas as pd


def _flag(row: pd.Series, key: str) -> bool:
    val = row.get(key)
    try:
        if val is None or pd.isna(val):
            return False
    except (TypeError, ValueError):
        return False
    return bool(val)


def _loc(row: pd.Series) -> float | None:
    val = row.get("range_loc")
    try:
        if val is None or pd.isna(val):
            return None
    except (TypeError, ValueError):
        return None
    return float(val)


def direction_allows(row: pd.Series, cfg: dict[str, Any], side: str) -> bool:
    """True if Coulling / Brooks / Damir gates (when enabled) allow this side."""
    if bool(cfg.get("firehose_vpa_filter", False)):
        vol_sma = row.get("vol_sma")
        try:
            has_vol = vol_sma is not None and not pd.isna(vol_sma) and float(vol_sma) > 0
        except (TypeError, ValueError):
            has_vol = False
        if has_vol:
            if _flag(row, "vpa_absorption"):
                return False
            if side == "buy" and _flag(row, "vpa_no_demand"):
                return False
            if side == "sell" and _flag(row, "vpa_no_supply"):
                return False

    if bool(cfg.get("firehose_damir_structure", False)):
        st = str(row.get("structure") or "chop")
        if side == "buy" and st == "trend_down":
            return False
        if side == "sell" and st == "trend_up":
            return False

    brooks_on = bool(cfg.get("firehose_brooks_range", False)) and _flag(row, "brooks_in_range")
    if brooks_on:
        if side == "buy" and _flag(row, "brooks_failed_bo_dn"):
            return True
        if side == "sell" and _flag(row, "brooks_failed_bo_up"):
            return True

    loc = _loc(row)
    if loc is not None and bool(cfg.get("firehose_damir_structure", False)):
        st = str(row.get("structure") or "chop")
        excess_hi = float(cfg.get("damir_excess_hi", 0.85))
        excess_lo = float(cfg.get("damir_excess_lo", 0.15))
        if st == "trend_up" and side == "buy" and loc >= excess_hi:
            return False
        if st == "trend_down" and side == "sell" and loc <= excess_lo:
            return False
        if st == "range":
            if side == "buy" and loc > float(cfg.get("brooks_mid_lo", 0.35)):
                return False
            if side == "sell" and loc < float(cfg.get("brooks_mid_hi", 0.65)):
                return False

    if brooks_on and loc is not None:
        if side == "buy" and loc > float(cfg.get("brooks_mid_lo", 0.35)):
            return False
        if side == "sell" and loc < float(cfg.get("brooks_mid_hi", 0.65)):
            return False
    return True
