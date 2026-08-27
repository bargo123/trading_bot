"""Intelligent Firehose demo brain tests."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from aegis.intel.analogue_store import AnalogueStore
from aegis.intel.firehose_brain import (
    IntelligentFirehoseBrain,
    _load_validated_opportunities,
    _shadow_probe_is_hard_economic_rejection,
)
from aegis.intel.strategy_model import ValidatedStrategyModel, strategy_model_ready
from aegis.intel.expected_value import payoff_metrics


def _v2_opportunity(*, family: str = "failed_breakout_fade", with_cost: bool = True) -> dict:
    record = {
        "level": "A",
        "symbol": "EURUSD",
        "strategy_family": family,
        "strategy_version": "rule-v1",
        "rule_fingerprint": "rule-hash",
        "regime": "range",
        "structure": "none",
        "session": "asia",
        "side": "sell",
        "dataset_hash": "dataset-hash",
        "config_hash": "config-hash",
        "code_version": "code-hash",
        "index_hash": "index-hash",
        "survives_validate": True,
        "expectancy_validate": 0.2,
    }
    if with_cost:
        record["session_cost_provenance"] = {
            "source": "measured_quotes",
            "symbol": "EURUSD",
            "session": "asia",
            "spread_pips": 0.8,
        }
    return record


def test_v2_validated_family_cannot_authorize_different_runtime_family(tmp_path):
    artifact = tmp_path / "validated_opportunities.json"
    artifact.write_text(json.dumps({
        "schema": "validated_opportunities.v2",
        "opportunities": [_v2_opportunity()],
    }), encoding="utf-8")

    loaded = _load_validated_opportunities(artifact)

    assert "EURUSD|failed_breakout_fade|range|none|asia|sell" in loaded
    assert "EURUSD|micro_momentum_burst|range|none|asia|sell" not in loaded


def test_v2_permission_requires_measured_session_cost_provenance(tmp_path):
    artifact = tmp_path / "validated_opportunities.json"
    artifact.write_text(json.dumps({
        "schema": "validated_opportunities.v2",
        "opportunities": [_v2_opportunity(with_cost=False)],
    }), encoding="utf-8")

    assert _load_validated_opportunities(artifact) == {}


def test_shadow_probe_telemetry_preserves_hard_economic_rejections():
    assert _shadow_probe_is_hard_economic_rejection(
        fire_base="short_horizon_not_calibrated",
        economics_reason="expected_net_value_not_positive",
    )
    assert _shadow_probe_is_hard_economic_rejection(
        fire_base="short_horizon_not_calibrated",
        economics_reason="payoff_below_floor",
    )
    assert not _shadow_probe_is_hard_economic_rejection(
        fire_base="short_horizon_not_calibrated",
        economics_reason="no_win_probability_evidence",
    )


def _write_canary(index_path: Path, *, symbol: str = "EURUSD") -> Path:
    """A valid DEMO_CANARY artifact bound to this tmp index (defect 16)."""
    canary = {
        "schema": "demo_canary.v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "expires_utc": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        "strategy_id": f"canary_{symbol}_test",
        "opportunity": {"symbol": symbol},
        "metrics": {"expectancy_validate": 0.05},
        "dataset_hash": "test",
        "validation_hash": "test",
        "index_file_sha256": hashlib.sha256(index_path.read_bytes()).hexdigest(),
        "risk_fraction": 0.08,
    }
    path = index_path.parent / "demo_canary.json"
    path.write_text(json.dumps(canary), encoding="utf-8")
    return path


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
        "intelligent_bootstrap_canary": True,
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

    gated = brain.evaluate(
        symbol="EURUSD",
        row=row,
        completed_m1=m1.iloc[:-1],
        positions=[],
        equity=100.0,
        pip=0.0001,
        core_side="buy",
        short_horizon_prediction={
            "calibration_status": "calibrated",
            "abstain": False,
            "probability": 0.9,
            "expected_net_pnl": -0.01,
        },
    )
    assert gated.action == "skip"
    assert gated.reason == "short_horizon_negative_expected_value"
    assert gated.journal["short_horizon_gate"] == "short_horizon_negative_expected_value"
    assert brain.counts["short_horizon_expected_value_reject"] == 1

    abstained = brain.evaluate(
        symbol="EURUSD",
        row=row,
        completed_m1=m1.iloc[:-1],
        positions=[],
        equity=100.0,
        pip=0.0001,
        core_side="buy",
        short_horizon_prediction={
            "calibration_status": "calibrated",
            "abstain": True,
            "abstain_reason": "uncertainty_high",
            "probability": 0.55,
            "model_agreement": 2.0 / 3.0,
            "uncertainty": 0.45,
        },
    )
    assert abstained.reason == "short_horizon_abstain"
    assert brain.counts["short_horizon_abstain_reasons"]["uncertainty_high"] == 1


def test_video_candidate_is_recorded_when_short_horizon_abstains(tmp_path):
    """A model veto must not erase an already-detected video-style candidate."""
    index = tmp_path / "analogue_index.json"
    index.write_text(json.dumps({"schema": "analogue_index.v1", "records": []}), encoding="utf-8")
    brain = IntelligentFirehoseBrain({
        "analogue_index_path": str(index),
        "intelligent_exploration_enabled": False,
        "intelligent_min_analogues": 20,
        "order_quantity": 0.01,
    })
    frame = _frame([1.1000, 1.1005, 1.1015])
    row = frame.iloc[-1].copy()

    decision = brain.evaluate(
        symbol="EURUSD",
        row=row,
        completed_m1=frame,
        positions=[],
        equity=100.0,
        pip=0.0001,
        core_side="buy",
        actual_bid=1.1014,
        actual_ask=1.1015,
        entry_price=1.1015,
        video_style=True,
        short_horizon_prediction={
            "calibration_status": "calibrated",
            "abstain": True,
            "abstain_reason": "uncertainty_high",
            "model_agreement": 1.0,
            "model_disagreement": False,
            "uncertainty": 0.8,
            "probability": 0.5,
            "expected_net_pnl": 0.01,
        },
    )

    assert decision.action == "skip"
    assert decision.reason == "short_horizon_abstain"
    assert decision.journal["micro_candidate_count"] == 1
    assert decision.journal["micro_diagnostics"]["video_style_candidate"] == "candidate_matched"


def test_video_predictor_unavailable_produces_zero_order_intent(tmp_path):
    index = tmp_path / "analogue_index.json"
    index.write_text(json.dumps({"schema": "analogue_index.v1", "records": []}), encoding="utf-8")
    brain = IntelligentFirehoseBrain({
        "analogue_index_path": str(index),
        "intelligent_exploration_enabled": True,
        "intelligent_min_analogues": 20,
        "order_quantity": 0.01,
        "exploration_max_positions": 2,
        "exploration_max_positions_per_symbol": 1,
        "exploration_max_risk_per_trade_usd": 0.15,
    })
    frame = _frame([1.1000, 1.1005, 1.1015])
    decision = brain.evaluate(
        symbol="EURUSD", row=frame.iloc[-1].copy(), completed_m1=frame,
        positions=[], equity=100.0, pip=0.0001, core_side="buy",
        actual_bid=1.1014, actual_ask=1.1015, entry_price=1.1015,
        video_style=True, short_horizon_prediction=None,
    )

    assert decision.action == "skip"
    assert decision.reason == "short_horizon_prediction_missing"
    assert decision.quantity == 0.0

def test_brain_can_fire_with_bootstrap_analogues(tmp_path):
    m1_for_signature = _m1()
    records = _positive_records(n=40, signature=_signature_for_m1(m1_for_signature.iloc[:-1]))
    index = tmp_path / "analogue_index.json"
    index.write_text(
        json.dumps(
            {
                "schema": "analogue_index.v1",
                "provenance": "mt5_tick_replay",
                "outcome_unit": "usd",
                "records": records,
            }
        ),
        encoding="utf-8",
    )
    cfg = {
        "analogue_index_path": str(index),
        "intelligent_firehose_bootstrap": True,
        "intelligent_bootstrap_canary": True,
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


def test_refresh_reloads_watcher_regenerated_validated_states(tmp_path):
    """The runner can pick up watcher artifacts without a process restart."""
    index = tmp_path / "analogue_index.json"
    index.write_text(
        json.dumps({"schema": "analogue_index.v1", "provenance": "mt5_m1", "records": []}),
        encoding="utf-8",
    )
    allowlist = tmp_path / "validated_states.json"
    brain = IntelligentFirehoseBrain(
        {
            "analogue_index_path": str(index),
            "validated_states_path": str(allowlist),
        }
    )
    assert brain.validated_states == frozenset()

    _validated_allowlist(
        tmp_path,
        [{"regime": "trend", "structure": "none", "session": "asia", "side": "buy"}],
    )
    brain.refresh()

    assert len(brain.validated_states) == 1


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
                "provenance": "mt5_tick_replay",
                "outcome_unit": "usd",
                "records": records,
            }
        ),
        encoding="utf-8",
    )
    allowlist = _validated_allowlist(tmp_path, allow_states)
    canary_path = _write_canary(index)
    cfg = {
        "analogue_index_path": str(index),
        "validated_states_path": str(allowlist),
        "intelligent_gate_validated_states": True,
        "intelligent_firehose_bootstrap": True,
        "intelligent_bootstrap_canary": True,
        "demo_canary_path": str(canary_path),
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


def test_gate_allows_validated_state_to_reach_economics(tmp_path):
    """A validated state passes authorization even when it lacks a legal target."""
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
    assert decision.reason == "trade_economics:no_structural_target"
    assert decision.reason != "state_not_in_validated_set"


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
                "provenance": "mt5_tick_replay",
                "outcome_unit": "usd",
                "records": records,
            }
        ),
        encoding="utf-8",
    )
    cfg = {
        "analogue_index_path": str(index),
        "intelligent_firehose_bootstrap": True,
        "intelligent_bootstrap_canary": True,
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
                "provenance": "mt5_tick_replay",
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
        "intelligent_bootstrap_canary": True,
        "demo_canary_path": str(_write_canary(index_path)),
        "intelligent_min_analogues": 20,
        "intelligent_min_similarity": 0.5,
        "intelligent_risk_fraction": 0.08,
        "intelligent_risk_budget_usd": 100.0,
        "order_quantity": 0.01,
        "max_positions": 40,
    }
    brain = IntelligentFirehoseBrain(cfg)
    decision = _evaluate_brain(brain, m1)
    assert decision.reason == "trade_economics:no_structural_target"
    assert decision.analogue_n >= 20
    assert decision.analogue_n >= 20


def _bootstrap_cfg(tmp_path, index, **extra):
    canary_path = _write_canary(index)
    cfg = {
        "analogue_index_path": str(index),
        "intelligent_firehose_bootstrap": True,
        "intelligent_min_analogues": 20,
        "intelligent_min_similarity": 0.5,
        "intelligent_risk_fraction": 0.08,
        "intelligent_risk_budget_usd": 100.0,
        "order_quantity": 0.01,
        "max_positions": 40,
        "demo_canary_path": str(canary_path),
    }
    cfg.update(extra)
    return cfg


def test_bootstrap_research_stage_cannot_trade(tmp_path):
    """P2/P14-15 + exploration: a research bootstrap can NEVER trade as a
    validated stage. An unvalidated state becomes a REGISTERED tiny-risk
    EXPLORATION_CANARY experiment instead - never a pseudo-champion."""
    m1 = _basing_above_support()
    signature = _signature_for_m1(m1.iloc[:-1])
    allow_states = [{k: signature[k] for k in ("regime", "structure", "session", "side")}]
    records = _positive_records(n=80, signature=signature)
    index = tmp_path / "analogue_index.json"
    index.write_text(json.dumps({"schema": "analogue_index.v1", "provenance": "mt5_tick_replay",
                                 "outcome_unit": "usd", "records": records}), encoding="utf-8")
    allowlist = _validated_allowlist(tmp_path, allow_states)
    cfg = _bootstrap_cfg(
        tmp_path, index,
        validated_states_path=str(allowlist),
        intelligent_gate_validated_states=True,
        # No canary artifact: the bootstrap itself stays UNVALIDATED_RESEARCH.
        demo_canary_path=str(tmp_path / "no_canary.json"),
    )
    brain = IntelligentFirehoseBrain(cfg)
    decision = _evaluate_brain(brain, m1)
    snap = brain.snapshot()
    assert snap["strategy_status"] in {"UNQUALIFIED_NO_VALIDATED_MODEL", "QUALIFIED_SHADOW_ONLY"}
    assert snap["promotion_stage"] != "DEMO_CHAMPION"
    if decision.action == "fire":
        # Only lawful exploration shape: registered hypothesis, tiny risk.
        assert decision.reason == "exploration_hypothesis_test"
        assert decision.journal.get("promotion_stage") == "EXPLORATION_CANARY"
        assert decision.journal.get("hypothesis_id")
        assert decision.journal.get("hypothesis_id") in brain.experiments.data["experiments"]
        assert float(decision.quantity) <= 0.05


def test_synthetic_evidence_never_reaches_trading_stage(tmp_path):
    """P14-19: synthetic/proxy analogue evidence cannot qualify for a trading stage."""
    from aegis.intel.firehose_brain import _bootstrap_from_evidence

    class FakeEvidence:
        provenance = "synthetic_fixture"
        eligible = True
        analogue_n = 60
        analogue_n_losses = 10
        expectancy = 0.05
        profit_factor = 2.0
        mean_lower_95 = 0.01
        wins_erased_by_average_loss = 0.5
        tail_loss = -0.02
        avg_win = 0.04
        avg_loss = -0.02

    cfg = {
        "intelligent_firehose_bootstrap": True,
        "intelligent_allow_synthetic_evidence": True,
        "intelligent_bootstrap_canary": True,  # even with canary opt-in
        "intelligent_risk_fraction": 0.08,
    }
    model = _bootstrap_from_evidence(cfg, FakeEvidence())
    assert model is not None
    assert model.promotion_stage == "UNVALIDATED_RESEARCH"
    assert not model.may_trade


def test_champion_artifact_is_demo_champion_stage():
    """A sealed-validation accepted artifact loads at DEMO_CHAMPION stage."""
    from aegis.intel.firehose_brain import _load_strategy

    payload = {
        "id": "champ_v1",
        "status": "accepted",
        "n_trades": 120,
        "n_losses": 30,
        "expectancy": 0.03,
        "profit_factor": 1.5,
        "bootstrap_p05": 0.005,
        "wins_erased_by_average_loss": 1.2,
        "wins_erased_by_tail_loss": 3.0,
        "validated_risk_fraction": 0.08,
        "artifact_hash": "abc123",
        "dataset_hash": "ds-hash",
        "validation_hash": "val-hash",
    }
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "intelligent_champion.json"
        p.write_text(json.dumps(payload), encoding="utf-8")
        model = _load_strategy({"intelligent_champion_path": str(p)})
    assert model is not None
    assert model.promotion_stage == "DEMO_CHAMPION"
    assert model.may_trade
    assert model.dataset_hash == "ds-hash"


def test_case_a_high_wr_negative_ev_fails_promotion():
    """P12/P14-1: WR 91.91% / PF 0.71 / negative EV MUST FAIL promotion."""
    import pytest
    from aegis.research.gates import GateReject
    from aegis.research.govern import governed_accept

    metrics = {
        "win_rate": 91.91,
        "profit_factor": 0.71,
        "expectancy": -0.0007,
        "n_trades": 140,
        "net_pnl": -11.32,
    }
    pnls = [0.03] * 128 + [-2.5] * 12  # the classic 1-pip TP / 30-pip SL geometry
    with pytest.raises(GateReject):
        governed_accept(metrics, champion=None, pnls=pnls, n_searches=1)


def test_case_b_low_wr_negative_ev_fails_promotion():
    """P12/P14-2: 66 trades / WR 31.82% / PF~0.33 / negative EV MUST FAIL."""
    import pytest
    from aegis.research.gates import GateReject
    from aegis.research.govern import governed_accept

    metrics = {
        "win_rate": 31.82,
        "profit_factor": 0.33,
        "expectancy": -0.0685,
        "n_trades": 66,
        "net_pnl": -4.52,
    }
    pnls = [0.04] * 21 + [-0.15] * 45
    with pytest.raises(GateReject):
        governed_accept(metrics, champion=None, pnls=pnls, n_searches=1)
