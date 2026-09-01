"""Tests for the outcome-learning consumer (research-only, read-only)."""
from __future__ import annotations

import json

import pytest

from aegis.research.outcome_learning import (
    build_daily_trade_behavior_reports,
    exit_pnls,
    record_fast_trade_autopsy,
    read_outcomes,
    render_daily_trade_behavior_markdown,
    summarize_fast_trade_autopsy,
    summarize_outcomes,
)
from aegis.research.registry import ExperimentRegistry


def _row(ticket: str, pnl: float, is_exit: bool = True, **extra) -> dict:
    return {"ticket": ticket, "pnl": pnl, "is_exit": is_exit, **extra}


def test_read_outcomes_dedupes_by_ticket(tmp_path):
    path = tmp_path / "outcome_log.jsonl"
    path.write_text(
        "\n".join(
            [
                json.dumps(_row("1", 0.05)),
                json.dumps(_row("1", 0.05)),
                json.dumps(_row("2", -0.1)),
                "not-json",
                json.dumps(_row("3", 0.01, is_exit=False)),
            ]
        ),
        encoding="utf-8",
    )
    rows = read_outcomes(path)
    assert [r["ticket"] for r in rows] == ["1", "2", "3"]


def test_read_outcomes_uses_position_side_and_never_guesses_from_exit_side(tmp_path):
    path = tmp_path / "outcome_log.jsonl"
    path.write_text(
        "\n".join(
            [
                json.dumps({
                    "ticket": "entry-known",
                    "is_exit": True,
                    "side": "sell",  # closing DEAL side, not position side
                    "position_side": "buy",
                    "evidence_status": "BROKER_CONFIRMED",
                    "pnl": 0.04,
                }),
                json.dumps({
                    "ticket": "entry-missing",
                    "is_exit": True,
                    "side": "buy",  # unsafe to interpret without entry evidence
                    "evidence_status": "BROKER_CONFIRMED",
                    "pnl": -0.04,
                }),
            ]
        ),
        encoding="utf-8",
    )

    rows = read_outcomes(path)

    assert rows[0]["side"] == "buy"
    assert rows[1]["side"] == "unknown"


def test_exit_pnls_uses_broker_confirmed_net_pnl_over_event_pnl():
    rows = [{
        "ticket": "broker-truth",
        "is_exit": True,
        "pnl": 0.20,
        "realized_net_usd": -0.12,
        "evidence_status": "BROKER_CONFIRMED",
    }]

    assert exit_pnls(rows) == [-0.12]


def test_learning_slices_use_broker_confirmed_net_pnl_over_event_pnl():
    rows = []
    for index in range(5):
        rows.append({
            "ticket": str(index),
            "is_exit": True,
            "symbol": "EURUSD",
            "side": "buy",
            "pnl": 0.20,
            "realized_net_usd": -0.12,
            "evidence_status": "BROKER_CONFIRMED",
        })

    summary = summarize_outcomes(rows)

    assert summary["by_symbol"][0]["expectancy"] == pytest.approx(-0.12)


def test_exit_pnls_and_summary_geometry():
    rows = [
        _row("1", 0.06, symbol="EURUSD", side="buy", close_reason="tp"),
        _row("2", 0.04, symbol="EURUSD", side="buy", close_reason="tp"),
        _row("3", -0.3, symbol="EURUSD", side="buy", close_reason="sl"),
        _row("4", 0.02, symbol="EURUSD", side="buy", close_reason="manual"),
        _row("5", 0.0, symbol="EURUSD", side="buy", close_reason="manual"),
    ]
    assert exit_pnls(rows) == [0.06, 0.04, -0.3, 0.02, 0.0]
    summary = summarize_outcomes(rows)
    metrics = summary["metrics"]
    assert summary["n_exits"] == 5
    assert metrics["win_rate"] == 3 / 5
    assert metrics["expectancy"] == pytest.approx((0.06 + 0.04 - 0.3 + 0.02) / 5)
    assert metrics["payoff_ratio"] == pytest.approx(0.04 / 0.3)
    assert metrics["wins_erased_by_average_loss"] == pytest.approx(0.3 / 0.04)
    assert metrics["tail_loss"] == 0.3
    assert len(summary["by_symbol"]) == 1
    assert summary["by_symbol"][0]["key"] == "EURUSD"
    assert summary["by_close_reason"] == []


def test_summary_empty_is_not_invented():
    summary = summarize_outcomes([])
    assert summary["n_rows"] == 0
    assert summary["n_exits"] == 0
    assert summary["metrics"]["n"] == 0


