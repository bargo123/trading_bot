"""Broker execution engines (IBKR, MT5, …).

Strategy / risk stay in Aegis; engines only connect, read market data, and send orders.
"""
from __future__ import annotations

from aegis.engines.base import (
    AccountSnapshot,
    Bar,
    BrokerEngine,
    OrderRequest,
    OrderResult,
    PositionSnapshot,
    Quote,
)
from aegis.engines.factory import create_engine

__all__ = [
    "AccountSnapshot",
    "Bar",
    "BrokerEngine",
    "OrderRequest",
    "OrderResult",
    "PositionSnapshot",
    "Quote",
    "create_engine",
]
