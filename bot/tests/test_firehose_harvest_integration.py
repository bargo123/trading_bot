"""End-to-end observed Firehose lifecycle metric coverage."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from aegis.intel.firehose_harvest_research import analyze_ticket_lifecycles
from aegis.intel.firehose_turnover import TurnoverMetrics


def _confirmed_lifecycles() -> TurnoverMetrics:
    metrics = TurnoverMetrics()
    metrics.record_open("T1", opened_at=0.0, slot_capacity=2)
    metrics.record_exit_trace("T1", observed_at=20.0, mfe_usd=4.0)
    metrics.record_close(
        "T1", closed_at=30.0, gross_pnl_usd=3.5, net_pnl_usd=3.0,
        cost_usd=0.5, confirmed=True,
    )
    metrics.record_open("T2", opened_at=60.0, slot_capacity=2)
    metrics.record_exit_trace("T2", observed_at=100.0, mfe_usd=4.0)
    metrics.record_close(
        "T2", closed_at=120.0, gross_pnl_usd=3.0, net_pnl_usd=3.0,
        cost_usd=0.0, confirmed=True,
    )
    return metrics


def test_two_confirmed_round_trips_report_turnover_and_capture():
    metrics = _confirmed_lifecycles().snapshot(3600.0)

    assert metrics["round_trips_per_hour"] == pytest.approx(2.0)
    assert metrics["profit_capture_ratio"] == pytest.approx(0.75)
    assert metrics["median_hold_seconds"] == pytest.approx(45.0)
    assert metrics["p90_hold_seconds"] == pytest.approx(57.0)
    assert metrics["close_to_entry_interval_seconds"] == pytest.approx(30.0)
    assert metrics["slot_utilization"] == pytest.approx(0.0125)
    assert metrics["gross_profit_per_hour"] == pytest.approx(6.5)
    assert metrics["net_profit_per_hour"] == pytest.approx(6.0)
    assert metrics["cost_per_round_trip_usd"] == pytest.approx(0.25)


def test_failed_close_does_not_release_slot_or_count_round_trip():
    metrics = TurnoverMetrics()
    metrics.record_open("T1", opened_at=0.0, slot_capacity=1)
    metrics.record_close(
        "T1", closed_at=60.0, gross_pnl_usd=1.0, net_pnl_usd=0.8,
        cost_usd=0.2, confirmed=False,
    )

    snapshot = metrics.snapshot(120.0)

    assert snapshot["round_trips_per_hour"] == 0.0
    assert snapshot["slot_utilization"] is None
    assert metrics.active_tickets == {"T1"}


def test_analyzer_accepts_only_confirmed_firehose_close_lifecycles():
    events = [
        {
            "event": "firehose_open", "ticket": "T1", "timestamp": "2026-08-24T10:00:00+00:00",
            "side": "BUY", "slot_capacity": 1,
        },
        {
            "event": "firehose_exit_trace", "ticket": "T1", "timestamp": "2026-08-24T10:00:10+00:00",
            "pnl_usd": 3.0, "mfe_usd": 4.0, "cost_usd": 0.2, "liquidation_bid": 1.2,
        },
        {
            "event": "firehose_close", "ticket": "T1", "timestamp": "2026-08-24T10:00:20+00:00",
            "confirmed": True, "realized_net_usd": 3.0, "cost_usd": 0.2,
        },
    ]

    report = analyze_ticket_lifecycles(events)

    assert report["status"] == "OK"
    assert report["completed_tickets"] == 1
    assert report["profit_capture_ratio"] == pytest.approx(0.75)


def test_cli_marks_malformed_journal_as_incomplete_evidence(tmp_path):
    journal = tmp_path / "journal.jsonl"
    json_out = tmp_path / "report.json"
    markdown_out = tmp_path / "report.md"
    journal.write_bytes(b'\x00{"event":"start"}\n')

    result = subprocess.run(
        [
            sys.executable, str(Path(__file__).parents[1] / "scripts" / "analyze_firehose_harvest.py"),
            "--journal", str(journal), "--json-out", str(json_out),
            "--markdown-out", str(markdown_out),
        ],
        capture_output=True, text=True, check=False,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(json_out.read_text(encoding="utf-8"))["status"] == "INCOMPLETE_JOURNAL_EVIDENCE"
