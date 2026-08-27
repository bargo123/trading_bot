"""Confirmed Firehose close cleanup and stale-signal re-entry protection."""
from __future__ import annotations

import json
import time
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
    reason: str | None = None


class TurnoverMetrics:
    """In-memory observations for confirmed Firehose ticket lifecycles."""

    def __init__(self) -> None:
        self._opens: dict[str, tuple[float, int | None]] = {}
        self._peaks: dict[str, float] = {}
        self._closes: list[tuple[float, float, float | None, float | None, float | None, float | None, int | None]] = []
        self._close_details: list[dict[str, Any]] = []
        self._green_at: dict[str, float] = {}
        self._mae: dict[str, float] = {}
        self._red_seconds: dict[str, float] = {}
        self._last_sample: dict[str, tuple[float, float]] = {}

    @property
    def active_tickets(self) -> set[str]:
        return set(self._opens)

    def record_open(self, ticket: str, *, opened_at: float, slot_capacity: int | None) -> None:
        if ticket and ticket not in self._opens:
            self._opens[ticket] = (float(opened_at), slot_capacity if slot_capacity and slot_capacity > 0 else None)
            self._green_at.pop(ticket, None)
            self._mae.pop(ticket, None)
            self._red_seconds.pop(ticket, None)
            self._last_sample.pop(ticket, None)

    def record_exit_trace(
        self,
        ticket: str,
        *,
        observed_at: float,
        mfe_usd: float | None,
        pnl_usd: float | None = None,
    ) -> None:
        if ticket not in self._opens or mfe_usd is None:
            return
        peak = float(mfe_usd)
        if peak > 0:
            self._peaks[ticket] = max(self._peaks.get(ticket, peak), peak)
        if pnl_usd is None:
            return
        now = float(observed_at)
        pnl = float(pnl_usd)
        if pnl < 0:
            self._mae[ticket] = min(self._mae.get(ticket, pnl), pnl)
        prior = self._last_sample.get(ticket)
        if prior is not None and prior[1] < 0.0 and now >= prior[0]:
            self._red_seconds[ticket] = self._red_seconds.get(ticket, 0.0) + (now - prior[0])
        self._last_sample[ticket] = (now, pnl)
        if pnl > 0.0 and ticket not in self._green_at:
            self._green_at[ticket] = now

    def record_close(
        self,
        ticket: str,
        *,
        closed_at: float,
        gross_pnl_usd: float | None,
        net_pnl_usd: float | None,
        cost_usd: float | None,
        confirmed: bool,
        exit_reason: str | None = None,
    ) -> None:
        if not confirmed or ticket not in self._opens:
            return
        opened_at, slot_capacity = self._opens.pop(ticket)
        peak_mfe = self._peaks.pop(ticket, None)
        self._closes.append((
            opened_at, float(closed_at), gross_pnl_usd, net_pnl_usd, cost_usd,
            peak_mfe, slot_capacity,
        ))
        self._close_details.append({
            "ticket": ticket,
            "opened_at": opened_at,
            "closed_at": float(closed_at),
            "exit_reason": str(exit_reason or "unknown"),
            "first_green_s": (
                max(0.0, self._green_at[ticket] - opened_at)
                if ticket in self._green_at else None
            ),
            "seconds_in_red": round(self._red_seconds.get(ticket, 0.0), 6),
            "mfe_usd": peak_mfe,
            "mae_usd": round(self._mae.get(ticket, 0.0), 6),
            "gross_pnl_usd": gross_pnl_usd,
            "net_pnl_usd": net_pnl_usd,
            "cost_usd": cost_usd,
        })
        self._green_at.pop(ticket, None)
        self._mae.pop(ticket, None)
        self._red_seconds.pop(ticket, None)
        self._last_sample.pop(ticket, None)

    def record_realized(
        self,
        ticket: str,
        *,
        net_pnl_usd: float,
        cost_usd: float | None = None,
        closed_at: float | None = None,
        exit_reason: str | None = None,
    ) -> bool:
        """Attach broker P&L, including exits triggered outside the runner."""
        for index in range(len(self._close_details) - 1, -1, -1):
            detail = self._close_details[index]
            if detail.get("ticket") != str(ticket) or detail.get("net_pnl_usd") is not None:
                continue
            detail["net_pnl_usd"] = float(net_pnl_usd)
            if cost_usd is not None:
                detail["cost_usd"] = float(cost_usd)
            opened, closed, gross, _net, cost, peak, capacity = self._closes[index]
            self._closes[index] = (
                opened, closed, gross if gross is not None else float(net_pnl_usd),
                float(net_pnl_usd), cost if cost is not None else cost_usd,
                peak, capacity,
            )
            return True
        if ticket in self._opens:
            # SL/TP or a terminal-side close can arrive before the runner's
            # local close-confirmation path. Materialize that broker truth as
            # a completed lifecycle instead of dropping its P&L.
            self.record_close(
                ticket,
                closed_at=float(closed_at if closed_at is not None else time.time()),
                gross_pnl_usd=float(net_pnl_usd),
                net_pnl_usd=float(net_pnl_usd),
                cost_usd=cost_usd,
                confirmed=True,
                exit_reason=exit_reason or "broker_reconciled",
            )
            self._close_details[-1]["net_pnl_usd"] = float(net_pnl_usd)
            if cost_usd is not None:
                self._close_details[-1]["cost_usd"] = float(cost_usd)
            return True
        return False

    def close_detail(self, ticket: str) -> dict[str, Any] | None:
        """Return the in-memory lifecycle facts for one completed ticket."""
        for index in range(len(self._close_details) - 1, -1, -1):
            detail = self._close_details[index]
            if detail.get("ticket") != str(ticket):
                continue
            row = dict(detail)
            row["mfe_usd"] = self._closes[index][5]
            return row
        return None

    def snapshot(self, now: float) -> dict[str, Any]:
        completed = self._closes
        details = self._close_details
        resolved = [detail for detail in details if detail.get("net_pnl_usd") is not None]
        resolved_net = [float(detail["net_pnl_usd"]) for detail in resolved]
        winners_resolved = [value for value in resolved_net if value > 0]
        losers_resolved = [value for value in resolved_net if value < 0]
        exit_reasons = [str(detail.get("exit_reason") or "") for detail in details]
        green_times = [
            float(detail["first_green_s"])
            for detail in details
            if detail.get("first_green_s") is not None
        ]
        red_seconds = [float(detail.get("seconds_in_red") or 0.0) for detail in details]
        telemetry: dict[str, Any] = {
            "completed_trades": len(details),
            "scratches": sum("scratch" in reason or "abort" in reason for reason in exit_reasons),
            "win_exits": len(winners_resolved),
            "loss_exits": len(losers_resolved),
            "green_within_3s": sum(value <= 3.0 for value in green_times),
            "green_within_5s": sum(value <= 5.0 for value in green_times),
            "green_within_10s": sum(value <= 10.0 for value in green_times),
            "green_within_20s": sum(value <= 20.0 for value in green_times),
            "green_within_30s": sum(value <= 30.0 for value in green_times),
            "median_time_to_green_s": median(green_times) if green_times else None,
            "median_seconds_in_red": median(red_seconds) if red_seconds else None,
            "resolved_outcomes": len(resolved_net),
            "outcome_evidence": "broker_reconciled_deals" if resolved_net else "NO_EVIDENCE",
        }
        if not completed:
            return {
                "median_hold_seconds": None, "p90_hold_seconds": None,
                "round_trips_per_hour": None, "close_to_entry_interval_seconds": None,
                "slot_utilization": None, "profit_capture_ratio": None,
                "gross_profit_per_hour": None, "net_profit_per_hour": None,
                "cost_per_round_trip_usd": None,
                "average_winner_usd": None, "average_loser_usd": None,
                "p95_loss_usd": None, "p99_loss_usd": None,
                "max_loss_usd": None, "wins_erased_by_avg_loss": None,
                **telemetry,
                "win_rate": None, "expectancy": None, "profit_factor": None,
                "daily_net": None, "captured_net_win_rate": None,
                "net_pnl": None, "never_green_rate": None,
                "green_then_loser_rate": None,
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
        confirmed_net = [value for value in net if value is not None]
        winners = [value for value in confirmed_net if value > 0]
        losers = sorted(value for value in confirmed_net if value < 0)
        average_winner = sum(winners) / len(winners) if winners else None
        average_loser = sum(losers) / len(losers) if losers else None
        tail_index = lambda percentile: min(len(losers) - 1, int((len(losers) - 1) * percentile))
        p95_loss = losers[tail_index(0.05)] if losers else None
        p99_loss = losers[tail_index(0.01)] if losers else None
        return {
            "median_hold_seconds": median(holds), "p90_hold_seconds": p90,
            "round_trips_per_hour": rate,
            "close_to_entry_interval_seconds": median(intervals) if intervals else None,
            "slot_utilization": sum(holds) / (elapsed * median(capacities)) if elapsed > 0 and all(v is not None for v in capacities) else None,
            "profit_capture_ratio": sum(net) / sum(peaks) if all(v is not None for v in net + peaks) and sum(peaks) > 0 else None,
            "gross_profit_per_hour": sum(gross) / (elapsed / 3600.0) if elapsed > 0 and all(v is not None for v in gross) else None,
            "net_profit_per_hour": sum(net) / (elapsed / 3600.0) if elapsed > 0 and all(v is not None for v in net) else None,
            "cost_per_round_trip_usd": sum(cost) / len(cost) if cost and all(v is not None for v in cost) else None,
            "average_winner_usd": average_winner,
            "average_loser_usd": average_loser,
            "p95_loss_usd": p95_loss,
            "p99_loss_usd": p99_loss,
            "max_loss_usd": min(losers) if losers else None,
            "wins_erased_by_avg_loss": (
                abs(average_loser) / average_winner
                if average_loser is not None and average_winner is not None and average_winner > 0
                else None
            ),
            **telemetry,
            "win_rate": (
                len(winners_resolved) / len(resolved_net) if resolved_net else None
            ),
            "expectancy": (
                sum(resolved_net) / len(resolved_net) if resolved_net else None
            ),
            "profit_factor": (
                sum(winners_resolved) / abs(sum(losers_resolved))
                if losers_resolved and winners_resolved else None
            ),
            "daily_net": sum(resolved_net) if resolved_net else None,
            "captured_net_win_rate": (
                len(winners_resolved) / len(resolved_net) if resolved_net else None
            ),
            "net_pnl": sum(resolved_net) if resolved_net else None,
            "never_green_rate": (
                sum(detail.get("first_green_s") is None for detail in details) / len(details)
                if details else None
            ),
            "green_then_loser_rate": (
                sum(
                    float(detail.get("net_pnl_usd")) < 0
                    and float(detail.get("mfe_usd") or 0.0) >= 0.10
                    for detail in details
                    if detail.get("net_pnl_usd") is not None
                ) / len(resolved)
                if resolved else None
            ),
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

    def _save(self) -> bool:
        if self.persist_path is None:
            return True
        temporary = self.persist_path.with_suffix(self.persist_path.suffix + ".tmp")
        try:
            self.persist_path.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(json.dumps(self._last_closed, sort_keys=True), encoding="utf-8")
            temporary.replace(self.persist_path)
            return True
        except OSError:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            return False

    def record_close(self, ticket: str, thesis_key: str, quote_fingerprint: str, closed_at: float) -> bool:
        if thesis_key and quote_fingerprint:
            previous = self._last_closed.get(thesis_key)
            self._last_closed[thesis_key] = (str(ticket), quote_fingerprint, float(closed_at))
            if self._save():
                return True
            if previous is None:
                self._last_closed.pop(thesis_key, None)
            else:
                self._last_closed[thesis_key] = previous
            return False
        return True

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
        if quote_fingerprint and not guard.record_close(ticket, meta.thesis_key, quote_fingerprint, closed_at):
            return CloseCleanup(False, False, basket_closed, "reentry_guard_persistence_failed")
        if not metadata_store.remove(ticket, clear_pending=True):
            return CloseCleanup(False, False, basket_closed, "ticket_metadata_persistence_failed")
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
    broker_facts = values.get("broker_close_facts")
    broker_facts = (
        dict(broker_facts)
        if isinstance(broker_facts, Mapping) and broker_facts.get("confirmed") is True
        else None
    )
    result = {
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
        "realized_net_usd": (
            broker_facts.get("realized_net_usd") if broker_facts else None
        ),
        "capture_ratio": (
            float(broker_facts["realized_net_usd"]) / float(values["peak_net_profit_usd"])
            if broker_facts
            and values.get("peak_net_profit_usd") is not None
            and float(values["peak_net_profit_usd"]) > 0
            else None
        ),
        "age_seconds": values.get("age_seconds"),
        "clips": values.get("clips", metadata.clip_sequence),
        "decision_reasons": values.get("decision_reasons", []),
        "ev": values.get("ev"),
        "cost_usd": broker_facts.get("cost_usd") if broker_facts else None,
        "turnover": values.get("turnover"),
        "regime": metadata.regime,
        "session": metadata.session,
        "slot_released": bool(slot_released),
        "basket_closed": bool(basket_closed),
        **{
            key: values[key]
            for key in (
                "evidence_status",
                "liquidation_mark",
                "liquidation_mark_side",
                "return_5s",
                "return_15s",
                "return_30s",
                "decision_snapshot",
                "remaining_ev_status",
                "spread_usd",
                "commission_usd",
            )
            if key in values
        },
    }
    if broker_facts:
        for key in (
            "gross_realized_pnl_usd", "commission_usd", "swap_usd", "fee_usd",
            "actual_close_price", "entry_slippage_usd", "exit_slippage_usd",
        ):
            if key in broker_facts:
                result[key] = broker_facts[key]
    return result


def quote_fingerprint(symbol: str, side: str, bid: float, ask: float) -> str:
    """Canonicalize the observed executable quote shared by close and entry."""
    return "|".join((
        str(symbol).upper(),
        str(side).lower(),
        format(float(bid), ".12g"),
        format(float(ask), ".12g"),
    ))
