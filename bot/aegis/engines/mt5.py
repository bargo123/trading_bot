"""MetaTrader 5 engine — stub for a future Windows implementation."""
from __future__ import annotations

from typing import Any, Optional

from aegis.engines.base import (
    AccountSnapshot,
    Bar,
    BrokerEngine,
    OrderRequest,
    OrderResult,
    PositionSnapshot,
    Quote,
)


class MT5Engine(BrokerEngine):
    """Placeholder so configs can select engine: mt5 later without redesign."""

    name = "mt5"

    def __init__(self, cfg: dict[str, Any]) -> None:
        self.cfg = cfg

    def connect(self) -> None:
        raise NotImplementedError(
            "MT5Engine is not implemented yet. "
            "It will use the MetaTrader5 package on Windows. "
            "Use engine: ibkr for paper testing on Mac."
        )

    def disconnect(self) -> None:
        return None

    def account(self) -> AccountSnapshot:
        raise NotImplementedError("MT5Engine not implemented")

    def quote(self, symbol: str) -> Quote:
        raise NotImplementedError("MT5Engine not implemented")

    def bars(self, symbol: str, timeframe: str, lookback_days: int) -> list[Bar]:
        raise NotImplementedError("MT5Engine not implemented")

    def positions(self, symbol: Optional[str] = None) -> list[PositionSnapshot]:
        raise NotImplementedError("MT5Engine not implemented")

    def place_order(self, req: OrderRequest) -> OrderResult:
        raise NotImplementedError("MT5Engine not implemented")

    def cancel_order(self, broker_order_id: str) -> OrderResult:
        raise NotImplementedError("MT5Engine not implemented")

    def working_orders(self) -> list[Any]:
        raise NotImplementedError("MT5Engine not implemented")

    def cancel_all_orders(self, timeout_s: float = 10.0, poll_s: float = 0.2) -> OrderResult:
        raise NotImplementedError("MT5Engine not implemented")

    def flatten_positions(
        self,
        symbol: Optional[str] = None,
        timeout_s: float = 15.0,
        poll_s: float = 0.2,
    ) -> OrderResult:
        raise NotImplementedError("MT5Engine not implemented")