def test_slice_learning_requires_minimum_sample():
    rows = [
        _row(str(i), 0.02, symbol="EURUSD", side="buy", close_reason="tp")
        for i in range(5)
    ]
    rows += [_row("99", -0.3, symbol="EURUSD", side="buy", close_reason="sl")]
    summary = summarize_outcomes(rows)
    reasons = {r["key"] for r in summary["by_close_reason"]}
    assert "tp" in reasons
    assert "sl" not in reasons


def test_fast_trade_autopsy_joins_runtime_evidence_and_records_no_evidence(tmp_path):
    outcomes = [
        {"ticket": "deal-loss-1", "position": "loss-1", "is_exit": True, "pnl": -0.02, "symbol": "AUDUSD", "close_reason": "manual"},
        {"ticket": "deal-win-1", "position": "win-1", "is_exit": True, "pnl": 0.05, "symbol": "EURAUD", "close_reason": "manual"},
    ]
    journal = {
        "loss-1": [
            {"event": "firehose_open", "ticket": "loss-1", "timestamp": "2026-01-01T00:00:00+00:00"},
            {"event": "firehose_exit_trace", "ticket": "loss-1", "timestamp": "2026-01-01T00:00:05+00:00", "pnl_usd": -0.01, "mfe_usd": 0.0},
            {"event": "pm_exit", "ticket": "loss-1", "timestamp": "2026-01-01T00:00:40+00:00", "mfe_before_close": 0.0, "mae_before_close": -0.04, "exit_reason": "fast_scratch:time_decay_no_progress"},
            {"event": "firehose_close", "ticket": "loss-1", "timestamp": "2026-01-01T00:00:40+00:00", "confirmed": True},
        ],
        "win-1": [
            {"event": "firehose_open", "ticket": "win-1", "timestamp": "2026-01-01T00:01:00+00:00"},
            {"event": "firehose_exit_trace", "ticket": "win-1", "timestamp": "2026-01-01T00:01:03+00:00", "pnl_usd": 0.01, "mfe_usd": 0.01},
            {"event": "pm_exit", "ticket": "win-1", "timestamp": "2026-01-01T00:01:08+00:00", "mfe_before_close": 0.05, "mae_before_close": -0.01, "exit_reason": "fast_take"},
            {"event": "firehose_close", "ticket": "win-1", "timestamp": "2026-01-01T00:01:08+00:00", "confirmed": True},
        ],
    }

    summary = summarize_fast_trade_autopsy(outcomes, journal)

    assert summary["n_trades"] == 2
    assert summary["median_hold_s"] == pytest.approx(24.0)
    assert summary["median_time_to_green_s"] == pytest.approx(3.0)
    assert summary["loss_categories"]["NO_PROGRESS"] == 1
    assert summary["winner_giveback_rate"] == pytest.approx(0.0)
    registry = ExperimentRegistry(tmp_path / "experiments.sqlite")
    experiment_id = record_fast_trade_autopsy(summary, registry=registry)
    row = registry.get(experiment_id)
    assert row is not None
    assert row["status"] == "failed"
    assert "observation only" in row["rejection_reason"]


def test_fast_trade_autopsy_separates_explicit_giveback_and_time_decay_losses():
    outcomes = [
        {"ticket": "giveback-loss", "is_exit": True, "pnl": -0.01, "symbol": "AUDNZD"},
        {"ticket": "time-loss", "is_exit": True, "pnl": -0.04, "symbol": "EURUSD"},
    ]
    journal = {
        "giveback-loss": [
            {"event": "firehose_open", "ticket": "giveback-loss", "timestamp": "2026-01-01T00:00:00+00:00"},
            {"event": "firehose_exit_trace", "ticket": "giveback-loss", "timestamp": "2026-01-01T00:00:03+00:00", "pnl_usd": -0.01, "mfe_usd": 0.18},
            {"event": "pm_exit", "ticket": "giveback-loss", "timestamp": "2026-01-01T00:00:04+00:00", "mfe_before_close": 0.18, "exit_reason": "fast_take:mfe_giveback_limit"},
        ],
        "time-loss": [
            {"event": "pm_exit", "ticket": "time-loss", "timestamp": "2026-01-01T00:00:40+00:00", "mfe_before_close": 0.0, "exit_reason": "pm_time_decay"},
        ],
    }

    summary = summarize_fast_trade_autopsy(outcomes, journal)

    assert summary["loss_categories"] == {
        "NO_PROGRESS": 1,
        "WINNER_GIVEBACK": 1,
    }
    assert summary["loss_category_metrics"]["WINNER_GIVEBACK"] == {
        "n": 1,
        "complete_evidence": 0,
        "net_pnl": -0.01,
        "avg_loss": -0.01,
        "median_hold_s": None,
        "median_mfe_usd": 0.18,
        "median_mae_usd": None,
    }


