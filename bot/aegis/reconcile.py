"""Deal-cursor reconciliation library.

Not wired into the live paper runner. Shadow and later authorized integration
may consume these types. Do not import this from intel/decide.py.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from math import isfinite
from pathlib import Path
from typing import Any, Literal, Mapping, Sequence


def _timestamp(value: str) -> float:
    text = str(value or "").strip()
    if not text:
        raise ValueError("deal time is required")
    normalized = text[:-1] + "+00:00" if text.endswith(("Z", "z")) else text
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError("deal time must include a timezone")
    return parsed.astimezone(timezone.utc).timestamp()


def _positive_milliseconds(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed if parsed > 0 else None


def _identity_key(value: str) -> tuple[int, int | str, str]:
    text = str(value or "")
    try:
        return (0, int(text), text)
    except ValueError:
        return (1, text, text)


@dataclass
class ReconcileCursor:
    processed_tickets: set[str] = field(default_factory=set)
    newest_time: str = ""

    def dump(self) -> dict[str, Any]:
        return {
            "processed_tickets": sorted(self.processed_tickets),
            "newest_time": self.newest_time,
        }

    def load_json(self, path: Path) -> bool:
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
            if not isinstance(raw, dict) or set(raw) != {
                "processed_tickets",
                "newest_time",
            }:
                return False
            tickets = raw["processed_tickets"]
            newest_time = raw["newest_time"]
            if (
                not isinstance(tickets, list)
                or any(
                    not isinstance(ticket, str) or not ticket or ticket == "0"
                    for ticket in tickets
                )
                or len(set(tickets)) != len(tickets)
                or not isinstance(newest_time, str)
                or (bool(tickets) and not newest_time)
            ):
                return False
            if newest_time:
                _timestamp(newest_time)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return False

        self.processed_tickets = set(tickets)
        self.newest_time = newest_time
        return True

    def save_json(self, path: Path) -> None:
        payload = self.dump()
        if any(not ticket or ticket == "0" for ticket in self.processed_tickets):
            raise ValueError("deal cursor ticket identity is invalid")
        if self.processed_tickets and not self.newest_time:
            raise ValueError("deal cursor watermark is required for processed tickets")
        if self.newest_time:
            _timestamp(self.newest_time)
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(destination.name + ".tmp")
        try:
            temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            temporary.replace(destination)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


@dataclass(frozen=True)
class BrokerMutationIntent:
    kind: Literal["entry", "close"]
    symbol: str
    side: Literal["buy", "sell"]
    client_tag: str
    created_at: str
    cursor_watermark: str
    outcome: Literal["prepared", "accepted", "ambiguous"] = "prepared"
    broker_order_id: str = ""
    position_id: str = ""
    ticket: str = ""
    requested_quantity: float = 0.0

    def __post_init__(self) -> None:
        if self.kind not in {"entry", "close"}:
            raise ValueError("broker mutation intent kind is invalid")
        if self.side not in {"buy", "sell"}:
            raise ValueError("broker mutation intent side is invalid")
        if not str(self.symbol or "").strip():
            raise ValueError("broker mutation intent symbol is required")
        if self.kind == "entry" and not str(self.client_tag or "").strip():
            raise ValueError("entry mutation intent client_tag is required")
        if self.kind == "close" and not (
            str(self.position_id or "").strip() or str(self.ticket or "").strip()
        ):
            raise ValueError("close mutation intent position identity is required")
        if self.outcome not in {"prepared", "accepted", "ambiguous"}:
            raise ValueError("broker mutation intent outcome is invalid")
        _timestamp(self.created_at)
        if self.cursor_watermark:
            _timestamp(self.cursor_watermark)
        for label, value in (
            ("broker_order_id", self.broker_order_id),
            ("position_id", self.position_id),
            ("ticket", self.ticket),
        ):
            if value == "0":
                raise ValueError(f"broker mutation intent {label} is invalid")
        if (
            isinstance(self.requested_quantity, bool)
            or not isinstance(self.requested_quantity, (int, float))
            or not isfinite(float(self.requested_quantity))
            or float(self.requested_quantity) < 0
        ):
            raise ValueError("broker mutation intent requested_quantity is invalid")
        if self.kind == "close" and float(self.requested_quantity) <= 0:
            raise ValueError("close mutation intent requested_quantity is required")
        if self.kind == "entry" and float(self.requested_quantity) != 0:
            raise ValueError("entry mutation intent requested_quantity must be zero")

    def dump(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "symbol": self.symbol,
            "side": self.side,
            "client_tag": self.client_tag,
            "created_at": self.created_at,
            "cursor_watermark": self.cursor_watermark,
            "outcome": self.outcome,
            "broker_order_id": self.broker_order_id,
            "position_id": self.position_id,
            "ticket": self.ticket,
            "requested_quantity": float(self.requested_quantity),
        }

    @classmethod
    def load(cls, raw: Mapping[str, Any]) -> "BrokerMutationIntent":
        expected = {
            "kind",
            "symbol",
            "side",
            "client_tag",
            "created_at",
            "cursor_watermark",
            "outcome",
            "broker_order_id",
            "position_id",
            "ticket",
            "requested_quantity",
        }
        if not isinstance(raw, Mapping) or set(raw) != expected:
            raise ValueError("broker mutation intent schema is invalid")
        string_fields = expected - {"requested_quantity"}
        if any(not isinstance(raw[name], str) for name in string_fields):
            raise ValueError("broker mutation intent fields must be strings")
        if isinstance(raw["requested_quantity"], bool) or not isinstance(
            raw["requested_quantity"], (int, float)
        ):
            raise ValueError("broker mutation intent requested_quantity is invalid")
        return cls(**{name: raw[name] for name in expected})


@dataclass(frozen=True)
class ReconciledDeal:
    ticket: str
    order: str
    symbol: str
    is_exit: bool
    pnl: float
    close_reason: str
    time: str
    position: str = ""
    time_msc: int | None = None
    entry: int = 0
    side: str = ""
    comment: str = ""

    @property
    def is_entry(self) -> bool:
        return self.entry in {0, 2}


def close_reason(comment: str, reason: Any = None) -> str:
    try:
        broker_reason = int(reason)
    except (TypeError, ValueError, OverflowError):
        broker_reason = None
    if broker_reason == 5:
        return "tp"
    if broker_reason == 4:
        return "sl"
    lowered = str(comment or "").casefold()
    if "[tp" in lowered:
        return "tp"
    if "[sl" in lowered:
        return "sl"
    if "flatten" in lowered or "manual" in lowered:
        return "manual"
    return "unknown"


def reconcile_new_deals(
    deals: Sequence[Mapping[str, Any]], cursor: ReconcileCursor
) -> list[ReconciledDeal]:
    prepared: list[
        tuple[tuple[float, tuple[int, int | str, str]], ReconciledDeal]
    ] = []
    seen_tickets: set[str] = set()
    for row in deals:
        ticket = str(row.get("ticket") or "")
        symbol = str(row.get("symbol") or "")
        if not symbol:
            continue
        if not ticket or ticket == "0":
            raise ValueError("deal ticket identity is invalid")
        if ticket in cursor.processed_tickets:
            continue
        if ticket in seen_tickets:
            raise ValueError(f"duplicate deal ticket {ticket}")
        seen_tickets.add(ticket)
        order = str(row.get("order") or "")
        position = str(row.get("position") or row.get("position_id") or "")
        if not order or order == "0":
            raise ValueError(f"deal {ticket} order identity is invalid")
        time_text = str(row.get("time") or "")
        parsed_time = _timestamp(time_text)
        time_msc = _positive_milliseconds(row.get("time_msc"))
        chronology = time_msc / 1000.0 if time_msc is not None else parsed_time
        try:
            entry = int(row.get("entry"))
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"deal {ticket} entry is invalid") from exc
        if entry not in {0, 1, 2, 3}:
            raise ValueError(f"deal {ticket} entry is invalid")
        try:
            pnl = sum(
                float(row.get(name) or 0.0)
                for name in ("profit", "commission", "swap", "fee")
            )
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"deal {ticket} pnl is invalid") from exc
        if not isfinite(pnl):
            raise ValueError(f"deal {ticket} pnl is not finite")
        event = ReconciledDeal(
            ticket=ticket,
            order=order,
            symbol=symbol,
            is_exit=entry in {1, 2, 3},
            pnl=pnl,
            close_reason=close_reason(
                str(row.get("comment") or ""), row.get("reason")
            ),
            time=time_text,
            position=position,
            time_msc=time_msc,
            entry=entry,
            side=str(row.get("side") or ""),
            comment=str(row.get("comment") or ""),
        )
        prepared.append(
            ((chronology, _identity_key(ticket)), event)
        )

    prepared.sort(key=lambda item: item[0])
    output = [event for _, event in prepared]
    if not output:
        return []

    cursor.processed_tickets.update(event.ticket for event in output)
    newest = max(output, key=lambda event: (
        event.time_msc / 1000.0 if event.time_msc is not None else _timestamp(event.time),
        _identity_key(event.ticket),
    ))
    if not cursor.newest_time or _timestamp(newest.time) > _timestamp(cursor.newest_time):
        cursor.newest_time = newest.time
    return output
