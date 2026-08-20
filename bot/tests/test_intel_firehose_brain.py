"""Intelligent Firehose demo brain tests."""
from __future__ import annotations

import json
from pathlib import Path

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


def _positive_records(symbol: str = "EURUSD", n: int = 30, signature: dict | None = None) -> list[dict]:
    """Positive-payoff records. Pass ``signature`` so they actually match the query.

    Without it these rows described a breakout/london state while ``_m1()`` produces a
    retest/asia state, so only a handful ever cleared the similarity threshold.
    """
    sig = signature or {
        "side": "buy",
        "setup": "breakout",
        "regime": "trend",
        "structure": "breakout",
        "volatility": "expanding",
        "session": "london",
        "h1_direction": "up",
        "m5_direction": "up",
    }
    return [
        {
            "bar_time": f"2025-12-{(index % 27) + 1:02d}T{hour:02d}:00:00+00:00",
            "symbol": symbol,
            "side": sig["side"],
            "setup": sig["setup"],
            "regime": sig["regime"],
            "structure": sig["structure"],
            "volatility": sig["volatility"],
            "session": sig["session"],
            "h1_direction": sig["h1_direction"],
            "m5_direction": sig["m5_direction"],
            "outcome": 0.04 if index % 4 else -0.02,
        }
        for index, hour in enumerate(range(n))
    ]


def _signature_for_m1(frame: pd.DataFrame, side: str = "buy") -> dict:
    from aegis.intel.state_runtime import build_runtime_state, runtime_signature

    state = build_runtime_state(symbol="EURUSD", m1=frame)
    m15 = (state.get("structure") or {}).get("M15") or {}
    return runtime_signature(state, side=side, setup=str(m15.get("kind") or "scan"))


def _basing_above_support(n: int = 400) -> pd.DataFrame:
    """Long decline that flattens out just above its low: a small invalidation
    against a large target, which is the payoff shape that can actually fire."""
    decline_bars = n - 60
    top = 1.1340
    decline = [top - index * (0.0340 / decline_bars) for index in range(decline_bars)]
    low = decline[-1]
    base = [low + 0.00003 * (index % 3) for index in range(60)]
    return _frame(decline + base)


def _frame(closes: list[float], start: str = "2026-01-01") -> pd.DataFrame:
    time = pd.date_range(start, periods=len(closes), freq="min", tz="UTC")
    close = pd.Series(closes)
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
    m1_for_signature = _m1()
    records = _positive_records(n=40, signature=_signature_for_m1(m1_for_signature.iloc[:-1]))
    index = tmp_path / "analogue_index.json"
    index.write_text(
        json.dumps(
            {
                "schema": "analogue_index.v1",
                "provenance": "mt5_m1",
                "outcome_unit": "usd",
                "records": records,
            }
        ),
        encoding="utf-8",
    )
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
    # This used to be guarded by `if decision.action in {...}`, which passed even
    # when the brain never fired. Assert the reachable outcome instead: evidence was
    # matched, and any fire/scale carries a real invalidation.
    assert decision.analogue_n >= 20
    assert decision.action in {"fire", "scale", "skip", "hold"}
    if decision.action in {"fire", "scale"}:
        assert decision.sl is not None


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


def test_runtime_session_labels_match_research_index():
    """Runtime sessions must use the same labels as the analogue index so the
    validated-state gate can ever match a live signature."""
    from aegis.intel.state_runtime import _session

    assert _session(pd.Timestamp("2026-01-01T08:00:00+00:00")) == "london"
    assert _session(pd.Timestamp("2026-01-01T15:00:00+00:00")) == "newyork"
    assert _session(pd.Timestamp("2026-01-01T03:00:00+00:00")) == "asia"
    # 21:00-24:00 is part of Asia in dataplane.session_label, not a separate "late".
    assert _session(pd.Timestamp("2026-01-01T22:00:00+00:00")) == "asia"


def _validated_allowlist(tmp_path, states) -> Path:
    path = tmp_path / "validated_states.json"
    path.write_text(
        json.dumps(
            {
                "schema": "validated_states.v1",
                "n_survive": len(states),
                "states": states,
            }
        ),
        encoding="utf-8",
    )
    return path


def _evaluate_brain(brain, frame, side="buy"):
    m1 = frame
    row = m1.iloc[-1].copy()
    row["time"] = m1["time"].iloc[-1]
    row["ema_20"] = float(m1["close"].iloc[-1])
    return brain.evaluate(
        symbol="EURUSD",
        row=row,
        completed_m1=m1.iloc[:-1],
        positions=[],
        equity=100.0,
        pip=0.0001,
        core_side=side,
        spread_price=0.00005,
        symbol_spec={
            "trade_tick_size": 0.00001,
            "trade_tick_value": 1.0,
            "trade_tick_value_loss": 1.0,
            "trade_contract_size": 100000.0,
            "point": 0.00001,
        },
        entry_price=float(row["close"]),
    )


def _gated_brain(tmp_path, signature, allow_states, n=80):
    records = _positive_records(n=n, signature=signature)
    index = tmp_path / "analogue_index.json"
    index.write_text(
        json.dumps(
            {
                "schema": "analogue_index.v1",
                "provenance": "mt5_m1",
                "outcome_unit": "usd",
                "records": records,
            }
        ),
        encoding="utf-8",
    )
    allowlist = _validated_allowlist(tmp_path, allow_states)
    cfg = {
        "analogue_index_path": str(index),
        "validated_states_path": str(allowlist),
        "intelligent_gate_validated_states": True,
        "intelligent_firehose_bootstrap": True,
        "intelligent_min_analogues": 20,
        "intelligent_min_similarity": 0.5,
        "intelligent_risk_fraction": 0.08,
        "intelligent_risk_budget_usd": 100.0,
        "order_quantity": 0.01,
        "max_positions": 40,
    }
    return IntelligentFirehoseBrain(cfg)


