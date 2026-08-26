"""Exact ticket -> hypothesis metadata persistence.

At CONFIRMED FILL, persist exact mapping for every new broker ticket:
- ticket
- hypothesis_id
- thesis_key
- strategy_family
- expected_mechanism
- side
- entry_price
- stop_loss
- target_price
- max_hold_s
- regime
- session
- opened_ts
- information_id if present

This mapping survives runner restart.
PM / FastExit must use exact ticket metadata.
Broker EXP comment/tag recovery remains ONLY as legacy/restart recovery
when exact metadata does not exist.
"""
from __future__ import annotations

import json
import os
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional


@dataclass
class TicketMetadata:
    """Exact metadata for a broker position ticket."""
    ticket: str
    hypothesis_id: str
    thesis_key: str
    strategy_family: str
    expected_mechanism: str
    side: str
    entry_price: float
    stop_loss: float
    target_price: float | None
    max_hold_s: int
    regime: str
    session: str
    opened_ts: float
    information_id: str | None = None
    symbol: str = ""
    basket_id: Any = None
    trigger_id: Any = None
    clip_sequence: Any = None
    entry_geometry: dict[str, Any] | None = None
    initial_risk: float | None = None
    cost_evidence: dict[str, Any] | None = None
    entry_ev: float | None = None
    decision_snapshot: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TicketMetadata":
        return cls(**data)


class TicketMetadataStore:
    """Persists ticket->hypothesis mappings to survive runner restarts."""

    def __init__(self, persist_path: Path):
        self.persist_path = Path(persist_path)
        self.persist_path.parent.mkdir(parents=True, exist_ok=True)
        self._store: dict[str, TicketMetadata] = {}
        self._pending_cleanup: dict[str, dict[str, Any]] = {}
        self._pending_basket_cleanup: dict[str, dict[str, str]] = {}
        self._load()

    def _load(self) -> None:
        if not self.persist_path.is_file():
            return
        try:
            data = json.loads(self.persist_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return
            tickets = data.get("tickets") if isinstance(data.get("tickets"), dict) else data
            pending = data.get("pending_cleanup", {}) if tickets is not data else {}
            pending_basket = data.get("pending_basket_cleanup", {}) if tickets is not data else {}
            for ticket, meta in tickets.items():
                if isinstance(meta, dict):
                    self._store[ticket] = TicketMetadata.from_dict(meta)
            if isinstance(pending, dict):
                self._pending_cleanup = {
                    str(ticket): dict(cleanup)
                    for ticket, cleanup in pending.items()
                    if isinstance(cleanup, dict)
                }
            if isinstance(pending_basket, dict):
                self._pending_basket_cleanup = {
                    str(ticket): marker
                    for ticket, cleanup in pending_basket.items()
                    if (marker := self._pending_basket_cleanup_marker(ticket, cleanup)) is not None
                }
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass

    @staticmethod
    def _pending_basket_cleanup_marker(ticket: Any, cleanup: Any) -> dict[str, str] | None:
        if not isinstance(cleanup, dict) or set(cleanup) != {"ticket_id", "basket_id", "symbol"}:
            return None
        ticket_id = str(ticket).strip()
        basket_id = str(cleanup.get("basket_id", "")).strip()
        symbol = str(cleanup.get("symbol", "")).strip().upper()
        if ticket_id != str(cleanup.get("ticket_id", "")).strip() or not all((ticket_id, basket_id, symbol)):
            return None
        return {"ticket_id": ticket_id, "basket_id": basket_id, "symbol": symbol}

    def _save(self) -> bool:
        temp_path: str | None = None
        try:
            data = {
                "tickets": {t: m.to_dict() for t, m in self._store.items()},
                "pending_cleanup": self._pending_cleanup,
                "pending_basket_cleanup": self._pending_basket_cleanup,
            }
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.persist_path.parent,
                prefix=f".{self.persist_path.name}.", suffix=".tmp", delete=False,
            ) as handle:
                temp_path = handle.name
                handle.write(json.dumps(data, indent=2))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, self.persist_path)
            return True
        except OSError:
            if temp_path:
                try:
                    Path(temp_path).unlink(missing_ok=True)
                except OSError:
                    pass
            return False

    def add(self, meta: TicketMetadata) -> bool:
        """Add or update ticket metadata."""
        previous = self._store.get(meta.ticket)
        self._store[meta.ticket] = meta
        if self._save():
            return True
        if previous is None:
            self._store.pop(meta.ticket, None)
        else:
            self._store[meta.ticket] = previous
        return False

    def get(self, ticket: str) -> Optional[TicketMetadata]:
        """Get metadata for a ticket."""
        return self._store.get(str(ticket))

    def remove(self, ticket: str, *, clear_pending: bool = False) -> bool:
        """Remove ticket metadata (e.g., on position close)."""
        ticket = str(ticket)
        previous = self._store.pop(ticket, None)
        pending = self._pending_cleanup.pop(ticket, None) if clear_pending else None
        if self._save():
            return True
        if previous is not None:
            self._store[ticket] = previous
        if clear_pending and pending is not None:
            self._pending_cleanup[ticket] = pending
        return False

    def begin_pending_cleanup(self, ticket: str, cleanup: dict[str, Any]) -> bool:
        """Persist exact close-cleanup identity before mutating basket ownership."""
        ticket = str(ticket)
        previous = self._pending_cleanup.get(ticket)
        self._pending_cleanup[ticket] = dict(cleanup)
        if self._save():
            return True
        if previous is None:
            self._pending_cleanup.pop(ticket, None)
        else:
            self._pending_cleanup[ticket] = previous
        return False

    def mark_pending_basket_removed(self, ticket: str, *, basket_closed: bool) -> bool:
        """Record durable basket removal before finalizing other local state."""
        ticket = str(ticket)
        previous = self._pending_cleanup.get(ticket)
        if previous is None:
            return False
        updated = {**previous, "basket_removed": True, "basket_closed": bool(basket_closed)}
        self._pending_cleanup[ticket] = updated
        if self._save():
            return True
        self._pending_cleanup[ticket] = previous
        return False

    def pending_cleanup(self, ticket: str) -> dict[str, Any] | None:
        cleanup = self._pending_cleanup.get(str(ticket))
        return dict(cleanup) if cleanup is not None else None

    def pending_cleanups(self) -> dict[str, dict[str, Any]]:
        return {ticket: dict(cleanup) for ticket, cleanup in self._pending_cleanup.items()}

    def begin_pending_basket_cleanup(self, ticket: str, basket_id: str, symbol: str) -> bool:
        """Persist failed-opening compensation identity before basket mutation."""
        marker = self._pending_basket_cleanup_marker(ticket, {
            "ticket_id": str(ticket), "basket_id": str(basket_id), "symbol": str(symbol),
        })
        if marker is None:
            return False
        ticket_id = marker["ticket_id"]
        previous = self._pending_basket_cleanup.get(ticket_id)
        self._pending_basket_cleanup[ticket_id] = marker
        if self._save():
            return True
        if previous is None:
            self._pending_basket_cleanup.pop(ticket_id, None)
        else:
            self._pending_basket_cleanup[ticket_id] = previous
        return False

    def clear_pending_basket_cleanup(self, ticket: str) -> bool:
        """Remove a failed-opening marker only after exact basket removal."""
        ticket_id = str(ticket)
        previous = self._pending_basket_cleanup.pop(ticket_id, None)
        if previous is None:
            return False
        if self._save():
            return True
        self._pending_basket_cleanup[ticket_id] = previous
        return False

    def pending_basket_cleanup(self, ticket: str) -> dict[str, str] | None:
        marker = self._pending_basket_cleanup.get(str(ticket))
        return dict(marker) if marker is not None else None

    def pending_basket_cleanups(self) -> dict[str, dict[str, str]]:
        return {ticket: dict(marker) for ticket, marker in self._pending_basket_cleanup.items()}

    def get_by_hypothesis(self, hypothesis_id: str) -> list[TicketMetadata]:
        """Get all tickets for a hypothesis."""
        return [m for m in self._store.values()
                if m.hypothesis_id == hypothesis_id]

    def get_by_symbol(self, symbol: str) -> list[TicketMetadata]:
        """Get all tickets for a symbol."""
        sym = str(symbol).upper()
        return [m for m in self._store.values() if m.symbol == sym]

    def snapshot(self) -> dict[str, Any]:
        """Debug snapshot."""
        return {t: m.to_dict() for t, m in self._store.items()}

    def clear(self) -> None:
        """Clear all metadata (for testing)."""
        self._store.clear()
        self._save()


