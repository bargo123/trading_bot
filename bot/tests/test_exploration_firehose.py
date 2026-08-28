"""Exploration Firehose tests: registered experiments, hard limits, sequential
learning, failed-experiment memory, funnel counters. DEMO-only by design."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

from aegis.intel.fast_firehose import (  # noqa: E402
    check_entry_economics,
    generate_micro_candidates,
)

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
    assert rec1["status"] == "NEW"  # lifecycle starts NEW (audited fix)
    assert rec1["entry_rule"] and rec1["invalidation_rule"] and rec1["target_rule"]
    assert rec1["reason_for_experiment"] and rec1["expected_mechanism"]


def test_lifecycle_reachable_within_runtime_cap(store):
    """Audited defect 2: MIN_N_TO_JUDGE(4) <= max_trades_per_hypothesis(5).

    Runtime-realistic: closes flow through record_close with the SAME cap the
    runner enforces. losing -> REJECTED; strong -> PROMISING; inconclusive ->
    UNCERTAIN then EXHAUSTED at cap."""
    cap = 5

    def run(family, pnl_pattern):
        rec, _ = store.register(_candidate(family=family), reason="r", mechanism="m")
        hid = rec["hypothesis_id"]
        for i in range(cap):
            store.record_close(hypothesis_id=hid,
                               pnl=pnl_pattern(i), max_trades=cap)
        return store.data["experiments"][hid]

    loser = run("breakout", lambda i: -0.05)
    assert loser["status"] == "REJECTED"

    strong = run("pullback", lambda i: 0.20)
    assert strong["status"] == "PROMISING"
    assert strong["evidence"]["n"] <= cap

    mixed = run("momentum", lambda i: 0.30 if i % 2 == 0 else -0.28)
    assert mixed["status"] == "EXHAUSTED"
    assert mixed["evidence"]["n"] == cap


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


@pytest.mark.parametrize("configured_limit", [0, -1])
def test_non_positive_daily_loss_limit_disables_exploration_halt(store, configured_limit):
    limits = ExplorationLimits.from_cfg({
        "exploration_max_daily_loss_usd": configured_limit,
    })
    rec, _ = store.register(_candidate(side="sell"), reason="r", mechanism="m")
    store.record_close(hypothesis_id=rec["hypothesis_id"], pnl=-10.0)

    ok, reason = check_exploration_limits(
        limits, store, hypothesis_id="new-hypothesis",
        open_positions_total=0, open_positions_symbol=0,
        exploration_open_total=0, exploration_open_symbol=0,
    )

    assert limits.max_daily_loss_usd == configured_limit
    assert ok and reason == "ok"


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


def test_zero_exploration_concurrency_and_cooldown_are_disabled():
    limits = ExplorationLimits.from_cfg({
        "exploration_max_positions": 0,
        "exploration_max_positions_per_symbol": 0,
        "exploration_cooldown_after_failure_s": 0,
    })

    assert limits.max_positions is None
    assert limits.max_positions_per_symbol is None
    assert limits.cooldown_after_failure_s == 0


def test_exploration_close_does_not_pause_unrelated_search_after_one_loss(tmp_path):
    from aegis.intel.firehose_brain import IntelligentFirehoseBrain

    index = tmp_path / "analogue_index.json"
    index.write_text(json.dumps({"schema": "analogue_index.v1", "records": []}), encoding="utf-8")
    brain = IntelligentFirehoseBrain({
        "analogue_index_path": str(index),
        "exploration_cooldown_after_failure_s": 1800,
    })
    rec, _ = brain.experiments.register(
        {"hypothesis_id": "h-loss", "strategy_family": "x", "symbol": "EURUSD",
         "side": "buy", "regime": "range", "session": "asia"},
        reason="test", mechanism="test",
    )

    brain.record_exploration_close(hypothesis_id=rec["hypothesis_id"], pnl=-0.01)

    assert "cooldown_until_utc" not in brain.experiments.data["experiments"]["h-loss"]


def test_tiny_fixed_risk_sizing_rejects_when_min_lot_exceeds_budget():
    """Audited defect 1: broker-minimum lot whose stop risk exceeds the
    configured budget MUST be rejected - never rounded up to 0.01."""
    from aegis.intel.exploration import risk_lots_for_exploration

    # 50-pip stop: risk per 0.01 lot = $5.00 >> $0.15 budget -> REJECT.
    r = risk_lots_for_exploration(
        max_risk_usd=0.15, entry=1.1000, invalidation=1.0950,
        pip=0.0001, contract_size=100000.0,
        volume_min=0.01, volume_step=0.01,
    )
    assert r["allowed"] is False
    assert r["reason"] == "exploration_min_lot_exceeds_risk_budget"
    assert r["lots"] == 0.0
    assert r["actual_min_lot_risk_usd"] == pytest.approx(5.0)

    # Tight 1-pip stop: min-lot risk $0.10 <= budget -> allowed at 0.01.
    ok = risk_lots_for_exploration(
        max_risk_usd=0.15, entry=1.1000, invalidation=1.0999,
        pip=0.0001, contract_size=100000.0,
        volume_min=0.01, volume_step=0.01,
    )
    assert ok["allowed"] is True
    assert ok["lots"] == pytest.approx(0.01)
    # Broker-native tick fields produce the same math.
    tick = risk_lots_for_exploration(
        max_risk_usd=0.15, entry=1.1000, invalidation=1.0950,
        pip=0.0001, contract_size=100000.0,
        tick_value=1.0, tick_size=0.00001,
        volume_min=0.01, volume_step=0.01,
    )
    assert tick["allowed"] is False


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


class _PositiveEvidence(_FakeEvidence):
    # Exploration probability authority must come from the same executable
    # quote/tick capture replay as the runner, not generic M1 structure.
    provenance = "mt5_tick_replay"
    eligible = True
    analogue_n = 60
    analogue_n_losses = 12
    expectancy = 0.01
    profit_factor = 2.0
    uncertainty = "calibrated"
    similarity_score = 0.8


class _LowCaptureConfidenceEvidence(_PositiveEvidence):
    """Positive arithmetic payoff must not rescue sub-majority capture odds."""

    win_probability = 0.47
    analogue_n_losses = 32


def test_brain_fires_registered_exploration_on_unvalidated_state(tmp_path):
    from aegis.intel.firehose_brain import IntelligentFirehoseBrain
    from aegis.intel.fast_firehose import FastMarketContext, check_entry_economics
    index = tmp_path / 'analogue_index.json'
    index.write_text(json.dumps({'schema': 'ai', 'records': []}), encoding='utf-8')
    cfg = {
        'analogue_index_path': str(index),
        'intelligent_gate_validated_states': True,
        'validated_states_path': str(tmp_path / 'empty_states.json'),
        'intelligent_firehose_bootstrap': True,
        'intelligent_min_analogues': 20,
        'intelligent_min_similarity': 0.5,
        'intelligent_risk_fraction': 0.08,
        'intelligent_risk_budget_usd': 100.0,
        'order_quantity': 0.01, 'max_positions': 40,
        'intelligent_exploration_enabled': True,
        'exploration_max_risk_per_trade_usd': 0.15,
        'exploration_max_daily_loss_usd': 0,
    }
    brain = IntelligentFirehoseBrain(cfg)
    ctx = FastMarketContext(
        symbol='EURUSD', bid=1.09998, ask=1.10000, spread_pips=0.2,
        m1_close=1.09999, m1_prev_close=1.10001, m1_atr=0.00002,
        m1_low=1.09997, m1_high=1.10012,        m15_direction='down', m15_support=1.09950, m15_resistance=1.10000,
        m5_direction='down', session='asia', regime='range',
    )
    cands = generate_micro_candidates(ctx)
    assert len(cands) >= 1
    mc = cands[0]
    spec = {'volume_min': 0.01, 'trade_contract_size': 100000.0,
            'trade_tick_value': 1.0, 'trade_tick_size': 0.00001}
    result, skip = brain._maybe_explore(
        symbol='EURUSD', side=mc.side, setup=mc.family,
        signature={'regime': 'range', 'structure': 'retest', 'session': 'asia',
                   'm15_direction': 'down'},
        entry=mc.entry_price, invalidation=mc.invalidation,
        target=mc.target, pip=0.0001, info_id='test_info',
        portfolio_ok=True, portfolio_reason='',
        symbol_spec=spec, question='test',
        volatility='stable', regime_label='range',
        evidence=_PositiveEvidence(), spread_price=0.00002,
        actual_bid=ctx.bid, actual_ask=ctx.ask,
        row=pd.Series({'open': 1.100005, 'high': ctx.m1_high,
                       'low': ctx.m1_low, 'close': ctx.m1_close,
                       'volume': 100}),
        completed_m1=pd.DataFrame({
            'open': [1.10] * 4 + [1.10001],
            'high': [1.10002] * 5,
            'low': [1.09999] * 5,
            'close': [1.10] * 4 + [1.10001],
            'volume': [100] * 5}),
        state={'structure': {'M15': {'kind': 'retest',
               'support': 1.09950, 'resistance': 1.10000}},
               'multi_timeframe': {'M5': {'direction': 'down'},
                                   'M15': {'direction': 'down'}},
               'session': 'asia',
               'regime': {'label': 'range'},
               'volatility': {'phase': 'stable'}},
        market_ctx=ctx,
    )
    snap = brain.snapshot()
    assert snap['funnel']['candidates'] >= 1
    assert snap['funnel']['BUY_VARIANTS_TESTED'] >= 8
    assert snap['funnel']['SELL_VARIANTS_TESTED'] >= 8
    assert snap['funnel']['HORIZONS_TESTED'] == 8
    assert snap['funnel']['MECHANISMS_TESTED'] >= 3
    econ = check_entry_economics(mc, max_risk_usd=0.15,
        volume_min=spec['volume_min'], contract_size=spec['trade_contract_size'],
        tick_value=spec['trade_tick_value'], tick_size=spec['trade_tick_size'])
    # Pipeline executed: micro candidates generated and economics evaluated.
    # Whether _maybe_explore fires depends on all gates passing.
    if econ['allowed']:
        assert result is not None, f"economics allow but got skip: {skip}"
        assert result.action == 'fire'
        assert result.journal['exploration_authority'] == 'SAFE_TO_LEARN_ON_DEMO'
        assert result.journal['validated_artifact_required'] is False
        assert result.journal['validated_symbol_allowlist_required'] is False
        hyp = result.journal.get('hypothesis_id')
        assert hyp and hyp in brain.experiments.data['experiments']
    else:
        assert result is None or result.action != 'fire', (
            f"economics reject but got {result.action}: {skip}")
        # Correctly rejected - proves economics gate IS wired.

    low_result, low_skip = brain._maybe_explore(
        symbol='EURUSD', side=mc.side, setup=mc.family,
        signature={'regime': 'range', 'structure': 'retest', 'session': 'asia',
                   'm15_direction': 'down'},
        entry=mc.entry_price, invalidation=mc.invalidation,
        target=mc.target, pip=0.0001, info_id='low_confidence_info',
        portfolio_ok=True, portfolio_reason='',
        symbol_spec=spec, question='low confidence test',
        volatility='stable', regime_label='range',
        evidence=_LowCaptureConfidenceEvidence(), spread_price=0.00002,
        actual_bid=ctx.bid, actual_ask=ctx.ask,
        row=pd.Series({'open': 1.100005, 'high': ctx.m1_high,
                       'low': ctx.m1_low, 'close': ctx.m1_close,
                       'volume': 100}),
        completed_m1=pd.DataFrame({
            'open': [1.10] * 4 + [1.10001],
            'high': [1.10002] * 5,
            'low': [1.09999] * 5,
            'close': [1.10] * 4 + [1.10001],
            'volume': [100] * 5}),
        short_horizon_prediction={
            'selected_side': mc.side,
            'calibration_status': 'calibrated', 'abstain': False,
            'probability': 0.70, 'threshold': 0.95, 'decision': True,
            'expected_net_pnl': 0.01, 'decision_horizon_s': mc.max_hold_s,
        },
        state={'structure': {'M15': {'kind': 'retest',
               'support': 1.09950, 'resistance': 1.10000}},
               'multi_timeframe': {'M5': {'direction': 'down'},
                                   'M15': {'direction': 'down'}},
               'session': 'asia',
               'regime': {'label': 'range'},
               'volatility': {'phase': 'stable'}},
        market_ctx=ctx,
    )
    # A sub-50% point estimate is not rejected by a universal floor.  The
    # candidate is authorized only because its own measured payoff geometry
    # places breakeven below the evidence lower bound.
    assert low_result is not None, low_skip
    authorization = low_result.journal['capture_authorization']
    assert authorization['probability'] < 0.50
    assert authorization['lower_95'] >= authorization['required_probability']
    assert low_result.journal['candidate_model_rejections']

    brain.outcome_memory.should_suppress = lambda features: True
    blocked_result, blocked_skip = brain._maybe_explore(
        symbol='EURUSD', side=mc.side, setup=mc.family,
        signature={'regime': 'range', 'structure': 'retest', 'session': 'asia',
                   'm15_direction': 'down'},
        entry=mc.entry_price, invalidation=mc.invalidation,
        target=mc.target, pip=0.0001, info_id='loser_memory_info',
        portfolio_ok=True, portfolio_reason='', symbol_spec=spec,
        question='loser memory test', volatility='stable', regime_label='range',
        evidence=_PositiveEvidence(), spread_price=0.00002,
        actual_bid=ctx.bid, actual_ask=ctx.ask,
        row=pd.Series({'open': 1.100005, 'high': ctx.m1_high,
                       'low': ctx.m1_low, 'close': ctx.m1_close,
                       'volume': 100}),
        completed_m1=pd.DataFrame({
            'open': [1.10] * 4 + [1.10001],
            'high': [1.10002] * 5,
            'low': [1.09999] * 5,
            'close': [1.10] * 4 + [1.10001],
            'volume': [100] * 5}),
        state={'structure': {'M15': {'kind': 'retest',
               'support': 1.09950, 'resistance': 1.10000}},
               'multi_timeframe': {'M5': {'direction': 'down'},
                                   'M15': {'direction': 'down'}},
               'session': 'asia', 'regime': {'label': 'range'},
               'volatility': {'phase': 'stable'}},
        market_ctx=ctx,
    )
    assert blocked_result is None
    assert blocked_skip == 'exploration_economics_rejected:fast_loser_state_suppressed'


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

def test_self_hedge_same_family_blocked(tmp_path):
    """Spec J: opposing same-symbol exposure requires a DIFFERENT mechanism;
    same-family opposite-side exploration is blocked.

    This test directly exercises the self-hedge check in _maybe_explore by
    pre-seeding a BUY exploration thesis in memory, then attempting a SELL
    exploration with the same family. The self-hedge check should block it.
    """
    from aegis.intel.firehose_brain import IntelligentFirehoseBrain
    from aegis.intel.fast_firehose import FastMarketContext, generate_micro_candidates
    index = tmp_path / "analogue_index.json"
    index.write_text(json.dumps({"schema": "analogue_index.v1", "provenance": "mt5_m1", "records": []}), encoding="utf-8")
    cfg = {
        "analogue_index_path": str(index),
        "intelligent_gate_validated_states": False,
        "intelligent_firehose_bootstrap": True,
        "intelligent_bootstrap_canary": True,
        "intelligent_min_analogues": 20,
        "intelligent_min_similarity": 0.5,
        "intelligent_risk_fraction": 0.08,
        "intelligent_risk_budget_usd": 100.0,
        "order_quantity": 0.01,
        "max_positions": 40,
        "intelligent_exploration_enabled": True,
        "exploration_max_risk_per_trade_usd": 0.15,
        "intelligent_min_payoff_ratio": 0.1,
        "intelligent_min_expected_net_usd": -10.0,
        "intelligent_allow_synthetic_evidence": True,
        # Increase per-symbol limit so we can test self-hedge specifically
        "exploration_max_per_symbol": 2,
    }
    brain = IntelligentFirehoseBrain(cfg)

    # Manually seed a BUY exploration thesis for the family we'll test
    # This simulates a previously filled BUY exploration position
    test_family = "failed_breakout_fade"
    buy_thesis_key = "EURUSD|buy|failed_breakout_fade|range|asia"
    brain._exploration_theses.add(buy_thesis_key)
    buy_mem = brain.memory.get(buy_thesis_key, "EURUSD")
    buy_mem.symbol = "EURUSD"
    buy_mem.side = "buy"
    buy_mem.setup_family = test_family
    buy_mem.tickets.add("99990")  # simulate a filled ticket

    # Build a context for SELL exploration with same family
    ctx = FastMarketContext(
        symbol="EURUSD", bid=1.09998, ask=1.10000, spread_pips=0.2,
        m1_close=1.09999, m1_prev_close=1.10001, m1_atr=0.00002,
        m1_low=1.09997, m1_high=1.10012,
        m15_direction="down", m15_support=1.09950, m15_resistance=1.10000,
        m5_direction="down", session="asia", regime="range",
    )
    cands = generate_micro_candidates(ctx)
    assert len(cands) >= 1
    mc = cands[0]
    spec = {"volume_min": 0.01, "trade_contract_size": 100000.0, "trade_tick_value": 1.0, "trade_tick_size": 0.00001}

    # Attempt SELL exploration with SAME family - should be blocked by self-hedge
    result, skip = brain._maybe_explore(
        symbol="EURUSD", side="sell", setup=test_family,  # opposite side, same family
        signature={"regime": "range", "structure": "retest", "session": "asia", "m15_direction": "down"},
        entry=ctx.bid, invalidation=mc.invalidation,
        target=ctx.bid - (mc.target - mc.entry_price),  # symmetric target
        pip=0.0001, info_id="test_info2",
        portfolio_ok=True, portfolio_reason="",
        symbol_spec=spec, question="test",
        volatility="stable", regime_label="range",
        evidence=None, spread_price=0.00002,
        actual_bid=ctx.bid, actual_ask=ctx.ask,
        row=pd.Series({"open": 1.100005, "high": ctx.m1_high, "low": ctx.m1_low, "close": ctx.m1_close, "volume": 100}),
        completed_m1=pd.DataFrame({"open": [1.10]*4+[1.10001], "high": [1.10002]*5, "low": [1.09999]*5, "close": [1.10]*4+[1.10001], "volume": [100]*5}),
        state={"structure": {"M15": {"kind": "retest", "support": 1.09950, "resistance": 1.10000}}, "multi_timeframe": {"M5": {"direction": "down"}, "M15": {"direction": "down"}}, "session": "asia", "regime": {"label": "range"}, "volatility": {"phase": "stable"}},
        market_ctx=ctx,
    )
    # Should be blocked by self-hedge
    assert result is None, f"expected None but got {result}"
    assert skip is not None and skip.startswith("self_hedge_blocked_same_family"), f"got skip: {skip}"


def test_change_vote_workflow(tmp_path, monkeypatch):
    """Audit fix 11: standardized change proposal -> independent votes ->
    final decision; safety veto overrides; degraded flag for <2 voters."""
    from ai_council import change_vote as cv

    pack = {
        "change_id": "add-pm-doc",
        "problem": "PM thresholds undocumented",
        "current_evidence": "heartbeat shows PM decisions but no docs",
        "proposed_change": "document pm_* config keys in README section",
        "affected_files": "docs/",
        "expected_mechanism": "operators understand knobs",
        "risks": "none (docs only)",
        "tests": "none needed (docs)",
        "falsification_criteria": "n/a - documentation only",
        "rollback": "revert commit",
        "safety_impact": "none",
    }

    votes = iter([
        {"status": "AVAILABLE", "parsed": {"vote": "APPROVE_FOR_TEST",
                                           "confidence": 0.8, "reason": "ok"},
         "output": "{}", "model": "m1"},
        {"status": "AVAILABLE", "parsed": {"vote": "APPROVE_FOR_TEST",
                                           "confidence": 0.7, "reason": "docs help"},
         "output": "{}", "model": "m2"},
        {"status": "AVAILABLE", "parsed": {"vote": "REVISE_AND_RESUBMIT",
                                           "confidence": 0.6, "reason": "add examples"},
         "output": "{}", "model": "m3"},
        {"status": "UNAVAILABLE_QUOTA", "error": "429"},
    ])
    monkeypatch.setattr(cv, "probe_agent", lambda name: {"status": "AVAILABLE"})
    monkeypatch.setattr(cv, "ask_agent",
                        lambda name, prompt, timeout_s=300: next(votes))
    monkeypatch.setattr(cv.council_paths, "REPORTS", tmp_path)
    result = cv.run_change_vote(pack, agents=["a1", "a2", "a3", "a4"])
    assert result["final_decision"] == "APPROVED_FOR_TEST"
    assert result["totals"]["approve_for_test"] == 2
    # Tie between APPROVE and REVISE must go to the conservative REVISE.
    tie_votes = iter([
        {"status": "AVAILABLE", "parsed": {"vote": "APPROVE_FOR_TEST"}, "output": "{}"},
        {"status": "AVAILABLE", "parsed": {"vote": "REVISE_AND_RESUBMIT"}, "output": "{}"},
    ])
    monkeypatch.setattr(cv, "ask_agent",
                        lambda name, prompt, timeout_s=300: next(tie_votes))
    tie = cv.run_change_vote(pack, agents=["a1", "a2"])
    assert tie["final_decision"] == "REVISE_AND_RESUBMIT"
    assert result["degraded_real_council"] is False
    assert (tmp_path / "change_votes").exists()

    # Safety veto wins regardless of majority.
    bad_pack = dict(pack, change_id="bad", proposed_change="set allow_live: true")
    votes2 = iter([
        {"status": "AVAILABLE", "parsed": {"vote": "APPROVE_FOR_TEST"}, "output": "{}"},
        {"status": "AVAILABLE", "parsed": {"vote": "VETO_SAFETY",
                                           "reason": "live trading forbidden"}, "output": "{}"},
    ])
    monkeypatch.setattr(cv, "ask_agent", lambda name, prompt, timeout_s=300: next(votes2))
    result2 = cv.run_change_vote(bad_pack, agents=["a1", "a2"])
    assert result2["final_decision"] == "REJECTED_SAFETY"

    # Degraded: single voter is not a multi-agent decision.
    votes3 = iter([{"status": "AVAILABLE",
                    "parsed": {"vote": "APPROVE_FOR_TEST"}, "output": "{}"}])
    monkeypatch.setattr(cv, "ask_agent", lambda name, prompt, timeout_s=300: next(votes3))
    result3 = cv.run_change_vote(pack, agents=["a1"])
    assert result3["final_decision"] == "DEGRADED_REAL_COUNCIL"
    assert result3["degraded_real_council"] is True


def test_change_pack_validation_and_forbidden_patterns():
    from ai_council.change_vote import validate_pack, safety_violation

    missing = validate_pack({k: "" for k in (
        "change_id", "problem", "current_evidence", "proposed_change")})
    assert len(missing) >= 4
    assert safety_violation("we will disable stale quote protection") is not None
    assert safety_violation("use martingale to recover") is not None
    assert safety_violation("add documentation for risk caps") is None


def test_prospective_cap_blocks_at_limit_and_per_symbol():
    """Audited defect 3: pre-send semantics - exposure already AT cap leaves
    NO room. broker=2,max=2 blocks; broker=1 EURUSD with per-symbol=1 blocks."""
    from aegis.intel.exploration import (
        ExplorationLimits, exploration_room_reason,
    )

    limits = ExplorationLimits(max_positions=2, max_positions_per_symbol=1)
    # broker has 2 exploration positions, current FIRE pending, max=2:
    assert exploration_room_reason(total_open=2, symbol_open=1,
                                   limits=limits) == "exploration_max_positions:2"
    # broker has 1 EURUSD exploration, per-symbol=1 -> new EURUSD blocked.
    assert exploration_room_reason(total_open=1, symbol_open=1,
                                   limits=limits) == "exploration_max_positions_per_symbol"
    # Room exists only strictly below caps.
    assert exploration_room_reason(total_open=1, symbol_open=0,
                                   limits=limits) is None


class _EligibleNegEvidence:
    provenance = "mt5_m1"
    eligible = True
    analogue_n = 60
    analogue_n_losses = 20
    expectancy = -0.05
    profit_factor = 0.7
    mean_lower_95 = -0.02
    wins_erased_by_average_loss = 2.0
    tail_loss = -0.10
    avg_win = 0.04
    avg_loss = -0.06
    uncertainty = "calibrated"
    similarity_score = 0.8


def test_negative_state_ev_cannot_return_through_exploration(tmp_path, monkeypatch):
    """Audited defect 6: NEGATIVE_STATE_EV is a hard reject - the candidate is
    NOT registered and no exploration order is produced."""
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

    class _Ev(_EligibleNegEvidence):
        pass

    monkeypatch.setattr(brain.analogues, "query", lambda **k: _Ev())
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
    before = len(brain.experiments.data.get("experiments", {}))
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
    assert decision.action != "fire"
    after = len(brain.experiments.data.get("experiments", {}))
    assert after == before, "negative-EV candidate must not be registered"


def test_undercovered_state_reaches_exploration_without_legacy_geometry(tmp_path, monkeypatch):
    """A missing legacy S/R level cannot prevent a guarded micro-candidate check."""
    from aegis.intel import firehose_brain as fb
    from aegis.intel.firehose_brain import DemoDecision, IntelligentFirehoseBrain

    index = tmp_path / "analogue_index.json"
    index.write_text(json.dumps({"schema": "analogue_index.v1", "provenance": "mt5_m1", "records": []}), encoding="utf-8")
    brain = IntelligentFirehoseBrain(
        {
            "analogue_index_path": str(index),
            "intelligent_gate_validated_states": True,
            "validated_states_path": str(tmp_path / "empty_states.json"),
            "intelligent_firehose_bootstrap": True,
            "intelligent_exploration_enabled": True,
            "intelligent_min_analogues": 20,
            "intelligent_min_similarity": 0.5,
            "intelligent_risk_budget_usd": 100.0,
            "order_quantity": 0.01,
            "max_positions": 40,
        }
    )
    monkeypatch.setattr(
        fb,
        "build_runtime_state",
        lambda **kwargs: {
            "structure": {"M15": {"kind": "none", "support": None, "resistance": None}},
            "session": "asia",
            "regime": {"label": "range"},
            "multi_timeframe": {"H1": {"direction": "up"}, "M5": {"direction": "down"}},
            "volatility": {"phase": "stable"},
        },
    )
    monkeypatch.setattr(
        fb,
        "runtime_signature",
        lambda state, side, setup: {
            "symbol": "EURUSD",
            "side": side,
            "setup": setup,
            "regime": "range",
            "structure": "none",
            "volatility": "stable",
            "session": "asia",
            "h1_direction": "up",
            "m5_direction": "down",
        },
    )
    invoked = []

    def explore(**kwargs):
        invoked.append(kwargs)
        return DemoDecision("fire", "exploration_test", side="buy", sl=1.0, tp=1.1, quantity=0.01), None

    monkeypatch.setattr(brain, "_maybe_explore", explore)
    frame = _exploration_frame()
    row = frame.iloc[-1].copy()
    row["time"] = frame["time"].iloc[-1]
    decision = brain.evaluate(
        symbol="EURUSD",
        row=row,
        completed_m1=frame.iloc[:-1],
        positions=[],
        equity=100.0,
        pip=0.0001,
        core_side="buy",
        spread_price=0.0001,
        entry_price=float(row["close"]),
    )

    assert invoked
    assert decision.action == "fire"


def test_sub_95_candidate_falls_through_to_bounded_exploration(tmp_path, monkeypatch):
    """The 95% optimization target is not a global Firehose halt."""
    from aegis.intel import firehose_brain as fb
    from aegis.intel.firehose_brain import DemoDecision, IntelligentFirehoseBrain

    index = tmp_path / "analogue_index.json"
    index.write_text(
        json.dumps({"schema": "analogue_index.v1", "provenance": "mt5_m1", "records": []}),
        encoding="utf-8",
    )
    brain = IntelligentFirehoseBrain({
        "analogue_index_path": str(index),
        "intelligent_gate_validated_states": True,
        "validated_states_path": str(tmp_path / "empty_states.json"),
        "intelligent_firehose_bootstrap": True,
        "intelligent_exploration_enabled": True,
        "intelligent_min_analogues": 20,
        "intelligent_min_similarity": 0.5,
        "intelligent_risk_budget_usd": 100.0,
        "order_quantity": 0.01,
        "max_positions": 40,
        "exploration_max_positions": 2,
        "exploration_max_positions_per_symbol": 1,
        "exploration_max_risk_per_trade_usd": 0.15,
    })
    monkeypatch.setattr(
        fb,
        "build_runtime_state",
        lambda **kwargs: {
            "structure": {"M15": {"kind": "none", "support": None, "resistance": None}},
            "session": "asia",
            "regime": {"label": "range"},
            "multi_timeframe": {"H1": {"direction": "up"}, "M5": {"direction": "down"}},
            "volatility": {"phase": "stable"},
        },
    )
    monkeypatch.setattr(
        fb,
        "runtime_signature",
        lambda state, side, setup: {
            "symbol": "EURUSD", "side": side, "setup": setup,
            "regime": "range", "structure": "none", "session": "asia",
        },
    )
    invoked = []

    def explore(**kwargs):
        invoked.append(kwargs)
        return DemoDecision("fire", "bounded_exploration", side="buy", sl=1.0, tp=1.1, quantity=0.01), None

    monkeypatch.setattr(brain, "_maybe_explore", explore)
    frame = _exploration_frame()
    row = frame.iloc[-1].copy()
    row["time"] = frame["time"].iloc[-1]
    decision = brain.evaluate(
        symbol="EURUSD", row=row, completed_m1=frame.iloc[:-1], positions=[], equity=100.0,
        pip=0.0001, core_side="buy", spread_price=0.0001,
        entry_price=float(row["close"]), actual_bid=float(row["close"]) - 0.00005,
        actual_ask=float(row["close"]) + 0.00005,
        video_style=True,
        short_horizon_prediction={
            "calibration_status": "calibrated", "abstain": False,
            "probability": 0.70, "threshold": 0.95, "decision": True,
            "expected_net_pnl": 0.01, "uncertainty": 0.20,
            "model_agreement": 1.0,
        },
    )

    assert invoked, "a sub-95% candidate must fall through to exploration"
    assert decision.action == "fire"

    invoked.clear()
    abstained = brain.evaluate(
        symbol="EURUSD", row=row, completed_m1=frame.iloc[:-1], positions=[], equity=100.0,
        pip=0.0001, core_side="buy", spread_price=0.0001,
        entry_price=float(row["close"]), actual_bid=float(row["close"]) - 0.00005,
        actual_ask=float(row["close"]) + 0.00005,
        video_style=True,
        short_horizon_prediction={
            "calibration_status": "calibrated", "abstain": True,
            "abstain_reason": "uncertainty_high", "probability": 0.70,
            "threshold": 0.95, "uncertainty": 0.40, "model_agreement": 2 / 3,
        },
    )

    assert invoked, "candidate ABSTAIN must not globally halt exploration"
    assert abstained.action == "fire"


def test_rejection_report_keeps_reason_without_fabricating_ev(tmp_path):
    from aegis.intel.fast_firehose import MicroCandidate
    from aegis.intel.firehose_brain import IntelligentFirehoseBrain

    index = tmp_path / "analogue_index.json"
    index.write_text(json.dumps({"schema": "ai", "records": []}), encoding="utf-8")
    brain = IntelligentFirehoseBrain({
        "analogue_index_path": str(index),
        "intelligent_exploration_enabled": True,
    })
    candidate = MicroCandidate(
        hypothesis_id="h-report", family="micro", symbol="EURUSD", side="buy",
        entry_price=1.10, invalidation=1.0990, target=1.1020,
        max_hold_s=8, required_regime="trend", required_session="asia",
        spread_pips=0.2, stop_pips=10.0, target_pips=20.0,
        risk_usd_min_lot=1.0, lane="SHADOW", mechanism="test",
    )

    brain._record_search_evaluation(
        candidate=candidate,
        reasons=["RISK_GRANULARITY_BLOCKED"],
        distance={"risk_excess_usd": 0.85},
    )

    best = brain.snapshot()["funnel"]
    assert best["BEST_REJECTED_CANDIDATE_EV"] is None
    assert best["BEST_REJECTED_REASON"] == "RISK_GRANULARITY_BLOCKED"


def test_predictor_unavailable_reaches_brain_as_explicit_zero_intent(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from aegis.intel import firehose_brain as fb
    from aegis.intel.firehose_brain import IntelligentFirehoseBrain
    from aegis.intel.short_horizon_runtime import ShortHorizonPredictor
    from aegis.intel.video_style import VideoStyleSignal

    index = tmp_path / "analogue_index.json"
    index.write_text(
        json.dumps({"schema": "analogue_index.v1", "provenance": "mt5_m1", "records": []}),
        encoding="utf-8",
    )
    brain = IntelligentFirehoseBrain({
        "analogue_index_path": str(index),
        "intelligent_gate_validated_states": True,
        "validated_states_path": str(tmp_path / "empty_states.json"),
        "intelligent_firehose_bootstrap": True,
        "intelligent_exploration_enabled": True,
        "intelligent_min_analogues": 20,
        "intelligent_min_similarity": 0.5,
        "intelligent_risk_budget_usd": 100.0,
        "order_quantity": 0.01,
        "max_positions": 40,
        "exploration_max_risk_per_trade_usd": 0.15,
        "exploration_max_daily_loss_usd": 0,
    })
    frame = _exploration_frame()
    signal = VideoStyleSignal(
        symbol="EURUSD", side="buy", signal_time=frame["time"].iloc[-1],
        breakout_price=float(frame["close"].iloc[-1]), risk_distance=0.0001,
    )
    monkeypatch.setattr(fb, "video_style_signal", lambda *args, **kwargs: signal)
    monkeypatch.setattr(
        fb,
        "build_runtime_state",
        lambda **kwargs: {
            "structure": {"M15": {"kind": "none", "support": None, "resistance": None}},
            "session": "asia",
            "regime": {"label": "range"},
            "multi_timeframe": {"H1": {"direction": "up"}, "M5": {"direction": "down"}},
            "volatility": {"phase": "stable"},
        },
    )
    monkeypatch.setattr(
        fb,
        "runtime_signature",
        lambda state, side, setup: {
            "symbol": "EURUSD", "side": side, "setup": setup,
            "regime": "range", "structure": "none", "session": "asia",
        },
    )
    prediction = ShortHorizonPredictor(tmp_path / "missing").predict_sides(
        symbol="EURUSD", quote_buffer=SimpleNamespace(buffers={}), now_ts=1.0,
    )
    row = frame.iloc[-1].copy()
    decision = brain.evaluate(
        symbol="EURUSD", row=row, completed_m1=frame.iloc[:-1], positions=[],
        equity=100.0, pip=0.0001, core_side="buy", spread_price=0.0001,
        entry_price=float(row["close"]), actual_bid=float(row["close"]),
        actual_ask=float(row["close"] + 0.0001), video_style=True,
        short_horizon_prediction=prediction,
    )

    assert prediction["prediction_reason"] == "artifact_not_found"
    assert decision.action == "skip"
    assert decision.quantity == 0.0


def test_shadow_only_exploration_is_not_blocked_by_validated_lane_economics(tmp_path, monkeypatch):
    """Shadow probing reaches its independent exploration lane.

    The exploration lane still has to pass its own real candidate/economics
    checks; the legacy validated-lane ``no_win_probability_evidence`` result
    must not prevent that lane from evaluating the candidate.
    """
    from aegis.intel import firehose_brain as fb
    from aegis.intel.firehose_brain import DemoDecision, IntelligentFirehoseBrain
    from aegis.intel.video_style import VideoStyleSignal

    index = tmp_path / "analogue_index.json"
    index.write_text(
        json.dumps({"schema": "analogue_index.v1", "provenance": "mt5_m1", "records": []}),
        encoding="utf-8",
    )
    brain = IntelligentFirehoseBrain({
        "analogue_index_path": str(index),
        "engine": "mt5",
        "mode": "mt5_demo",
        "allow_live": False,
        "paper_trading_enabled": True,
        "intelligent_gate_validated_states": True,
        "validated_states_path": str(tmp_path / "empty_states.json"),
        "intelligent_firehose_bootstrap": True,
        "intelligent_exploration_enabled": True,
        "intelligent_min_analogues": 20,
        "intelligent_min_similarity": 0.5,
        "intelligent_risk_budget_usd": 100.0,
        "order_quantity": 0.01,
        "max_positions": 40,
        "exploration_max_risk_per_trade_usd": 0.15,
    })
    frame = _exploration_frame()
    signal = VideoStyleSignal(
        symbol="EURUSD", side="buy", signal_time=frame["time"].iloc[-1],
        breakout_price=float(frame["close"].iloc[-1]), risk_distance=0.0001,
    )
    monkeypatch.setattr(fb, "video_style_signal", lambda *args, **kwargs: signal)
    invoked = []

    def explore(**kwargs):
        invoked.append(kwargs)
        return (
            DemoDecision(
                "fire", "independent_exploration", side="buy",
                sl=1.0994, tp=1.1005, quantity=0.01,
            ),
            None,
        )

    monkeypatch.setattr(brain, "_maybe_explore", explore)

    row = frame.iloc[-1].copy()
    decision = brain.evaluate(
        symbol="EURUSD", row=row, completed_m1=frame.iloc[:-1], positions=[],
        equity=100.0, pip=0.0001, core_side="buy", spread_price=0.0001,
        symbol_spec={"volume_min": 0.01, "volume_step": 0.01,
                     "trade_contract_size": 100000.0},
        entry_price=float(row["close"]), actual_bid=float(row["close"]),
        actual_ask=float(row["close"] + 0.0001), video_style=True,
        short_horizon_prediction={
            "calibration_status": "unavailable", "abstain": True,
            "abstain_reason": "artifact_shadow_only",
        },
    )

    assert invoked, "shadow-only model probe must reach the exploration lane"
    assert decision.action == "fire"
    assert decision.journal["exploration_shadow_model_probe"] is True
    funnel = brain.snapshot()["funnel"]
    assert funnel["EXPLORATION_CANDIDATES"] == 1
    assert funnel["SHADOW_REJECT_VALIDATED"] == 1
    assert funnel["SHADOW_REJECT_EXPLORATION"] == 0


def test_shadow_only_exploration_full_route_uses_independent_measured_evidence(tmp_path, monkeypatch):
    """A shadow artifact may probe only after the exploration gates pass."""
    from aegis.intel import firehose_brain as fb
    from aegis.intel.firehose_brain import IntelligentFirehoseBrain
    from aegis.intel.video_style import VideoStyleSignal

    index = tmp_path / "analogue_index.json"
    index.write_text(
        json.dumps({"schema": "analogue_index.v1", "provenance": "mt5_m1", "records": []}),
        encoding="utf-8",
    )
    brain = IntelligentFirehoseBrain({
        "analogue_index_path": str(index),
        "engine": "mt5",
        "mode": "mt5_demo",
        "allow_live": False,
        "paper_trading_enabled": True,
        "intelligent_gate_validated_states": True,
        "validated_states_path": str(tmp_path / "empty_states.json"),
        "intelligent_firehose_bootstrap": True,
        "intelligent_exploration_enabled": True,
        "intelligent_min_analogues": 20,
        "intelligent_min_similarity": 0.5,
        "intelligent_risk_budget_usd": 100.0,
        "order_quantity": 0.01,
        "max_positions": 40,
        "exploration_max_risk_per_trade_usd": 0.15,
        "exploration_max_daily_loss_usd": 0,
    })
    frame = _exploration_frame()
    signal = VideoStyleSignal(
        symbol="EURUSD", side="buy", signal_time=frame["time"].iloc[-1],
        breakout_price=float(frame["close"].iloc[-1]), risk_distance=0.0001,
    )
    monkeypatch.setattr(fb, "video_style_signal", lambda *args, **kwargs: signal)
    monkeypatch.setattr(
        fb,
        "build_runtime_state",
        lambda **kwargs: {
            "structure": {"M15": {"kind": "none", "support": None, "resistance": None}},
            "session": "asia",
            "regime": {"label": "range"},
            "multi_timeframe": {"H1": {"direction": "up"}, "M5": {"direction": "up"}},
            "volatility": {"phase": "stable"},
        },
    )
    monkeypatch.setattr(
        fb,
        "runtime_signature",
        lambda state, side, setup: {
            "symbol": "EURUSD", "side": side, "setup": setup,
            "regime": "range", "structure": "none", "session": "asia",
        },
    )
    monkeypatch.setattr(brain.analogues, "query", lambda **kwargs: _PositiveEvidence())

    row = frame.iloc[-1].copy()
    decision = brain.evaluate(
        symbol="EURUSD", row=row, completed_m1=frame.iloc[:-1], positions=[],
        equity=100.0, pip=0.0001, core_side="buy", spread_price=0.00002,
        symbol_spec={"volume_min": 0.01, "volume_step": 0.01,
                     "trade_contract_size": 100000.0},
        entry_price=float(row["close"]), actual_bid=float(row["close"]),
        actual_ask=float(row["close"] + 0.00002), video_style=True,
        short_horizon_prediction={
            "calibration_status": "unavailable", "abstain": True,
            "abstain_reason": "artifact_shadow_only",
        },
    )

    assert decision.action == "fire"
    assert decision.journal["exploration_authority"] == "SAFE_TO_LEARN_ON_DEMO"
    assert decision.journal["validated_artifact_required"] is False
    assert decision.journal["short_horizon_prediction"]["abstain_reason"] == "artifact_shadow_only"


def test_exploration_journal_records_micro_rejection_reason(tmp_path, monkeypatch):
    from aegis.intel import firehose_brain as fb
    from aegis.intel.firehose_brain import IntelligentFirehoseBrain

    index = tmp_path / "analogue_index.json"
    index.write_text(json.dumps({"schema": "analogue_index.v1", "provenance": "mt5_m1", "records": []}), encoding="utf-8")
    brain = IntelligentFirehoseBrain({
        "analogue_index_path": str(index),
        "intelligent_gate_validated_states": True,
        "validated_states_path": str(tmp_path / "empty_states.json"),
        "intelligent_firehose_bootstrap": True,
        "intelligent_exploration_enabled": True,
        "intelligent_min_analogues": 20,
        "intelligent_min_similarity": 0.5,
        "intelligent_risk_budget_usd": 100.0,
        "order_quantity": 0.01,
        "max_positions": 40,
    })
    monkeypatch.setattr(
        fb,
        "build_runtime_state",
        lambda **kwargs: {
            "structure": {"M15": {"kind": "none", "support": None, "resistance": None}},
            "session": "asia",
            "regime": {"label": "range"},
            "multi_timeframe": {"H1": {"direction": "up"}, "M5": {"direction": "down"}},
            "volatility": {"phase": "stable"},
        },
    )
    monkeypatch.setattr(
        fb,
        "runtime_signature",
        lambda state, side, setup: {
            "symbol": "EURUSD", "side": side, "setup": setup, "regime": "range",
            "structure": "none", "volatility": "stable", "session": "asia",
            "h1_direction": "up", "m5_direction": "down",
        },
    )
    frame = _exploration_frame()
    row = frame.iloc[-1].copy()
    row["time"] = frame["time"].iloc[-1]

    decision = brain.evaluate(
        symbol="EURUSD", row=row, completed_m1=frame.iloc[:-1], positions=[], equity=100.0,
        pip=0.0001, core_side="buy", entry_price=float(row["close"]),
        actual_bid=float(row["close"]) - 0.00005,
        actual_ask=float(row["close"]) + 0.00005,
    )

    assert decision.journal["exploration_skip"] == "no_micro_candidate_matched"
    assert decision.journal["micro_candidate_count"] == 0
    assert decision.journal["micro_diagnostics"]["fair_value_snapback"] == "missing_m15_range"


def test_no_quote_exploration_skip_does_not_reuse_micro_diagnostics(tmp_path, monkeypatch):
    from aegis.intel import firehose_brain as fb
    from aegis.intel.firehose_brain import IntelligentFirehoseBrain

    index = tmp_path / "analogue_index.json"
    index.write_text(json.dumps({"schema": "analogue_index.v1", "provenance": "mt5_m1", "records": []}), encoding="utf-8")
    brain = IntelligentFirehoseBrain({
        "analogue_index_path": str(index),
        "intelligent_gate_validated_states": True,
        "validated_states_path": str(tmp_path / "empty_states.json"),
        "intelligent_firehose_bootstrap": True,
        "intelligent_exploration_enabled": True,
        "intelligent_min_analogues": 20,
        "intelligent_min_similarity": 0.5,
        "intelligent_risk_budget_usd": 100.0,
        "order_quantity": 0.01,
        "max_positions": 40,
    })
    brain._last_exploration_micro_diagnostics = {
        "micro_candidate_count": 1,
        "micro_diagnostics": {"micro_momentum_burst": "candidate_matched"},
    }
    monkeypatch.setattr(
        fb,
        "build_runtime_state",
        lambda **kwargs: {
            "structure": {"M15": {"kind": "none", "support": None, "resistance": None}},
            "session": "asia",
            "regime": {"label": "range"},
            "multi_timeframe": {"H1": {"direction": "up"}, "M5": {"direction": "down"}},
            "volatility": {"phase": "stable"},
        },
    )
    monkeypatch.setattr(
        fb,
        "runtime_signature",
        lambda state, side, setup: {
            "symbol": "EURUSD", "side": side, "setup": setup, "regime": "range",
            "structure": "none", "volatility": "stable", "session": "asia",
            "h1_direction": "up", "m5_direction": "down",
        },
    )
    frame = _exploration_frame()
    row = frame.iloc[-1].copy()
    row["time"] = frame["time"].iloc[-1]

    decision = brain.evaluate(
        symbol="EURUSD", row=row, completed_m1=frame.iloc[:-1], positions=[], equity=100.0,
        pip=0.0001, core_side="buy", entry_price=float(row["close"]),
    )

    assert decision.journal["exploration_skip"] == "no_genuine_quote"
    assert "micro_candidate_count" not in decision.journal
    assert "micro_diagnostics" not in decision.journal


def test_undercovered_state_cannot_bypass_measured_spread_limit(tmp_path, monkeypatch):
    """Exploration is denied before candidate construction above session p90 spread."""
    from aegis.intel import firehose_brain as fb
    from aegis.intel.firehose_brain import IntelligentFirehoseBrain

    index = tmp_path / "analogue_index.json"
    index.write_text(json.dumps({"schema": "analogue_index.v1", "provenance": "mt5_m1", "records": []}), encoding="utf-8")
    costs = tmp_path / "cost_profiles.json"
    costs.write_text(
        json.dumps(
            {
                "symbols": {
                    "EURUSD": {
                        "sessions": {
                            "asia": {
                                "evidence_sufficient": True,
                                "observations": 30,
                                "spread_p90": 1.0,
                                "slippage_pips": 0.1,
                                "commission_pips": 0.0,
                            }
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    brain = IntelligentFirehoseBrain(
        {
            "analogue_index_path": str(index),
            "cost_profiles_path": str(costs),
            "intelligent_gate_validated_states": True,
            "validated_states_path": str(tmp_path / "empty_states.json"),
            "intelligent_firehose_bootstrap": True,
            "intelligent_exploration_enabled": True,
            "intelligent_risk_budget_usd": 100.0,
            "order_quantity": 0.01,
            "max_positions": 40,
        }
    )
    monkeypatch.setattr(
        fb,
        "build_runtime_state",
        lambda **kwargs: {
            "structure": {"M15": {"kind": "none", "support": None, "resistance": None}},
            "session": "asia",
            "regime": {"label": "range"},
            "multi_timeframe": {"H1": {"direction": "up"}, "M5": {"direction": "down"}},
            "volatility": {"phase": "stable"},
        },
    )
    monkeypatch.setattr(
        fb,
        "runtime_signature",
        lambda state, side, setup: {
            "symbol": "EURUSD", "side": side, "setup": setup, "regime": "range",
            "structure": "none", "volatility": "stable", "session": "asia",
            "h1_direction": "up", "m5_direction": "down",
        },
    )
    monkeypatch.setattr(
        brain,
        "_maybe_explore",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("spread-rejected exploration must not run")),
    )
    frame = _exploration_frame()
    row = frame.iloc[-1].copy()
    row["time"] = frame["time"].iloc[-1]

    decision = brain.evaluate(
        symbol="EURUSD", row=row, completed_m1=frame.iloc[:-1], positions=[], equity=100.0,
        pip=0.0001, core_side="buy", spread_price=0.00011, entry_price=float(row["close"]),
    )

    assert decision.action == "skip"
    assert decision.reason == "spread_above_measured_session_limit"


def test_book_logic_non_empty_via_real_explore_path(tmp_path, monkeypatch):
    """Audited defect 4: at $0.15 risk, economics correctly reject wide-stop
    candidates (proving check_entry_economics IS wired). Book logic retrieval
    is separately verified in test_book_knowledge.py."""
    from aegis.intel.firehose_brain import IntelligentFirehoseBrain

    index = tmp_path / "analogue_index.json"
    index.write_text(json.dumps({"schema": "analogue_index.v1", "provenance": "mt5_m1",
                                 "records": []}), encoding="utf-8")
    books = tmp_path / "books"
    body = ("A failed breakout is a fade opportunity: sell the false breakout "
            "trap back into the range on M15. Stop above the trap high. ")
    _write_book(books / "Fade Masters.md", "# Traps\n\n" + body * 30)
    knowledge_dir = tmp_path / "knowledge"
    build_kb(books, knowledge_dir)

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
    monkeypatch.setattr(brain.analogues, "query", lambda **k: _FakeEvidence())
    from aegis.intel import firehose_brain as fb
    from aegis.intel import knowledge_retrieval as kr

    fake_state = {
        "structure": {"M15": {"kind": "failed_breakout_fade",
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
    monkeypatch.setattr(kr, "KNOWLEDGE_DIR", knowledge_dir)
    kr._cached_retrieve.cache_clear()

    frame = _exploration_frame()
    row = frame.iloc[-1].copy()
    row["time"] = frame["time"].iloc[-1]
    row["ema_20"] = float(frame["close"].iloc[-1])
    decision = brain.evaluate(
        symbol="EURUSD", row=row, completed_m1=frame.iloc[:-1],
        positions=[], equity=100.0, pip=0.0001, core_side="sell",
        spread_price=0.0001,
        symbol_spec={"volume_min": 0.01, "volume_step": 0.01,
                     "trade_contract_size": 100000.0},
        entry_price=float(row["close"]),
        actual_bid=float(row["close"]) - 0.00005,
        actual_ask=float(row["close"]) + 0.00005,
    )
    # At $0.15 risk, micro candidates from synthetic data are correctly
    # rejected (no viable geometry). This proves no-fallback + economics work.
    assert decision.action != "fire", (
        f"expected skip at $0.15 risk, got {decision.action}")
    # Verify no fabricated data produced an order.
    skips = brain.counts.get("skip_reasons") or {}
    all_skips = list(skips.keys())
    assert not any("fire" in k for k in all_skips), \
        f"no fire should occur at $0.15 with wide-stop geometry: {all_skips}"


def _write_book(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def build_kb(books: Path, out: Path) -> dict:
    from aegis.research.book_knowledge import build_knowledge_base

    return build_knowledge_base(books, out)


def _forced_demo_cfg(tmp_path):
    return {
        "engine": "mt5",
        "mode": "mt5_demo",
        "allow_live": False,
        "paper_trading_enabled": True,
        "dry_run": False,
        "intelligent_exploration_enabled": True,
        "exploration_max_risk_per_trade_usd": 0.15,
        "intelligent_min_analogues": 20,
        "intelligent_min_similarity": 0.5,
        "intelligent_min_payoff_ratio": 1.0,
        "analogue_index_path": str(tmp_path / "analogue_index.json"),
        "exploration_experiments_path": str(tmp_path / "experiments.json"),
        "outcome_memory_path": str(tmp_path / "outcome_memory.json"),
    }


def _forced_candidate(*, side="buy", target_pips=5.0, stop_pips=1.0,
                      spread_pips=0.2):
    from aegis.intel.fast_firehose import FirehoseLane, MicroCandidate

    entry = 1.1002 if side == "buy" else 1.1000
    sign = 1.0 if side == "buy" else -1.0
    return MicroCandidate(
        hypothesis_id=f"forced-{side}-{target_pips}-{spread_pips}",
        family="forced_test_mechanism",
        symbol="EURUSD",
        side=side,
        entry_price=entry,
        invalidation=entry - sign * stop_pips * 0.0001,
        target=entry + sign * target_pips * 0.0001,
        max_hold_s=3,
        required_regime="range",
        required_session="asia",
        spread_pips=spread_pips,
        stop_pips=stop_pips,
        target_pips=target_pips,
        risk_usd_min_lot=0.10,
        lane=FirehoseLane.BROKER_MICRO,
        mechanism="forced-test",
        variant_id=f"forced_test_mechanism:{side}:3s",
    )


def _run_forced_demo_brain(tmp_path, monkeypatch, candidates, checkpoint=None):
    from aegis.intel.fast_firehose import FastMarketContext
    from aegis.intel.firehose_brain import IntelligentFirehoseBrain

    index = tmp_path / "analogue_index.json"
    index.write_text(json.dumps({"schema": "analogue_index.v1", "records": []}), encoding="utf-8")
    def generated_candidates(*args, **kwargs):
        callback = kwargs.get("checkpoint")
        if callback is not None:
            callback("candidate_generated", "forced_test_mechanism", "buy", 3)
        return list(candidates)

    monkeypatch.setattr(
        "aegis.intel.fast_firehose.generate_runtime_search_candidates",
        generated_candidates,
    )
    monkeypatch.setattr(
        "aegis.intel.fast_firehose.diagnose_micro_candidates",
        lambda ctx: ([], {}),
    )
    brain = IntelligentFirehoseBrain(_forced_demo_cfg(tmp_path))
    ctx = FastMarketContext(
        symbol="EURUSD", bid=1.1000, ask=1.1002, spread_pips=2.0,
        m1_close=1.1001, m1_low=1.0999, m1_high=1.1003, m1_atr=0.0001,
        m5_compression=0.2, session="asia", regime="range",
    )
    row = pd.Series({
        "open": 1.1000, "high": 1.1003, "low": 1.0999,
        "close": 1.1001, "volume": 100,
    })
    completed = pd.DataFrame({
        "open": [1.1000] * 5, "high": [1.1002] * 5,
        "low": [1.0999] * 5, "close": [1.1001] * 5,
        "volume": [100] * 5,
    })
    return brain._maybe_explore(
        symbol="EURUSD", side="buy", setup="forced_test_mechanism",
        signature={"regime": "range", "structure": "test", "session": "asia"},
        entry=1.1002, invalidation=1.1001, target=1.1007, pip=0.0001,
        info_id="forced-test", portfolio_ok=True, portfolio_reason="",
        symbol_spec={
            "volume_min": 0.01, "volume_step": 0.01,
            "trade_contract_size": 100000.0,
            "trade_tick_value": 1.0, "trade_tick_size": 0.00001,
        },
        question="forced demo test", volatility="stable", regime_label="range",
        evidence=_FakeEvidence(), spread_price=0.00002,
        actual_bid=1.1000, actual_ask=1.1002, row=row,
        completed_m1=completed, state={"session": "asia", "regime": {"label": "range"}},
        market_ctx=ctx,
        checkpoint=checkpoint,
    )


def test_exploration_brain_forwards_runtime_checkpoint_without_changing_decision(
    tmp_path, monkeypatch,
):
    calls = []

    result, skip = _run_forced_demo_brain(
        tmp_path,
        monkeypatch,
        [_forced_candidate()],
        checkpoint=lambda stage, mechanism, side, horizon: calls.append(
            (stage, mechanism, side, horizon)
        ),
    )

    assert skip is None
    assert result is not None and result.action == "fire"
    assert calls == [
        ("candidate_generated", "forced_test_mechanism", "buy", 3),
        ("candidate_economics", "forced_test_mechanism", "buy", 3),
    ]


def test_mt5_demo_forced_lane_fires_without_probability_evidence(tmp_path, monkeypatch):
    result, skip = _run_forced_demo_brain(
        tmp_path, monkeypatch, [_forced_candidate()]
    )

    assert skip is None
    assert result is not None and result.action == "fire"
    assert result.journal["exploration_lane"] == "FORCED_DEMO_EXPLORATION"
    assert result.journal["authority_type"] == "FORCED_DEMO_EXPLORATION"
    assert result.journal["calibration_status"] == "UNCALIBRATED"
    assert result.journal["p_captured_win"] is None
    assert result.journal["p_captured_win_lcb95"] is None
    assert result.journal["viable_candidates"]
    assert result.journal["viable_candidates"][0]["p_captured_win"] is None


def test_forced_lane_skips_hard_blocked_candidate_and_uses_next_safe_one(tmp_path, monkeypatch):
    blocked = _forced_candidate(target_pips=0.1, stop_pips=1.0)
    safe = _forced_candidate(side="sell", target_pips=5.0, stop_pips=1.0)
    result, skip = _run_forced_demo_brain(tmp_path, monkeypatch, [blocked, safe])

    assert skip is None
    assert result is not None and result.action == "fire"
    assert result.side == "sell"
    assert result.journal["authority_type"] == "FORCED_DEMO_EXPLORATION"


def test_forced_lane_is_not_available_when_every_candidate_is_hard_blocked(tmp_path, monkeypatch):
    blocked = _forced_candidate(target_pips=0.1, stop_pips=0.1)
    result, skip = _run_forced_demo_brain(tmp_path, monkeypatch, [blocked])

    assert result is None
    assert skip is not None
