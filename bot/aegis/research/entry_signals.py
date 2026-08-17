"""Research entry candidates built on confirmed structure, not the live every-bar EMA.

CORE_STRATEGY_V1 stays frozen; these are challengers evaluated in the shadow research
path only. Stops come from ATR and the invalidation level, and targets are an
R-multiple, so no candidate inherits the 1-pip / 30-pip payoff.
"""
from __future__ import annotations

from typing import Any, Optional

import pandas as pd

from aegis.strategy import Signal


def _atr(row: pd.Series) -> float | None:
    atr = row.get("atr")
    try:
        value = float(atr)
    except (TypeError, ValueError):
        return None
    if value != value or value <= 0:
        return None
    return value


def _news_blocks(row: pd.Series, cfg: dict[str, Any]) -> bool:
    events = cfg.get("calendar_events")
    if not events:
        return False
    from aegis.research.news import CalendarError, in_blackout

    symbol = str(cfg.get("symbol") or row.get("symbol") or "")
    if len("".join(ch for ch in symbol.upper() if ch.isalpha())) != 6:
        return False
    try:
        blocked, _ = in_blackout(
            symbol,
            row["time"],
            events,
            before_minutes=float(cfg.get("news_before_minutes", 30) or 30),
            after_minutes=float(cfg.get("news_after_minutes", 30) or 30),
        )
    except CalendarError:
        return False
    return blocked


def _geometry(
    row: pd.Series,
    cfg: dict[str, Any],
    side: str,
    reason: str,
) -> Optional[Signal]:
    atr = _atr(row)
    if atr is None:
        return None
    close = float(row["close"])
    stop_mult = float(cfg.get("entry_atr_stop_mult", 1.5) or 1.5)
    rr = float(cfg.get("entry_rr", 2.0) or 2.0)
    risk = atr * stop_mult
    if risk <= 0:
        return None
    if _news_blocks(row, cfg):
        return None
    if side == "buy":
        sl = close - risk
        tp = close + risk * rr
    else:
        sl = close + risk
        tp = close - risk * rr
    return Signal(side, "research_entry", close, sl, tp, None, row["time"], reason)


def _htf_agrees(row: pd.Series, side: str) -> bool:
    h1 = row.get("h1_up")
    try:
        up = float(h1)
    except (TypeError, ValueError):
        return False
    if up != up:
        return False
    return (up >= 0.5) if side == "buy" else (up < 0.5)


def sig_structure_breakout(row: pd.Series, cfg: dict[str, Any]) -> Optional[Signal]:
    """Close beyond a confirmed pivot level, in the direction of the completed H1 bar."""
    event = str(row.get("struct_event") or "")
    if event == "breakout_up":
        if pd.isna(row.get("piv_high")) or not _htf_agrees(row, "buy"):
            return None
        return _geometry(row, cfg, "buy", "structure_breakout_up")
    if event == "breakout_dn":
        if pd.isna(row.get("piv_low")) or not _htf_agrees(row, "sell"):
            return None
        return _geometry(row, cfg, "sell", "structure_breakout_dn")
    return None


def sig_failed_break(row: pd.Series, cfg: dict[str, Any]) -> Optional[Signal]:
    """Prior bar poked through a level and price closed back inside: trade the failure."""
    event = str(row.get("struct_event") or "")
    if event == "failure_up":
        if pd.isna(row.get("piv_high")):
            return None
        return _geometry(row, cfg, "sell", "failed_break_up")
    if event == "failure_dn":
        if pd.isna(row.get("piv_low")):
            return None
        return _geometry(row, cfg, "buy", "failed_break_dn")
    return None


def sig_level_retest(row: pd.Series, cfg: dict[str, Any]) -> Optional[Signal]:
    """Price back at a confirmed level, taken only with the completed H1 direction."""
    event = str(row.get("struct_event") or "")
    if event == "retest_up" and _htf_agrees(row, "buy"):
        return _geometry(row, cfg, "buy", "level_retest_up")
    if event == "retest_dn" and _htf_agrees(row, "sell"):
        return _geometry(row, cfg, "sell", "level_retest_dn")
    return None


def sig_chan_bb_fade(row: pd.Series, cfg: dict[str, Any]) -> Optional[Signal]:
    """Chan mean-reversion at 2σ bands; ATR stop and R-multiple target (research only).

    Chan 2013 prototype fades to BB mid; here we use symmetric R geometry so payoffs
    stay comparable to other research entries. Costs must be checked by the replay path.
    """
    if pd.isna(row.get("bb_lower")) or pd.isna(row.get("bb_upper")):
        return None
    close = float(row["close"])
    lo, up = float(row["bb_lower"]), float(row["bb_upper"])
    if close < lo:
        return _geometry(row, cfg, "buy", "chan_bb_fade_long")
    if close > up:
        return _geometry(row, cfg, "sell", "chan_bb_fade_short")
    return None


