"""Exploration Firehose tests: registered experiments, hard limits, sequential
learning, failed-experiment memory, funnel counters. DEMO-only by design."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aegis.intel.exploration import (  # noqa: E402
    ExperimentStore,
    ExplorationLimits,
    check_exploration_limits,
    hypothesis_id,
    risk_lots_for_exploration,
)


@pytest.fixture()
def store(tmp_path):
    return ExperimentStore(tmp_path / "exploration_experiments.json")


def _candidate(symbol="EURUSD", side="buy", family="breakout"):
    return {
        "hypothesis_id": hypothesis_id(
            strategy_family=family, symbol=symbol, side=side,
            regime="range", session="asia",
        ),
        "strategy_family": family,
        "symbol": symbol,
        "side": side,
        "entry_rule": "breakout buy at market",
        "invalidation": "close below 1.0995",
        "target": "1.1005",
        "regime": "range",
        "session": "asia",
        "information_id": "info-1",
    }


def test_hypothesis_id_is_stable_and_identity_sensitive():
    a = hypothesis_id(strategy_family="breakout", symbol="EURUSD", side="buy",
                      regime="range", session="asia")
    b = hypothesis_id(strategy_family="breakout", symbol="EURUSD", side="buy",
                      regime="range", session="asia")
    c = hypothesis_id(strategy_family="pullback", symbol="EURUSD", side="buy",
                      regime="range", session="asia")
    assert a == b and a != c


def test_register_is_idempotent_and_records_fields(store):
    rec1, created1 = store.register(_candidate(), reason="r", mechanism="m")
    rec2, created2 = store.register(_candidate(), reason="r", mechanism="m")
    assert created1 is True and created2 is False
    assert rec1["status"] == "ACTIVE"
    assert rec1["entry_rule"] and rec1["invalidation_rule"] and rec1["target_rule"]
    assert rec1["reason_for_experiment"] and rec1["expected_mechanism"]


def test_failed_memory_blocks_rediscovery(store):
    rec, _ = store.register(_candidate(), reason="r", mechanism="m")
    for i in range(8):
        store.record_close(hypothesis_id=rec["hypothesis_id"], pnl=-0.05)
    assert rec["status"] == "REJECTED"
    hit = store.has_failed_identity(
        strategy_family="breakout", symbol="EURUSD", side="buy",
        regime="range", session="asia",
    )
    assert hit is not None and hit["hypothesis_id"] == rec["hypothesis_id"]
    # A different family on the same symbol is NOT blocked.
    assert store.has_failed_identity(
        strategy_family="pullback", symbol="EURUSD", side="buy",
        regime="range", session="asia",
    ) is None


def test_sequential_evidence_updates_and_promotes(store):
    rec, _ = store.register(_candidate(side="sell"), reason="r", mechanism="m")
    hid = rec["hypothesis_id"]
    for i in range(10):
        store.record_close(hypothesis_id=hid, pnl=0.20 if i % 4 else -0.10)
    ev = store.data["experiments"][hid]["evidence"]
    assert ev["n"] == 10
    assert ev["expectancy"] > 0
    assert ev["profit_factor"] > 1
    assert ev["payoff"] == 2.0
    assert ev["bootstrap_p05"] is not None
    assert store.data["experiments"][hid]["status"] in {"PROMISING", "ACTIVE"}
    assert store.data["experiments"][hid]["status"] != "REJECTED"


def test_limits_max_positions_and_per_symbol(store):
    limits = ExplorationLimits(max_positions=2, max_positions_per_symbol=1)
    ok, reason = check_exploration_limits(
        limits, store, hypothesis_id="h1",
        open_positions_total=3, open_positions_symbol=1,
        exploration_open_total=2, exploration_open_symbol=1,
    )
    assert not ok and reason.startswith("exploration_max_positions:")
    ok, reason = check_exploration_limits(
        limits, store, hypothesis_id="h1",
        open_positions_total=10, open_positions_symbol=1,
        exploration_open_total=1, exploration_open_symbol=1,
    )
    assert not ok and reason == "exploration_max_positions_per_symbol"


def test_daily_loss_limit_halts_exploration(store):
    limits = ExplorationLimits(max_daily_loss_usd=1.0)
    rec, _ = store.register(_candidate(side="sell"), reason="r", mechanism="m")
    for _ in range(12):
        store.record_close(hypothesis_id=rec["hypothesis_id"], pnl=-0.10)
    assert store.daily_pnl() <= -1.0
    ok, reason = check_exploration_limits(
        limits, store, hypothesis_id="h1",
        open_positions_total=0, open_positions_symbol=0,
        exploration_open_total=0, exploration_open_symbol=0,
    )
    assert not ok and reason.startswith("exploration_max_daily_loss_usd")


def test_per_hypothesis_trade_cap_and_failure_cooldown(store):
    limits = ExplorationLimits(max_trades_per_hypothesis=5, cooldown_after_failure_s=1800)
    rec, _ = store.register(_candidate(), reason="r", mechanism="m")
    for _ in range(5):
        store.record_close(hypothesis_id=rec["hypothesis_id"], pnl=-0.02)
    ok, reason = check_exploration_limits(
        limits, store, hypothesis_id=rec["hypothesis_id"],
        open_positions_total=0, open_positions_symbol=0,
        exploration_open_total=0, exploration_open_symbol=0,
    )
    assert not ok and reason == "exploration_max_trades_per_hypothesis"
    rec_hz, _ = store.register(_candidate(family="pullback"), reason="r", mechanism="m")
    store.note_failure(rec_hz["hypothesis_id"], cooldown_s=1800)
    ok, reason = check_exploration_limits(
        limits, store, hypothesis_id=rec_hz["hypothesis_id"],
        open_positions_total=0, open_positions_symbol=0,
        exploration_open_total=0, exploration_open_symbol=0,
    )
    assert not ok and reason == "exploration_cooldown_after_failure"


def test_tiny_fixed_risk_sizing_never_scales_up():
    lots = risk_lots_for_exploration(
        max_risk_usd=0.15, entry=1.1000, invalidation=1.0950,
        pip=0.0001, min_lot=0.01, lot_step=0.01,
    )
    # 50-pip stop: 0.15 USD / (50 pips * $10 per pip per lot) -> 0.0003 lots -> min 0.01.
    assert lots == 0.01
    tight = risk_lots_for_exploration(
        max_risk_usd=0.15, entry=1.1000, invalidation=1.0999,
        pip=0.0001, min_lot=0.01, lot_step=0.01,
    )
    assert tight >= 0.01  # never below broker minimum


# ---------------------------------------------------------------------------
# Brain-level exploration integration
# ---------------------------------------------------------------------------


class _FakeEvidence:
    provenance = "mt5_m1"
    eligible = False
    analogue_n = 0
    analogue_n_losses = 0
    expectancy = None
    profit_factor = None
    mean_lower_95 = None
    wins_erased_by_average_loss = 99.0
    tail_loss = 0.0
    avg_win = None
    avg_loss = None
    uncertainty = "uncalibrated"
    similarity_score = 0.0


def test_brain_fires_registered_exploration_on_unvalidated_state(tmp_path, monkeypatch):
    """No validated model + unvalidated state => REGISTERED tiny exploration fire."""
    from aegis.intel.firehose_brain import IntelligentFirehoseBrain

    index = tmp_path / "analogue_index.json"
    index.write_text(json.dumps({"schema": "analogue_index.v1", "provenance": "mt5_m1",
                                 "records": []}), encoding="utf-8")
    cfg = {
        "analogue_index_path": str(index),
        "intelligent_gate_validated_states": True,
        "validated_states_path": str(tmp_path / "empty_states.json"),
        "intelligent_firehose_bootstrap": True,
        "intelligent_min_analogues": 20,
        "intelligent_min_similarity": 0.5,
        "intelligent_risk_fraction": 0.08,
        "intelligent_risk_budget_usd": 100.0,
        "order_quantity": 0.01,
        "max_positions": 40,
        "intelligent_exploration_enabled": True,
        "exploration_max_risk_per_trade_usd": 0.15,
    }
    brain = IntelligentFirehoseBrain(cfg)

    class _Ev:
        pass

    monkeypatch.setattr(brain.analogues, "query", lambda **k: _FakeEvidence())
    # Deterministic runtime state with real geometry so the exploration gate
    # chain (not structure detection) is what's under test.
    from aegis.intel import firehose_brain as fb

    fake_state = {
        "structure": {"M15": {"kind": "retest",
                              "support": 1.0995, "resistance": 1.1005}},
        "session": "asia",
        "regime": {"label": "range"},
        "multi_timeframe": {"H1": {"direction": "up"}, "M5": {"direction": "down"}},
        "volatility": {"phase": "stable"},
    }
    monkeypatch.setattr(fb, "build_runtime_state", lambda **k: fake_state)
    monkeypatch.setattr(
        fb, "runtime_signature",
        lambda state, side, setup: {"regime": "range", "structure": "retest",
                                    "session": "asia"},
    )
    frame = _exploration_frame()
    row = frame.iloc[-1].copy()
    row["time"] = frame["time"].iloc[-1]
    row["ema_20"] = float(frame["close"].iloc[-1])
    decision = brain.evaluate(
        symbol="EURUSD", row=row, completed_m1=frame.iloc[:-1],
        positions=[], equity=100.0, pip=0.0001, core_side="buy",
        spread_price=0.0002,
        symbol_spec={"volume_min": 0.01, "volume_step": 0.01,
                     "trade_contract_size": 100000.0},
        entry_price=float(row["close"]),
    )
    assert decision.action == "fire"
    assert decision.journal.get("exploration") is True
    assert decision.journal.get("promotion_stage") == "EXPLORATION_CANARY"
    hyp = decision.journal.get("hypothesis_id")
    assert hyp and hyp in brain.experiments.data["experiments"]
    # Tiny risk: quantity respects the per-trade risk budget.
    assert float(decision.quantity) <= 0.05
    snap = brain.snapshot()
    assert snap["funnel"]["candidates"] >= 1
    assert snap["funnel"]["exploration_fire"] >= 1
    assert snap["experiments_active"] >= 1
    # Race guard: the in-flight reservation must cap immediate re-fires.
    total_exp, sym_exp = brain.exploration_open_counts("EURUSD")
    assert total_exp >= 1
    row2 = frame.iloc[-2].copy()
    row2["time"] = frame["time"].iloc[-2]
    row2["ema_20"] = float(frame["close"].iloc[-2])
    decision2 = brain.evaluate(
        symbol="EURUSD", row=row2, completed_m1=frame.iloc[:-1],
        positions=[], equity=100.0, pip=0.0001, core_side="buy",
        spread_price=0.0002,
        symbol_spec={"volume_min": 0.01, "volume_step": 0.01,
                     "trade_contract_size": 100000.0},
        entry_price=float(row2["close"]),
    )
    # The second same-symbol fire must be limit-blocked (recorded in skip
    # reasons) even though its final mapped reason is the entry-gate skip.
    assert decision2.action != "fire"
    skips = brain.counts.get("skip_reasons") or {}
    assert skips.get("exploration_max_positions_per_symbol", 0) >= 1


def _exploration_frame(n=400):
    import pandas as pd

    time = pd.date_range("2026-06-01", periods=n, freq="min", tz="UTC")
    # Oscillate around 1.1000 so the last close sits INSIDE the fake
    # support/resistance geometry (buy: sl 1.0994 / tp 1.1005).
    close = pd.Series([1.1000 + (0.00003 if i % 2 else -0.00003) for i in range(n)])
    return pd.DataFrame({
        "time": time,
        "open": close - 0.00002,
        "high": close + 0.00008,
        "low": close - 0.00008,
        "close": close,
        "volume": 100.0,
    })


def test_exploration_disabled_keeps_pure_shadow(tmp_path, monkeypatch):
    from aegis.intel.firehose_brain import IntelligentFirehoseBrain

    index = tmp_path / "analogue_index.json"
    index.write_text(json.dumps({"schema": "analogue_index.v1", "provenance": "mt5_m1",
                                 "records": []}), encoding="utf-8")
    cfg = {
        "analogue_index_path": str(index),
        "intelligent_gate_validated_states": True,
        "validated_states_path": str(tmp_path / "empty_states.json"),
        "intelligent_firehose_bootstrap": True,
        "intelligent_min_analogues": 20,
        "intelligent_min_similarity": 0.5,
        "intelligent_risk_fraction": 0.08,
        "intelligent_risk_budget_usd": 100.0,
        "order_quantity": 0.01,
        "max_positions": 40,
        "intelligent_exploration_enabled": False,
    }
    brain = IntelligentFirehoseBrain(cfg)

    monkeypatch.setattr(brain.analogues, "query", lambda **k: _FakeEvidence())
    frame = _exploration_frame()
    row = frame.iloc[-1].copy()
    row["time"] = frame["time"].iloc[-1]
    row["ema_20"] = float(frame["close"].iloc[-1])
    decision = brain.evaluate(
        symbol="EURUSD", row=row, completed_m1=frame.iloc[:-1],
        positions=[], equity=100.0, pip=0.0001, core_side="buy",
        spread_price=0.0002,
        symbol_spec={"volume_min": 0.01, "volume_step": 0.01},
        entry_price=float(row["close"]),
    )
    assert decision.action != "fire"
    assert not decision.journal.get("exploration")


def test_champion_requirements_unchanged_by_exploration():
    """Exploration NEVER weakens champion gates: CASE A/B still fail."""
    import pytest as _pytest
    from aegis.research.gates import GateReject
    from aegis.research.govern import governed_accept

    with _pytest.raises(GateReject):
        governed_accept(
            {"win_rate": 91.91, "profit_factor": 0.71, "expectancy": -0.0007,
             "n_trades": 140, "net_pnl": -11.32},
            champion=None,
            pnls=[0.03] * 128 + [-2.5] * 12,
            n_searches=1,
        )


def test_heartbeat_rates_present_after_activity(tmp_path, monkeypatch):
    from aegis.intel.firehose_brain import IntelligentFirehoseBrain

    index = tmp_path / "analogue_index.json"
    index.write_text(json.dumps({"schema": "analogue_index.v1", "provenance": "mt5_m1",
                                 "records": []}), encoding="utf-8")
    cfg = {
        "analogue_index_path": str(index),
        "intelligent_exploration_enabled": True,
        "intelligent_risk_fraction": 0.08,
        "intelligent_risk_budget_usd": 100.0,
    }
    brain = IntelligentFirehoseBrain(cfg)
    brain._note_stage("candidate")
    brain._note_stage("exploration_fire")
    snap = brain.snapshot()
    for key in ("candidate_rate_per_hour", "exploration_fires_per_hour",
                "shadow_candidates_per_hour", "demo_canary_fires_per_hour",
                "champion_fires_per_hour", "minutes_since_last_candidate",
                "minutes_since_last_exploration_fire",
                "minutes_since_last_validated_fire"):
        assert key in snap, key
    assert snap["candidate_rate_per_hour"] >= 1.0

def test_self_hedge_same_family_blocked(tmp_path, monkeypatch):
    """Spec J: opposing same-symbol exposure requires a DIFFERENT mechanism;
    same-family opposite-side exploration is blocked."""
    from aegis.intel.firehose_brain import IntelligentFirehoseBrain

    index = tmp_path / "analogue_index.json"
    index.write_text(json.dumps({"schema": "analogue_index.v1", "provenance": "mt5_m1",
                                 "records": []}), encoding="utf-8")
    cfg = {
        "analogue_index_path": str(index),
        "intelligent_gate_validated_states": True,
        "validated_states_path": str(tmp_path / "empty_states.json"),
        "intelligent_firehose_bootstrap": True,
        "intelligent_min_analogues": 20,
        "intelligent_min_similarity": 0.5,
        "intelligent_risk_fraction": 0.08,
        "intelligent_risk_budget_usd": 100.0,
        "order_quantity": 0.01,
        "max_positions": 40,
        "intelligent_exploration_enabled": True,
    }
    brain = IntelligentFirehoseBrain(cfg)

    class _Ev:
        pass

    monkeypatch.setattr(brain.analogues, "query", lambda **k: _FakeEvidence())
    from aegis.intel import firehose_brain as fb

    fake_state = {
        "structure": {"M15": {"kind": "retest",
                              "support": 1.0995, "resistance": 1.1005}},
        "session": "asia",
        "regime": {"label": "range"},
        "multi_timeframe": {"H1": {"direction": "up"}, "M5": {"direction": "down"}},
        "volatility": {"phase": "stable"},
    }
    monkeypatch.setattr(fb, "build_runtime_state", lambda **k: fake_state)
    monkeypatch.setattr(
        fb, "runtime_signature",
        lambda state, side, setup: {"regime": "range", "structure": "retest",
                                    "session": "asia"},
    )
    frame = _exploration_frame()

    def _eval(side):
        row = frame.iloc[-1].copy()
        row["time"] = frame["time"].iloc[-1]
        row["ema_20"] = float(frame["close"].iloc[-1])
        return brain.evaluate(
            symbol="EURUSD", row=row, completed_m1=frame.iloc[:-1],
            positions=[], equity=100.0, pip=0.0001, core_side=side,
            spread_price=0.0002,
            symbol_spec={"volume_min": 0.01, "volume_step": 0.01,
                         "trade_contract_size": 100000.0},
            entry_price=float(row["close"]),
        )

    first = _eval("buy")
    assert first.action == "fire" and first.journal.get("exploration")
    # Opposite side, SAME family/mechanism -> blocked as self-hedge.
    second = _eval("sell")
    skips = brain.counts.get("skip_reasons") or {}
    assert skips.get("self_hedge_blocked_same_family", 0) >= 1
    assert second.action != "fire"
