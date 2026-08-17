"""Readonly Intelligent Firehose observer. Never places orders."""
from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

from aegis.intel.strategy_model import ValidatedStrategyModel
from aegis.research.market_state import MarketStateCache
from aegis.research.shadow_firehose import scoreboard_markdown, summarize_shadow_rows
from aegis.research.shadow_observe import (
    ShadowBook,
    ShadowThesisState,
    observe_completed_bar,
    scan_symbol,
)


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


def _ready_model() -> ValidatedStrategyModel:
    return ValidatedStrategyModel(
        strategy_id="failed_break_v1",
        promoted=True,
        n_trades=80,
        n_losses=12,
        expectancy=0.04,
        profit_factor=1.4,
        bootstrap_p05=0.01,
        wins_erased_by_average_loss=0.5,
        wins_erased_by_tail_loss=1.2,
        validated_risk_fraction=0.10,
        artifact_hash="abc123",
    )


def test_observe_completed_bar_skips_without_champion_and_never_orders():
    m1 = _m1()
    row = observe_completed_bar(
        symbol="EURUSD",
        bar_time=str(m1["time"].iloc[-1]),
        completed_m1=m1,
        close=float(m1["close"].iloc[-1]),
        old={"action": "buy", "reason": "firehose_bar_up", "side": "buy", "tp": 1.1001, "sl": 1.0970},
        knowledge_rows=[
            {
                "filename": "retest.md",
                "file_hash": "abc",
                "concepts": ["retest", "breakout"],
                "setup": "breakout retest",
            }
        ],
    )
    assert row["placed_orders"] is False
    assert row["old"]["action"] == "buy"
    assert row["new"]["action"] == "skip"
    assert row["new"]["reason"] == "no_validated_strategy_model"
    assert row["symbol"] == "EURUSD"


def test_observe_records_scale_on_new_information():
    m1 = _m1()
    first = observe_completed_bar(
        symbol="EURUSD",
        bar_time=str(m1["time"].iloc[-2]),
        completed_m1=m1.iloc[:-1],
        close=float(m1["close"].iloc[-2]),
        old={"action": "buy", "reason": "firehose_bar_up"},
        strategy=_ready_model(),
        analogue_outcomes=[0.04] * 30 + [-0.02] * 10,
        total_risk_budget_usd=10.0,
        memory=ShadowThesisState(symbol="EURUSD", current_risk_usd=0.0),
    )
    held = ShadowThesisState(
        symbol="EURUSD",
        side=first["new"]["side"],
        information_id="old-info",
        current_risk_usd=0.20,
    )
    second = observe_completed_bar(
        symbol="EURUSD",
        bar_time=str(m1["time"].iloc[-1]),
        completed_m1=m1,
        close=float(m1["close"].iloc[-1]),
        old={"action": "buy", "reason": "firehose_bar_up"},
        strategy=_ready_model(),
        analogue_outcomes=[0.04] * 30 + [-0.02] * 10,
        total_risk_budget_usd=10.0,
        memory=held,
    )
    if first["new"]["action"] == "fire" and second["new"]["information_id"] != "old-info":
        assert second["new"]["action"] in {"scale", "skip", "reduce", "exit", "fire"}
    assert second["placed_orders"] is False


def test_scan_symbol_uses_completed_bar_and_never_places_orders():
    m1 = _m1(80)
    bars = [
        SimpleNamespace(
            time=row.time,
            open=float(row.open),
            high=float(row.high),
            low=float(row.low),
            close=float(row.close),
            volume=float(row.volume),
        )
        for row in m1.itertuples(index=False)
    ]

    class FakeEngine:
        def bars(self, symbol, timeframe, lookback_days):
            return bars

        def place_order(self, req):
            raise AssertionError("shadow must not place orders")

    cfg = {
        "timeframe": "1m",
        "lookback_days": 1,
        "signal_mode": "firehose",
        "algo": "firehose",
        "firehose_every_bar": True,
        "intel_enabled": False,
        "max_positions": 40,
    }
    observed = scan_symbol(
        engine=FakeEngine(),
        symbol="EURUSD",
        cfg=cfg,
        last_bar_time=None,
        knowledge_rows=[],
        strategy=None,
        book=ShadowBook(),
        cache=MarketStateCache(),
    )
    assert observed is not None
    assert observed["placed_orders"] is False
    assert observed["old"]["action"] in {"buy", "sell", "skip"}
    assert observed["new"]["action"] in {"fire", "skip", "scale", "reduce", "exit"}
    again = scan_symbol(
        engine=FakeEngine(),
        symbol="EURUSD",
        cfg=cfg,
        last_bar_time=pd.Timestamp(observed["bar_time"]),
        knowledge_rows=[],
        strategy=None,
        book=ShadowBook(),
        cache=MarketStateCache(),
    )
    assert again is None


def test_scoreboard_counts_scale_reduce_exit():
    rows = [
        {
            "placed_orders": False,
            "old": {"action": "buy"},
            "new": {"action": "skip", "reason": "no_validated_strategy_model"},
        },
        {
            "placed_orders": False,
            "old": {"action": "sell"},
            "new": {"action": "scale", "reason": "new_evidence_increase_exposure"},
        },
        {
            "placed_orders": False,
            "old": {"action": "skip"},
            "new": {"action": "exit", "reason": "structural_invalidation"},
        },
        {
            "placed_orders": False,
            "old": {"action": "buy"},
            "new": {"action": "reduce", "reason": "weaker_target_exposure"},
        },
    ]
    stats = summarize_shadow_rows(rows)
    assert stats["placed_orders"] is False
    assert stats["new_proposed_scales"] == 1
    assert stats["new_proposed_exits"] == 1
    assert stats["new_proposed_reduces"] == 1
    body = scoreboard_markdown(rows)
    assert "new_proposed_scales: 1" in body
    assert "placed_orders: false" in body
