"""Shared, deterministic video-style signal and geometry primitives.

This module is intentionally neutral: research simulation and the governed
Firehose runtime both consume it, while it has no broker or order path.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class VideoStyleConfig:
    starting_equity: float = 100.0
    risk_per_trade: float = 0.15
    stop_r: float = 0.5
    reward_to_risk: float = 3.0
    scale_after_r: float = 0.75
    max_layers: int = 4
    spread_cost: float = 0.0
    slippage_cost: float = 0.0
    commission_cost: float = 0.0
    max_hold_bars: int = 0
    max_hold_s: int = 45

    def __post_init__(self) -> None:
        if self.starting_equity <= 0 or self.risk_per_trade <= 0:
            raise ValueError("starting_equity and risk_per_trade must be positive")
        if self.stop_r <= 0 or self.reward_to_risk <= 0 or self.scale_after_r <= 0:
            raise ValueError("R parameters must be positive")
        if self.max_layers < 1 or self.max_hold_bars < 0 or self.max_hold_s <= 0:
            raise ValueError(
                "max_layers must be positive, max_hold_bars non-negative, "
                "and max_hold_s positive"
            )
        if min(self.spread_cost, self.slippage_cost, self.commission_cost) < 0:
            raise ValueError("costs must be non-negative")


@dataclass(frozen=True)
class VideoStyleSignal:
    """Completed-bar breakout intent shared by research and runtime Firehose."""

    symbol: str
    side: str
    signal_time: Any
    breakout_price: float
    risk_distance: float


_REQUIRED_COLUMNS = {"time", "open", "high", "low", "close"}


def _normalise_bars(symbol: str, frame: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame):
        raise ValueError(f"{symbol}: bars must be a pandas DataFrame")
    missing = _REQUIRED_COLUMNS.difference(frame.columns)
    if missing:
        raise ValueError(f"{symbol}: required columns missing: {sorted(missing)}")
    if frame.empty:
        return frame.copy()
    out = frame.loc[:, sorted(_REQUIRED_COLUMNS)].copy()
    for column in ("open", "high", "low", "close"):
        out[column] = pd.to_numeric(out[column], errors="raise")
    if out[["open", "high", "low", "close"]].isna().any().any():
        raise ValueError(f"{symbol}: price columns contain nulls")
    if (out["high"] < out[["open", "close"]].max(axis=1)).any():
        raise ValueError(f"{symbol}: high is below open or close")
    if (out["low"] > out[["open", "close"]].min(axis=1)).any():
        raise ValueError(f"{symbol}: low is above open or close")
    return out.sort_values("time", kind="stable").reset_index(drop=True)


def video_style_signal(
    bars: pd.DataFrame,
    *,
    symbol: str,
) -> VideoStyleSignal | None:
    """Return a next-bar breakout signal without looking into the entry bar."""
    symbol = str(symbol or "").strip().upper()
    if not symbol:
        raise ValueError("symbol must not be empty")
    frame = _normalise_bars(symbol, bars)
    if len(frame) < 2:
        return None
    prior = frame.iloc[-2]
    latest = frame.iloc[-1]
    latest_close = float(latest["close"])
    prior_high = float(prior["high"])
    prior_low = float(prior["low"])
    if latest_close > prior_high:
        side = "buy"
    elif latest_close < prior_low:
        side = "sell"
    else:
        return None
    risk_distance = float(latest["high"]) - float(latest["low"])
    if risk_distance <= 0:
        return None
    return VideoStyleSignal(
        symbol=symbol,
        side=side,
        signal_time=latest["time"],
        breakout_price=latest_close,
        risk_distance=risk_distance,
    )


def video_style_geometry(
    signal: VideoStyleSignal,
    *,
    entry_price: float,
    cfg: VideoStyleConfig,
) -> tuple[float, float]:
    """Build the tight stop / larger target used by both paths."""
    entry = float(entry_price)
    stop_distance = float(cfg.stop_r) * float(signal.risk_distance)
    direction = 1.0 if signal.side == "buy" else -1.0
    stop = entry - direction * stop_distance
    target = entry + direction * float(cfg.reward_to_risk) * stop_distance
    return stop, target


def video_style_scale_allowed(
    *,
    side: str,
    last_entry_price: float,
    current_price: float,
    stop_distance: float,
    unrealized_pnl: float,
    current_layers: int,
    max_layers: int,
    scale_after_r: float,
) -> bool:
    """Allow a same-thesis clip only after profitable favorable movement."""
    if current_layers < 1 or current_layers >= int(max_layers):
        return False
    if float(unrealized_pnl) < 0 or float(stop_distance) <= 0:
        return False
    move = float(current_price) - float(last_entry_price)
    if str(side).lower() == "sell":
        move = -move
    elif str(side).lower() != "buy":
        return False
    return move >= float(scale_after_r) * float(stop_distance)
