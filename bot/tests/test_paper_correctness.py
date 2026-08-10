#!/usr/bin/env python3
"""Paper/backtest accounting parity tests."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aegis.paper import PaperBot, PaperBroker, PaperPosition


def test_paper_close_charges_round_trip_cost() -> None:
    broker = PaperBroker(equity=100.0, cost_bps=10.0)
    broker.position = PaperPosition("buy", "test", 100.0, 99.0, 101.0, None, 1.0, "test")
    pnl = broker.close(101.0, "tp")
    assert abs(pnl - 0.8) < 1e-9
    assert abs(broker.equity - 100.8) < 1e-9


def test_paper_rejects_duplicate_closed_bar(tmp_path: Path) -> None:
    bot = PaperBot(
        {
            "starting_equity": 100,
            "risk_percent": 1,
            "max_daily_loss_percent": 3,
            "max_total_drawdown_percent": 12,
            "max_positions": 1,
        },
        tmp_path / "journal.jsonl",
    )
    ts = pd.Timestamp("2024-01-02 10:00", tz="UTC")
    assert bot.accept_new_bar(ts)
    assert not bot.accept_new_bar(ts)
    assert not bot.accept_new_bar(ts - pd.Timedelta(minutes=1))
    assert bot.accept_new_bar(ts + pd.Timedelta(minutes=1))


if __name__ == "__main__":
    from tempfile import TemporaryDirectory

    test_paper_close_charges_round_trip_cost()
    with TemporaryDirectory() as td:
        test_paper_rejects_duplicate_closed_bar(Path(td))
    print("ALL PAPER CORRECTNESS TESTS PASSED")

