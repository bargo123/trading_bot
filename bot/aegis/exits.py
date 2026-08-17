"""Firehose / scalp exits. Tharp: exits dominate expectancy.

Brooks *Ranges*: treat range trades as scalps — do not hold a green trade
hoping it becomes a breakout. Grimes: time-stop if the imbalance does not pay;
after a real open profit, do not give the whole R back. Elder: if the thesis
fails, get out. Volman: a scalp has a small target; it is not a 25-pip hold.
Harris: closing still pays spread — only arm after a real open profit.

This is not a 100% lock. Authors disagree (Fuller trail vs Brooks scalp).
Flags default off.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def update_mfe(peak: float | None, pnl: float) -> float:
    cur = float(pnl)
    if peak is None:
        return cur
    return max(float(peak), cur)


def working_stop(
    side: str,
    entry: float,
    core_sl: float,
    cfg: dict[str, Any],
) -> tuple[float, str]:
    """Tighter of CORE SL and intel scratch. Does not rewrite the CORE 30-pip formula.

    Tharp: the left tail dominates expectancy on 1-pip/30-pip. Scratch is a meta
    overlay; intel_enabled must be on. Returns (stop_price, outcome_name_if_hit).
    """
    pip = float(cfg.get("volman_pip_size", cfg.get("firehose_pip_size", 0.0001)))
    cap = float(cfg.get("intel_scratch_pips") or 0)
    if not bool(cfg.get("intel_enabled", False)) or cap <= 0 or pip <= 0:
        return float(core_sl), "sl"
    side = str(side or "").lower()
    if side == "buy":
        scratch = float(entry) - cap * pip
        if scratch > float(core_sl) + 1e-12:
            return scratch, "intel_scratch"
        return float(core_sl), "sl"
    scratch = float(entry) + cap * pip
    if scratch < float(core_sl) - 1e-12:
        return scratch, "intel_scratch"
    return float(core_sl), "sl"


def firehose_stops_from_quote(
    side: str,
    bid: float,
    ask: float,
    cfg: dict[str, Any],
    pip: float,
) -> tuple[float, float] | None:
    """CORE 1/30 distances from live bid/ask, not the closed-bar close.

    Tharp: 1R is entry-to-stop in money. Harris: a market buy pays the offer, so
    TP/SL glued to the signal close opens immediately red and can put TP behind
    the ask. Distances stay firehose_tp_pips / firehose_sl_pips. Returns
    (stop, take) or None when spread >= take (do not scalp).
    """
    bid_f = float(bid or 0.0)
    ask_f = float(ask or 0.0)
    pip_f = float(pip or 0.0)
    if bid_f <= 0 or ask_f <= 0 or pip_f <= 0 or ask_f + 1e-18 < bid_f:
        return None
    tp_pips = float(cfg.get("firehose_tp_pips") or 1)
    sl_pips = float(cfg.get("firehose_sl_pips") or 30)
    spread = ask_f - bid_f
    if spread + 1e-18 >= tp_pips * pip_f:
        return None
    side_l = str(side or "").lower()
    if side_l == "buy":
        return ask_f - sl_pips * pip_f, ask_f + tp_pips * pip_f
    if side_l == "sell":
        return bid_f + sl_pips * pip_f, bid_f - tp_pips * pip_f
    return None


def should_scratch_never_green(
    *,
    held_s: float,
    peak: float | None,
    pnls: list[float],
    cfg: dict[str, Any],
) -> bool:
    """Grimes/Elder: if the 1-pip scalp never paid, do not sit into the 30-pip SL.

    Only fires when every clip on the symbol is red and MFE never armed the
    give-back lock. Does not rewrite CORE TP/SL for trades that went green.
    """
    cap = float(cfg.get("scratch_never_green_seconds") or 0)
    if cap <= 0 or float(held_s) < cap:
        return False
    if not pnls or any(float(x) >= -1e-12 for x in pnls):
        return False
    lock = float(cfg.get("lock_mfe_usd") or 0.0)
    peak_f = 0.0 if peak is None else float(peak)
    return peak_f + 1e-12 < max(lock, 1e-9)


def should_block_scratch_cooldown(
    *,
    since_s: float | None,
    cfg: dict[str, Any],
) -> bool:
    """Elder/Davey: after a failed scalp, do not immediately re-spray the same name."""
    cap = float(cfg.get("scratch_cooldown_s") or 0)
    if cap <= 0 or since_s is None:
        return False
    return float(since_s) < cap


def quick_win_clips(positions: list[Any], flatten_profit: float) -> list[Any]:
    """Clips whose unrealized PnL meets flatten_if_profit_usd.

    Harvest those tickets only. Leave still-red extras on the same symbol.
    Does not rewrite CORE 1/30; this is the $0.05 scalp take, per clip.
    """
    thresh = float(flatten_profit or 0.0)
    if thresh <= 0:
        return []
    out: list[Any] = []
    for pos in positions or []:
        if float(getattr(pos, "unrealized_pnl", 0.0) or 0.0) + 1e-12 >= thresh:
            out.append(pos)
    return out


def mfe_after_quick_win(remaining_pnls: list[float]) -> float | None:
    """Symbol MFE after harvesting winner tickets. None clears the lock.

    A harvested clip's peak must not arm give-back flatten on leftover red extras.
    """
    if not remaining_pnls:
        return None
    return max(float(x) for x in remaining_pnls)


def giveback_reason(peak: float, pnl: float, cfg: dict[str, Any]) -> str | None:
    """Close if the trade was actually winning and then gave it back.

    lock_mfe_usd: minimum peak open P&L before the lock arms.
    giveback_floor_usd: close once open P&L falls to this (0 = do not let it go red).
    giveback_frac: optional extra — close after giving back this fraction of peak.
    """
    if not bool(cfg.get("close_if_gave_back", False)):
        return None
    lock = float(cfg.get("lock_mfe_usd", 0.0) or 0.0)
    if lock <= 0 or float(peak) + 1e-12 < lock:
        return None
    floor = float(cfg.get("giveback_floor_usd", 0.0) or 0.0)
    if float(pnl) <= floor + 1e-12:
        return "gave_back"
    frac = float(cfg.get("giveback_frac", 0.0) or 0.0)
    if frac > 0 and float(pnl) <= float(peak) * (1.0 - frac) + 1e-12:
        return "gave_back_frac"
    return None


def load_mfe(path: Path) -> dict[str, float]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    out: dict[str, float] = {}
    if isinstance(raw, dict):
        for key, val in raw.items():
            try:
                out[str(key)] = float(val)
            except (TypeError, ValueError):
                continue
    return out


def save_mfe(path: Path, data: dict[str, float]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
