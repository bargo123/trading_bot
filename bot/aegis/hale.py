"""Heikin-Ashi Level Exhaustion (HALE) signal-only features."""
from __future__ import annotations

from typing import Any, Optional

import numpy as np
import pandas as pd

from aegis.cafb import _excluded_hour, _higher_timeframe_context
from aegis.features import enrich_all
from aegis.strategy import Signal, in_session


def heikin_ashi(df: pd.DataFrame) -> pd.DataFrame:
    """Return canonical Heikin-Ashi values without replacing executable OHLC."""
    ha_close = (df["open"] + df["high"] + df["low"] + df["close"]) / 4.0
    ha_open = pd.Series(np.nan, index=df.index, dtype=float)
    if len(df):
        ha_open.iloc[0] = (float(df["open"].iloc[0]) + float(df["close"].iloc[0])) / 2.0
        for i in range(1, len(df)):
            ha_open.iloc[i] = (float(ha_open.iloc[i - 1]) + float(ha_close.iloc[i - 1])) / 2.0
    ha_high = pd.concat([df["high"], ha_open, ha_close], axis=1).max(axis=1)
    ha_low = pd.concat([df["low"], ha_open, ha_close], axis=1).min(axis=1)
    return pd.DataFrame(
        {
            "hale_ha_open": ha_open,
            "hale_ha_high": ha_high,
            "hale_ha_low": ha_low,
            "hale_ha_close": ha_close,
        },
        index=df.index,
    )


