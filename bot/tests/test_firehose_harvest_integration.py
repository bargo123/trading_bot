"""End-to-end observed Firehose lifecycle metric coverage."""
from __future__ import annotations

import builtins
import json
import subprocess
import sys
from pathlib import Path

import pytest

from aegis.intel.firehose_harvest_research import analyze_ticket_lifecycles
from aegis.intel.firehose_turnover import TurnoverMetrics
from scripts import run_broker_paper


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

    assert snapshot["round_trips_per_hour"] is None
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


def test_confirmed_close_event_preserves_numeric_cost_and_net_pnl():
    from aegis.intel.fast_exit_runner import confirmed_close_event

    event = confirmed_close_event({
        "ticket": "T1",
        "symbol": "EURUSD",
        "confirmed": True,
        "cost_usd": 0.2,
        "realized_net_usd": 3.0,
        "mfe_usd": 4.0,
        "mae_usd": 0.5,
        "exit_reason": "target",
    })

    assert isinstance(event["cost_usd"], float)
    assert isinstance(event["realized_net_usd"], float)


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


def test_corrupt_journal_discards_complete_lifecycle_metrics_and_policy(tmp_path):
    journal = tmp_path / "journal.jsonl"
    replay = tmp_path / "replay.jsonl"
    json_out = tmp_path / "report.json"
    markdown_out = tmp_path / "report.md"
    complete = [
        {"event": "firehose_open", "ticket": "T1", "timestamp": "2026-08-24T10:00:00+00:00", "side": "BUY", "slot_capacity": 1},
        {"event": "firehose_exit_trace", "ticket": "T1", "timestamp": "2026-08-24T10:00:10+00:00", "pnl_usd": 3.0, "mfe_usd": 4.0, "cost_usd": 0.2, "liquidation_bid": 1.2},
        {"event": "firehose_close", "ticket": "T1", "timestamp": "2026-08-24T10:00:20+00:00", "confirmed": True, "realized_net_usd": 3.0, "cost_usd": 0.2},
    ]
    journal.write_bytes(b"\n".join(json.dumps(event).encode() for event in complete) + b"\n\x00corrupt\n")
    replay.write_text(json.dumps({"policy": "quick", "split": "oos", "quote_observed": True, "gross_pnl_usd": 1.0, "cost_usd": 0.1}) + "\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(Path(__file__).parents[1] / "scripts" / "analyze_firehose_harvest.py"), "--journal", str(journal), "--replay", str(replay), "--json-out", str(json_out), "--markdown-out", str(markdown_out)],
        capture_output=True, text=True, check=False,
    )

    report = json.loads(json_out.read_text(encoding="utf-8"))
    assert result.returncode == 0, result.stderr
    assert report["status"] == "INCOMPLETE_JOURNAL_EVIDENCE"
    assert report["completed_tickets"] == 0
    assert report["round_trips_per_hour"] is None
    assert report["profit_capture_ratio"] is None
    assert report["buckets"]["0.70_usd"]["status"] == "INCOMPLETE_JOURNAL_EVIDENCE"
    assert report["buckets"]["0.70_usd"]["realized_net_usd"] is None
    assert report["policy_comparison"] == {"status": "NO_EVIDENCE", "selection_metric": "oos_expectancy_after_cost", "winner": None}
    assert "round_trips_per_hour: `INCOMPLETE_JOURNAL_EVIDENCE`" in markdown_out.read_text(encoding="utf-8")


def test_runner_heartbeat_emits_metrics_without_research_or_council_calls(tmp_path, monkeypatch):
    calls = []
    imported = []
    original_import = builtins.__import__

    class MetricsSpy:
        def snapshot(self, now):
            calls.append(now)
            return {"round_trips_per_hour": None}

    class ForbiddenSystem:
        def __getattr__(self, name):
            raise AssertionError(f"forbidden system accessed: {name}")

    def guarded_import(name, *args, **kwargs):
        imported.append(name)
        if name.startswith(("aegis.research_factory", "ai_council")):
            raise AssertionError(f"forbidden system imported: {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setitem(sys.modules, "aegis.research_factory.core", ForbiddenSystem())
    monkeypatch.setitem(sys.modules, "ai_council.agents", ForbiddenSystem())
    monkeypatch.setattr(builtins, "__import__", guarded_import)
    heartbeat = tmp_path / "heartbeat.json"

    run_broker_paper.write_runner_heartbeat(
        heartbeat, pid=7, symbols=["EURUSD"], qty=0.01, metrics=MetricsSpy(), now=123.0,
    )

    assert calls == [123.0]
    assert not [name for name in imported if name.startswith(("aegis.research_factory", "ai_council"))]
    payload = json.loads(heartbeat.read_text(encoding="utf-8"))
    assert payload["firehose_turnover"] == {"round_trips_per_hour": None}
    assert payload["prediction_scope"] == "GITHUB_TOOLS_AND_BOOK_ALGORITHMS_ONLY"
    assert payload["council_influence"] is False
    assert payload["research_factory_influence"] is False
    assert payload["book_algorithm_registry_count"] == 616
    assert payload["book_ranking_role"] == "secondary_tiebreak_after_capture_confidence_and_ev"