def test_fast_trade_autopsy_uses_broker_confirmed_net_pnl_over_event_pnl():
    outcomes = [{
        "ticket": "broker-truth",
        "is_exit": True,
        # A stale/event-level value must not override broker-confirmed net.
        "pnl": 0.20,
        "realized_net_usd": -0.12,
        "evidence_status": "BROKER_CONFIRMED",
        "symbol": "EURUSD",
    }]

    summary = summarize_fast_trade_autopsy(outcomes, {})

    assert summary["n_trades"] == 1
    assert summary["metrics"]["n_wins"] == 0
    assert summary["metrics"]["n_losses"] == 1
    assert summary["trades"][0]["pnl"] == pytest.approx(-0.12)


def test_daily_trade_behavior_records_green_to_red_broker_confirmed_lifecycle():
    outcomes = [{
        "ticket": "deal-1",
        "position": "position-1",
        "is_exit": True,
        "pnl": 0.50,
        "realized_net_usd": -0.02,
        "evidence_status": "BROKER_CONFIRMED",
        "symbol": "EURJPY",
        "side": "buy",
    }]
    journal = {"position-1": [
        {"event": "firehose_open", "ticket": "position-1", "timestamp": "2026-08-28T08:00:00+00:00"},
        {"event": "firehose_exit_trace", "ticket": "position-1", "timestamp": "2026-08-28T08:00:01+00:00", "pnl_usd": -0.03},
        {"event": "firehose_exit_trace", "ticket": "position-1", "timestamp": "2026-08-28T08:00:02+00:00", "pnl_usd": 0.02},
        {"event": "firehose_exit_trace", "ticket": "position-1", "timestamp": "2026-08-28T08:00:03+00:00", "pnl_usd": 0.05},
        {"event": "firehose_exit_trace", "ticket": "position-1", "timestamp": "2026-08-28T08:00:04+00:00", "pnl_usd": -0.01},
        {"event": "pm_exit", "ticket": "position-1", "timestamp": "2026-08-28T08:00:04+00:00", "action": "SCRATCH", "exit_reason": "prediction_collapsed", "mfe_before_close": 0.05},
        {"event": "firehose_close", "ticket": "position-1", "timestamp": "2026-08-28T08:00:05+00:00", "confirmed": True},
    ]}

    summary = summarize_fast_trade_autopsy(outcomes, journal)
    reports = build_daily_trade_behavior_reports(summary, timezone_name="Asia/Amman")

    trade = reports["2026-08-28"]["trades"][0]
    assert trade["state_path"] == [
        "OPEN", "RED", "GREEN", "PEAK", "GREEN_TO_RED", "CLOSE_LOSS",
    ]
    assert trade["first_net_green_s"] == pytest.approx(2.0)
    assert trade["peak_executable_pnl_usd"] == pytest.approx(0.05)
    assert trade["broker_confirmed_net_pnl_usd"] == pytest.approx(-0.02)
    assert trade["exit_action"] == "SCRATCH"
    assert trade["exit_reason"] == "prediction_collapsed"
    assert reports["2026-08-28"]["winner_to_loser_count"] == 1
    assert reports["2026-08-28"]["net_pnl_usd"] == pytest.approx(-0.02)


def test_daily_trade_behavior_markdown_exposes_each_trade_path():
    report = {
        "date": "2026-08-28",
        "timezone": "Asia/Amman",
        "n_trades": 1,
        "n_wins": 1,
        "n_losses": 0,
        "net_pnl_usd": 0.04,
        "winner_to_loser_count": 0,
        "winner_to_loser_rate": 0.0,
        "trades": [{
            "ticket": "T1",
            "symbol": "EURUSD",
            "side": "sell",
            "state_path": ["OPEN", "GREEN", "PEAK", "CLOSE_WIN"],
            "broker_confirmed_net_pnl_usd": 0.04,
            "first_net_green_s": 0.3,
            "peak_executable_pnl_usd": 0.06,
            "giveback_usd": 0.02,
            "exit_action": "HARVEST",
            "exit_reason": "profit_without_continuation_evidence",
        }],
    }

    markdown = render_daily_trade_behavior_markdown(report)

    assert "OPEN -> GREEN -> PEAK -> CLOSE_WIN" in markdown
    assert "profit_without_continuation_evidence" in markdown
