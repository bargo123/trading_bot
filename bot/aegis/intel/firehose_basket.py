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

from aegis.sizing import ContractSpec


def _geometry_items(geometry: Mapping[str, Any]) -> tuple[tuple[str, Any], ...]:
    return tuple(sorted((str(key), value) for key, value in geometry.items()))


def _finite_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _positive_float(value: Any, field: str) -> float:
    number = _finite_float(value)
    if number is None or number <= 0:
        raise ValueError(field)
    return number


def _positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise ValueError(field)
    number = _finite_float(value)
    if number is None or number <= 0 or not number.is_integer():
        raise ValueError(field)
    return int(number)


def _finite_mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(field)
    copied: dict[str, Any] = {}
    for key, item in value.items():
        if isinstance(item, Mapping):
            copied[str(key)] = _finite_mapping(item, field)
        elif isinstance(item, (int, float)) and not isinstance(item, bool):
            number = _finite_float(item)
            if number is None:
                raise ValueError(field)
            copied[str(key)] = number
        else:
            copied[str(key)] = item
    return copied


def _trusted_ticks(contract: ContractSpec | None, symbol: str) -> tuple[float, float]:
    if contract is None or str(contract.symbol).upper() != str(symbol).upper():
        raise ValueError("missing_trusted_contract")
    return (
        _positive_float(contract.tick_value, "trusted_tick_value"),
        _positive_float(contract.tick_size, "trusted_tick_size"),
    )


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
        ticket_id = str(data["ticket_id"]).strip()
        trigger_id = str(data["trigger_id"]).strip()
        geometry = _finite_mapping(data["entry_geometry"], "entry_geometry")
        if not ticket_id or not trigger_id or not geometry:
            raise ValueError("ticket")
        return cls(
            ticket_id=ticket_id,
            trigger_id=trigger_id,
            clip_sequence=_positive_int(data["clip_sequence"], "clip_sequence"),
            volume=_positive_float(data["volume"], "volume"),
            initial_risk=_positive_float(data["initial_risk"], "initial_risk"),
            _entry_geometry=_geometry_items(geometry),
            cost_evidence=_finite_mapping(data["cost_evidence"], "cost_evidence"),
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
    def from_dict(cls, data: Mapping[str, Any], trusted_contract: ContractSpec | None) -> "BasketMetadata":
        basket_id = str(data["basket_id"]).strip()
        hypothesis_id = str(data["hypothesis_id"]).strip()
        family = str(data["family"]).strip()
        symbol = str(data["symbol"]).strip().upper()
        side = str(data["side"]).lower()
        regime = str(data["regime"]).strip()
        session = str(data["session"]).strip()
        geometry = _finite_mapping(data["entry_geometry"], "entry_geometry")
        if (
            not all((basket_id, hypothesis_id, family, symbol, regime, session))
            or side not in {"buy", "sell"} or not geometry
            or not isinstance(data.get("tickets", []), list)
        ):
            raise ValueError("basket")
        risk_budget = _positive_float(data["risk_budget"], "risk_budget")
        clip_cap = _positive_int(data["clip_cap"], "clip_cap")
        tick_value, tick_size = _trusted_ticks(trusted_contract, symbol)
        if (
            _positive_float(data["tick_value"], "tick_value") != tick_value
            or _positive_float(data["tick_size"], "tick_size") != tick_size
        ):
            raise ValueError("persisted_contract_mismatch")
        tickets = tuple(BasketTicket.from_dict(ticket) for ticket in data.get("tickets", []))
        if len(tickets) > clip_cap:
            raise ValueError("clip_cap")
        if tuple(ticket.clip_sequence for ticket in tickets) != tuple(range(1, len(tickets) + 1)):
            raise ValueError("clip_sequence")
        if len({ticket.ticket_id for ticket in tickets}) != len(tickets):
            raise ValueError("ticket_id")
        pnl = _finite_float(data.get("unrealized_pnl", 0.0))
        if pnl is None:
            raise ValueError("unrealized_pnl")
        for ticket in tickets:
            try:
                recomputed_risk = _broker_native_risk(
                    ticket.entry_geometry["entry_price"],
                    ticket.entry_geometry["stop_loss"],
                    ticket.volume,
                    tick_value,
                    tick_size,
                )
            except KeyError:
                raise ValueError("entry_geometry") from None
            if ticket.initial_risk != recomputed_risk:
                raise ValueError("initial_risk")
        return cls(
            basket_id=basket_id,
            hypothesis_id=hypothesis_id,
            family=family,
            symbol=symbol,
            side=side,
            risk_budget=risk_budget,
            clip_cap=clip_cap,
            tick_value=tick_value,
            tick_size=tick_size,
            regime=regime,
            session=session,
            _entry_geometry=_geometry_items(geometry),
            unrealized_pnl=pnl,
            tickets=tickets,
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
    *,
    now: float | None = None,
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
    trusted_now = _finite_float(time.time() if now is None else now)
    if pnl is None or observed_at is None or trusted_now is None:
        return _decision(basket, False, "missing_broker_pnl", risk)
    if observed_at > trusted_now or trusted_now - observed_at > 5.0:
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
    if not math.isfinite(risk) or risk <= 0:
        raise ValueError("invalid_broker_risk")
    return risk


class BasketMetadataStore:
    """Atomically persists exact basket-to-ticket ownership records."""

    def __init__(self, persist_path: Path, *, trusted_contract: ContractSpec | None = None):
        self.persist_path = Path(persist_path)
        self.trusted_contract = trusted_contract
        self.persist_path.parent.mkdir(parents=True, exist_ok=True)
        self._store: dict[str, BasketMetadata] = {}
        self._load()

    def _load(self) -> None:
        if not self.persist_path.is_file():
            return
        if self.trusted_contract is None:
            self._store = {}
            return
        try:
            data = json.loads(self.persist_path.read_text(encoding="utf-8"))
            if not isinstance(data, Mapping) or any(
                not isinstance(basket, Mapping) for basket in data.values()
            ):
                raise ValueError("persisted_basket_store")
            loaded: dict[str, BasketMetadata] = {}
            for basket_id, basket in data.items():
                restored = BasketMetadata.from_dict(basket, self.trusted_contract)
                if basket_id != restored.basket_id:
                    raise ValueError("basket_id")
                loaded[basket_id] = restored
            self._store = loaded
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
            trusted_value, trusted_size = _trusted_ticks(self.trusted_contract, symbol)
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
                or value != trusted_value or size != trusted_size
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
                if self.trusted_contract is None:
                    raise ValueError("missing_trusted_contract")
                raise KeyError(str(basket_id))
            _trusted_ticks(self.trusted_contract, basket.symbol)
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
