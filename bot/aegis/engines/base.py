"""Abstract broker engine interface.

Implementations: IBKR paper/live, MT5 (later), etc.
Aegis signals never import a specific broker — only this interface.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Optional

Side = Literal["buy", "sell"]
OrderKind = Literal["market", "limit"]


@dataclass(frozen=True)
class AccountSnapshot:
    account_id: str
    equity: float
    currency: str
    available_funds: float
    is_paper: bool
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Quote:
    symbol: str
    bid: float
    ask: float
    time: datetime


@dataclass(frozen=True)
class Bar:
    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


@dataclass(frozen=True)
class PositionSnapshot:
    symbol: str
    side: Side
    quantity: float
    avg_price: float
    unrealized_pnl: float = 0.0


@dataclass(frozen=True)
class OrderRequest:
    symbol: str
    side: Side
    quantity: float
    kind: OrderKind = "market"
    limit_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    client_tag: str = ""


@dataclass(frozen=True)
class OrderResult:
    ok: bool
    broker_order_id: str = ""
    message: str = ""
    filled: bool = False
    fill_price: Optional[float] = None


class BrokerEngine(ABC):
    """One connection to one broker backend."""

    name: str = "base"

    @abstractmethod
    def connect(self) -> None:
        ...

    @abstractmethod
    def disconnect(self) -> None:
        ...

    @abstractmethod
    def account(self) -> AccountSnapshot:
        ...

    @abstractmethod
    def quote(self, symbol: str) -> Quote:
        ...

    @abstractmethod
    def bars(self, symbol: str, timeframe: str, lookback_days: int) -> list[Bar]:
        ...

    @abstractmethod
    def positions(self, symbol: Optional[str] = None) -> list[PositionSnapshot]:
        ...

    @abstractmethod
    def place_order(self, req: OrderRequest) -> OrderResult:
        ...

    @abstractmethod
    def cancel_order(self, broker_order_id: str) -> OrderResult:
        ...

    def place_and_cancel_limit(
        self,
        symbol: str,
        side: Side,
        quantity: float,
        limit_price: float,
    ) -> OrderResult:
        """Safety helper for smoke tests: place a limit then cancel immediately."""
        placed = self.place_order(
            OrderRequest(
                symbol=symbol,
                side=side,
                quantity=quantity,
                kind="limit",
                limit_price=limit_price,
                client_tag="smoke_cancel",
            )
        )
        if not placed.ok or not placed.broker_order_id:
            return placed
        cancelled = self.cancel_order(placed.broker_order_id)
        return OrderResult(
            ok=cancelled.ok,
            broker_order_id=placed.broker_order_id,
            message=f"placed then cancel: {cancelled.message}",
            filled=False,
        )