def prepare_hale(df: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame:
    """Build HALE signal features with levels frozen before the trigger."""
    frame = enrich_all(df, cfg).sort_values("time").reset_index(drop=True)
    frame["time"] = pd.to_datetime(frame["time"], utc=True)
    ha = heikin_ashi(frame)
    frame = pd.concat([frame, ha], axis=1)
    frame["hale_ha_body"] = (frame["hale_ha_close"] - frame["hale_ha_open"]).abs()
    frame["hale_ha_color"] = np.where(
        frame["hale_ha_close"] > frame["hale_ha_open"],
        1,
        np.where(frame["hale_ha_close"] < frame["hale_ha_open"], -1, 0),
    )

    day = frame["time"].dt.floor("D")
    daily = (
        frame.assign(_hale_day=day)
        .groupby("_hale_day", sort=True)
        .agg(_high=("high", "max"), _low=("low", "min"))
    )
    previous = daily.shift(1)
    frame["hale_prev_day_high"] = day.map(previous["_high"])
    frame["hale_prev_day_low"] = day.map(previous["_low"])
    frame["hale_session_high_prior"] = frame.groupby(day, sort=False)["high"].transform(
        lambda values: values.expanding().max().shift(1)
    )
    frame["hale_session_low_prior"] = frame.groupby(day, sort=False)["low"].transform(
        lambda values: values.expanding().min().shift(1)
    )

    impulse_bars = max(3, int(cfg.get("hale_impulse_bars", 3)))
    frame["hale_session_high_before_impulse"] = frame.groupby(day, sort=False)["high"].transform(
        lambda values: values.expanding().max().shift(impulse_bars + 1)
    )
    frame["hale_session_low_before_impulse"] = frame.groupby(day, sort=False)["low"].transform(
        lambda values: values.expanding().min().shift(impulse_bars + 1)
    )
    grid = max(float(cfg.get("hale_round_grid", 0.005)), np.finfo(float).eps)
    frame["hale_round_level"] = (frame["close"].shift(1) / grid).round() * grid

    colors = frame["hale_ha_color"]
    prior_colors = pd.concat([colors.shift(i) for i in range(1, impulse_bars + 1)], axis=1)
    frame["hale_impulse_up"] = prior_colors.eq(1).all(axis=1)
    frame["hale_impulse_down"] = prior_colors.eq(-1).all(axis=1)
    frame["hale_impulse_displacement"] = (
        frame["close"].shift(1) - frame["close"].shift(impulse_bars)
    ).abs()
    earlier_bodies = pd.concat(
        [frame["hale_ha_body"].shift(i) for i in range(2, impulse_bars + 1)],
        axis=1,
    )
    frame["hale_impulse_body_median"] = earlier_bodies.median(axis=1)
    frame["hale_last_body"] = frame["hale_ha_body"].shift(1)
    frame["hale_impulse_high"] = frame["high"].rolling(impulse_bars).max().shift(1)
    frame["hale_impulse_low"] = frame["low"].rolling(impulse_bars).min().shift(1)
    frame["hale_prev_color"] = colors.shift(1)
    pullback_bars = max(1, int(cfg.get("hale_pullback_bars", 2)))
    pullback_colors = pd.concat([colors.shift(i) for i in range(1, pullback_bars + 1)], axis=1)
    frame["hale_pullback_up"] = pullback_colors.eq(1).all(axis=1)
    frame["hale_pullback_down"] = pullback_colors.eq(-1).all(axis=1)
    frame["hale_pullback_high"] = frame["high"].rolling(pullback_bars).max().shift(1)
    frame["hale_pullback_low"] = frame["low"].rolling(pullback_bars).min().shift(1)

    up_levels = pd.concat(
        [
            frame["hale_prev_day_high"],
            frame["hale_session_high_before_impulse"],
            frame["hale_round_level"],
        ],
        axis=1,
    )
    down_levels = pd.concat(
        [
            frame["hale_prev_day_low"],
            frame["hale_session_low_before_impulse"],
            frame["hale_round_level"],
        ],
        axis=1,
    )
    frame["hale_level_distance_up"] = up_levels.sub(frame["hale_impulse_high"], axis=0).abs().min(axis=1)
    frame["hale_level_distance_down"] = down_levels.sub(frame["hale_impulse_low"], axis=0).abs().min(axis=1)

    context = _higher_timeframe_context(frame, cfg)
    frame = pd.merge_asof(
        frame.sort_values("time"),
        context.sort_values("time"),
        on="time",
        direction="backward",
    )
    return frame.reset_index(drop=True)


def _cost_ok_for_sized_trade(
    close: float,
    stop_distance: float,
    reward_distance: float,
    cfg: dict[str, Any],
) -> bool:
    """Conservatively gate rewards against variable and fixed round-trip costs."""
    if close <= 0 or stop_distance <= 0 or reward_distance <= 0:
        return False
    equity = max(0.0, float(cfg.get("starting_equity", 100.0)))
    risk_money = equity * max(0.0, float(cfg.get("risk_percent", 1.0))) / 100.0
    risk_units = risk_money / stop_distance
    leverage_units = equity * max(0.0, float(cfg.get("max_gross_leverage", 30.0))) / close
    units = min(risk_units, leverage_units)
    step = max(0.0, float(cfg.get("unit_step", 0.0)))
    if step > 0:
        units = np.floor(units / step) * step
    if units <= 0 or units < max(0.0, float(cfg.get("min_units", 0.0))):
        return False
    one_way_bps = (
        float(cfg.get("spread_bps", 1.0))
        + float(cfg.get("slippage_bps", 0.5))
        + float(cfg.get("commission_bps", 0.0))
    )
    variable_cost = units * close * one_way_bps / 10000.0 * 2.0
    fixed_cost = max(0.0, float(cfg.get("commission_round_trip_usd", 0.0)))
    gross_reward = units * reward_distance
    return gross_reward > (variable_cost + fixed_cost) * max(0.0, float(cfg.get("cost_buffer", 1.5)))


def _signal_time_ok(row: pd.Series, cfg: dict[str, Any]) -> bool:
    ts = pd.Timestamp(row["time"])
    return in_session(ts, cfg.get("session_start_utc"), cfg.get("session_end_utc")) and not _excluded_hour(ts, cfg)


def sig_hale_fade(row: pd.Series, cfg: dict[str, Any]) -> Optional[Signal]:
    """Fade a contracted HA impulse only at an objective level and range regime."""
    required = [
        "time",
        "close",
        "atr",
        "cafb_htf_regime",
        "hale_ha_color",
        "hale_prev_color",
        "hale_impulse_displacement",
        "hale_impulse_body_median",
        "hale_last_body",
        "hale_impulse_high",
        "hale_impulse_low",
    ]
    if any(pd.isna(row.get(key)) for key in required) or not _signal_time_ok(row, cfg):
        return None
    if str(row["cafb_htf_regime"]) != "range":
        return None
    close = float(row["close"])
    atr_v = float(row["atr"])
    median_body = float(row["hale_impulse_body_median"])
    if close <= 0 or atr_v <= 0 or median_body <= 0:
        return None
    if float(row["hale_impulse_displacement"]) < max(0.0, float(cfg.get("hale_impulse_atr", 1.0))) * atr_v:
        return None
    if float(row["hale_last_body"]) > max(0.0, float(cfg.get("hale_contraction_ratio", 0.6))) * median_body:
        return None

    color = int(row["hale_ha_color"])
    previous = int(row["hale_prev_color"])
    level_limit = max(0.0, float(cfg.get("hale_level_atr", 0.5))) * atr_v
    stop_buffer = max(0.0, float(cfg.get("hale_stop_buffer_atr", 0.15))) * atr_v
    target_r = max(0.01, float(cfg.get("hale_target_r", 0.7)))
    ts = pd.Timestamp(row["time"])

    if bool(row.get("hale_impulse_up", False)) and previous == 1 and color == -1:
        level_distance = row.get("hale_level_distance_up")
        if pd.isna(level_distance) or float(level_distance) > level_limit:
            return None
        sl = max(close, float(row["hale_impulse_high"])) + stop_buffer
        risk = sl - close
        reward = target_r * risk
        if not _cost_ok_for_sized_trade(close, risk, reward, cfg):
            return None
        return Signal("sell", "hale_fade", close, sl, close - reward, None, ts, "hale_fade_short")

    if bool(row.get("hale_impulse_down", False)) and previous == -1 and color == 1:
        level_distance = row.get("hale_level_distance_down")
        if pd.isna(level_distance) or float(level_distance) > level_limit:
            return None
        sl = min(close, float(row["hale_impulse_low"])) - stop_buffer
        risk = close - sl
        reward = target_r * risk
        if not _cost_ok_for_sized_trade(close, risk, reward, cfg):
            return None
        return Signal("buy", "hale_fade", close, sl, close + reward, None, ts, "hale_fade_long")
    return None


def sig_hale_pullback(row: pd.Series, cfg: dict[str, Any]) -> Optional[Signal]:
    """Join a lagged HTF trend after an opposite-color HA pullback resumes."""
    required = [
        "time",
        "close",
        "ema_20",
        "atr",
        "cafb_htf_regime",
        "hale_ha_color",
        "hale_prev_color",
        "hale_pullback_high",
        "hale_pullback_low",
    ]
    if any(pd.isna(row.get(key)) for key in required) or not _signal_time_ok(row, cfg):
        return None
    close = float(row["close"])
    atr_v = float(row["atr"])
    if close <= 0 or atr_v <= 0:
        return None
    if abs(close - float(row["ema_20"])) > max(0.0, float(cfg.get("hale_pullback_near_atr", 0.75))) * atr_v:
        return None
    regime = str(row["cafb_htf_regime"])
    color = int(row["hale_ha_color"])
    previous = int(row["hale_prev_color"])
    stop_buffer = max(0.0, float(cfg.get("hale_stop_buffer_atr", 0.15))) * atr_v
    target_r = max(0.01, float(cfg.get("hale_target_r", 0.7)))
    ts = pd.Timestamp(row["time"])

    if regime == "trend_up" and bool(row.get("hale_pullback_down", False)) and previous == -1 and color == 1:
        sl = min(close, float(row["hale_pullback_low"])) - stop_buffer
        risk = close - sl
        reward = target_r * risk
        if not _cost_ok_for_sized_trade(close, risk, reward, cfg):
            return None
        return Signal(
            "buy",
            "hale_pullback",
            close,
            sl,
            close + reward,
            None,
            ts,
            "hale_pullback_long",
        )

    if regime == "trend_down" and bool(row.get("hale_pullback_up", False)) and previous == 1 and color == -1:
        sl = max(close, float(row["hale_pullback_high"])) + stop_buffer
        risk = sl - close
        reward = target_r * risk
        if not _cost_ok_for_sized_trade(close, risk, reward, cfg):
            return None
        return Signal(
            "sell",
            "hale_pullback",
            close,
            sl,
            close - reward,
            None,
            ts,
            "hale_pullback_short",
        )
    return None