def sig_chan_momentum(row: pd.Series, cfg: dict[str, Any]) -> Optional[Signal]:
    """Chan-style short-horizon momentum: price vs EMA and 3-bar pip return agree."""
    if pd.isna(row.get("close_ema_pips")):
        return None
    try:
        cep = float(row["close_ema_pips"])
        ret3 = float(row.get("ret3_pips") or 0.0)
    except (TypeError, ValueError):
        return None
    if cep > 0 and ret3 > 0 and _htf_agrees(row, "buy"):
        return _geometry(row, cfg, "buy", "chan_momentum_up")
    if cep < 0 and ret3 < 0 and _htf_agrees(row, "sell"):
        return _geometry(row, cfg, "sell", "chan_momentum_dn")
    return None


def sig_elliott_leg3(row: pd.Series, cfg: dict[str, Any]) -> Optional[Signal]:
    """Frost/Prechter proxy: third/fifth leg of alternating swings with HTF bias."""
    try:
        phase = int(row.get("elliott_phase") or 0)
    except (TypeError, ValueError):
        return None
    if phase not in {3, 5}:
        return None
    if float(row.get("elliott_up_leg") or 0) >= 0.5 and _htf_agrees(row, "buy"):
        return _geometry(row, cfg, "buy", f"elliott_leg{phase}_up")
    if float(row.get("elliott_up_leg") or 0) < 0.5 and _htf_agrees(row, "sell"):
        return _geometry(row, cfg, "sell", f"elliott_leg{phase}_dn")
    return None


def sig_gann_turn(row: pd.Series, cfg: dict[str, Any]) -> Optional[Signal]:
    """Gann proxy: cycle boundary plus angle sign agrees with HTF."""
    if float(row.get("gann_cycle_hit") or 0.0) < 0.5:
        return None
    try:
        angle = float(row.get("gann_angle_z") or 0.0)
    except (TypeError, ValueError):
        return None
    if angle > 0 and _htf_agrees(row, "buy"):
        return _geometry(row, cfg, "buy", "gann_cycle_turn_up")
    if angle < 0 and _htf_agrees(row, "sell"):
        return _geometry(row, cfg, "sell", "gann_cycle_turn_dn")
    return None


def sig_six_book_stack(row: pd.Series, cfg: dict[str, Any]) -> Optional[Signal]:
    """Zuckerman-style ensemble: trade only when many book proxies agree (research_proxy)."""
    from aegis.research.johnson import johnson_allows
    from aegis.research.six_book import stack_votes

    if not johnson_allows(row):
        return None
    min_votes = int(cfg.get("stack_min_votes", 3) or 3)
    buy_v = stack_votes(row, "buy")
    sell_v = stack_votes(row, "sell")
    if buy_v >= min_votes and buy_v > sell_v:
        return _geometry(row, cfg, "buy", f"six_book_stack_{buy_v}")
    if sell_v >= min_votes and sell_v > buy_v:
        return _geometry(row, cfg, "sell", f"six_book_stack_{sell_v}")
    return None


ENTRY_SIGNALS = {
    "structure_breakout": sig_structure_breakout,
    "failed_break": sig_failed_break,
    "level_retest": sig_level_retest,
    "chan_bb_fade": sig_chan_bb_fade,
    "chan_momentum": sig_chan_momentum,
    "elliott_leg3": sig_elliott_leg3,
    "gann_turn": sig_gann_turn,
    "six_book_stack": sig_six_book_stack,
}


def structure_prepare(df: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame:
    """Standard indicators plus confirmed-pivot and completed-HTF columns."""
    from aegis.research.entry_features import add_entry_features
    from aegis.strategy import prepare

    return add_entry_features(prepare(df, {**cfg, "signal_mode": "firehose"}))


def chan_prepare(df: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame:
    """BB columns from prepare(); no extra lookahead."""
    from aegis.strategy import prepare

    return prepare(df, {**cfg, "signal_mode": "firehose"})


def momentum_prepare(df: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame:
    return chan_prepare(df, cfg)


def elliott_prepare(df: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame:
    from aegis.research.entry_features import add_entry_features
    from aegis.research.elliott import add_elliott_legs

    return add_elliott_legs(add_entry_features(chan_prepare(df, cfg)))


def gann_prepare(df: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame:
    from aegis.research.entry_features import add_entry_features
    from aegis.research.gann import add_gann_columns

    return add_gann_columns(add_entry_features(chan_prepare(df, cfg)))


def entry_families() -> dict[str, tuple[Any, Any]]:
    """All research entry candidates as (prepare_fn, signal_fn).

    Includes the pullback-continuation entry from `aegis.research.entries` so every
    challenger is measured in one comparable table instead of two parallel paths.
    """
    from aegis.research.entries import prepare_pullback, sig_pullback_retest
    from aegis.research.six_book import prepare_six_book

    structure_names = {
        "structure_breakout",
        "failed_break",
        "level_retest",
    }
    families: dict[str, tuple[Any, Any]] = {
        name: (structure_prepare, fn) for name, fn in ENTRY_SIGNALS.items() if name in structure_names
    }
    families["chan_bb_fade"] = (chan_prepare, sig_chan_bb_fade)
    families["chan_momentum"] = (momentum_prepare, sig_chan_momentum)
    families["elliott_leg3"] = (elliott_prepare, sig_elliott_leg3)
    families["gann_turn"] = (gann_prepare, sig_gann_turn)
    families["six_book_stack"] = (prepare_six_book, sig_six_book_stack)
    families["pullback_retest"] = (prepare_pullback, sig_pullback_retest)
    return families