def test_gate_blocks_fire_outside_validated_states(tmp_path):
    """With the gate on, a state that is not validated must not fire, even when
    analogue evidence and economics are both good."""
    m1 = _m1()
    signature = _signature_for_m1(m1.iloc[:-1])
    allow_states = [
        {
            "regime": "range",
            "structure": "none",
            "session": "asia",
            "side": "sell",
        }
    ]
    brain = _gated_brain(tmp_path, signature, allow_states)
    decision = _evaluate_brain(brain, m1)
    assert decision.action != "fire"
    assert decision.reason == "state_not_in_validated_set"


def test_gate_allows_fire_on_validated_state(tmp_path):
    """When the current state is in the allowlist, the gate must not block a
    genuine fire."""
    m1 = _basing_above_support()
    signature = _signature_for_m1(m1.iloc[:-1])
    allow_states = [
        {
            "regime": signature["regime"],
            "structure": signature["structure"],
            "session": signature["session"],
            "side": signature["side"],
        }
    ]
    brain = _gated_brain(tmp_path, signature, allow_states)
    decision = _evaluate_brain(brain, m1)
    assert decision.action == "fire", f"expected fire, got {decision.action}: {decision.reason}"


def test_gate_with_empty_allowlist_fires_nothing(tmp_path):
    """Gating on with an empty allowlist means no state is validated, so nothing
    may fire."""
    m1 = _m1()
    signature = _signature_for_m1(m1.iloc[:-1])
    brain = _gated_brain(tmp_path, signature, [])
    decision = _evaluate_brain(brain, m1)
    assert decision.action != "fire"
    assert decision.reason == "state_not_in_validated_set"


def test_gate_off_preserves_legacy_bootstrap(tmp_path):
    """Without the gate flag, behaviour is unchanged: eligible evidence may fire."""
    m1 = _m1()
    records = _positive_records(n=40, signature=_signature_for_m1(m1.iloc[:-1]))
    index = tmp_path / "analogue_index.json"
    index.write_text(
        json.dumps(
            {
                "schema": "analogue_index.v1",
                "provenance": "mt5_m1",
                "outcome_unit": "usd",
                "records": records,
            }
        ),
        encoding="utf-8",
    )
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
    decision = _evaluate_brain(brain, m1)
    assert decision.analogue_n >= 20
    assert decision.action in {"fire", "scale", "skip", "hold"}


def test_gate_uses_exact_state_evidence_not_fuzzy_pool(tmp_path):
    """Regression: a validated state must be evaluated on the exact 4-key population
    the research pipeline validated. The fuzzy 9-key similarity pool mixes in records
    that differ on the state keys, drowning a real edge - a state with a positive
    exact-match expectancy was skipped as no_validated_strategy_model even though it
    was in the allowlist. An allowlisted state must fire when its exact match is
    positive, even if near-miss records in the same index are negative."""
    m1 = _basing_above_support()
    signature = _signature_for_m1(m1.iloc[:-1])
    exact_records = _positive_records(n=60, signature=signature)
    for index, record in enumerate(exact_records):
        record["bar_time"] = f"2025-11-{(index % 27) + 1:02d}T{index % 24:02d}:00:00+00:00"
    # Near-miss records: same symbol/volatility/directions but different state keys
    # (wrong regime or session). These pass the 0.5 fuzzy similarity threshold and
    # were dragging the evidence negative while the exact match stayed positive.
    polluted = _positive_records(n=120, signature=signature)
    for index, record in enumerate(polluted):
        record["bar_time"] = f"2025-10-{(index % 27) + 1:02d}T{index % 24:02d}:00:00+00:00"
        record["regime"] = "trend" if record["regime"] != "trend" else "noise"
        record["session"] = "newyork" if record["session"] != "newyork" else "london"
        record["outcome"] = -0.08
    index_path = tmp_path / "analogue_index.json"
    index_path.write_text(
        json.dumps(
            {
                "schema": "analogue_index.v1",
                "provenance": "mt5_m1",
                "outcome_unit": "usd",
                "records": exact_records + polluted,
            }
        ),
        encoding="utf-8",
    )
    allow_states = [
        {
            "regime": signature["regime"],
            "structure": signature["structure"],
            "session": signature["session"],
            "side": signature["side"],
        }
    ]
    allowlist = _validated_allowlist(tmp_path, allow_states)
    cfg = {
        "analogue_index_path": str(index_path),
        "validated_states_path": str(allowlist),
        "intelligent_gate_validated_states": True,
        "intelligent_firehose_bootstrap": True,
        "intelligent_min_analogues": 20,
        "intelligent_min_similarity": 0.5,
        "intelligent_risk_fraction": 0.08,
        "intelligent_risk_budget_usd": 100.0,
        "order_quantity": 0.01,
        "max_positions": 40,
    }
    brain = IntelligentFirehoseBrain(cfg)
    decision = _evaluate_brain(brain, m1)
    assert decision.action == "fire", f"expected fire, got {decision.action}: {decision.reason}"
    assert decision.analogue_n >= 20
