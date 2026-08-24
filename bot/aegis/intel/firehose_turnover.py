"""Confirmed Firehose close cleanup and stale-signal re-entry protection."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from aegis.intel.ticket_metadata import TicketMetadataStore


@dataclass(frozen=True)
class CloseCleanup:
    metadata_removed: bool
    slot_released: bool


class FirehoseReentryGuard:
    """Reject only the exact trigger that just closed; no winner cooldown."""

    def __init__(self) -> None:
        self._last_closed: dict[str, tuple[str, str, float]] = {}

    def record_close(self, ticket: str, thesis_key: str, quote_fingerprint: str, closed_at: float) -> None:
        if thesis_key and quote_fingerprint:
            self._last_closed[thesis_key] = (str(ticket), quote_fingerprint, float(closed_at))

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
    return CloseCleanup(metadata_removed=meta is not None, slot_released=True)
