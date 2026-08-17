"""Rule families for losses/wins. Not sklearn clustering."""
from __future__ import annotations

from typing import Any


def family_for(trade: dict[str, Any], feats: dict[str, Any]) -> str:
    outcome = str(trade.get("outcome") or "")
    pnl = float(trade.get("pnl") or 0.0)
    er = feats.get("kaufman_er")
    loc = feats.get("range_loc")
    in_range = bool(feats.get("brooks_in_range"))
    jump = bool(feats.get("harris_jump"))
    doji = bool(feats.get("volman_doji"))
    barb = bool(feats.get("brooks_barbwire"))
    impulse_g = bool(feats.get("impulse_green"))
    impulse_r = bool(feats.get("impulse_red"))
    side = str(trade.get("side") or "").lower()
    if pnl > 0:
        if outcome in {"tp", "quick_win"}:
            return "win_quick"
        return "win_other"
    if outcome == "intel_scratch":
        return "loss_scratch"
    if jump:
        return "loss_chase_jump"
    if barb:
        return "loss_barbwire"
    if (side == "buy" and impulse_r) or (side == "sell" and impulse_g):
        return "loss_impulse_against"
    if doji:
        return "loss_doji"
    if er is not None and float(er) < 0.25:
        return "loss_chop_er"
    if in_range and loc is not None and 0.33 < float(loc) < 0.67:
        return "loss_range_mid"
    if outcome == "sl":
        return "loss_stop"
    if outcome in {"eof", "time"}:
        return "loss_time"
    return "loss_other"


def family_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for rec in records:
        name = str(rec.get("family") or "unknown")
        out[name] = out.get(name, 0) + 1
    return out
