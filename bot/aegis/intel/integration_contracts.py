"""Versioned, fail-closed contracts for the governed Firehose boundary.

The contracts in this module are deliberately transport-neutral.  They let
research, replay, monitoring, and broker-lifecycle code exchange immutable
records without importing an execution engine.  ``EventLedger`` is the
causal boundary used before a record is allowed into a deterministic replay
or decision stream; quarantined records are audit evidence only.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import math
import time
from typing import Any, Callable, ClassVar, Iterable, Mapping
from uuid import uuid4


class ContractValidationError(ValueError):
    """Raised when a contract cannot carry the required common identity."""


def _finite_timestamp(value: Any) -> float:
    if isinstance(value, datetime):
        item = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        result = item.timestamp()
    elif isinstance(value, str):
        try:
            item = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except (TypeError, ValueError) as exc:
            raise ContractValidationError("invalid_timestamp") from exc
        if item.tzinfo is None:
            item = item.replace(tzinfo=timezone.utc)
        result = item.timestamp()
    else:
        try:
            result = float(value)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ContractValidationError("invalid_timestamp") from exc
    if not math.isfinite(result) or result < 0:
        raise ContractValidationError("invalid_timestamp")
    return result


def _text(value: Any) -> str:
    return str(value or "").strip()


@dataclass(frozen=True)
class FirehoseContract:
    """Common identity shared by every AEGIS integration message."""

    event_id: str = field(default_factory=lambda: uuid4().hex)
    correlation_id: str = ""
    strategy_id: str = ""
    experiment_id: str = ""
    basket_id: str = ""
    symbol: str = ""
    event_ts: float = field(default_factory=time.time)
    source: str = ""
    reason: str = ""
    status: str = "CREATED"
    payload: Mapping[str, Any] = field(default_factory=dict)

    contract_type: ClassVar[str] = "FirehoseContract"
    schema_version: ClassVar[str] = "aegis.firehose_contract.v1"

    def __post_init__(self) -> None:
        event_id = _text(self.event_id) or uuid4().hex
        correlation_id = _text(self.correlation_id)
        symbol = _text(self.symbol).upper()
        source = _text(self.source)
        status = _text(self.status).upper()
        if not correlation_id:
            raise ContractValidationError("missing_correlation_id")
        if not symbol:
            raise ContractValidationError("missing_symbol")
        if not source:
            raise ContractValidationError("missing_source")
        if not status:
            raise ContractValidationError("missing_status")
        object.__setattr__(self, "event_id", event_id)
        object.__setattr__(self, "correlation_id", correlation_id)
        object.__setattr__(self, "strategy_id", _text(self.strategy_id))
        object.__setattr__(self, "experiment_id", _text(self.experiment_id))
        object.__setattr__(self, "basket_id", _text(self.basket_id))
        object.__setattr__(self, "symbol", symbol)
        object.__setattr__(self, "event_ts", _finite_timestamp(self.event_ts))
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "reason", _text(self.reason))
        object.__setattr__(self, "status", status)
        object.__setattr__(
            self,
            "payload",
            dict(self.payload) if isinstance(self.payload, Mapping) else {},
        )

    @property
    def timestamp(self) -> float:
        """Compatibility alias for transports that call the event time timestamp."""
        return self.event_ts

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "FirehoseContract":
        if not isinstance(value, Mapping):
            raise ContractValidationError("invalid_contract_mapping")
        raw = dict(value)
        requested_type = _text(
            raw.get("contract_type") or raw.get("contract") or raw.get("type")
        )
        if requested_type and requested_type.lower() != cls.contract_type.lower():
            raise ContractValidationError("contract_type_mismatch")
        payload = dict(raw.get("payload") or {}) if isinstance(raw.get("payload"), Mapping) else {}
        common = {
            "event_id", "correlation_id", "strategy_id", "experiment_id",
            "basket_id", "symbol", "event_ts", "timestamp", "time", "ts",
            "observed_at", "source", "reason", "status", "payload",
            "contract_type", "contract", "type", "schema_version",
        }
        for key, item in raw.items():
            if key not in common:
                payload.setdefault(key, item)
        timestamp = raw.get("event_ts")
        if timestamp is None:
            timestamp = raw.get("timestamp", raw.get("time", raw.get("ts", raw.get("observed_at"))))
        return cls(
            event_id=_text(raw.get("event_id")) or uuid4().hex,
            correlation_id=_text(raw.get("correlation_id")),
            strategy_id=_text(raw.get("strategy_id")),
            experiment_id=_text(raw.get("experiment_id")),
            basket_id=_text(raw.get("basket_id")),
            symbol=_text(raw.get("symbol")),
            event_ts=timestamp,
            source=_text(raw.get("source")),
            reason=_text(raw.get("reason")),
            status=_text(raw.get("status")) or "CREATED",
            payload=payload,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_type": self.contract_type,
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "correlation_id": self.correlation_id,
            "strategy_id": self.strategy_id,
            "experiment_id": self.experiment_id,
            "basket_id": self.basket_id,
            "symbol": self.symbol,
            "event_ts": self.event_ts,
            "timestamp": self.event_ts,
            "source": self.source,
            "reason": self.reason,
            "status": self.status,
            "payload": dict(self.payload),
        }


class MarketEvent(FirehoseContract):
    contract_type = "MarketEvent"
    schema_version = "aegis.market_event.v1"


class BrokerSpecSnapshot(FirehoseContract):
    contract_type = "BrokerSpecSnapshot"
    schema_version = "aegis.broker_spec_snapshot.v1"


class ResearchSource(FirehoseContract):
    contract_type = "ResearchSource"
    schema_version = "aegis.research_source.v1"


class ExperimentSpec(FirehoseContract):
    contract_type = "ExperimentSpec"
    schema_version = "aegis.experiment_spec.v1"


class CandidateStrategy(FirehoseContract):
    contract_type = "CandidateStrategy"
    schema_version = "aegis.candidate_strategy.v1"


class StrategySignal(FirehoseContract):
    contract_type = "StrategySignal"
    schema_version = "aegis.strategy_signal.v1"


class BasketIntent(FirehoseContract):
    contract_type = "BasketIntent"
    schema_version = "aegis.basket_intent.v1"


class BasketState(FirehoseContract):
    contract_type = "BasketState"
    schema_version = "aegis.basket_state.v1"


class OrderIntent(FirehoseContract):
    contract_type = "OrderIntent"
    schema_version = "aegis.order_intent.v1"


class PendingOrderIntent(FirehoseContract):
    contract_type = "PendingOrderIntent"
    schema_version = "aegis.pending_order_intent.v1"


class PreflightResult(FirehoseContract):
    contract_type = "PreflightResult"
    schema_version = "aegis.preflight_result.v1"


class OrderAcknowledgement(FirehoseContract):
    contract_type = "OrderAcknowledgement"
    schema_version = "aegis.order_acknowledgement.v1"


class FillEvent(FirehoseContract):
    contract_type = "FillEvent"
    schema_version = "aegis.fill_event.v1"


class PositionEvent(FirehoseContract):
    contract_type = "PositionEvent"
    schema_version = "aegis.position_event.v1"


class CloseIntent(FirehoseContract):
    contract_type = "CloseIntent"
    schema_version = "aegis.close_intent.v1"


class ConfirmedClose(FirehoseContract):
    contract_type = "ConfirmedClose"
    schema_version = "aegis.confirmed_close.v1"


class ReplayFill(FirehoseContract):
    contract_type = "ReplayFill"
    schema_version = "aegis.replay_fill.v1"


class ExecutionReport(FirehoseContract):
    contract_type = "ExecutionReport"
    schema_version = "aegis.execution_report.v1"


class ReconciliationEvent(FirehoseContract):
    contract_type = "ReconciliationEvent"
    schema_version = "aegis.reconciliation_event.v1"


class ConfirmedOutcome(FirehoseContract):
    contract_type = "ConfirmedOutcome"
    schema_version = "aegis.confirmed_outcome.v1"


class PromotionDecision(FirehoseContract):
    contract_type = "PromotionDecision"
    schema_version = "aegis.promotion_decision.v1"


CONTRACT_CLASSES: dict[str, type[FirehoseContract]] = {
    item.contract_type: item
    for item in (
        MarketEvent,
        BrokerSpecSnapshot,
        ResearchSource,
        ExperimentSpec,
        CandidateStrategy,
        StrategySignal,
        BasketIntent,
        BasketState,
        OrderIntent,
        PendingOrderIntent,
        PreflightResult,
        OrderAcknowledgement,
        FillEvent,
        PositionEvent,
        CloseIntent,
        ConfirmedClose,
        ReplayFill,
        ExecutionReport,
        ReconciliationEvent,
        ConfirmedOutcome,
        PromotionDecision,
    )
}
CONTRACT_TYPES = tuple(CONTRACT_CLASSES)


# These are deliberately data-only lifecycle vocabularies.  Broker methods
# remain owned by run_broker_paper.py/MT5Engine; this module only prevents an
# audit stream from claiming a fill or close before the corresponding event.
BASKET_STATES = (
    "CREATED",
    "OPENING",
    "OPEN",
    "ADDING",
    "REDUCING",
    "REVERSAL_PENDING",
    "CANCELLING_PENDING",
    "CLOSING",
    "RECONCILING",
    "CLOSED",
    "FAILED",
    "QUARANTINED",
)
ORDER_STATES = (
    "INTENDED",
    "PREFLIGHT_REJECTED",
    "READY",
    "SENT",
    "ACKNOWLEDGED",
    "PARTIALLY_FILLED",
    "FILLED",
    "CANCEL_REQUESTED",
    "CANCELLED",
    "CLOSE_REQUESTED",
    "CLOSED",
    "REJECTED",
    "UNKNOWN",
    "RECONCILIATION_REQUIRED",
)

_BASKET_TRANSITIONS = {
    "CREATED": {"OPENING", "FAILED", "QUARANTINED"},
    "OPENING": {"OPEN", "RECONCILING", "FAILED", "QUARANTINED"},
    "OPEN": {"ADDING", "REDUCING", "REVERSAL_PENDING", "CLOSING", "RECONCILING", "QUARANTINED"},
    "ADDING": {"OPEN", "RECONCILING", "FAILED", "QUARANTINED"},
    "REDUCING": {"OPEN", "CLOSING", "RECONCILING", "FAILED", "QUARANTINED"},
    "REVERSAL_PENDING": {"CANCELLING_PENDING", "CLOSING", "RECONCILING", "FAILED", "QUARANTINED"},
    "CANCELLING_PENDING": {"OPEN", "CLOSING", "RECONCILING", "FAILED", "QUARANTINED"},
    "CLOSING": {"RECONCILING", "CLOSED", "FAILED", "QUARANTINED"},
    "RECONCILING": {"OPEN", "CLOSED", "FAILED", "QUARANTINED"},
    "CLOSED": set(),
    "FAILED": {"RECONCILING", "QUARANTINED"},
    "QUARANTINED": {"RECONCILING", "FAILED"},
}
_ORDER_TRANSITIONS = {
    "INTENDED": {"PREFLIGHT_REJECTED", "READY", "REJECTED", "UNKNOWN"},
    "PREFLIGHT_REJECTED": set(),
    "READY": {"SENT", "PREFLIGHT_REJECTED", "REJECTED", "UNKNOWN"},
    "SENT": {"ACKNOWLEDGED", "REJECTED", "UNKNOWN", "RECONCILIATION_REQUIRED"},
    "ACKNOWLEDGED": {"PARTIALLY_FILLED", "FILLED", "REJECTED", "UNKNOWN", "RECONCILIATION_REQUIRED"},
    "PARTIALLY_FILLED": {"FILLED", "CANCEL_REQUESTED", "CLOSE_REQUESTED", "UNKNOWN", "RECONCILIATION_REQUIRED"},
    # A broker acknowledgement of the opening fill is not a close.  The
    # runner must emit CLOSE_REQUESTED and receive a separate close event
    # before the audit stream can claim CLOSED.
    "FILLED": {"CLOSE_REQUESTED", "UNKNOWN", "RECONCILIATION_REQUIRED"},
    "CANCEL_REQUESTED": {"CANCELLED", "PARTIALLY_FILLED", "FILLED", "UNKNOWN", "RECONCILIATION_REQUIRED"},
    "CANCELLED": set(),
    "CLOSE_REQUESTED": {"CLOSED", "UNKNOWN", "RECONCILIATION_REQUIRED"},
    "CLOSED": set(),
    "REJECTED": set(),
    "UNKNOWN": {"RECONCILIATION_REQUIRED"},
    "RECONCILIATION_REQUIRED": {"PARTIALLY_FILLED", "FILLED", "CANCELLED", "CLOSED", "REJECTED", "UNKNOWN"},
}


@dataclass(frozen=True)
class StateTransition:
    """Result of a data-only lifecycle transition attempt."""

    accepted: bool
    previous: str
    current: str
    reason: str
    sequence: int


class LifecycleStateMachine:
    """Validate basket/order state changes without granting execution power."""

    def __init__(self, kind: str, *, initial: str | None = None) -> None:
        normalized_kind = str(kind or "").strip().lower()
        if normalized_kind not in {"basket", "order"}:
            raise ValueError("unknown_lifecycle_kind")
        self.kind = normalized_kind
        self.states = BASKET_STATES if normalized_kind == "basket" else ORDER_STATES
        default = "CREATED" if normalized_kind == "basket" else "INTENDED"
        candidate = str(initial or default).strip().upper()
        if candidate not in self.states:
            raise ValueError("invalid_initial_state")
        self._state = candidate
        self._sequence = 0
        self._history: list[StateTransition] = []

    @property
    def state(self) -> str:
        return self._state

    @property
    def history(self) -> tuple[StateTransition, ...]:
        return tuple(self._history)

    def can_transition(self, next_state: str) -> tuple[bool, str]:
        candidate = str(next_state or "").strip().upper()
        if candidate not in self.states:
            return False, "unknown_state"
        transitions = _BASKET_TRANSITIONS if self.kind == "basket" else _ORDER_TRANSITIONS
        if candidate not in transitions.get(self._state, set()):
            return False, f"invalid_transition:{self._state}->{candidate}"
        return True, "allowed"

    def transition(self, next_state: str) -> StateTransition:
        candidate = str(next_state or "").strip().upper()
        allowed, reason = self.can_transition(candidate)
        self._sequence += 1
        previous = self._state
        if allowed:
            self._state = candidate
        result = StateTransition(
            accepted=allowed,
            previous=previous,
            current=self._state,
            reason=reason,
            sequence=self._sequence,
        )
        self._history.append(result)
        return result


class OrderedEventBus:
    """Small synchronous causal bus used by replay/observability consumers."""

    def __init__(self, *, ledger: EventLedger | None = None, max_quote_age_s: float = 5.0) -> None:
        self.ledger = ledger or EventLedger(max_quote_age_s=max_quote_age_s)
        self._subscribers: list[Callable[[FirehoseContract, LedgerResult], None]] = []

    def subscribe(self, callback: Callable[[FirehoseContract, LedgerResult], None]) -> None:
        if not callable(callback):
            raise TypeError("subscriber_not_callable")
        self._subscribers.append(callback)

    def publish(
        self,
        value: FirehoseContract | Mapping[str, Any],
        *,
        now_ts: float | None = None,
    ) -> LedgerResult:
        result = self.ledger.append(value, now_ts=now_ts)
        if result.accepted:
            event = self.ledger.replay()[-1]
            for callback in tuple(self._subscribers):
                callback(event, result)
        return result

    def replay(self) -> tuple[FirehoseContract, ...]:
        return self.ledger.replay()

    def quarantine(self) -> tuple[dict[str, Any], ...]:
        return self.ledger.quarantine()


def make_contract_event(
    contract_cls: type[FirehoseContract],
    *,
    event_id: str | None = None,
    correlation_id: str,
    symbol: str,
    event_ts: Any,
    source: str,
    status: str = "CREATED",
    reason: str = "",
    strategy_id: str = "",
    experiment_id: str = "",
    basket_id: str = "",
    payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Serialize one versioned lifecycle contract for the runner journal.

    This helper is transport-only: it creates an audit record and cannot send,
    modify, or close a broker position.
    """
    if not isinstance(contract_cls, type) or not issubclass(contract_cls, FirehoseContract):
        raise ContractValidationError("invalid_contract_class")
    contract = contract_cls(
        event_id=event_id or uuid4().hex,
        correlation_id=correlation_id,
        strategy_id=strategy_id,
        experiment_id=experiment_id,
        basket_id=basket_id,
        symbol=symbol,
        event_ts=event_ts,
        source=source,
        reason=reason,
        status=status,
        payload=dict(payload or {}),
    )
    return {
        "event": "firehose_contract.v1",
        "contract_type": contract.contract_type,
        "contract": contract.to_dict(),
    }


