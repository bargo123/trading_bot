"""Persistent Firehose basket ownership and fail-closed clip limits."""
from __future__ import annotations

import json
import math
import os
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping


def _geometry_items(geometry: Mapping[str, Any]) -> tuple[tuple[str, Any], ...]:
    return tuple(sorted((str(key), value) for key, value in geometry.items()))


def _finite_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


@dataclass(frozen=True)
class BasketTicket:
    """An immutable record of one broker ticket owned by a basket."""

    ticket_id: str
    trigger_id: str
    clip_sequence: int
    volume: float
    initial_risk: float
    _entry_geometry: tuple[tuple[str, Any], ...]
    cost_evidence: dict[str, Any]
    regime: str
    session: str

    @property
    def entry_geometry(self) -> dict[str, Any]:
        return dict(self._entry_geometry)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticket_id": self.ticket_id,
            "trigger_id": self.trigger_id,
            "clip_sequence": self.clip_sequence,
            "volume": self.volume,
            "initial_risk": self.initial_risk,
            "entry_geometry": self.entry_geometry,
            "cost_evidence": self.cost_evidence,
            "regime": self.regime,
            "session": self.session,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "BasketTicket":
        return cls(
            ticket_id=str(data["ticket_id"]),
            trigger_id=str(data["trigger_id"]),
            clip_sequence=int(data["clip_sequence"]),
            volume=float(data["volume"]),
            initial_risk=float(data["initial_risk"]),
            _entry_geometry=_geometry_items(data["entry_geometry"]),
            cost_evidence=dict(data["cost_evidence"]),
            regime=str(data["regime"]),
            session=str(data["session"]),
        )


