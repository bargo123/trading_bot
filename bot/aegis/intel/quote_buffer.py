"""Bounded per-symbol quote/tick history for genuine sub-minute features.

Records quotes continuously on runner polling (NOT only on new M1 bars).
Provides point-in-time returns for 5s, 15s, 30s, 60s using correct
liquidation-side semantics: BUY -> BID, SELL -> ASK.

For a requested horizon N:
- never use observations after now
- require genuine history covering approximately N seconds
- select the latest observation at/before now-N as the starting observation
- select latest observation at/before now as endpoint
- if there is no observation sufficiently old to cover N => None
- no interpolation/fabrication
"""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional


@dataclass
class QuotePoint:
    """Single broker quote observation."""
    timestamp: float
    bid: float
    ask: float


@dataclass
class SymbolQuoteBuffer:
    """Bounded quote history for one symbol.

    Keeps up to max_points observations. Oldest are evicted.
    """
    max_points: int = 3600  # 1 hour at 1Hz = 3600 points
    points: deque = field(default_factory=deque)

    def add(self, timestamp: float, bid: float, ask: float) -> None:
        """Add a new quote observation."""
        self.points.append(QuotePoint(timestamp=timestamp, bid=bid, ask=ask))
        # Evict old points beyond max_points
        while len(self.points) > self.max_points:
            self.points.popleft()

    def get_points_since(self, since_ts: float) -> list[QuotePoint]:
        """Get all points with timestamp >= since_ts (point-in-time, no lookahead)."""
        return [p for p in self.points if p.timestamp >= since_ts]

    def get_latest(self) -> Optional[QuotePoint]:
        """Get most recent quote."""
        return self.points[-1] if self.points else None

    def get_at_or_before(self, ts: float) -> Optional[QuotePoint]:
        """Get the latest point with timestamp <= ts (for historical lookback)."""
        for p in reversed(self.points):
            if p.timestamp <= ts:
                return p
        return None


