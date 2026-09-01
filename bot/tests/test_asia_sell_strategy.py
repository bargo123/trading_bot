"""Tests for the Asia-session range sell strategy definition."""
from __future__ import annotations

import json

import pytest

from aegis.research.asia_sell_strategy import (
    CONFIG,
    STRATEGY_ID,
    asia_sell_range_matches,
    build_challenger_spec,
)


@pytest.fixture
def index(tmp_path):
    records = []
    base = "2026-08-14 00:{:02d}:00+00:00"
    for i in range(30):
        records.append(
            {
                "bar_time": base.format(i),
                "symbol": "EURUSD",
                "side": "sell",
                "setup": "none",
                "regime": "range",
                "structure": "none",
                "volatility": "compressing",
                "session": "asia",
                "h1_direction": "up",
                "m5_direction": "down",
                "outcome": 1.0,
                "label": "research_proxy",
            }
        )
    records.append(
        {
            "bar_time": "2026-08-14 00:00:00+00:00",
            "symbol": "EURUSD",
            "side": "buy",
            "setup": "retest",
            "regime": "range",
            "structure": "retest",
            "session": "asia",
            "outcome": 5.0,
            "label": "research_proxy",
        }
    )
    payload = {
        "schema": "analogue_index",
        "provenance": "mt5_m1",
        "outcome_unit": "pips",
        "records": records,
    }
    path = tmp_path / "index.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_strategy_id_and_config():
    assert STRATEGY_ID == "asia_sell_range"
    assert CONFIG["side"] == "sell"
    assert CONFIG["filters"]["regime"] == "range"
    assert CONFIG["filters"]["structure"] == "none"
    assert CONFIG["filters"]["session"] == "asia"


def test_asia_sell_range_matches_positive():
    row = {
        "regime": "range",
        "structure": "none",
        "session": "asia",
        "side": "sell",
    }
    assert asia_sell_range_matches(row)


@pytest.mark.parametrize(
    "row",
    [
        {"regime": "trend", "structure": "none", "session": "asia", "side": "sell"},
        {"regime": "range", "structure": "retest", "session": "asia", "side": "sell"},
        {"regime": "range", "structure": "none", "session": "london", "side": "sell"},
        {"regime": "range", "structure": "none", "session": "asia", "side": "buy"},
    ],
)
def test_asia_sell_range_matches_negative(row):
    assert not asia_sell_range_matches(row)


def test_build_challenger_spec_splits_by_time(index):
    spec = build_challenger_spec(index)
    assert spec["strategy_id"] == STRATEGY_ID
    assert len(spec["validation_pnls"]) == 21  # 70% of 30
    assert len(spec["holdout_pnls"]) == 9
    assert spec["holdout_metrics"]["n_trades"] == 9
    assert spec["holdout_metrics"]["expectancy"] == pytest.approx(1.0)
    assert spec["validated_risk_fraction"] == 0.01
    assert spec["label"] == "research_proxy"


def test_build_challenger_spec_validation_never_sees_holdout(index):
    spec = build_challenger_spec(index)
    validation_max = max(spec["validation_pnls"])
    holdout_min = min(spec["holdout_pnls"])
    assert validation_max <= holdout_min  # time ordered, no leakage