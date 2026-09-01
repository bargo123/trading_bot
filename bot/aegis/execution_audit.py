"""FIRE execution audit: classify what a FIRE actually produced.

FIRE means immediate market execution. This module turns a place_order result
into a deterministic execution status so the runner can:
  * never treat a pending order (10008) as a filled position,
  * never retry an uncertain request that may have already filled
    (order_send returned None, network timeout),
  * measure the decision -> request -> fill -> confirmed chain.

Pure functions only; no broker imports, no I/O. Tests live in
tests/test_execution_audit.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping, Sequence

#: MT5 retcodes that mean the order was PLACED but NOT filled (pending order).
PENDING_RETCODES = frozenset({10008})

#: Retcodes that mean immediate market execution happened (DONE / DONE_PARTIAL).
FILLED_RETCODES = frozenset({10009, 10010})

#: Retcodes that are definitive rejections: retrying is safe (nothing was sent).
REJECT_RETCODES = frozenset({10004, 10006, 10007, 10011, 10012, 10013, 10014,
                             10015, 10016, 10017, 10018, 10019, 10020, 10021,
                             10022, 10023, 10024, 10025, 10026, 10027, 10028,
                             10029, 10030, 10031, 10032, 10033, 10034, 10035,
                             10036, 10037, 10038, 10039, 10040, 10041, 10042,
                             10043, 10044, 10045, 10046, 10047, 10048, 10049})

#: Message markers for uncertain outcomes: the request may have reached the
#: broker even though we saw no usable response.
UNCERTAIN_MARKERS = (
    "returned None",
    "timed out",
    "timeout",
    "connection lost",
    "disconnected",
)

#: Execution statuses (the vocabulary in the task spec).
STATUS_REQUEST_SENT = "REQUEST_SENT"
STATUS_ORDER_ACCEPTED = "ORDER_ACCEPTED"
STATUS_DEAL_EXECUTED = "DEAL_EXECUTED"
STATUS_PARTIALLY_FILLED = "PARTIALLY_FILLED"
STATUS_POSITION_CONFIRMED = "POSITION_CONFIRMED"
STATUS_REJECTED = "REJECTED"
STATUS_CANCELLED = "CANCELLED"
STATUS_EXPIRED = "EXPIRED"
STATUS_TIMEOUT = "TIMEOUT"
STATUS_RECONCILIATION_FAILED = "RECONCILIATION_FAILED"
STATUS_MISMATCH = "FIRE_EXECUTION_MISMATCH"


def retcode_from(message: str | None) -> int | None:
    """Extract an MT5 retcode int from a broker message, if present."""
    import re

    text = str(message or "")
    for match in re.finditer(r"(?<!\d)(\d{5})(?!\d)", text):
        return int(match.group(1))
    return None


def is_uncertain(message: str | None) -> bool:
    """True when we cannot prove the request was rejected - retry must reconcile."""
    text = str(message or "").casefold()
    return any(str(marker).casefold() in text for marker in UNCERTAIN_MARKERS)


def classify(
    *,
    ok: bool,
    message: str | None,
    filled: bool | None = None,
    positions_before: Sequence[Any] | None = None,
    positions_after: Sequence[Any] | None = None,
) -> dict[str, Any]:
    """Classify a FIRE attempt into a deterministic execution status.

    Returns a dict with ``status`` and ``duplicate_risk`` flags. The runner
    must never blindly resend when ``status`` is POSITION_CONFIRMED or an
    uncertain state where positions_after shows new exposure.
    """
    text = str(message or "")
    retcode = retcode_from(text)
    if ok and filled is False and retcode in PENDING_RETCODES:
        return {
            "status": STATUS_MISMATCH,
            "retcode": retcode,
            "duplicate_risk": False,
            "detail": "market FIRE produced a pending order (10008); no position opened",
        }
    if ok and filled is True and retcode in FILLED_RETCODES:
        return {
            "status": STATUS_DEAL_EXECUTED,
            "retcode": retcode,
            "duplicate_risk": False,
            "detail": "market execution confirmed by broker retcode",
        }
    if ok and filled is True and retcode is None:
        # Engines that do not surface retcodes but report filled.
        return {
            "status": STATUS_DEAL_EXECUTED,
            "retcode": None,
            "duplicate_risk": False,
            "detail": "engine reported filled",
        }
    if ok and not filled:
        # Unknown-but-accepted state. Check whether exposure actually appeared.
        grew = _exposure_grew(positions_before, positions_after)
        if grew:
            return {
                "status": STATUS_POSITION_CONFIRMED,
                "retcode": retcode,
                "duplicate_risk": False,
                "detail": "position appeared despite ambiguous broker reply",
            }
        return {
            "status": STATUS_ORDER_ACCEPTED,
            "retcode": retcode,
            "duplicate_risk": True,
            "detail": "accepted but not filled and no position appeared",
        }
    # not ok
    if is_uncertain(message):
        grew = _exposure_grew(positions_before, positions_after)
        if grew:
            return {
                "status": STATUS_POSITION_CONFIRMED,
                "retcode": retcode,
                "duplicate_risk": False,
                "detail": "uncertain reply but exposure appeared - do not resend",
            }
        return {
            "status": STATUS_TIMEOUT,
            "retcode": retcode,
            "duplicate_risk": True,
            "detail": "uncertain reply, no exposure - reconcile before resend",
        }
    if retcode in {10019, 10020}:
        return {
            "status": STATUS_REJECTED,
            "retcode": retcode,
            "duplicate_risk": False,
            "detail": "margin/no-money rejection - safe to retry later",
        }
    if retcode in REJECT_RETCODES or retcode is None:
        return {
            "status": STATUS_REJECTED,
            "retcode": retcode,
            "duplicate_risk": False,
            "detail": "definitive rejection - safe to retry",
        }
    return {
        "status": STATUS_REJECTED,
        "retcode": retcode,
        "duplicate_risk": False,
        "detail": "rejected by broker",
    }


def _exposure_grew(before: Sequence[Any] | None, after: Sequence[Any] | None) -> bool:
    if before is None or after is None:
        return False
    return len(after) > len(before)


@dataclass
class FireLatency:
    """Decision -> request -> fill -> confirmed timestamp chain for one FIRE."""

    decision_ts: float = 0.0
    quote_ts: float = 0.0
    request_ts: float = 0.0
    response_ts: float = 0.0
    confirmed_ts: float = 0.0

    def __post_init__(self) -> None:
        # Broker Quote.time is a timezone-aware datetime; latency arithmetic
        # and serialization use epoch seconds throughout this module.
        if isinstance(self.quote_ts, datetime):
            self.quote_ts = float(self.quote_ts.timestamp())

    def decision_to_request_ms(self) -> float | None:
        if self.decision_ts and self.request_ts:
            return (self.request_ts - self.decision_ts) * 1000.0
        return None

    def request_to_fill_ms(self) -> float | None:
        if self.request_ts and self.response_ts:
            return (self.response_ts - self.request_ts) * 1000.0
        return None

    def decision_to_confirmed_ms(self) -> float | None:
        if self.decision_ts and self.confirmed_ts:
            return (self.confirmed_ts - self.decision_ts) * 1000.0
        return None

    def as_dict(self) -> dict[str, Any]:
        # The runner updates quote_ts after a broker refresh; normalize that
        # assignment as well as constructor values before serializing.
        self.__post_init__()
        return {
            "decision_ts": round(self.decision_ts, 3),
            "quote_ts": round(self.quote_ts, 3),
            "request_ts": round(self.request_ts, 3),
            "response_ts": round(self.response_ts, 3),
            "confirmed_ts": round(self.confirmed_ts, 3),
            "latency_decision_to_request_ms": (
                round(self.decision_to_request_ms(), 3) if self.decision_to_request_ms() is not None else None
            ),
            "latency_request_to_fill_ms": (
                round(self.request_to_fill_ms(), 3) if self.request_to_fill_ms() is not None else None
            ),
            "latency_decision_to_confirmed_ms": (
                round(self.decision_to_confirmed_ms(), 3) if self.decision_to_confirmed_ms() is not None else None
            ),
        }


@dataclass
class PendingRetryGuard:
    """Per-symbol dedup for FIRE sends: never resend the same tag blindly.

    The runner records each request with its client_tag. If a resend is
    attempted for a tag that was already sent and the outcome was uncertain,
    the guard forces a position reconciliation first.
    """

    sent: dict[str, tuple[str, float]] = field(default_factory=dict)

    def mark_sent(self, symbol: str, client_tag: str, now: float) -> None:
        self.sent[str(symbol).upper()] = (str(client_tag), float(now))

    def was_sent(self, symbol: str, client_tag: str, within_s: float = 60.0, now: float | None = None) -> bool:
        entry = self.sent.get(str(symbol).upper())
        if entry is None:
            return False
        tag, ts = entry
        if now is None:
            import time

            now = time.time()
        return bool(tag) and tag == str(client_tag) and (float(now) - ts) <= within_s

    def clear(self, symbol: str) -> None:
        self.sent.pop(str(symbol).upper(), None)


def summarize_execution(events: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Aggregate execution events from a journal for reporting."""
    counts: dict[str, int] = {}
    for event in events:
        status = str(event.get("execution_status") or STATUS_REQUEST_SENT)
        counts[status] = counts.get(status, 0) + 1
    return {
        "events": len(events),
        "statuses": counts,
        "mismatches": int(counts.get(STATUS_MISMATCH, 0)),
        "uncertain": int(counts.get(STATUS_TIMEOUT, 0)),
    }
