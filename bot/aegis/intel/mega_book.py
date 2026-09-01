"""Multi-book direction votes around CORE firehose.

INVENTED_ALGORITHM / research_proxy: combine measurable proxies from the
usable library on M1 OHLC. Not a faithful replica of any author system,
not a 100% WR claim, not Medallion. Authors disagree — each vote is a
flaggable censor; trade only when enough independent proxies agree.

Uses features already on the live prepare() row. Does not import
aegis.research (paper-runner isolation).
"""
from __future__ import annotations

from typing import Any

import pandas as pd


def _num(row: pd.Series, key: str) -> float | None:
    val = row.get(key)
    try:
        if val is None or pd.isna(val):
            return None
        return float(val)
    except (TypeError, ValueError):
        return None


def _flag(row: pd.Series, key: str) -> bool:
    val = row.get(key)
    try:
        if val is None or pd.isna(val):
            return False
    except (TypeError, ValueError):
        return False
    return bool(val)


def mega_book_votes(row: pd.Series, cfg: dict[str, Any], side: str) -> dict[str, Any]:
    """Return {votes:int, names:[str], needed:int, ok:bool} for CORE side."""
    side = str(side or "").lower()
    needed = int(cfg.get("intel_mega_min_votes", 5) or 5)
    names: list[str] = []

    close = _num(row, "close")
    open_ = _num(row, "open")
    htf = _num(row, "htf_ema")
    ema20 = _num(row, "ema_20")
    er = _num(row, "kaufman_er")
    loc = _num(row, "range_loc")
    js = _num(row, "jansen_score")
    rsi = _num(row, "rsi")
    adx = _num(row, "adx")
    cep = _num(row, "close_ema_pips")
    ret3 = _num(row, "ret3_pips")
    st = str(row.get("structure") or "chop")

    # 1) HTF / Clenow-style higher-timeframe side
    if close is not None and htf is not None:
        if side == "buy" and close >= htf:
            names.append("htf")
        if side == "sell" and close <= htf:
            names.append("htf")

    # 2) Damir structure
    if side == "buy" and st in {"trend_up", "chop", "range"}:
        if st == "trend_up":
            names.append("damir")
        elif st == "range" and loc is not None and loc <= 0.35:
            names.append("damir")
    if side == "sell" and st in {"trend_down", "chop", "range"}:
        if st == "trend_down":
            names.append("damir")
        elif st == "range" and loc is not None and loc >= 0.65:
            names.append("damir")

    # 3) Volman 20-EMA + body-with
    if close is not None and ema20 is not None and open_ is not None:
        body_ok = (side == "buy" and close >= open_) or (side == "sell" and close <= open_)
        ema_ok = (side == "buy" and close >= ema20) or (side == "sell" and close <= ema20)
        if body_ok and ema_ok and not _flag(row, "volman_doji"):
            names.append("volman")

    # 4) Kaufman efficiency (directional tape, not dead)
    er_min = float(cfg.get("intel_mega_er_min", 0.35) or 0.35)
    if er is not None and er >= er_min and cep is not None:
        if (side == "buy" and cep > 0) or (side == "sell" and cep < 0):
            names.append("kaufman")

    # 5) Brooks Ranges — buy low / sell high, or failed breakout
    if _flag(row, "brooks_in_range") and loc is not None:
        if side == "buy" and (loc <= 0.35 or _flag(row, "brooks_failed_bo_dn")):
            names.append("brooks")
        if side == "sell" and (loc >= 0.65 or _flag(row, "brooks_failed_bo_up")):
            names.append("brooks")
    elif not _flag(row, "brooks_in_range"):
        # Trend day: Brooks overlap low — count as vote if impulse agrees
        if side == "buy" and _flag(row, "impulse_green"):
            names.append("brooks")
        if side == "sell" and _flag(row, "impulse_red"):
            names.append("brooks")

    # 6) Coulling VPA proxy (tick volume)
    if not _flag(row, "vpa_absorption"):
        if side == "buy" and (_flag(row, "vpa_effort_up") or not _flag(row, "vpa_no_demand")):
            if _flag(row, "vpa_effort_up"):
                names.append("coulling")
        if side == "sell" and (_flag(row, "vpa_effort_dn") or not _flag(row, "vpa_no_supply")):
            if _flag(row, "vpa_effort_dn"):
                names.append("coulling")

    # 7) Jansen factor score
    jan_min = float(cfg.get("intel_mega_jansen_min", 0.15) or 0.15)
    if js is not None:
        if side == "buy" and js >= jan_min:
            names.append("jansen")
        if side == "sell" and js <= -jan_min:
            names.append("jansen")

    # 8) Harris — reject jump-against; vote when quiet or jump-with
    if not _flag(row, "harris_jump"):
        names.append("harris")
    elif ret3 is not None:
        if side == "buy" and ret3 > 0:
            names.append("harris")
        if side == "sell" and ret3 < 0:
            names.append("harris")

    # 9) Elder impulse
    if side == "buy" and _flag(row, "impulse_green") and not _flag(row, "impulse_red"):
        names.append("elder")
    if side == "sell" and _flag(row, "impulse_red") and not _flag(row, "impulse_green"):
        names.append("elder")

    # 10) RSI not extreme-against (Tharp/Elder caution)
    if rsi is not None:
        if side == "buy" and rsi < 70.0:
            names.append("rsi")
        if side == "sell" and rsi > 30.0:
            names.append("rsi")

    # 11) ADX not weak-edge spray (Grimes/Davey)
    weak = float(cfg.get("intel_weak_adx", 22.0) or 22.0)
    if adx is not None and adx >= weak:
        names.append("adx")

    # 12) 3-bar momentum with side (Chan momentum proxy)
    if ret3 is not None:
        if side == "buy" and ret3 > 0:
            names.append("chan_mom")
        if side == "sell" and ret3 < 0:
            names.append("chan_mom")

    votes = len(names)
    return {
        "votes": votes,
        "names": names,
        "needed": needed,
        "ok": votes >= needed,
    }
