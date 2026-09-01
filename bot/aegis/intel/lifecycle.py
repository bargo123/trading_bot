"""Demo lifecycle helpers. Runner may import this module; it must not import research."""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping, Sequence

from aegis.engines import PositionSnapshot
from aegis.portfolio_risk import portfolio_exposure, portfolio_pretrade_decision
from aegis.reconcile import (
    ReconcileCursor,
    aggregate_confirmed_exit_deals,
    reconcile_new_deals,
)


def new_cursor() -> ReconcileCursor:
    return ReconcileCursor()


def load_cursor(path: Path) -> ReconcileCursor:
    """Load a persisted cursor. A missing/corrupt file yields a fresh cursor."""
    cursor = ReconcileCursor()
    try:
        cursor.load_json(path)
    except Exception:
        cursor = ReconcileCursor()
    return cursor


def save_cursor(cursor: ReconcileCursor, path: Path) -> None:
    """Atomically persist the cursor so restarts do not re-ingest old deals."""
    cursor.save_json(path)


def pretrade_ok(
    *,
    positions: Sequence[PositionSnapshot],
    symbol: str,
    side: str,
    quantity: float,
    avg_price: float,
    cfg: Mapping[str, Any],
) -> tuple[bool, str]:
    ok, reason, _event = portfolio_pretrade_decision(
        positions=list(positions),
        symbol=symbol,
        side=side,
        quantity=quantity,
        avg_price=avg_price,
        cfg=dict(cfg),
    )
    return ok, reason


def exposure_snapshot(positions: Sequence[PositionSnapshot]) -> dict[str, Any]:
    try:
        exposure = portfolio_exposure(list(positions))
    except ValueError:
        exposure = {}
    return {"currency_direction": exposure, "n": len(positions)}


def ingest_deals(deals: Sequence[Mapping[str, Any]], cursor: ReconcileCursor) -> list[dict[str, Any]]:
    return [asdict(event) for event in reconcile_new_deals(deals, cursor)]
