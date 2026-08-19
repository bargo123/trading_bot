"""Tests for the outcome-learning consumer (research-only, read-only)."""
from __future__ import annotations

import json

import pytest

from aegis.research.outcome_learning import (
    exit_pnls,
    read_outcomes,
    summarize_outcomes,
)


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