def firehose_lifecycle_identity(metadata: TicketMetadata | None) -> dict[str, Any]:
    """Return primary lifecycle identity only when exact ownership is complete."""
    if metadata is None:
        return {}
    basket_id = metadata.basket_id
    trigger_id = metadata.trigger_id
    clip_sequence = metadata.clip_sequence
    if (
        not isinstance(basket_id, str)
        or not basket_id.strip()
        or not isinstance(trigger_id, str)
        or not trigger_id.strip()
        or not isinstance(clip_sequence, int)
        or isinstance(clip_sequence, bool)
        or clip_sequence <= 0
    ):
        return {}
    return {
        "basket_id": basket_id,
        "trigger_id": trigger_id,
        "clip_sequence": clip_sequence,
    }


def create_ticket_metadata(
    *,
    ticket: str,
    hypothesis_id: str,
    thesis_key: str,
    strategy_family: str,
    expected_mechanism: str,
    side: str,
    entry_price: float,
    stop_loss: float,
    target_price: float | None,
    max_hold_s: int,
    regime: str,
    session: str,
    information_id: str | None = None,
    symbol: str = "",
    basket_id: Any = None,
    trigger_id: Any = None,
    clip_sequence: Any = None,
    entry_geometry: dict[str, Any] | None = None,
    initial_risk: float | None = None,
    cost_evidence: dict[str, Any] | None = None,
    entry_ev: float | None = None,
    decision_snapshot: dict[str, Any] | None = None,
) -> TicketMetadata:
    """Create ticket metadata with current timestamp."""
    return TicketMetadata(
        ticket=str(ticket).strip(),
        hypothesis_id=hypothesis_id,
        thesis_key=thesis_key,
        strategy_family=strategy_family,
        expected_mechanism=expected_mechanism,
        side=side.lower(),
        entry_price=float(entry_price),
        stop_loss=float(stop_loss),
        target_price=float(target_price) if target_price is not None else None,
        max_hold_s=int(max_hold_s),
        regime=regime,
        session=session,
        opened_ts=time.time(),
        information_id=information_id,
        symbol=str(symbol).upper(),
        basket_id=basket_id,
        trigger_id=trigger_id,
        clip_sequence=clip_sequence,
        entry_geometry=dict(entry_geometry) if entry_geometry is not None else None,
        initial_risk=float(initial_risk) if initial_risk is not None else None,
        cost_evidence=dict(cost_evidence) if cost_evidence is not None else None,
        entry_ev=float(entry_ev) if entry_ev is not None else None,
        decision_snapshot=(
            dict(decision_snapshot) if decision_snapshot is not None else None
        ),
    )
