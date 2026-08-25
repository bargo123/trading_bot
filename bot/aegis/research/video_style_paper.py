"""Research-only, all-symbol video-style paper simulation.

This module operates on completed OHLC bars and a virtual ledger only.  It has
no broker or MT5 dependencies and deliberately records ``placed_orders`` as
false in every result.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

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
    """Build the tight stop / larger target geometry used by both paths."""
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


@dataclass(frozen=True)
class PaperTrade:
    symbol: str
    side: str
    layer: int
    entry_time: Any
    exit_time: Any
    entry_price: float
    exit_price: float
    quantity: float
    gross_pnl: float
    costs: float
    net_pnl: float
    r_multiple: float
    exit_reason: str


@dataclass(frozen=True)
class VideoStyleResult:
    placed_orders: bool
    starting_equity: float
    ending_equity: float
    max_drawdown: float
    wins: int
    losses: int
    trades: tuple[PaperTrade, ...]
    per_symbol: Mapping[str, Mapping[str, float | int]]


@dataclass
class _Layer:
    side: str
    layer: int
    entry_time: Any
    entry_price: float
    quantity: float
    risk_distance: float
    bars_held: int = 0


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


def _pnl(side: str, entry: float, exit_price: float, quantity: float) -> float:
    direction = 1.0 if side == "buy" else -1.0
    return quantity * direction * (exit_price - entry)


def _elapsed_seconds(start: Any, end: Any) -> float | None:
    """Return elapsed seconds for numeric or timestamp-like bar times."""
    if isinstance(start, (int, float)) and not isinstance(start, bool):
        if isinstance(end, (int, float)) and not isinstance(end, bool):
            return float(end) - float(start)
        return None
    try:
        start_ts = pd.Timestamp(start)
        end_ts = pd.Timestamp(end)
    except (TypeError, ValueError):
        return None
    if pd.isna(start_ts) or pd.isna(end_ts):
        return None
    try:
        return float((end_ts - start_ts).total_seconds())
    except (TypeError, ValueError):
        return None


def _close_layers(
    *,
    symbol: str,
    layers: list[_Layer],
    exit_time: Any,
    exit_price: float,
    reason: str,
    cfg: VideoStyleConfig,
) -> list[PaperTrade]:
    closed: list[PaperTrade] = []
    for layer in layers:
        gross = _pnl(layer.side, layer.entry_price, exit_price, layer.quantity)
        costs = layer.quantity * (
            2.0 * (cfg.spread_cost + cfg.slippage_cost) + cfg.commission_cost
        )
        net = gross - costs
        closed.append(
            PaperTrade(
                symbol=symbol,
                side=layer.side,
                layer=layer.layer,
                entry_time=layer.entry_time,
                exit_time=exit_time,
                entry_price=layer.entry_price,
                exit_price=exit_price,
                quantity=layer.quantity,
                gross_pnl=gross,
                costs=costs,
                net_pnl=net,
                r_multiple=net / cfg.risk_per_trade,
                exit_reason=reason,
            )
        )
    return closed


def _symbol_result(
    symbol: str,
    bars: pd.DataFrame,
    cfg: VideoStyleConfig,
    equity: float,
) -> tuple[list[PaperTrade], float, float]:
    if len(bars) < 3:
        return [], equity, 0.0
    layers: list[_Layer] = []
    pending_entry: tuple[str, float, Any] | None = None
    pending_add = False
    trades: list[PaperTrade] = []
    high_water = equity
    max_drawdown = 0.0

    for i in range(2, len(bars)):
        row = bars.iloc[i]

        if not layers and pending_entry is None:
            signal = video_style_signal(bars.iloc[:i], symbol=symbol)
            if signal is not None:
                pending_entry = (signal.side, signal.risk_distance, signal.signal_time)

        if pending_entry is not None and not layers:
            side, risk_distance, signal_time = pending_entry
            entry_price = float(row["open"])
            quantity = cfg.risk_per_trade / (cfg.stop_r * risk_distance)
            layers.append(
                _Layer(side, 1, row["time"], entry_price, quantity, risk_distance)
            )
            pending_entry = None

        if pending_add and layers and len(layers) < cfg.max_layers:
            first = layers[0]
            quantity = cfg.risk_per_trade / (cfg.stop_r * first.risk_distance)
            layers.append(
                _Layer(
                    first.side,
                    len(layers) + 1,
                    row["time"],
                    float(row["open"]),
                    quantity,
                    first.risk_distance,
                )
            )
        pending_add = False

        if layers:
            first = layers[0]
            position_signal = VideoStyleSignal(
                symbol=symbol,
                side=first.side,
                signal_time=first.entry_time,
                breakout_price=first.entry_price,
                risk_distance=first.risk_distance,
            )
            stop, target = video_style_geometry(
                position_signal, entry_price=first.entry_price, cfg=cfg
            )
            stop_distance = abs(first.entry_price - stop)
            low, high = float(row["low"]), float(row["high"])
            exit_price: float | None = None
            reason: str | None = None
            if first.side == "buy":
                if low <= stop:
                    exit_price, reason = stop, "stop"
                elif high >= target:
                    exit_price, reason = target, "target"
            else:
                if high >= stop:
                    exit_price, reason = stop, "stop"
                elif low <= target:
                    exit_price, reason = target, "target"
            for layer in layers:
                layer.bars_held += 1
            elapsed_s = _elapsed_seconds(first.entry_time, row["time"])
            time_expired = elapsed_s is not None and elapsed_s >= float(cfg.max_hold_s)
            if reason is None and (
                time_expired
                or (cfg.max_hold_bars and layers[0].bars_held >= cfg.max_hold_bars)
            ):
                exit_price, reason = float(row["close"]), "time"
            if reason is not None:
                closed = _close_layers(
                    symbol=symbol,
                    layers=layers,
                    exit_time=row["time"],
                    exit_price=float(exit_price),
                    reason=reason,
                    cfg=cfg,
                )
                trades.extend(closed)
                equity += sum(item.net_pnl for item in closed)
                high_water = max(high_water, equity)
                max_drawdown = max(max_drawdown, high_water - equity)
                layers = []
                pending_add = False
                continue

            unrealized = sum(
                _pnl(first.side, layer.entry_price, float(row["close"]), layer.quantity)
                for layer in layers
            )
            last_entry = layers[-1].entry_price
            if (
                i < len(bars) - 1
                and video_style_scale_allowed(
                    side=first.side,
                    last_entry_price=last_entry,
                    current_price=float(row["close"]),
                    stop_distance=stop_distance,
                    unrealized_pnl=unrealized,
                    current_layers=len(layers),
                    max_layers=cfg.max_layers,
                    scale_after_r=cfg.scale_after_r,
                )
            ):
                pending_add = True
            continue

    if layers:
        closed = _close_layers(
            symbol=symbol,
            layers=layers,
            exit_time=bars.iloc[-1]["time"],
            exit_price=float(bars.iloc[-1]["close"]),
            reason="end_of_data",
            cfg=cfg,
        )
        trades.extend(closed)
        equity += sum(item.net_pnl for item in closed)
        high_water = max(high_water, equity)
        max_drawdown = max(max_drawdown, high_water - equity)
    return trades, equity, max_drawdown


def simulate_video_style(
    bars_by_symbol: Mapping[str, pd.DataFrame],
    cfg: VideoStyleConfig,
) -> VideoStyleResult:
    """Run the video-style hypothesis over every supplied symbol.

    Input rows are completed bars.  A breakout is observed on a completed bar
    and entered at the following bar open, so the signal cannot see the entry
    bar's high, low, or close.
    """
    equity = float(cfg.starting_equity)
    all_trades: list[PaperTrade] = []
    max_drawdown = 0.0
    per_symbol: dict[str, dict[str, float | int]] = {}
    for raw_symbol, frame in bars_by_symbol.items():
        symbol = str(raw_symbol or "").strip().upper()
        if not symbol:
            raise ValueError("symbol must not be empty")
        bars = _normalise_bars(symbol, frame)
        trades, equity, symbol_drawdown = _symbol_result(symbol, bars, cfg, equity)
        all_trades.extend(trades)
        max_drawdown = max(max_drawdown, symbol_drawdown)
        per_symbol[symbol] = {
            "trades": len(trades),
            "wins": sum(trade.net_pnl > 0 for trade in trades),
            "losses": sum(trade.net_pnl < 0 for trade in trades),
            "net_pnl": sum(trade.net_pnl for trade in trades),
        }
    return VideoStyleResult(
        placed_orders=False,
        starting_equity=float(cfg.starting_equity),
        ending_equity=equity,
        max_drawdown=max_drawdown,
        wins=sum(trade.net_pnl > 0 for trade in all_trades),
        losses=sum(trade.net_pnl < 0 for trade in all_trades),
        trades=tuple(all_trades),
        per_symbol=per_symbol,
    )
