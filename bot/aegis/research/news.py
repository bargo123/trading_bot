"""Economic-event blackout gate from an offline point-in-time calendar file.

The gate is `implemented` only against a calendar the caller supplies. Any live or
automatic news feed, and any headline sentiment model, stays `unavailable`:
`load_calendar` still raises. Rows must carry `as_of_utc` (when we knew the event)
so a backtest cannot use knowledge it would not have had at the bar.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import pandas as pd

from aegis.research.paths import RESEARCH_DIR
from aegis.research.capabilities import require_capability

CALENDAR_SCHEMA = "calendar.v1"
DEFAULT_CALENDAR_PATH = RESEARCH_DIR / "calendar" / "high_impact.jsonl"
REQUIRED_FIELDS = ("event_id", "currency", "impact", "event_utc", "as_of_utc")
BLOCKING_IMPACTS = frozenset({"high", "3"})


class CalendarError(ValueError):
    """Missing, non point-in-time, or unusable calendar input."""


def load_calendar() -> None:
    """Live/automatic news feed. Not present in this environment."""
    require_capability("news_calendar")


def _ts(value: Any, field: str) -> pd.Timestamp:
    try:
        stamp = pd.Timestamp(value)
    except (TypeError, ValueError) as exc:
        raise CalendarError(f"{field} is not a timestamp: {value!r}") from exc
    if stamp.tzinfo is None:
        raise CalendarError(f"{field} must be timezone-aware UTC: {value!r}")
    return stamp.tz_convert("UTC")


def _row(payload: Mapping[str, Any]) -> dict[str, Any]:
    missing = [f for f in REQUIRED_FIELDS if not str(payload.get(f) or "").strip()]
    if missing:
        raise CalendarError(f"calendar row missing {missing}; as_of_utc is mandatory")
    return {
        "schema": CALENDAR_SCHEMA,
        "event_id": str(payload["event_id"]),
        "title": str(payload.get("title") or payload["event_id"]),
        "currency": str(payload["currency"]).upper(),
        "impact": str(payload["impact"]).lower(),
        "event_utc": _ts(payload["event_utc"], "event_utc"),
        "as_of_utc": _ts(payload["as_of_utc"], "as_of_utc"),
    }


def load_calendar_file(path: Path) -> list[dict[str, Any]]:
    """Read a JSONL calendar dump. Revisions are kept; filtering happens per as-of."""
    source = Path(path)
    if not source.is_file():
        raise CalendarError(f"calendar file not found: {source}")
    rows: list[dict[str, Any]] = []
    for line in source.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise CalendarError(f"calendar line is not JSON: {line[:80]!r}") from exc
        if not isinstance(payload, Mapping):
            raise CalendarError("calendar rows must be JSON objects")
        rows.append(_row(payload))
    if not rows:
        raise CalendarError(f"calendar file is empty: {source}")
    return rows


def events_known_at(events: Iterable[Mapping[str, Any]], as_of: Any) -> list[dict[str, Any]]:
    """Keep only what was published by `as_of`; the newest revision of each event wins."""
    cutoff = _ts(as_of, "as_of")
    latest: dict[str, dict[str, Any]] = {}
    for event in events:
        row = dict(event)
        known = row.get("as_of_utc")
        known_ts = known if isinstance(known, pd.Timestamp) else _ts(known, "as_of_utc")
        if known_ts > cutoff:
            continue
        prior = latest.get(str(row["event_id"]))
        if prior is None or known_ts >= prior["as_of_utc"]:
            row["as_of_utc"] = known_ts
            latest[str(row["event_id"])] = row
    return sorted(latest.values(), key=lambda r: r["event_utc"])


def pair_currencies(symbol: str) -> tuple[str, str]:
    name = "".join(ch for ch in str(symbol).upper() if ch.isalpha())
    if len(name) != 6:
        raise CalendarError(f"cannot split symbol into two currencies: {symbol!r}")
    return name[:3], name[3:]


def in_blackout(
    symbol: str,
    when: Any,
    events: Sequence[Mapping[str, Any]],
    *,
    before_minutes: float,
    after_minutes: float,
    impacts: Iterable[str] = BLOCKING_IMPACTS,
) -> tuple[bool, str]:
    """True when `when` sits inside a blocking event window for either leg of the pair.

    An empty event list is treated as no calendar rather than a clear window, so
    callers cannot accidentally trade a news window because ingest failed.
    """
    if not events:
        raise CalendarError("no calendar events supplied; fail closed instead of trading blind")
    blocking = {str(i).lower() for i in impacts}
    legs = set(pair_currencies(symbol))
    bar = _ts(when, "when")
    before = pd.Timedelta(minutes=float(before_minutes))
    after = pd.Timedelta(minutes=float(after_minutes))
    for event in events:
        if str(event.get("impact", "")).lower() not in blocking:
            continue
        currency = str(event.get("currency", "")).upper()
        if currency not in legs:
            continue
        stamp = event.get("event_utc")
        stamp = stamp if isinstance(stamp, pd.Timestamp) else _ts(stamp, "event_utc")
        if stamp - before <= bar < stamp + after:
            return True, (
                f"{currency} {event.get('impact')} event {event.get('title')} "
                f"at {stamp.isoformat()} blocks {symbol}"
            )
    return False, "no blocking event window"
