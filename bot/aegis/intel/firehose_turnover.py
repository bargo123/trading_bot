"""Confirmed Firehose close cleanup and stale-signal re-entry protection."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from aegis.intel.ticket_metadata import TicketMetadataStore


@dataclass(frozen=True)
class CloseCleanup:
    metadata_removed: bool
    slot_released: bool


class FirehoseReentryGuard:
    """Reject only the exact trigger that just closed; no winner cooldown."""

    def __init__(self, persist_path: Path | None = None) -> None:
        self.persist_path = Path(persist_path) if persist_path is not None else None
        self._last_closed: dict[str, tuple[str, str, float]] = {}
        self._load()

    def _load(self) -> None:
        if self.persist_path is None or not self.persist_path.is_file():
            return
        try:
            rows = json.loads(self.persist_path.read_text(encoding="utf-8"))
            if not isinstance(rows, dict):
                return
            for thesis_key, row in rows.items():
                if not isinstance(row, list) or len(row) != 3:
                    continue
                ticket, fingerprint, closed_at = row
                if isinstance(ticket, str) and isinstance(fingerprint, str):
                    self._last_closed[str(thesis_key)] = (ticket, fingerprint, float(closed_at))
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return

    def _save(self) -> None:
        if self.persist_path is None:
            return
        temporary = self.persist_path.with_suffix(self.persist_path.suffix + ".tmp")
        try:
            self.persist_path.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(json.dumps(self._last_closed, sort_keys=True), encoding="utf-8")
            temporary.replace(self.persist_path)
        except OSError:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass

    def record_close(self, ticket: str, thesis_key: str, quote_fingerprint: str, closed_at: float) -> None:
        if thesis_key and quote_fingerprint:
            self._last_closed[thesis_key] = (str(ticket), quote_fingerprint, float(closed_at))
            self._save()

    def allows(self, thesis_key: str, quote_fingerprint: str, now: float) -> tuple[bool, str]:
        del now  # The guard is fingerprint-based, not a time cooldown.
        prior = self._last_closed.get(thesis_key)
        if prior is not None and prior[1] == quote_fingerprint:
            return False, "stale_reentry"
        return True, "fresh_quote"


def confirmed_close_cleanup(
    metadata_store: TicketMetadataStore,
    guard: FirehoseReentryGuard,
    ticket: str,
    *,
    quote_fingerprint: Optional[str],
    closed_at: float,
    confirmed: bool = True,
) -> CloseCleanup:
    """Release local ticket state only after the broker confirms its close."""
    if not confirmed:
        return CloseCleanup(metadata_removed=False, slot_released=False)
    meta = metadata_store.get(ticket)
    if meta is not None:
        metadata_store.remove(ticket)
        if quote_fingerprint:
            guard.record_close(ticket, meta.thesis_key, quote_fingerprint, closed_at)
    released = meta is not None
    return CloseCleanup(metadata_removed=released, slot_released=released)


def quote_fingerprint(symbol: str, side: str, bid: float, ask: float) -> str:
    """Canonicalize the observed executable quote shared by close and entry."""
    return "|".join((
        str(symbol).upper(),
        str(side).lower(),
        format(float(bid), ".12g"),
        format(float(ask), ".12g"),
    ))
