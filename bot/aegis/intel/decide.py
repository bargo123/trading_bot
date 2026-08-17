"""Meta-decision around CORE_STRATEGY_V1. Does not change sig_firehose math.

CORE says TRADE. This layer says ACCEPT / REJECT / WAIT.
WAIT is treated as skip-this-bar in the M1 backtest (no limit-entry engine yet).
"""
from __future__ import annotations

from typing import Any, Literal

import pandas as pd

from aegis.intel.score import quality_score
from aegis.intel.similarity import similarity_allows

Decision = Literal["accept", "reject", "wait"]

# Last intel call (reset at the start of each decision). Paper runner journals this.
LAST: dict[str, Any] = {
    "decision": "accept",
    "quality": None,
    "reason": "",
    "side": "",
}


def reset_last() -> None:
    LAST.update({"decision": "accept", "quality": None, "reason": "", "side": ""})


def last_intel() -> dict[str, Any]:
    return dict(LAST)


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


def intel_decision(row: pd.Series, cfg: dict[str, Any], side: str) -> Decision:
    reset_last()
    side = str(side or "").lower()
    LAST["side"] = side
    if not bool(cfg.get("intel_enabled", False)):
        LAST["decision"] = "accept"
        LAST["reason"] = "intel_off"
        return "accept"

    q = quality_score(row, cfg, side)
    LAST["quality"] = q

    def _done(decision: Decision, reason: str) -> Decision:
        LAST["decision"] = decision
        LAST["reason"] = reason
        return decision

    min_q = float(cfg.get("intel_quality_min", 0.0) or 0.0)
    if min_q > 0 and q < min_q:
        return _done("reject", f"quality_{q:.1f}<{min_q:.0f}")

    if bool(cfg.get("intel_skip_incomplete", False)):
        for key in ("rsi", "adx", "kaufman_er", "range_loc"):
            if _num(row, key) is None:
                return _done("wait", "incomplete")

    if bool(cfg.get("intel_skip_extreme_doji", False)) and _flag(row, "volman_doji"):
        loc = _num(row, "range_loc")
        if loc is not None:
            if side == "buy" and loc >= 0.90:
                return _done("reject", "extreme_doji_buy")
            if side == "sell" and loc <= 0.10:
                return _done("reject", "extreme_doji_sell")

    # Kaufman dead tape at the Damir/Brooks floor — SELL only. Not a global ER gate.
    if bool(cfg.get("intel_skip_floor_chop_sell", False)) and side == "sell":
        er = _num(row, "kaufman_er")
        loc = _num(row, "range_loc")
        er_max = float(cfg.get("intel_floor_chop_er", 0.05) or 0.05)
        loc_max = float(cfg.get("intel_floor_chop_loc", 0.15) or 0.15)
        if er is not None and loc is not None and er < er_max and loc <= loc_max:
            return _done("reject", "floor_chop_sell")

    min_er = float(cfg.get("intel_min_er", 0.0) or 0.0)
    if min_er > 0:
        er = _num(row, "kaufman_er")
        if er is None or er < min_er:
            return _done("reject", "er")

    if bool(cfg.get("intel_skip_doji", False)) and _flag(row, "volman_doji"):
        return _done("wait", "doji")

    # Tighter than require-body: Volman doji AND body against CORE EMA-side spray.
    if bool(cfg.get("intel_skip_doji_against", False)) and _flag(row, "volman_doji"):
        o, c = _num(row, "open"), _num(row, "close")
        if o is not None and c is not None:
            if side == "buy" and c < o:
                return _done("reject", "doji_against")
            if side == "sell" and c > o:
                return _done("reject", "doji_against")

    if bool(cfg.get("intel_skip_ceiling_doji_buy", False)) and side == "buy":
        loc = _num(row, "range_loc")
        if _flag(row, "volman_doji") and loc is not None and loc >= 0.90:
            return _done("reject", "ceiling_doji_buy")

    # Brooks: close already through the prior-range ceiling. BUY only.
    # Hydra after stretched_doji_buy: 09:47 doji skipped, 09:48 non-doji loc>1 printed.
    if bool(cfg.get("intel_skip_above_range_buy", False)) and side == "buy":
        loc = _num(row, "range_loc")
        if loc is not None and loc > 1.0:
            return _done("reject", "above_range_buy")

    # Ceiling stretch BUY without requiring a doji. Not stretched_doji_buy / ceiling-doji-buy.
    if bool(cfg.get("intel_skip_stretched_buy", False)) and side == "buy":
        loc = _num(row, "range_loc")
        ema_pips = _num(row, "close_ema_pips")
        loc_min = float(cfg.get("intel_stretched_buy_loc", 0.85) or 0.85)
        ema_min = float(cfg.get("intel_stretched_buy_ema_pips", 1.0) or 1.0)
        if loc is not None and ema_pips is not None and loc >= loc_min and ema_pips >= ema_min:
            return _done("reject", "stretched_buy")

    # Opposite of rejected floor-chop (low ER): SELL at the floor after a directional run.
    # Not stretched_sell (no EMA pips). Not wrong_edge (needs high ER). Not loc<0.
    if bool(cfg.get("intel_skip_floor_run_sell", False)) and side == "sell":
        loc = _num(row, "range_loc")
        er = _num(row, "kaufman_er")
        loc_max = float(cfg.get("intel_floor_run_loc", 0.15) or 0.15)
        er_min = float(cfg.get("intel_floor_run_er", 0.40) or 0.40)
        if loc is not None and er is not None and loc <= loc_max and er >= er_min:
            return _done("reject", "floor_run_sell")

    # Brooks: close already through the prior-range floor. Not floor-chop (ER gate).
    if bool(cfg.get("intel_skip_below_range_sell", False)) and side == "sell":
        loc = _num(row, "range_loc")
        if loc is not None and loc < 0.0:
            return _done("reject", "below_range_sell")

    # NY hour 19 sells. Not london_hour_12. Not stretched_sell.
    if bool(cfg.get("intel_skip_ny_hour_19_sell", False)) and side == "sell":
        ts = row.get("time")
        hour = None
        if ts is not None:
            t = pd.Timestamp(ts)
            if getattr(t, "tzinfo", None) is not None:
                t = t.tz_convert("UTC")
            hour = int(t.hour)
        if hour == 19:
            return _done("reject", "ny_hour_19_sell")

    # Buy doji at the ceiling, stretched off EMA. Not loc>=0.90 ceiling-doji-buy.
    if bool(cfg.get("intel_skip_stretched_doji_buy", False)) and side == "buy":
        loc = _num(row, "range_loc")
        ema_pips = _num(row, "close_ema_pips")
        loc_min = float(cfg.get("intel_stretched_doji_loc", 0.85) or 0.85)
        ema_min = float(cfg.get("intel_stretched_doji_ema_pips", 1.0) or 1.0)
        if (
            _flag(row, "volman_doji")
            and loc is not None
            and ema_pips is not None
            and loc >= loc_min
            and ema_pips >= ema_min
        ):
            return _done("reject", "stretched_doji_buy")

    if bool(cfg.get("intel_skip_chop_doji", False)) and _flag(row, "volman_doji"):
        er = _num(row, "kaufman_er")
        if er is None or er < float(cfg.get("intel_chop_doji_er", 0.20) or 0.20):
            return _done("wait", "chop_doji")

    if bool(cfg.get("intel_skip_barbwire", False)) and _flag(row, "brooks_barbwire"):
        return _done("wait", "barbwire")

    # Brooks overlapping/barbwire — SELL only. Tighter than global barbwire WAIT.
    if bool(cfg.get("intel_skip_barbwire_sell", False)) and side == "sell":
        if _flag(row, "brooks_barbwire"):
            return _done("reject", "barbwire_sell")

    # Brooks overlapping/barbwire — BUY only. Mirror of live barbwire_sell. Not global WAIT.
    if bool(cfg.get("intel_skip_barbwire_buy", False)) and side == "buy":
        if _flag(row, "brooks_barbwire"):
            return _done("reject", "barbwire_buy")

    # Mirror of stretched_doji_buy: SELL already >=3 pips through EMA.
    if bool(cfg.get("intel_skip_stretched_sell", False)) and side == "sell":
        ema_pips = _num(row, "close_ema_pips")
        ema_max = float(cfg.get("intel_stretched_sell_ema_pips", -3.0) or -3.0)
        if ema_pips is not None and ema_pips <= ema_max:
            return _done("reject", "stretched_sell")

    if bool(cfg.get("intel_skip_range_mid", False)):
        loc = _num(row, "range_loc")
        if _flag(row, "brooks_in_range") and loc is not None and 0.33 < loc < 0.67:
            return _done("wait", "range_mid")

    # Brooks range middle — SELL only. Tighter than global range_mid WAIT.
    if bool(cfg.get("intel_skip_range_mid_sell", False)) and side == "sell":
        loc = _num(row, "range_loc")
        if _flag(row, "brooks_in_range") and loc is not None and 0.33 < loc < 0.67:
            return _done("reject", "range_mid_sell")

    # Don't sell after a 3-bar dump (chase). Not stretched_sell (EMA pips).
    if bool(cfg.get("intel_skip_ret3_chase_sell", False)) and side == "sell":
        ret3 = _num(row, "ret3_pips")
        thresh = float(cfg.get("intel_ret3_chase_pips", -1.5) or -1.5)
        if ret3 is not None and ret3 <= thresh:
            return _done("reject", "ret3_chase_sell")

    # London lunch hour sells. Not london_dead_er (that needs ER<0.10).
    if bool(cfg.get("intel_skip_london_hour_12_sell", False)) and side == "sell":
        ts = row.get("time")
        hour = None
        if ts is not None:
            t = pd.Timestamp(ts)
            if getattr(t, "tzinfo", None) is not None:
                t = t.tz_convert("UTC")
            hour = int(t.hour)
        if hour == 12:
            return _done("reject", "london_hour_12_sell")

    # London open BUY chase: hour 9, impulse with, 3-bar rally. Not loc>1, not doji, not EMA stretch.
    if bool(cfg.get("intel_skip_london_open_chase_buy", False)) and side == "buy":
        ts = row.get("time")
        hour = None
        if ts is not None:
            t = pd.Timestamp(ts)
            if getattr(t, "tzinfo", None) is not None:
                t = t.tz_convert("UTC")
            hour = int(t.hour)
        ret3 = _num(row, "ret3_pips")
        ret_min = float(cfg.get("intel_london_open_ret3", 1.0) or 1.0)
        if hour == 9 and _flag(row, "impulse_green") and ret3 is not None and ret3 >= ret_min:
            return _done("reject", "london_open_chase_buy")

    # Late NY / Asia hour 21 sells. Not skip-NaN. Not hour-12 / hour-19.
    if bool(cfg.get("intel_skip_hour_21_sell", False)) and side == "sell":
        ts = row.get("time")
        hour = None
        if ts is not None:
            t = pd.Timestamp(ts)
            if getattr(t, "tzinfo", None) is not None:
                t = t.tz_convert("UTC")
            hour = int(t.hour)
        if hour == 21:
            return _done("reject", "hour_21_sell")

    # Asia hour 4 sells. Not loc<0 / floor_run / rsi_ext widen. Not hour-12/19/21.
    if bool(cfg.get("intel_skip_asia_hour_4_sell", False)) and side == "sell":
        ts = row.get("time")
        hour = None
        if ts is not None:
            t = pd.Timestamp(ts)
            if getattr(t, "tzinfo", None) is not None:
                t = t.tz_convert("UTC")
            hour = int(t.hour)
        if hour == 4:
            return _done("reject", "asia_hour_4_sell")

    # Asia midnight dead-tape SELL. Not hour-4 / hour-21 / london_dead_er (7/8/11/12).
    if bool(cfg.get("intel_skip_hour_0_dead_er_sell", False)) and side == "sell":
        ts = row.get("time")
        hour = None
        if ts is not None:
            t = pd.Timestamp(ts)
            if getattr(t, "tzinfo", None) is not None:
                t = t.tz_convert("UTC")
            hour = int(t.hour)
        er = _num(row, "kaufman_er")
        er_max = float(cfg.get("intel_hour_0_dead_er", 0.10) or 0.10)
        if hour == 0 and er is not None and er < er_max:
            return _done("reject", "hour_0_dead_er_sell")

    # Asia hour 5 BUY already stretched off EMA, still in range. Not loc>1, not late_buy RSI 65–70.
    if bool(cfg.get("intel_skip_asia_hour_5_stretch_buy", False)) and side == "buy":
        ts = row.get("time")
        hour = None
        if ts is not None:
            t = pd.Timestamp(ts)
            if getattr(t, "tzinfo", None) is not None:
                t = t.tz_convert("UTC")
            hour = int(t.hour)
        loc = _num(row, "range_loc")
        ema_pips = _num(row, "close_ema_pips")
        ema_min = float(cfg.get("intel_hour_5_ema_pips", 2.0) or 2.0)
        loc_min = float(cfg.get("intel_hour_5_loc", 0.80) or 0.80)
        if (
            hour == 5
            and loc is not None
            and ema_pips is not None
            and loc >= loc_min
            and loc <= 1.0
            and ema_pips >= ema_min
        ):
            return _done("reject", "asia_hour_5_stretch_buy")

    # Strong-ADX BUY already stretched off EMA. Not loc>1, not doji, not hour-9 chase.
    if bool(cfg.get("intel_skip_strong_adx_stretch_buy", False)) and side == "buy":
        adx = _num(row, "adx")
        ema_pips = _num(row, "close_ema_pips")
        adx_min = float(cfg.get("intel_strong_adx", 35.0) or 35.0)
        ema_min = float(cfg.get("intel_strong_adx_ema_pips", 1.2) or 1.2)
        if adx is not None and ema_pips is not None and adx >= adx_min and ema_pips >= ema_min:
            return _done("reject", "strong_adx_stretch_buy")

    if bool(cfg.get("intel_skip_wrong_edge", False)) and _flag(row, "brooks_in_range"):
        loc = _num(row, "range_loc")
        buy_loc = float(cfg.get("intel_wrong_buy_loc", 0.67) or 0.67)
        sell_loc = float(cfg.get("intel_wrong_sell_loc", 0.33) or 0.33)
        if loc is not None:
            if side == "buy" and loc >= buy_loc:
                return _done("reject", "wrong_edge_buy")
            if side == "sell" and loc <= sell_loc:
                return _done("reject", "wrong_edge_sell")

    # Wilder ADX<~22 = range. Brooks/Damir: do not spray the range floor/ceiling
    # as a breakout. Narrower than intel_skip_wrong_edge (which lost path-dependent OOS).
    if bool(cfg.get("intel_skip_weak_adx_edge", False)) and _flag(row, "brooks_in_range"):
        adx = _num(row, "adx")
        loc = _num(row, "range_loc")
        thresh = float(cfg.get("intel_weak_adx", 22.0) or 22.0)
        if adx is not None and loc is not None and adx < thresh:
            if side == "buy" and loc >= 0.90:
                return _done("reject", "weak_adx_edge_buy")
            if side == "sell" and loc <= 0.10:
                return _done("reject", "weak_adx_edge_sell")

    if bool(cfg.get("intel_skip_impulse_against", False)):
        if side == "buy" and _flag(row, "impulse_red"):
            return _done("reject", "impulse_against")
        if side == "sell" and _flag(row, "impulse_green"):
            return _done("reject", "impulse_against")

    max_streak = int(cfg.get("intel_max_ema_streak", 0) or 0)
    if max_streak > 0:
        streak = _num(row, "ema_side_streak")
        if streak is not None and streak > max_streak:
            return _done("reject", "ema_streak")

    max_expand = float(cfg.get("intel_max_atr_expand", 0.0) or 0.0)
    if max_expand > 0:
        exp = _num(row, "atr_expand")
        if exp is not None and exp > max_expand:
            return _done("wait", "atr_expand")

    if bool(cfg.get("intel_skip_rsi_ext", False)):
        rsi = _num(row, "rsi")
        buy_max = float(cfg.get("intel_rsi_buy_max", 70.0) or 70.0)
        sell_min = float(cfg.get("intel_rsi_sell_min", 30.0) or 30.0)
        if rsi is not None:
            if side == "buy" and rsi >= buy_max:
                return _done("reject", "rsi_ext_buy")
            if side == "sell" and rsi <= sell_min:
                return _done("reject", "rsi_ext_sell")

    # Remaining rsi_ext leftover: buy RSI 65–70 at the range ceiling, stretched off EMA.
    if bool(cfg.get("intel_skip_late_buy_chase", False)) and side == "buy":
        rsi = _num(row, "rsi")
        loc = _num(row, "range_loc")
        ema_pips = _num(row, "close_ema_pips")
        if (
            rsi is not None
            and loc is not None
            and ema_pips is not None
            and 65.0 <= rsi < 70.0
            and loc >= 0.85
            and ema_pips >= 1.5
        ):
            return _done("reject", "late_buy_chase")

    # Ceiling stretch BUY inside the prior range. Not doji, not RSI 65–70, not loc>1 hydra.
    if bool(cfg.get("intel_skip_ceiling_stretch_buy", False)) and side == "buy":
        loc = _num(row, "range_loc")
        ema_pips = _num(row, "close_ema_pips")
        loc_min = float(cfg.get("intel_ceiling_stretch_loc", 0.90) or 0.90)
        ema_min = float(cfg.get("intel_ceiling_stretch_ema_pips", 2.0) or 2.0)
        if (
            loc is not None
            and ema_pips is not None
            and loc_min <= loc <= 1.0
            and ema_pips >= ema_min
        ):
            return _done("reject", "ceiling_stretch_buy")

    # London afternoon dead-tape BUY. Not london_dead_er 7/8/11/12, not hour-0 sell.
    if bool(cfg.get("intel_skip_hour_13_dead_er_buy", False)) and side == "buy":
        ts = row.get("time")
        hour = None
        if ts is not None:
            t = pd.Timestamp(ts)
            if getattr(t, "tzinfo", None) is not None:
                t = t.tz_convert("UTC")
            hour = int(t.hour)
        er = _num(row, "kaufman_er")
        er_max = float(cfg.get("intel_hour_13_dead_er", 0.10) or 0.10)
        if hour == 13 and er is not None and er < er_max:
            return _done("reject", "hour_13_dead_er_buy")

    # NY hour-18 BUY stretched off EMA. Not strong_adx (no ADX floor), not hour-19 sell.
    if bool(cfg.get("intel_skip_ny_hour_18_stretch_buy", False)) and side == "buy":
        ts = row.get("time")
        hour = None
        if ts is not None:
            t = pd.Timestamp(ts)
            if getattr(t, "tzinfo", None) is not None:
                t = t.tz_convert("UTC")
            hour = int(t.hour)
        ema_pips = _num(row, "close_ema_pips")
        ema_min = float(cfg.get("intel_hour_18_ema_pips", 2.5) or 2.5)
        if hour == 18 and ema_pips is not None and ema_pips >= ema_min:
            return _done("reject", "ny_hour_18_stretch_buy")

    if bool(cfg.get("intel_skip_london_dead_er", False)):
        ts = row.get("time")
        er = _num(row, "kaufman_er")
        if ts is not None and er is not None and er < 0.10:
            t = pd.Timestamp(ts)
            if getattr(t, "tzinfo", None) is not None:
                t = t.tz_convert("UTC")
            if int(t.hour) in {7, 8, 11, 12}:
                return _done("reject", "london_dead_er")

    if bool(cfg.get("intel_require_body", False)):
        o, c = _num(row, "open"), _num(row, "close")
        if o is None or c is None:
            return _done("reject", "body")
        if side == "buy" and c < o:
            return _done("reject", "body")
        if side == "sell" and c > o:
            return _done("reject", "body")

    min_jan = float(cfg.get("intel_min_jansen", 0.0) or 0.0)
    if min_jan > 0:
        js = _num(row, "jansen_score")
        if js is None:
            return _done("reject", "jansen")
        if side == "buy" and js < min_jan:
            return _done("reject", "jansen")
        if side == "sell" and js > -min_jan:
            return _done("reject", "jansen")

    fri_h = int(cfg.get("intel_skip_friday_hour", -1) or -1)
    if fri_h >= 0:
        ts = row.get("time")
        if ts is not None:
            t = pd.Timestamp(ts)
            if getattr(t, "tzinfo", None) is not None:
                t = t.tz_convert("UTC")
            if int(t.weekday()) == 4 and int(t.hour) >= fri_h:
                return _done("wait", "friday")

    min_wr = float(cfg.get("intel_knn_min_wr", 0.0) or 0.0)
    if min_wr > 0:
        memory = cfg.get("_intel_memory") or []
        k = int(cfg.get("intel_knn_k", 15) or 15)
        if not similarity_allows(row, memory, k=k, min_wr=min_wr):
            return _done("reject", "knn")

    return _done("accept", "ok")


def intel_allows(row: pd.Series, cfg: dict[str, Any], side: str) -> bool:
    return intel_decision(row, cfg, side) == "accept"