class QuoteBuffer:
    """Global per-symbol quote buffer manager."""

    def __init__(self, max_points_per_symbol: int = 3600):
        self.max_points_per_symbol = max_points_per_symbol
        self.buffers: dict[str, SymbolQuoteBuffer] = {}

    def _get_or_create(self, symbol: str) -> SymbolQuoteBuffer:
        sym = str(symbol).upper()
        if sym not in self.buffers:
            self.buffers[sym] = SymbolQuoteBuffer(max_points=self.max_points_per_symbol)
        return self.buffers[sym]

    def record(self, symbol: str, timestamp: float, bid: float, ask: float) -> None:
        """Record a quote observation for a symbol."""
        self._get_or_create(symbol).add(timestamp, bid, ask)

    def record_from_quote(self, symbol: str, quote: Mapping[str, Any]) -> None:
        """Record from a broker quote object with bid/ask/time."""
        try:
            ts = float(quote.get("time", 0.0) or time.time())
            bid = float(quote.get("bid", 0.0))
            ask = float(quote.get("ask", 0.0))
            if bid > 0 and ask > 0:
                self.record(symbol, ts, bid, ask)
        except (TypeError, ValueError):
            pass

    def get_latest(self, symbol: str) -> Optional[QuotePoint]:
        """Get most recent quote for symbol."""
        buf = self.buffers.get(str(symbol).upper())
        return buf.get_latest() if buf else None

    def _returns_for_side(
        self,
        symbol: str,
        window_seconds: int,
        side: str,
        now: float
    ) -> Optional[float]:
        """Calculate return over window for a specific side.

        BUY uses BID prices (liquidation side for closing a long).
        SELL uses ASK prices (liquidation side for closing a short).

        Returns price change (not percentage) in raw price units.

        Implementation:
        - Select endpoint: latest observation at/before `now`
        - Select startpoint: latest observation at/before `now - window_seconds`
        - Both must exist and startpoint must be strictly before endpoint
        - No interpolation, no future observations
        """
        buf = self.buffers.get(str(symbol).upper())
        if not buf:
            return None

        price_attr = "bid" if side.lower() == "buy" else "ask"

        # Endpoint: latest quote at or before now (no future observations)
        end_point = buf.get_at_or_before(now)
        if end_point is None:
            return None
        end_price = getattr(end_point, price_attr)
        if end_price <= 0:
            return None

        # Startpoint: latest quote at or before now - window_seconds
        start_ts = now - window_seconds
        start_point = buf.get_at_or_before(start_ts)
        if start_point is None:
            return None  # insufficient history to cover the window
        start_price = getattr(start_point, price_attr)
        if start_price <= 0:
            return None

        # Ensure start is strictly before end (genuine time progression)
        if start_point.timestamp >= end_point.timestamp:
            return None

        return end_price - start_price

    def return_5s(self, symbol: str, side: str, now: float) -> Optional[float]:
        """5-second return for side."""
        return self._returns_for_side(symbol, 5, side, now)

    def return_15s(self, symbol: str, side: str, now: float) -> Optional[float]:
        """15-second return for side."""
        return self._returns_for_side(symbol, 15, side, now)

    def return_30s(self, symbol: str, side: str, now: float) -> Optional[float]:
        """30-second return for side."""
        return self._returns_for_side(symbol, 30, side, now)

    def return_60s(self, symbol: str, side: str, now: float) -> Optional[float]:
        """60-second return for side."""
        return self._returns_for_side(symbol, 60, side, now)

    def tick_rate_per_min(self, symbol: str, now: float) -> Optional[float]:
        """Observed tick/quote rate per minute over last 60s (observations at/before now)."""
        buf = self.buffers.get(str(symbol).upper())
        if not buf:
            return None
        since = now - 60
        points = buf.get_points_since(since)
        # Filter to only observations at/before now
        points = [p for p in points if p.timestamp <= now]
        if not points:
            return None
        return len(points)  # points per minute

    def quote_change_rate(self, symbol: str, now: float) -> Optional[float]:
        """Mean absolute quote change per observation over last 60s."""
        buf = self.buffers.get(str(symbol).upper())
        if not buf:
            return None
        since = now - 60
        points = buf.get_points_since(since)
        points = [p for p in points if p.timestamp <= now]
        if len(points) < 2:
            return None
        changes = []
        for i in range(1, len(points)):
            mid_prev = (points[i-1].bid + points[i-1].ask) / 2.0
            mid_curr = (points[i].bid + points[i].ask) / 2.0
            if mid_prev > 0:
                changes.append(abs(mid_curr - mid_prev) / mid_prev)
        return sum(changes) / len(changes) if changes else None

    def short_volatility(self, symbol: str, now: float) -> Optional[float]:
        """Short-term volatility (std of mid-price returns) over last 60s."""
        import math
        buf = self.buffers.get(str(symbol).upper())
        if not buf:
            return None
        since = now - 60
        points = buf.get_points_since(since)
        points = [p for p in points if p.timestamp <= now]
        if len(points) < 3:
            return None
        mids = [(p.bid + p.ask) / 2.0 for p in points if p.bid > 0 and p.ask > 0]
        if len(mids) < 3:
            return None
        returns = [(mids[i] - mids[i-1]) / mids[i-1] for i in range(1, len(mids)) if mids[i-1] > 0]
        if not returns:
            return None
        mean = sum(returns) / len(returns)
        var = sum((r - mean) ** 2 for r in returns) / len(returns)
        return math.sqrt(var)

    def signed_tick_imbalance(self, symbol: str, now: float) -> Optional[float]:
        """Signed imbalance of upticks vs downticks over last 60s."""
        buf = self.buffers.get(str(symbol).upper())
        if not buf:
            return None
        since = now - 60
        points = buf.get_points_since(since)
        points = [p for p in points if p.timestamp <= now]
        if len(points) < 2:
            return None
        up = down = 0
        for i in range(1, len(points)):
            mid_prev = (points[i-1].bid + points[i-1].ask) / 2.0
            mid_curr = (points[i].bid + points[i].ask) / 2.0
            if mid_curr > mid_prev:
                up += 1
            elif mid_curr < mid_prev:
                down += 1
        total = up + down
        return (up - down) / total if total > 0 else None

    def clear(self, symbol: Optional[str] = None) -> None:
        """Clear buffer(s)."""
        if symbol:
            self.buffers.pop(str(symbol).upper(), None)
        else:
            self.buffers.clear()

    def snapshot(self) -> dict[str, Any]:
        """Debug snapshot of buffer sizes."""
        return {
            sym: len(buf.points)
            for sym, buf in self.buffers.items()
        }