"""Fixture-only tests for read-only Firehose harvest evidence analysis."""
from __future__ import annotations

import json

import pytest

from aegis.intel.firehose_harvest_research import (
    analyze_ticket_lifecycles,
    compare_exit_policies,
    write_harvest_report,
)


COMPLETE_TICKET_EVENTS = [
    {
        "event": "firehose_open",
        "ticket": "T1",
        "timestamp": "2026-08-24T10:00:00+00:00",
        "slot_capacity": 2,
    },
    {
        "event": "firehose_exit_trace",
        "ticket": "T1",
        "timestamp": "2026-08-24T10:00:10+00:00",
        "pnl_usd": 0.70,
        "mfe_usd": 0.80,
        "cost_usd": 0.05,
    },
    {
        "event": "pm_exit",
        "ticket": "T1",
        "timestamp": "2026-08-24T10:00:20+00:00",
        "confirmed": True,
        "realized_net_usd": 0.55,
        "cost_usd": 0.05,
    },
]

INCOMPLETE_REPLAY_ROWS = [
    {"policy": "quick_harvest", "split": "oos", "net_pnl_usd": 0.40},
]

COSTED_OOS_ROWS = [
    {
        "policy": "highest_win_rate_policy",
        "split": "oos",
        "quote_observed": True,
        "cost_usd": 0.05,
        "gross_pnl_usd": 0.10,
    },
    {
        "policy": "highest_win_rate_policy",
        "split": "oos",
        "quote_observed": True,
        "cost_usd": 0.05,
        "gross_pnl_usd": 0.10,
    },
    {
        "policy": "higher_expectancy_policy",
        "split": "oos",
        "quote_observed": True,
        "cost_usd": 0.05,
        "gross_pnl_usd": 0.80,
    },
    {
        "policy": "higher_expectancy_policy",
        "split": "oos",
        "quote_observed": True,
        "cost_usd": 0.05,
        "gross_pnl_usd": -0.20,
    },
]


def test_incomplete_ticket_is_reported_not_inferred():
    report = analyze_ticket_lifecycles([{"event": "firehose_open", "ticket": "T1"}])

    assert report["completed_tickets"] == 0
    assert report["incomplete_tickets"] == ["T1"]
    assert report["buckets"]["0.70_usd"]["count"] == 0
    assert report["status"] == "NO_COMPLETE_LIFECYCLE_EVIDENCE"


def test_complete_ticket_reports_peak_capture_and_hold_metrics():
    report = analyze_ticket_lifecycles(COMPLETE_TICKET_EVENTS)
    bucket = report["buckets"]["0.70_usd"]

    assert report["status"] == "OK"
    assert bucket["count"] == 1
    assert bucket["realized_net_usd"] == pytest.approx(0.55)
    assert bucket["peak_unrealized_usd"] == pytest.approx(0.80)
    assert bucket["profit_capture_ratio"] == pytest.approx(0.6875)
    assert bucket["post_threshold_hold_seconds"] == pytest.approx(10.0)


def test_missing_complete_fields_are_incomplete_not_zeroes():
    events = COMPLETE_TICKET_EVENTS[:-1] + [
        {
            "event": "pm_exit",
            "ticket": "T1",
            "timestamp": "2026-08-24T10:00:20+00:00",
            "confirmed": True,
            "realized_net_usd": 0.55,
        }
    ]

    report = analyze_ticket_lifecycles(events)

    assert report["status"] == "NO_COMPLETE_LIFECYCLE_EVIDENCE"
    assert report["completed_tickets"] == 0
    assert report["incomplete_tickets"] == ["T1"]


def test_policy_comparison_rejects_missing_cost_or_quote_evidence():
    result = compare_exit_policies(INCOMPLETE_REPLAY_ROWS)

    assert result["status"] == "NO_EVIDENCE"


def test_policy_comparison_ranks_by_oos_expectancy_not_win_rate():
    result = compare_exit_policies(COSTED_OOS_ROWS)

    assert result["selection_metric"] == "oos_expectancy_after_cost"
    assert result["winner"] == "higher_expectancy_policy"
    assert result["winner"] != "highest_win_rate_policy"


def test_report_writer_only_writes_requested_report_paths(tmp_path):
    report = analyze_ticket_lifecycles(COMPLETE_TICKET_EVENTS)
    json_path = tmp_path / "report.json"
    markdown_path = tmp_path / "report.md"

    write_harvest_report(report, json_path, markdown_path)

    assert json.loads(json_path.read_text(encoding="utf-8"))["status"] == "OK"
    assert "Firehose Harvest Evidence" in markdown_path.read_text(encoding="utf-8")
