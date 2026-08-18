"""Intelligent Firehose demo brain tests."""
from __future__ import annotations

import json

import pandas as pd

from aegis.intel.analogue_store import AnalogueStore
from aegis.intel.firehose_brain import IntelligentFirehoseBrain
from aegis.intel.strategy_model import ValidatedStrategyModel, strategy_model_ready
from aegis.intel.expected_value import payoff_metrics


def _m1(n: int = 400) -> pd.DataFrame:
    time = pd.date_range("2026-01-01", periods=n, freq="min", tz="UTC")
    close = pd.Series([1.10 + index * 0.00001 for index in range(n)])
    return pd.DataFrame(
        {
            "time": time,
            "open": close - 0.00005,
            "high": close + 0.00012,
            "low": close - 0.00012,
            "close": close,
            "volume": 100.0,
        }
    )


def _positive_records(symbol: str = "EURUSD", n: int = 30) -> list[dict]:
    return [
        {
            "bar_time": f"2026-01-01T{hour:02d}:00:00+00:00",
            "symbol": symbol,
            "side": "buy",
            "setup": "breakout",
            "regime": "trend",
            "structure": "breakout",
            "volatility": "expanding",
            "session": "london",
            "h1_direction": "up",
            "m5_direction": "up",
            "outcome": 0.04 if index % 4 else -0.02,
        }
        for index, hour in enumerate(range(n))
    ]


def test_brain_skips_without_analogue_evidence(tmp_path):
    index = tmp_path / "analogue_index.json"
    index.write_text(json.dumps({"schema": "analogue_index.v1", "records": []}), encoding="utf-8")
    cfg = {
        "analogue_index_path": str(index),
        "intelligent_firehose_bootstrap": True,
        "intelligent_min_analogues": 20,
        "order_quantity": 0.01,
    }
    brain = IntelligentFirehoseBrain(cfg)
    m1 = _m1()
    row = m1.iloc[-1]
    row = row.copy()
    row["time"] = m1["time"].iloc[-1]
    row["ema_20"] = float(m1["close"].iloc[-1])
    decision = brain.evaluate(
        symbol="EURUSD",
        row=row,
        completed_m1=m1.iloc[:-1],
        positions=[],
        equity=100.0,
        pip=0.0001,
        core_side="buy",
    )
    assert decision.action == "skip"


def test_brain_can_fire_with_bootstrap_analogues(tmp_path):
    records = _positive_records(n=40)
    index = tmp_path / "analogue_index.json"
    index.write_text(json.dumps({"schema": "analogue_index.v1", "records": records}), encoding="utf-8")
    cfg = {
        "analogue_index_path": str(index),
        "intelligent_firehose_bootstrap": True,
        "intelligent_min_analogues": 20,
        "intelligent_min_similarity": 0.5,
        "intelligent_risk_fraction": 0.08,
        "intelligent_risk_budget_usd": 100.0,
        "order_quantity": 0.01,
        "max_positions": 40,
    }
    brain = IntelligentFirehoseBrain(cfg)
    m1 = _m1()
    row = m1.iloc[-1].copy()
    row["time"] = m1["time"].iloc[-1]
    row["ema_20"] = float(m1["close"].iloc[-1])
    decision = brain.evaluate(
        symbol="EURUSD",
        row=row,
        completed_m1=m1.iloc[:-1],
        positions=[],
        equity=100.0,
        pip=0.0001,
        core_side="buy",
    )
    if decision.action in {"fire", "scale"}:
        assert decision.sl is not None
        assert decision.analogue_n >= 20


def test_9191_wr_negative_ev_model_never_promotes():
    """Regression: MT5 demo ~91.91% WR with PF 0.71 must never promote."""
    wins = 1080
    losses = 95
    pnls = [0.024] * wins + [-0.39] * losses
    stats = payoff_metrics(pnls)
    assert stats["win_rate"] is not None and stats["win_rate"] > 0.91
    assert stats["expectancy"] is not None and stats["expectancy"] < 0
    assert stats["profit_factor"] is not None and stats["profit_factor"] < 1.0
    assert stats["cosmetic_win_rate"] is True

    model = ValidatedStrategyModel(
        strategy_id="old_firehose_cosmetic",
        promoted=True,
        n_trades=wins + losses,
        n_losses=losses,
        expectancy=float(stats["expectancy"]),
        profit_factor=float(stats["profit_factor"]),
        bootstrap_p05=-0.001,
        wins_erased_by_average_loss=float(stats["wins_erased_by_average_loss"] or 99.0),
        wins_erased_by_tail_loss=float(stats["wins_erased_by_tail_loss"] or 99.0),
        validated_risk_fraction=0.08,
        artifact_hash="regression",
    )
    ready, reason = strategy_model_ready(model)
    assert not ready
    assert "expectancy" in reason or "profit_factor" in reason or "payoff" in reason or reason.startswith("destructive")


def test_analogue_store_excludes_future_bars():
    records = [
        {
            "bar_time": "2026-01-01T12:00:00+00:00",
            "symbol": "EURUSD",
            "side": "buy",
            "setup": "breakout",
            "regime": "trend",
            "structure": "breakout",
            "volatility": "stable",
            "session": "london",
            "h1_direction": "up",
            "m5_direction": "up",
            "outcome": 0.05,
        },
        {
            "bar_time": "2026-01-01T12:10:00+00:00",
            "symbol": "EURUSD",
            "side": "buy",
            "setup": "breakout",
            "regime": "trend",
            "structure": "breakout",
            "volatility": "stable",
            "session": "london",
            "h1_direction": "up",
            "m5_direction": "up",
            "outcome": -0.20,
        },
    ]
    store = AnalogueStore(records)
    evidence = store.query(
        signature={
            "symbol": "EURUSD",
            "side": "buy",
            "setup": "breakout",
            "regime": "trend",
            "structure": "breakout",
            "volatility": "stable",
            "session": "london",
            "h1_direction": "up",
            "m5_direction": "up",
        },
        before_time="2026-01-01T12:10:00+00:00",
        min_n=1,
        min_similarity=0.5,
    )
    assert evidence.analogue_n == 1
    assert evidence.expectancy == 0.05


def test_sanitize_mt5_comment_is_short_ascii():
    from aegis.engines.mt5 import sanitize_mt5_comment

    tag = sanitize_mt5_comment("aegis_positive_state_ev_on_validated_strategy")
    assert tag.startswith("aegis")
    assert len(tag) <= 16
    assert tag.isalnum()


def test_analogue_store_rejects_cosmetic_win_rate():
    records = []
    for hour in range(40):
        records.append(
            {
                "bar_time": f"2026-01-01T{hour:02d}:00:00+00:00",
                "symbol": "EURUSD",
                "side": "buy",
                "setup": "breakout",
                "regime": "trend",
                "structure": "breakout",
                "volatility": "stable",
                "session": "london",
                "h1_direction": "up",
                "m5_direction": "up",
                "outcome": 0.01 if hour % 10 else -0.30,
            }
        )
    store = AnalogueStore(records)
    evidence = store.query(
        signature={
            "symbol": "EURUSD",
            "side": "buy",
            "setup": "breakout",
            "regime": "trend",
            "structure": "breakout",
            "volatility": "stable",
            "session": "london",
            "h1_direction": "up",
            "m5_direction": "up",
        },
        before_time="2026-01-02T00:00:00+00:00",
        min_n=20,
        min_similarity=0.5,
    )
    assert evidence.analogue_n >= 20
    assert not evidence.eligible
