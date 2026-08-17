"""TradeQualityScore 0–100 from the closed bar only. No future bars.

INVENTED_ALGORITHM: weighted blend of Harris cost, Kaufman ER, Jansen side
agreement, Brooks range location, and body-with-trade. Not a trained model
and not a 100% WR claim.
"""
from __future__ import annotations

from typing import Any

import pandas as pd


def _num(row: pd.Series, key: str, default: float = 0.0) -> float:
    val = row.get(key)
    try:
        if val is None or pd.isna(val):
            return default
        return float(val)
    except (TypeError, ValueError):
        return default


def _flag(row: pd.Series, key: str) -> bool:
    val = row.get(key)
    try:
        if val is None or pd.isna(val):
            return False
    except (TypeError, ValueError):
        return False
    return bool(val)


def quality_parts(row: pd.Series, cfg: dict[str, Any], side: str) -> dict[str, float]:
    side = str(side or "").lower()
    pip = float(cfg.get("volman_pip_size", cfg.get("firehose_pip_size", 0.0001)))
    tp_pips = float(cfg.get("firehose_tp_pips", 1.0) or 1.0)
    spread = _num(row, "spread")
    if spread <= 0:
        spread = float(cfg.get("max_spread_price") or 0.0) or 0.0
    cost_frac = spread / max(tp_pips * pip, 1e-12)
    cost_s = max(0.0, 1.0 - min(cost_frac, 2.0) / 2.0) * 100.0

    er = _num(row, "kaufman_er", 0.0)
    er_s = max(0.0, min(1.0, er / 0.6)) * 100.0

    js = _num(row, "jansen_score", 0.0)
    if side == "buy":
        jan_s = max(0.0, min(1.0, (js + 1.0) / 2.0)) * 100.0
    else:
        jan_s = max(0.0, min(1.0, (1.0 - js) / 2.0)) * 100.0

    o, c = _num(row, "open"), _num(row, "close")
    body_ok = (side == "buy" and c >= o) or (side == "sell" and c <= o)
    body_s = 100.0 if body_ok else 25.0

    rng_pos = _num(row, "range_loc", 0.5)
    rsi = _num(row, "rsi", 50.0)
    # Brooks/Damir: buy low / sell high. CORE EMA spray does the opposite at
    # range edges — that is the never-green 30-pip stop pattern in loss_db.
    wrong_edge = False
    wrong_extreme = False
    if _flag(row, "brooks_in_range"):
        if (side == "buy" and rng_pos >= 0.67) or (side == "sell" and rng_pos <= 0.33):
            range_s = 12.0
            wrong_edge = True
            if (side == "buy" and rng_pos >= 0.90) or (side == "sell" and rng_pos <= 0.10):
                wrong_extreme = True
        elif (side == "buy" and rng_pos <= 0.33) or (side == "sell" and rng_pos >= 0.67):
            range_s = 88.0
        else:
            range_s = 22.0
    else:
        range_s = 70.0
    rsi_ext = (side == "buy" and rsi >= 70.0) or (side == "sell" and rsi <= 30.0)

    atr = _num(row, "atr", 0.0)
    atr_vs_tp = atr / max(tp_pips * pip, 1e-12)
    vol_s = 80.0 if atr_vs_tp <= 8.0 else max(10.0, 80.0 - 10.0 * (atr_vs_tp - 8.0))

    barb_s = 15.0 if _flag(row, "brooks_barbwire") else 80.0
    against = (side == "buy" and _flag(row, "impulse_red")) or (
        side == "sell" and _flag(row, "impulse_green")
    )
    impulse_s = 20.0 if against else 80.0

    return {
        "cost": cost_s,
        "er": er_s,
        "jansen": jan_s,
        "body": body_s,
        "range": range_s,
        "vol": vol_s,
        "barbwire": barb_s,
        "impulse": impulse_s,
        "wrong_edge": 10.0 if wrong_edge else 85.0,
        "wrong_extreme": 8.0 if wrong_extreme else 85.0,
        "rsi_ext": 10.0 if rsi_ext else 85.0,
    }


# Caps so a 1-pip spray at the range floor/ceiling cannot print "quality 87".
# loss_db 30-pip stops were all loc<=0.10 sells or loc>=0.90 buys.
WRONG_EXTREME_QUALITY_CAP = 28.0
RSI_EXT_QUALITY_CAP = 32.0


def quality_score(row: pd.Series, cfg: dict[str, Any], side: str) -> float:
    p = quality_parts(row, cfg, side)
    score = (
        0.18 * p["cost"]
        + 0.12 * p["er"]
        + 0.12 * p["jansen"]
        + 0.10 * p["body"]
        + 0.16 * p["range"]
        + 0.08 * p["vol"]
        + 0.12 * p["barbwire"]
        + 0.12 * p["impulse"]
    )
    if p["wrong_extreme"] <= 10.0:
        score = min(score, WRONG_EXTREME_QUALITY_CAP)
    if p["rsi_ext"] <= 10.0:
        score = min(score, RSI_EXT_QUALITY_CAP)
    return float(max(0.0, min(100.0, score)))
