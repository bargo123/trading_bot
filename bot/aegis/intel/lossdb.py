"""Loss / win rows from a CORE backtest. Features are from the signal bar only."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from aegis.intel.cluster import family_for
from aegis.intel.paths import INTEL_DIR, ensure_intel_dirs
from aegis.intel.score import quality_parts, quality_score

FEATURE_KEYS = (
    "open",
    "high",
    "low",
    "close",
    "volume",
    "ema_20",
    "atr",
    "rsi",
    "adx",
    "kaufman_er",
    "jansen_score",
    "harris_jump",
    "brooks_in_range",
    "range_loc",
    "volman_doji",
    "impulse_green",
    "impulse_red",
    "spread",
    "brooks_barbwire",
    "ema_side_streak",
    "atr_expand",
    "close_ema_pips",
    "ret3_pips",
)


def _row_features(row: pd.Series) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in FEATURE_KEYS:
        if key not in row.index:
            out[key] = None
            continue
        val = row.get(key)
        try:
            if val is None or pd.isna(val):
                out[key] = None
            elif hasattr(val, "item"):
                out[key] = val.item()
            else:
                out[key] = val if isinstance(val, (bool, str)) else float(val)
        except (TypeError, ValueError):
            out[key] = str(val)
    ts = row.get("time")
    hour = None
    if ts is not None:
        t = pd.Timestamp(ts)
        hour = int(t.tz_convert("UTC").hour) if getattr(t, "tzinfo", None) else int(t.hour)
    out["hour_utc"] = hour
    return out


def trade_record(
    trade: dict[str, Any],
    entry_row: pd.Series | None,
    cfg: dict[str, Any],
) -> dict[str, Any]:
    side = str(trade.get("side") or "")
    pnl = float(trade.get("pnl") or 0.0)
    feats: dict[str, Any] = {}
    score = None
    parts: dict[str, float] = {}
    if entry_row is not None:
        feats = _row_features(entry_row)
        score = quality_score(entry_row, cfg, side)
        parts = quality_parts(entry_row, cfg, side)
    rec = {
        "symbol": trade.get("symbol") or cfg.get("symbol"),
        "side": side,
        "entry": trade.get("entry"),
        "exit": trade.get("exit"),
        "entry_time": str(trade.get("entry_time")),
        "exit_time": str(trade.get("exit_time")),
        "pnl": pnl,
        "r": trade.get("r"),
        "outcome": trade.get("outcome"),
        "reason": trade.get("reason"),
        "mfe": trade.get("mfe"),
        "mae": trade.get("mae"),
        "bars_held": trade.get("bars_held"),
        "win": pnl > 0,
        "quality": score,
        "quality_parts": parts,
        "family": family_for(trade, feats),
        "features": feats,
    }
    return rec


def split_and_write(
    records: list[dict[str, Any]],
    *,
    dest: Path | None = None,
) -> dict[str, int]:
    ensure_intel_dirs()
    root = dest or INTEL_DIR
    loss_p = root / "loss_db" / "rows.jsonl"
    win_p = root / "win_db" / "rows.jsonl"
    n_l = n_w = 0
    with loss_p.open("w", encoding="utf-8") as lf, win_p.open("w", encoding="utf-8") as wf:
        for rec in records:
            line = json.dumps(rec, default=str) + "\n"
            if rec.get("win"):
                wf.write(line)
                n_w += 1
            else:
                lf.write(line)
                n_l += 1
    return {"wins": n_w, "losses": n_l, "loss_path": str(loss_p), "win_path": str(win_p)}
