from __future__ import annotations

import json
from pathlib import Path

from scripts.watch_firehose_live import (
    expand_event,
    format_event,
    heartbeat_summary,
    runtime_paths,
    should_display,
)


def test_runtime_paths_follow_configured_test_name(tmp_path):
    config = tmp_path / "firehose.yaml"
    config.write_text(
        "symbol: EURUSD\ntimeframe: M1\nmode: mt5_demo\ntest_name: custom_firehose\n",
        encoding="utf-8",
    )

    journal, heartbeat = runtime_paths(config)

    assert journal == tmp_path / "reports" / "custom_firehose_journal.jsonl"
    assert heartbeat == tmp_path / "reports" / "bot_heartbeat.json"


def test_expand_event_exposes_each_blocked_candidate_with_exact_details():
    event = {
        "event": "intel_brain_skip",
        "symbol": "EURUSD",
        "short_horizon_gate": "short_horizon_not_calibrated",
        "candidate_evaluations": [
            {
                "variant_id": "stoch_mr:sell:3s",
                "symbol": "EURUSD",
                "side": "sell",
                "mechanism": "stoch_mr",
                "horizon_s": 3,
                "reasons": ["RISK_GRANULARITY_BLOCKED", "SPREAD_FAILURE"],
                "p_green": None,
                "expected_net_value_usd": None,
                "distance_to_eligibility": {
                    "risk_excess_usd": 0.1429,
                    "spread_excess_pips": 0.1625,
                },
                "entry": 1.1002,
                "stop": 1.0992,
                "target": 1.1007,
                "spread_pips": 1.5,
                "lots": 0.01,
            }
        ],
    }

    expanded = expand_event(event)
    assert len(expanded) == 1
    candidate = expanded[0]
    assert candidate["event"] == "candidate_blocked"
    assert candidate["candidate_id"] == "stoch_mr:sell:3s"
    assert candidate["reject_reason"] == "RISK_GRANULARITY_BLOCKED, SPREAD_FAILURE"
    assert candidate["distance_to_eligibility"]["risk_excess_usd"] == 0.1429
    assert candidate["source_event"] == "intel_brain_skip"

    rendered = format_event(candidate)
    assert "RISK_GRANULARITY_BLOCKED, SPREAD_FAILURE" in rendered
    assert "risk_excess_usd=0.1429" in rendered
    assert "SYMBOL: EURUSD" in rendered
    assert "SIDE: SELL" in rendered
    assert "HORIZON: 3s" in rendered


def test_should_display_filters_blocked_and_symbol_events():
    blocked = {
        "event": "candidate_blocked",
        "symbol": "EURUSD",
        "reject_reason": "SPREAD_FAILURE",
    }
    selected = {
        "event": "global_opportunity_allocation",
        "symbol": "GBPUSD",
        "selected": 1,
    }

    assert should_display(blocked, blocked_only=True, symbol=None)
    assert not should_display(selected, blocked_only=True, symbol=None)
    assert should_display(blocked, blocked_only=False, symbol="EURUSD")
    assert not should_display(blocked, blocked_only=False, symbol="GBPUSD")


def test_heartbeat_summary_reports_live_funnel_and_safety_state():
    heartbeat = {
        "status": "running",
        "runtime_phase": "RUNNING_SCAN",
        "trading_eligible": True,
        "firehose_telemetry": {
            "SCANS": 26,
            "BUY_VARIANTS_TESTED": 5824,
            "SELL_VARIANTS_TESTED": 5824,
            "GLOBAL_CANDIDATES": 4,
            "GLOBAL_SELECTED": 1,
            "FRESH_TICK_ACQUISITION_ATTEMPTS": 2,
            "FRESH_TICK_ACQUIRED": 1,
            "SPREAD_FAIL": 3,
            "GEOMETRY_FAIL": 2,
            "RISK_FAIL": 5,
            "RISK_REJECT": 4,
            "OMS_REJECTS_BY_REASON": {"OMS_VOLUME": 1},
            "ORDER_SEND_ATTEMPTS": 1,
            "SUBMITTED": 1,
            "FILLS": 1,
            "OPEN_TICKETS": 1,
            "WIN_EXITS": 2,
            "LOSS_EXITS": 1,
        },
    }

    rendered = heartbeat_summary(heartbeat)
    assert "SCANS=26" in rendered
    assert "BUY_VARIANTS=5824" in rendered
    assert "SELL_VARIANTS=5824" in rendered
    assert "GLOBAL_CANDIDATES=4" in rendered
    assert "BLOCKED_RISK=9" in rendered
    assert "BLOCKED_OMS=1" in rendered
    assert "FILLS=1" in rendered
    assert "OPEN_POSITIONS=1" in rendered
