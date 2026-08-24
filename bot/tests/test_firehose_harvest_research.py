"""Fixture-only tests for read-only Firehose harvest evidence analysis."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

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
        "side": "BUY",
        "slot_capacity": 2,
    },
    {
        "event": "firehose_exit_trace",
        "ticket": "T1",
        "timestamp": "2026-08-24T10:00:10+00:00",
        "pnl_usd": 0.70,
        "mfe_usd": 0.80,
        "cost_usd": 0.05,
        "liquidation_bid": 1.2345,
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


def test_missing_applicable_liquidation_quote_is_incomplete():
    events = [dict(event) for event in COMPLETE_TICKET_EVENTS]
    events[0]["side"] = "BUY"
    events[1].pop("liquidation_bid")

    report = analyze_ticket_lifecycles(events)

    assert report["status"] == "NO_COMPLETE_LIFECYCLE_EVIDENCE"
    assert report["incomplete_tickets"] == ["T1"]


def test_sell_requires_observed_ask_liquidation_quote():
    events = [dict(event) for event in COMPLETE_TICKET_EVENTS]
    events[0]["side"] = "SELL"
    events[1]["liquidation_ask"] = events[1].pop("liquidation_bid")

    report = analyze_ticket_lifecycles(events)

    assert report["completed_tickets"] == 1


def test_unconfirmed_firehose_close_is_incomplete():
    events = [dict(event) for event in COMPLETE_TICKET_EVENTS]
    events[2]["confirmed"] = False
    events[2]["ok"] = True
    assert analyze_ticket_lifecycles(events)["completed_tickets"] == 0

    events = [dict(event) for event in COMPLETE_TICKET_EVENTS]
    events[2]["event"] = "firehose_close"
    events[2]["confirmed"] = False
    assert analyze_ticket_lifecycles(events)["completed_tickets"] == 0


def test_bucket_erasure_is_threshold_specific():
    report = analyze_ticket_lifecycles(COMPLETE_TICKET_EVENTS)
    erased = report["wins_erased_by_bucket"]["0.70_usd"]

    assert erased == {"status": "OK", "reached_count": 1, "count": 1, "rate": 1.0}
    assert report["giveback_magnitude_usd"]["average"] == pytest.approx(0.25)


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
    report["policy_comparison"] = compare_exit_policies(COSTED_OOS_ROWS)
    json_path = tmp_path / "report.json"
    markdown_path = tmp_path / "report.md"

    write_harvest_report(report, json_path, markdown_path)

    assert json.loads(json_path.read_text(encoding="utf-8"))["status"] == "OK"
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "Firehose Harvest Evidence" in markdown
    assert "0.70_usd" in markdown
    assert "wins_erased_by_bucket" in markdown
    assert "round_trips_per_hour:" in markdown
    assert "max_loss_usd: `NO_COMPLETE_LIFECYCLE_EVIDENCE`" in markdown
    assert "profit_capture_ratio: 0.6875" in markdown
    assert "Policy comparison: `OK`" in markdown
    assert "highest_win_rate_policy: oos_count=2, oos_expectancy_after_cost=0.05" in markdown
    assert "higher_expectancy_policy: oos_count=2, oos_expectancy_after_cost=0.25" in markdown
    assert "profit_factor=`NO_EVIDENCE`, tail=`NO_EVIDENCE`, drawdown=`NO_EVIDENCE`" in markdown


def test_cli_includes_costed_oos_replay_comparison(tmp_path):
    journal = tmp_path / "journal.jsonl"
    replay = tmp_path / "replay.jsonl"
    json_out = tmp_path / "report.json"
    markdown_out = tmp_path / "report.md"
    journal.write_text("\n".join(json.dumps(event) for event in COMPLETE_TICKET_EVENTS) + "\n", encoding="utf-8")
    replay.write_text("\n".join(json.dumps(row) for row in COSTED_OOS_ROWS) + "\n", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).parents[1] / "scripts" / "analyze_firehose_harvest.py"),
            "--journal",
            str(journal),
            "--replay",
            str(replay),
            "--json-out",
            str(json_out),
            "--markdown-out",
            str(markdown_out),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(json_out.read_text(encoding="utf-8"))["policy_comparison"]["winner"] == "higher_expectancy_policy"