@dataclass(frozen=True)
class BasketMetadata:
    """Exact, restart-safe ownership and risk state for one basket."""

    basket_id: str
    hypothesis_id: str
    family: str
    symbol: str
    side: str
    risk_budget: float
    clip_cap: int
    tick_value: float
    tick_size: float
    regime: str
    session: str
    _entry_geometry: tuple[tuple[str, Any], ...]
    unrealized_pnl: float
    tickets: tuple[BasketTicket, ...] = ()

    @property
    def entry_geometry(self) -> dict[str, Any]:
        return dict(self._entry_geometry)

    @property
    def ticket_ids(self) -> tuple[str, ...]:
        return tuple(ticket.ticket_id for ticket in self.tickets)

    @property
    def total_risk(self) -> float:
        return sum(ticket.initial_risk for ticket in self.tickets)

    def to_dict(self) -> dict[str, Any]:
        return {
            "basket_id": self.basket_id,
            "hypothesis_id": self.hypothesis_id,
            "family": self.family,
            "symbol": self.symbol,
            "side": self.side,
            "risk_budget": self.risk_budget,
            "clip_cap": self.clip_cap,
            "tick_value": self.tick_value,
            "tick_size": self.tick_size,
            "regime": self.regime,
            "session": self.session,
            "entry_geometry": self.entry_geometry,
            "unrealized_pnl": self.unrealized_pnl,
            "tickets": [ticket.to_dict() for ticket in self.tickets],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "BasketMetadata":
        return cls(
            basket_id=str(data["basket_id"]),
            hypothesis_id=str(data["hypothesis_id"]),
            family=str(data["family"]),
            symbol=str(data["symbol"]),
            side=str(data["side"]),
            risk_budget=float(data["risk_budget"]),
            clip_cap=int(data["clip_cap"]),
            tick_value=float(data["tick_value"]),
            tick_size=float(data["tick_size"]),
            regime=str(data["regime"]),
            session=str(data["session"]),
            _entry_geometry=_geometry_items(data["entry_geometry"]),
            unrealized_pnl=float(data.get("unrealized_pnl", 0.0)),
            tickets=tuple(BasketTicket.from_dict(ticket) for ticket in data.get("tickets", [])),
        )


@dataclass(frozen=True)
class BasketDecision:
    """The fail-closed result of assessing a proposed basket clip."""

    allowed: bool
    reason: str
    proposed_risk: float
    total_risk: float

    def as_tuple(self) -> tuple[bool, str]:
        return self.allowed, self.reason


def _decision(basket: BasketMetadata, allowed: bool, reason: str, proposed_risk: float) -> tuple[bool, str]:
    return BasketDecision(allowed, reason, proposed_risk, basket.total_risk).as_tuple()


def can_add_clip(
    basket: BasketMetadata,
    continuation: Mapping[str, Any] | None,
    proposed_risk: float,
) -> tuple[bool, str]:
    """Return whether a fresh, same-side clip is allowed for this basket."""
    try:
        risk = float(proposed_risk)
    except (TypeError, ValueError):
        return _decision(basket, False, "invalid_risk", 0.0)
    if not math.isfinite(risk) or risk <= 0:
        return _decision(basket, False, "invalid_risk", risk)
    risk_budget = _finite_float(basket.risk_budget)
    total_risk = _finite_float(basket.total_risk)
    if risk_budget is None or risk_budget <= 0:
        return _decision(basket, False, "invalid_risk_budget", risk)
    if total_risk is None or total_risk < 0:
        return _decision(basket, False, "invalid_risk", risk)
    if not isinstance(continuation, Mapping):
        return _decision(basket, False, "no_validated_policy", risk)
    if str(continuation.get("side", "")).lower() != basket.side:
        return _decision(basket, False, "opposite_side_self_hedge", risk)
    if len(basket.tickets) >= basket.clip_cap:
        return _decision(basket, False, "clip_cap", risk)
    artifact = continuation.get("policy_artifact")
    if not isinstance(artifact, Mapping) or not (artifact.get("validated") and artifact.get("complete")):
        return _decision(basket, False, "no_validated_policy", risk)
    broker_pnl = continuation.get("broker_pnl")
    if not isinstance(broker_pnl, Mapping):
        return _decision(basket, False, "missing_broker_pnl", risk)
    pnl = _finite_float(broker_pnl.get("unrealized_pnl"))
    observed_at = _finite_float(broker_pnl.get("observed_at"))
    evaluated_at = _finite_float(continuation.get("evaluated_at"))
    if pnl is None or observed_at is None or evaluated_at is None:
        return _decision(basket, False, "missing_broker_pnl", risk)
    if observed_at > evaluated_at or evaluated_at - observed_at > 5.0:
        return _decision(basket, False, "stale_broker_pnl", risk)
    if pnl < 0:
        return _decision(basket, False, "losing_basket", risk)
    trigger_id = str(continuation.get("trigger_id", "")).strip()
    if not continuation.get("fresh_trigger") or not trigger_id or trigger_id in {
        ticket.trigger_id for ticket in basket.tickets
    }:
        return _decision(basket, False, "stale_trigger", risk)
    if not continuation.get("positive_evidence"):
        return _decision(basket, False, "no_positive_continuation", risk)
    if not continuation.get("normal_spread"):
        return _decision(basket, False, "abnormal_spread", risk)
    remaining_ev = _finite_float(continuation.get("remaining_ev"))
    if remaining_ev is None or remaining_ev <= 0:
        return _decision(basket, False, "nonpositive_remaining_ev", risk)
    if continuation.get("adverse_selection"):
        return _decision(basket, False, "adverse_selection", risk)
    if total_risk + risk > risk_budget:
        return _decision(basket, False, "risk_budget", risk)
    return _decision(basket, True, "allowed", risk)


def _broker_native_risk(
    entry_price: float,
    stop_loss: float,
    volume: float,
    tick_value: float,
    tick_size: float,
) -> float:
    values = tuple(_finite_float(value) for value in (
        entry_price, stop_loss, volume, tick_value, tick_size,
    ))
    if any(value is None for value in values):
        raise ValueError("invalid_broker_risk")
    entry, stop, lots, value, size = values
    if lots <= 0 or value <= 0 or size <= 0:
        raise ValueError("invalid_broker_risk")
    try:
        ticks = abs(Decimal(str(entry)) - Decimal(str(stop))) / Decimal(str(size))
        risk = float(ticks * Decimal(str(value)) * Decimal(str(lots)))
    except (ArithmeticError, ValueError):
        raise ValueError("invalid_broker_risk") from None
    if not math.isfinite(risk):
        raise ValueError("invalid_broker_risk")
    return risk


class BasketMetadataStore:
    """Atomically persists exact basket-to-ticket ownership records."""

    def __init__(self, persist_path: Path):
        self.persist_path = Path(persist_path)
        self.persist_path.parent.mkdir(parents=True, exist_ok=True)
        self._store: dict[str, BasketMetadata] = {}
        self._load()

    def _load(self) -> None:
        if not self.persist_path.is_file():
            return
        try:
            data = json.loads(self.persist_path.read_text(encoding="utf-8"))
            self._store = {
                str(basket_id): BasketMetadata.from_dict(basket)
                for basket_id, basket in data.items()
                if isinstance(basket, Mapping)
            }
        except (OSError, json.JSONDecodeError, TypeError, ValueError, KeyError):
            self._store = {}

    def _save(self) -> None:
        payload = json.dumps(
            {basket_id: basket.to_dict() for basket_id, basket in self._store.items()},
            indent=2,
            sort_keys=True,
        )
        temp_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.persist_path.parent,
                prefix=f".{self.persist_path.name}.", suffix=".tmp", delete=False,
            ) as handle:
                temp_path = handle.name
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, self.persist_path)
        except OSError:
            if temp_path:
                try:
                    Path(temp_path).unlink(missing_ok=True)
                except OSError:
                    pass
            raise

    @contextmanager
    def _admission_lock(self):
        """Serialize reload, validation, and persistence across processes."""
        lock_path = self.persist_path.with_name(f".{self.persist_path.name}.lock")
        with lock_path.open("a+b") as handle:
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                while True:
                    try:
                        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                        break
                    except OSError:
                        time.sleep(0.01)
                try:
                    yield
                finally:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def create_basket(
        self,
        *,
        basket_id: str,
        hypothesis_id: str,
        family: str,
        symbol: str,
        side: str,
        risk_budget: float,
        clip_cap: int,
        tick_value: float,
        tick_size: float,
        regime: str,
        session: str,
        entry_geometry: Mapping[str, Any],
        unrealized_pnl: float = 0.0,
    ) -> BasketMetadata:
        with self._admission_lock():
            self._load()
            basket_id = str(basket_id).strip()
            if not basket_id or basket_id in self._store:
                raise ValueError("basket_id")
            if str(side).lower() not in {"buy", "sell"}:
                raise ValueError("side")
            budget = _finite_float(risk_budget)
            value = _finite_float(tick_value)
            size = _finite_float(tick_size)
            pnl = _finite_float(unrealized_pnl)
            if (
                budget is None or budget <= 0 or value is None or value <= 0
                or size is None or size <= 0 or pnl is None
                or isinstance(clip_cap, bool) or int(clip_cap) != clip_cap or int(clip_cap) <= 0
            ):
                raise ValueError("invalid_basket_limits")
            basket = BasketMetadata(
                basket_id=basket_id,
                hypothesis_id=str(hypothesis_id),
                family=str(family),
                symbol=str(symbol).upper(),
                side=str(side).lower(),
                risk_budget=budget,
                clip_cap=int(clip_cap),
                tick_value=value,
                tick_size=size,
                regime=str(regime),
                session=str(session),
                _entry_geometry=_geometry_items(entry_geometry),
                unrealized_pnl=pnl,
            )
            self._store[basket_id] = basket
            try:
                self._save()
            except Exception:
                self._store.pop(basket_id, None)
                raise
            return basket

    def get_basket(self, basket_id: str) -> BasketMetadata | None:
        return self._store.get(str(basket_id))

    def get_ticket(self, ticket_id: str) -> BasketTicket | None:
        ticket_id = str(ticket_id)
        for basket in self._store.values():
            for ticket in basket.tickets:
                if ticket.ticket_id == ticket_id:
                    return ticket
        return None

    def record_ticket(
        self,
        basket_id: str,
        *,
        ticket_id: str,
        trigger_id: str,
        clip_sequence: int,
        entry_price: float,
        stop_loss: float,
        volume: float,
        cost_evidence: Mapping[str, Any],
        regime: str,
        session: str,
        continuation: Mapping[str, Any] | None = None,
    ) -> BasketTicket:
        with self._admission_lock():
            self._load()
            basket = self.get_basket(basket_id)
            if basket is None:
                raise KeyError(str(basket_id))
            if self.get_ticket(ticket_id) is not None:
                raise ValueError("ticket_id")
            if clip_sequence != len(basket.tickets) + 1:
                raise ValueError("clip_sequence")
            risk = _broker_native_risk(entry_price, stop_loss, volume, basket.tick_value, basket.tick_size)
            allowed, reason = can_add_clip(basket, continuation, risk) if basket.tickets else (
                basket.total_risk + risk <= basket.risk_budget,
                "allowed" if basket.total_risk + risk <= basket.risk_budget else "risk_budget",
            )
            if not allowed:
                raise ValueError(reason)
            ticket = BasketTicket(
                ticket_id=str(ticket_id),
                trigger_id=str(trigger_id),
                clip_sequence=int(clip_sequence),
                volume=float(volume),
                initial_risk=risk,
                _entry_geometry=_geometry_items({"entry_price": float(entry_price), "stop_loss": float(stop_loss)}),
                cost_evidence=dict(cost_evidence),
                regime=str(regime),
                session=str(session),
            )
            updated = BasketMetadata(
                **{**basket.__dict__, "tickets": (*basket.tickets, ticket)}
            )
            self._store[basket.basket_id] = updated
            try:
                self._save()
            except Exception:
                self._store[basket.basket_id] = basket
                raise
            return ticket
