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
    basket_id: str | None = None
    trigger_id: str | None = None
    clip_sequence: int | None = None
    entry_geometry: dict[str, Any] | None = None
    initial_risk: float | None = None
    cost_evidence: dict[str, Any] | None = None

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
        self._load()

    def _load(self) -> None:
        if not self.persist_path.is_file():
            return
        try:
            data = json.loads(self.persist_path.read_text(encoding="utf-8"))
            for ticket, meta in data.items():
                if isinstance(meta, dict):
                    self._store[ticket] = TicketMetadata.from_dict(meta)
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass

    def _save(self) -> None:
        temp_path: str | None = None
        try:
            data = {t: m.to_dict() for t, m in self._store.items()}
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.persist_path.parent,
                prefix=f".{self.persist_path.name}.", suffix=".tmp", delete=False,
            ) as handle:
                temp_path = handle.name
                handle.write(json.dumps(data, indent=2))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, self.persist_path)
        except OSError:
            if temp_path:
                try:
                    Path(temp_path).unlink(missing_ok=True)
                except OSError:
                    pass

    def add(self, meta: TicketMetadata) -> None:
        """Add or update ticket metadata."""
        self._store[meta.ticket] = meta
        self._save()

    def get(self, ticket: str) -> Optional[TicketMetadata]:
        """Get metadata for a ticket."""
        return self._store.get(str(ticket))

    def remove(self, ticket: str) -> None:
        """Remove ticket metadata (e.g., on position close)."""
        self._store.pop(str(ticket), None)
        self._save()

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
    basket_id: str | None = None,
    trigger_id: str | None = None,
    clip_sequence: int | None = None,
    entry_geometry: dict[str, Any] | None = None,
    initial_risk: float | None = None,
    cost_evidence: dict[str, Any] | None = None,
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
        basket_id=str(basket_id).strip() if basket_id is not None else None,
        trigger_id=str(trigger_id).strip() if trigger_id is not None else None,
        clip_sequence=int(clip_sequence) if clip_sequence is not None else None,
        entry_geometry=dict(entry_geometry) if entry_geometry is not None else None,
        initial_risk=float(initial_risk) if initial_risk is not None else None,
        cost_evidence=dict(cost_evidence) if cost_evidence is not None else None,
    )
