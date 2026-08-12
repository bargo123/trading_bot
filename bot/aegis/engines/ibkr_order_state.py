"""Shared IB order-state classification and deduplication helpers."""
from __future__ import annotations

from typing import Any, Iterable

WORKING_STATUSES = frozenset({"PendingSubmit", "ApiPending", "PreSubmitted", "Submitted"})
CANCELLING_STATUSES = frozenset({"PendingCancel"})
TERMINAL_STATUSES = frozenset({"Filled", "Cancelled", "ApiCancelled", "Inactive"})


def _normalized(status: str) -> str:
    return str(status or "").strip().casefold()


def is_working_status(status: str) -> bool:
    """Return whether IB currently treats a status as a working order."""
    return _normalized(status) in {_normalized(item) for item in WORKING_STATUSES}


def is_cancelling_status(status: str) -> bool:
    """Return whether cancellation has been requested but not acknowledged."""
    return _normalized(status) in {_normalized(item) for item in CANCELLING_STATUSES}


def is_terminal_status(status: str) -> bool:
    """Return whether an order can no longer work at the broker."""
    return _normalized(status) in {_normalized(item) for item in TERMINAL_STATUSES}


def trade_status(trade: Any) -> str:
    return str(getattr(getattr(trade, "orderStatus", None), "status", "") or "")


def trade_identity(trade: Any) -> tuple[Any, ...]:
    """Prefer IB's stable permId, falling back to the client/order pair."""
    order = getattr(trade, "order", None)
    perm_id = int(getattr(order, "permId", 0) or 0)
    if perm_id:
        return ("perm", perm_id)
    return (
        "client_order",
        int(getattr(order, "clientId", 0) or 0),
        int(getattr(order, "orderId", 0) or 0),
    )


def dedupe_trades(trades: Iterable[Any]) -> list[Any]:
    """Return one latest trade object for each broker order identity."""
    unique: dict[tuple[Any, ...], Any] = {}
    for trade in trades:
        unique[trade_identity(trade)] = trade
    return list(unique.values())


def working_trades(trades: Iterable[Any]) -> list[Any]:
    return [trade for trade in dedupe_trades(trades) if is_working_status(trade_status(trade))]


def cancelling_trades(trades: Iterable[Any]) -> list[Any]:
    return [trade for trade in dedupe_trades(trades) if is_cancelling_status(trade_status(trade))]
