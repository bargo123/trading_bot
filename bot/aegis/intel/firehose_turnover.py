"""Confirmed Firehose close cleanup and stale-signal re-entry protection."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Any, Mapping, Optional

from aegis.intel.ticket_metadata import TicketMetadata, TicketMetadataStore


@dataclass(frozen=True)
class CloseCleanup:
    metadata_removed: bool
    slot_released: bool
    basket_closed: bool = False


class TurnoverMetrics:
    """In-memory observations for confirmed Firehose ticket lifecycles."""

    def __init__(self) -> None:
        self._opens: dict[str, tuple[float, int | None]] = {}
        self._peaks: dict[str, float] = {}
        self._closes: list[tuple[float, float, float | None, float | None, float | None, float | None, int | None]] = []

    @property
    def active_tickets(self) -> set[str]:
        return set(self._opens)

    def record_open(self, ticket: str, *, opened_at: float, slot_capacity: int | None) -> None:
        if ticket and ticket not in self._opens:
            self._opens[ticket] = (float(opened_at), slot_capacity if slot_capacity and slot_capacity > 0 else None)

    def record_exit_trace(self, ticket: str, *, observed_at: float, mfe_usd: float | None) -> None:
        del observed_at
        if ticket not in self._opens or mfe_usd is None:
            return
        peak = float(mfe_usd)
        if peak > 0:
            self._peaks[ticket] = max(self._peaks.get(ticket, peak), peak)

    def record_close(
        self,
        ticket: str,
        *,
        closed_at: float,
        gross_pnl_usd: float | None,
        net_pnl_usd: float | None,
        cost_usd: float | None,
        confirmed: bool,
    ) -> None:
        if not confirmed or ticket not in self._opens:
            return
        opened_at, slot_capacity = self._opens.pop(ticket)
        self._closes.append((
            opened_at, float(closed_at), gross_pnl_usd, net_pnl_usd, cost_usd,
            self._peaks.pop(ticket, None), slot_capacity,
        ))

    def snapshot(self, now: float) -> dict[str, float | None]:
        completed = self._closes
        if not completed:
            return {
                "median_hold_seconds": None, "p90_hold_seconds": None,
                "round_trips_per_hour": None, "close_to_entry_interval_seconds": None,
                "slot_utilization": None, "profit_capture_ratio": None,
                "gross_profit_per_hour": None, "net_profit_per_hour": None,
                "cost_per_round_trip_usd": None,
            }
        holds = sorted(closed - opened for opened, closed, _, _, _, _, _ in completed)
        p90_index = (len(holds) - 1) * 0.9
        lower, upper = int(p90_index), min(int(p90_index) + 1, len(holds) - 1)
        p90 = holds[lower] + (holds[upper] - holds[lower]) * (p90_index - lower)
        first_open = min(opened for opened, _, _, _, _, _, _ in completed)
        elapsed = float(now) - first_open
        rate = len(completed) / (elapsed / 3600.0) if elapsed > 0 else None
        intervals = [
            opened - prior_closed
            for opened, _, _, _, _, _, _ in sorted(completed)
            for prior_closed in [max((closed for _, closed, _, _, _, _, _ in completed if closed <= opened), default=None)]
            if prior_closed is not None
        ]
        capacities = [capacity for _, _, _, _, _, _, capacity in completed]
        gross = [value for _, _, value, _, _, _, _ in completed]
        net = [value for _, _, _, value, _, _, _ in completed]
        cost = [value for _, _, _, _, value, _, _ in completed]
        peaks = [value for _, _, _, _, _, value, _ in completed]
        return {
            "median_hold_seconds": median(holds), "p90_hold_seconds": p90,
            "round_trips_per_hour": rate,
            "close_to_entry_interval_seconds": median(intervals) if intervals else None,
            "slot_utilization": sum(holds) / (elapsed * median(capacities)) if elapsed > 0 and all(v is not None for v in capacities) else None,
            "profit_capture_ratio": sum(net) / sum(peaks) if all(v is not None for v in net + peaks) and sum(peaks) > 0 else None,
            "gross_profit_per_hour": sum(gross) / (elapsed / 3600.0) if elapsed > 0 and all(v is not None for v in gross) else None,
            "net_profit_per_hour": sum(net) / (elapsed / 3600.0) if elapsed > 0 and all(v is not None for v in net) else None,
            "cost_per_round_trip_usd": sum(cost) / len(cost) if cost and all(v is not None for v in cost) else None,
        }


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
        return CloseCleanup(metadata_removed=False, slot_released=False, basket_closed=False)
    meta = metadata_store.get(ticket)
    basket_closed = False
    if meta is not None:
        if meta.basket_id:
            basket_closed = sum(
                item.get("basket_id") == meta.basket_id
                for item in metadata_store.snapshot().values()
            ) == 1
        metadata_store.remove(ticket)
        if quote_fingerprint:
            guard.record_close(ticket, meta.thesis_key, quote_fingerprint, closed_at)
    removed = meta is not None
    released = removed and (not meta.basket_id or basket_closed)
    return CloseCleanup(
        metadata_removed=removed,
        slot_released=released,
        basket_closed=basket_closed,
    )


def basket_lifecycle_trace(
    metadata: TicketMetadata | None,
    *,
    event: str,
    timestamp: str,
    confirmed: bool,
    observation: Mapping[str, Any] | None = None,
    slot_released: bool = False,
    basket_closed: bool = False,
) -> dict[str, Any] | None:
    """Format a basket observation only for confirmed, exactly-owned tickets."""
    if (
        not confirmed
        or metadata is None
        or not all((
            metadata.basket_id,
            metadata.trigger_id,
            metadata.clip_sequence,
            metadata.entry_geometry,
            metadata.initial_risk,
            metadata.cost_evidence,
        ))
    ):
        return None
    values = dict(observation or {})
    return {
        "event": event,
        "timestamp": timestamp,
        "confirmed": True,
        "basket_id": metadata.basket_id,
        "ticket_id": metadata.ticket,
        "hypothesis_id": metadata.hypothesis_id,
        "family": metadata.strategy_family,
        "symbol": metadata.symbol,
        "side": metadata.side,
        "trigger_id": metadata.trigger_id,
        "clip_sequence": metadata.clip_sequence,
        "entry_geometry": dict(metadata.entry_geometry),
        "initial_risk_usd": metadata.initial_risk,
        "cost_evidence": dict(metadata.cost_evidence),
        "mfe_usd": values.get("mfe_usd"),
        "mae_usd": values.get("mae_usd"),
        "peak_net_profit_usd": values.get("peak_net_profit_usd"),
        "realized_net_usd": None,
        "capture_ratio": None,
        "age_seconds": values.get("age_seconds"),
        "clips": values.get("clips", metadata.clip_sequence),
        "decision_reasons": values.get("decision_reasons", []),
        "ev": values.get("ev"),
        "cost_usd": None,
        "turnover": values.get("turnover"),
        "regime": metadata.regime,
        "session": metadata.session,
        "slot_released": bool(slot_released),
        "basket_closed": bool(basket_closed),
    }


def quote_fingerprint(symbol: str, side: str, bid: float, ask: float) -> str:
    """Canonicalize the observed executable quote shared by close and entry."""
    return "|".join((
        str(symbol).upper(),
        str(side).lower(),
        format(float(bid), ".12g"),
        format(float(ask), ".12g"),
    ))
