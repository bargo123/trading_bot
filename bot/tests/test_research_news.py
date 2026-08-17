from __future__ import annotations

import json
from pathlib import Path

import pytest

from aegis.research.capabilities import CapabilityUnavailable
from aegis.research.news import (
    CalendarError,
    events_known_at,
    in_blackout,
    load_calendar,
    load_calendar_file,
    pair_currencies,
)


def _rows() -> list[dict]:
    return [
        {
            "event_id": "us_cpi_2026_08",
            "title": "US CPI",
            "currency": "USD",
            "impact": "high",
            "event_utc": "2026-08-17T12:30:00+00:00",
            "as_of_utc": "2026-08-10T00:00:00+00:00",
        },
        {
            "event_id": "eu_hicp_2026_08",
            "title": "Euro area HICP",
            "currency": "EUR",
            "impact": "high",
            "event_utc": "2026-08-18T09:00:00+00:00",
            "as_of_utc": "2026-08-10T00:00:00+00:00",
        },
        {
            "event_id": "jp_minor",
            "title": "JP minor survey",
            "currency": "JPY",
            "impact": "low",
            "event_utc": "2026-08-17T12:30:00+00:00",
            "as_of_utc": "2026-08-10T00:00:00+00:00",
        },
    ]


def _write(path: Path, rows: list[dict]) -> Path:
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return path


def test_live_news_feed_stays_unavailable():
    with pytest.raises(CapabilityUnavailable):
        load_calendar()


def test_calendar_file_requires_point_in_time_as_of(tmp_path: Path):
    bad = _rows()[0].copy()
    bad.pop("as_of_utc")
    path = _write(tmp_path / "cal.jsonl", [bad])
    with pytest.raises(CalendarError, match="as_of_utc"):
        load_calendar_file(path)


def test_events_known_at_hides_future_knowledge(tmp_path: Path):
    rows = _rows()
    rows.append(
        {
            "event_id": "surprise_speech",
            "title": "Unscheduled speech",
            "currency": "USD",
            "impact": "high",
            "event_utc": "2026-08-17T12:30:00+00:00",
            "as_of_utc": "2026-08-17T12:00:00+00:00",
        }
    )
    events = load_calendar_file(_write(tmp_path / "cal.jsonl", rows))
    early = events_known_at(events, "2026-08-11T00:00:00+00:00")
    assert {e["event_id"] for e in early} == {"us_cpi_2026_08", "eu_hicp_2026_08", "jp_minor"}
    later = events_known_at(events, "2026-08-17T12:10:00+00:00")
    assert "surprise_speech" in {e["event_id"] for e in later}


def test_revision_supersedes_earlier_as_of(tmp_path: Path):
    rows = _rows()
    rows.append(
        {
            "event_id": "us_cpi_2026_08",
            "title": "US CPI (rescheduled)",
            "currency": "USD",
            "impact": "high",
            "event_utc": "2026-08-17T13:30:00+00:00",
            "as_of_utc": "2026-08-12T00:00:00+00:00",
        }
    )
    events = load_calendar_file(_write(tmp_path / "cal.jsonl", rows))
    known = events_known_at(events, "2026-08-13T00:00:00+00:00")
    cpi = [e for e in known if e["event_id"] == "us_cpi_2026_08"]
    assert len(cpi) == 1
    assert cpi[0]["event_utc"].isoformat() == "2026-08-17T13:30:00+00:00"


def test_pair_currencies_splits_six_letter_symbols():
    assert pair_currencies("EURUSD") == ("EUR", "USD")
    assert pair_currencies("AUDSGD") == ("AUD", "SGD")
    with pytest.raises(CalendarError, match="symbol"):
        pair_currencies("XAU")


def test_blackout_blocks_either_leg_and_respects_impact(tmp_path: Path):
    events = events_known_at(
        load_calendar_file(_write(tmp_path / "cal.jsonl", _rows())),
        "2026-08-11T00:00:00+00:00",
    )
    blocked, why = in_blackout(
        "EURUSD",
        "2026-08-17T12:25:00+00:00",
        events,
        before_minutes=15,
        after_minutes=15,
    )
    assert blocked
    assert "USD" in why

    blocked_eur, _ = in_blackout(
        "EURCAD",
        "2026-08-18T09:05:00+00:00",
        events,
        before_minutes=15,
        after_minutes=15,
    )
    assert blocked_eur

    clear, _ = in_blackout(
        "GBPJPY",
        "2026-08-17T12:25:00+00:00",
        events,
        before_minutes=15,
        after_minutes=15,
    )
    assert not clear

    far, _ = in_blackout(
        "EURUSD",
        "2026-08-17T10:00:00+00:00",
        events,
        before_minutes=15,
        after_minutes=15,
    )
    assert not far


def test_blackout_fails_closed_without_calendar():
    with pytest.raises(CalendarError, match="fail closed"):
        in_blackout("EURUSD", "2026-08-17T12:25:00+00:00", [], before_minutes=15, after_minutes=15)
