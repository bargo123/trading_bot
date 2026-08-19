"""Tests for exit-horizon research on forward M1 paths."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from aegis.research.exit_research import (
    bps_to_pips,
    exit_horizon_summary,
    per_trade_cost_pips,
    recommended_exit,
    research_exit_horizons,
    simulate_exit,
)


def _frame(outcome_path: list[float]) -> pd.DataFrame:
    n = len(outcome_path)
    return pd.DataFrame(
        {
            "time": pd.to_datetime(
                [f"2026-08-14 00:{i:02d}:00+00:00" for i in range(n)], utc=True
            ),
            "open": [1.0] * n,
            "high": [max(a, b) for a, b in zip(outcome_path, outcome_path)],
            "low": [min(a, b) for a, b in zip(outcome_path, outcome_path)],
            "close": outcome_path,
            "volume": [1] * n,
        }
    )


def test_bps_to_pips():
    # 0.2 bps on a 4-digit symbol at price ~1.0 is 0.2 pips
    assert bps_to_pips(0.2, "EURUSD", 0.0001) == pytest.approx(0.2)
    # JPY pair price base 100
    assert bps_to_pips(0.2, "USDJPY", 0.01) == pytest.approx(0.2)


def test_per_trade_cost_pips():
    cost = per_trade_cost_pips("EURUSD", 0.0001, spread_bps=0.2, slippage_bps=0.1)
    assert cost == pytest.approx(0.3)


def test_simulate_exit_sell_hits_target():
    frame = _frame([1.0000, 0.9998, 0.9995, 0.9990])
    out = simulate_exit(frame, start_idx=0, side="sell", tp_pips=2.0, sl_pips=30.0, pip=0.0001)
    assert out == pytest.approx(2.0)


def test_simulate_exit_sell_hits_stop():
    frame = _frame([1.0000, 1.0020, 1.0030])
    out = simulate_exit(frame, start_idx=0, side="sell", tp_pips=2.0, sl_pips=30.0, pip=0.0001)
    assert out == pytest.approx(-30.0)


def test_simulate_exit_buy_hits_target():
    frame = _frame([1.0000, 1.0002, 1.0005, 1.0010])
    out = simulate_exit(frame, start_idx=0, side="buy", tp_pips=2.0, sl_pips=30.0, pip=0.0001)
    assert out == pytest.approx(2.0)


def test_research_exit_horizons_returns_costed_rows():
    records = [
        {
            "bar_time": "2026-08-14 00:00:00+00:00",
            "symbol": "EURUSD",
            "side": "sell",
            "regime": "range",
            "structure": "none",
            "session": "asia",
        },
        {
            "bar_time": "2026-08-14 00:01:00+00:00",
            "symbol": "EURUSD",
            "side": "sell",
            "regime": "range",
            "structure": "none",
            "session": "asia",
        },
    ]
    frame = _frame([1.0000, 0.9998, 0.9995, 0.9990, 0.9988])
    rows = research_exit_horizons(
        records,
        {"EURUSD": frame},
        pip_by_symbol={"EURUSD": 0.0001},
        spread_bps=0.2,
        slippage_bps=0.1,
    )
    assert len(rows) == len(records) * 4
    for row in rows:
        assert row["cost_pips"] == pytest.approx(0.3)
        assert row["net_outcome_pips"] == pytest.approx(row["outcome_pips"] - 0.3)
    # first record, tp=2 -> target hit (+2), net 1.7
    tp2 = [r for r in rows if r["tp_pips"] == 2.0 and r["bar_time"] == records[0]["bar_time"]][0]
    assert tp2["outcome_pips"] == pytest.approx(2.0)
    assert tp2["net_outcome_pips"] == pytest.approx(1.7)


def test_exit_horizon_summary_orders_by_net_expectancy():
    rows = []
    for tp in (1.0, 2.0, 5.0):
        rows.append({"tp_pips": tp, "sl_pips": 30.0, "net_outcome_pips": tp})
    summary = exit_horizon_summary(rows)
    assert [s["tp_pips"] for s in summary] == [5.0, 2.0, 1.0]
    assert summary[0]["expectancy_net"] == pytest.approx(5.0)


def test_recommended_exit_none_when_no_positive():
    rows = [{"tp_pips": 1.0, "sl_pips": 30.0, "net_outcome_pips": -0.2}]
    summary = exit_horizon_summary(rows)
    assert recommended_exit(summary) is None


def test_recommended_exit_picks_positive_max():
    rows = []
    for tp, value in ((1.0, 0.1), (2.0, 0.4), (5.0, -0.2)):
        rows.append({"tp_pips": tp, "sl_pips": 30.0, "net_outcome_pips": value})
    summary = exit_horizon_summary(rows)
    best = recommended_exit(summary)
    assert best is not None
    assert best["tp_pips"] == 2.0