@dataclass(frozen=True)
class LedgerResult:
    accepted: bool
    event_id: str | None
    reason_code: str | None
    sequence: int | None


def _event_class(value: Mapping[str, Any]) -> type[FirehoseContract] | None:
    requested = _text(value.get("contract_type") or value.get("contract") or value.get("type"))
    if requested in CONTRACT_CLASSES:
        return CONTRACT_CLASSES[requested]
    normalized = requested.lower().replace("_", "").replace(".", "")
    for name, contract_cls in CONTRACT_CLASSES.items():
        if normalized == name.lower().replace("_", ""):
            return contract_cls
    event_name = _text(value.get("event")).lower()
    if event_name in {"quote", "tick", "raw_tick", "quote_sample", "market_event"}:
        return MarketEvent
    if event_name in {"order_check", "preflight"}:
        return PreflightResult
    if event_name in {"order", "firehose_funnel.v1", "execution_report"}:
        return ExecutionReport
    if event_name in {"confirmed_close_finalization", "firehose_close"}:
        return ConfirmedClose
    return None


class EventLedger:
    """Ordered causal ledger that quarantines unusable events.

    This is intentionally a small synchronous boundary.  Producers may be
    asynchronous, but the runner/replay consumer receives only the accepted
    monotonic sequence.  It never mutates broker state.
    """

    def __init__(
        self,
        *,
        max_quote_age_s: float = 5.0,
        future_tolerance_s: float = 0.0,
    ) -> None:
        self.max_quote_age_s = max(0.0, float(max_quote_age_s))
        self.future_tolerance_s = max(0.0, float(future_tolerance_s))
        self._accepted: list[FirehoseContract] = []
        self._quarantined: list[dict[str, Any]] = []
        self._seen_ids: set[str] = set()
        self._last_event_ts_by_correlation: dict[str, float] = {}
        self._last_sequence_by_correlation: dict[str, int] = {}
        self._identity_by_correlation: dict[str, tuple[str, str | None]] = {}
        self._reason_counts: dict[str, int] = {}

    def _quarantine(
        self,
        value: Any,
        reason_code: str,
        *,
        event_id: str | None = None,
    ) -> LedgerResult:
        self._reason_counts[reason_code] = self._reason_counts.get(reason_code, 0) + 1
        if isinstance(value, FirehoseContract):
            row: Any = value.to_dict()
            event_id = event_id or value.event_id
        elif isinstance(value, Mapping):
            row = dict(value)
            event_id = event_id or _text(row.get("event_id")) or None
        else:
            row = {"value_type": type(value).__name__}
        self._quarantined.append({
            "event_id": event_id,
            "reason_code": reason_code,
            "event": row,
        })
        return LedgerResult(False, event_id, reason_code, None)

    @staticmethod
    def _market_values(event: FirehoseContract) -> tuple[Any, Any]:
        payload = event.payload
        return payload.get("bid"), payload.get("ask")

    def append(
        self,
        value: FirehoseContract | Mapping[str, Any],
        *,
        now_ts: float | None = None,
    ) -> LedgerResult:
        raw_event_id = (
            value.event_id if isinstance(value, FirehoseContract)
            else _text(value.get("event_id")) if isinstance(value, Mapping)
            else None
        )
        if isinstance(value, FirehoseContract):
            event = value
        elif isinstance(value, Mapping):
            event_cls = _event_class(value)
            if event_cls is None:
                return self._quarantine(value, "unknown_contract", event_id=raw_event_id)
            try:
                event = event_cls.from_mapping(value)
            except ContractValidationError as exc:
                return self._quarantine(
                    value,
                    str(exc) or "contract_validation_error",
                    event_id=raw_event_id,
                )
        else:
            return self._quarantine(value, "invalid_event")

        if event.event_id in self._seen_ids:
            return self._quarantine(event, "duplicate_event")
        observed_now = _finite_timestamp(time.time() if now_ts is None else now_ts)
        if event.event_ts > observed_now + self.future_tolerance_s:
            return self._quarantine(event, "future_event")

        if isinstance(event, MarketEvent):
            if self.max_quote_age_s > 0 and observed_now - event.event_ts > self.max_quote_age_s:
                return self._quarantine(event, "stale_quote")
            bid, ask = self._market_values(event)
            try:
                bid_value = float(bid)
                ask_value = float(ask)
            except (TypeError, ValueError, OverflowError):
                return self._quarantine(event, "missing_bid_ask")
            if not math.isfinite(bid_value) or not math.isfinite(ask_value) or bid_value <= 0 or ask_value <= 0:
                return self._quarantine(event, "invalid_quote")
            if ask_value < bid_value:
                return self._quarantine(event, "crossed_market")
            decision_ts = event.payload.get(
                "decision_ts",
                event.payload.get("decision_timestamp", event.payload.get("decision_time")),
            )
            if decision_ts is not None:
                try:
                    if event.event_ts > _finite_timestamp(decision_ts) + self.future_tolerance_s:
                        return self._quarantine(event, "quote_after_decision")
                except ContractValidationError:
                    return self._quarantine(event, "invalid_decision_timestamp")

        last_event_ts = self._last_event_ts_by_correlation.get(event.correlation_id)
        if last_event_ts is not None and event.event_ts < last_event_ts:
            return self._quarantine(event, "out_of_order")

        sequence = event.payload.get("sequence")
        if sequence is not None:
            try:
                sequence_value = int(sequence)
            except (TypeError, ValueError, OverflowError):
                return self._quarantine(event, "event_sequence_invalid")
            previous_sequence = self._last_sequence_by_correlation.get(event.correlation_id)
            if previous_sequence is not None and sequence_value <= previous_sequence:
                return self._quarantine(event, "event_sequence_invalid")
        session = _text(event.payload.get("session")) or None
        identity = (event.symbol, session)
        previous_identity = self._identity_by_correlation.get(event.correlation_id)
        if previous_identity is not None and previous_identity != identity:
            return self._quarantine(event, "symbol_session_mismatch")

        self._seen_ids.add(event.event_id)
        self._accepted.append(event)
        self._last_event_ts_by_correlation[event.correlation_id] = event.event_ts
        self._identity_by_correlation[event.correlation_id] = identity
        if sequence is not None:
            self._last_sequence_by_correlation[event.correlation_id] = int(sequence)
        return LedgerResult(True, event.event_id, None, len(self._accepted))

    def replay(self) -> tuple[FirehoseContract, ...]:
        """Return the accepted sequence in deterministic arrival order."""
        return tuple(self._accepted)

    def quarantine(self) -> tuple[dict[str, Any], ...]:
        return tuple(dict(item) for item in self._quarantined)

    def stats(self) -> dict[str, Any]:
        return {
            "accepted": len(self._accepted),
            "quarantined": len(self._quarantined),
            "reason_counts": dict(self._reason_counts),
            "last_event_ts": (
                max(self._last_event_ts_by_correlation.values())
                if self._last_event_ts_by_correlation else None
            ),
            "last_event_ts_by_correlation": dict(self._last_event_ts_by_correlation),
        }


__all__ = [
    "BASKET_STATES",
    "BasketIntent",
    "BasketState",
    "BrokerSpecSnapshot",
    "CandidateStrategy",
    "CloseIntent",
    "ConfirmedClose",
    "ConfirmedOutcome",
    "CONTRACT_CLASSES",
    "CONTRACT_TYPES",
    "ContractValidationError",
    "EventLedger",
    "ExecutionReport",
    "ExperimentSpec",
    "FillEvent",
    "FirehoseContract",
    "LifecycleStateMachine",
    "LedgerResult",
    "make_contract_event",
    "MarketEvent",
    "OrderAcknowledgement",
    "OrderIntent",
    "ORDER_STATES",
    "OrderedEventBus",
    "PendingOrderIntent",
    "PositionEvent",
    "PreflightResult",
    "PromotionDecision",
    "ReconciliationEvent",
    "ReplayFill",
    "ResearchSource",
    "StrategySignal",
    "StateTransition",
]
