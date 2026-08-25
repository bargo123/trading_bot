"""Tests for the outcome-learning consumer (research-only, read-only)."""
from __future__ import annotations

import json

import pytest

from aegis.research.outcome_learning import (
    exit_pnls,
    record_fast_trade_autopsy,
    read_outcomes,
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
