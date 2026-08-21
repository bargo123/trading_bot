#!/usr/bin/env python3
"""The per-trade economics gate, exercised through the real brain.

Two properties matter and they pull in opposite directions:

1. The 1-pip-target / 30-pip-stop shape must never reach FIRE, no matter how good
   the historical win rate looks. That is the reported 91.91% WR / 0.71 PF failure.
2. The firehose must still FIRE when the geometry and the evidence are genuinely
   good. Fixing (1) by making the bot afraid to trade is not a fix.

Both are asserted here, so a future change cannot satisfy one by breaking the other.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from aegis.intel.analogue_store import AnalogueStore, is_measured_provenance
from aegis.intel.firehose_brain import IntelligentFirehoseBrain
from aegis.intel.state_runtime import build_runtime_state, runtime_signature

# Real MetaQuotes-Demo EURUSD spec.
EURUSD_SPEC = {
    "trade_tick_size": 0.00001,
    "trade_tick_value": 1.0,
    "trade_tick_value_loss": 1.0,
    "trade_contract_size": 100000.0,
    "point": 0.00001,
}
PIP = 0.0001
HALF_PIP_SPREAD = 0.00005


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


def _ramp_into_resistance(n: int = 400) -> pd.DataFrame:
    """Steady climb: the last bar sits just under M15 resistance.

    This is the geometry that produces the pathological payoff - a target a pip
    away above a stop tens of pips away.
    """
    return _frame([1.10 + index * 0.00001 for index in range(n)])


def _basing_above_support(n: int = 400) -> pd.DataFrame:
    """Long decline that flattens out just above its low.

    M15 support then sits a few pips under the entry while M15 resistance is the
    far-away start of the decline - a small invalidation against a large target,
    which is the payoff shape the firehose is supposed to want.
    """
    decline_bars = n - 60
    top = 1.1340
    decline = [top - index * (0.0340 / decline_bars) for index in range(decline_bars)]
    low = decline[-1]
    base = [low + 0.00003 * (index % 3) for index in range(60)]
    return _frame(decline + base)


def _signature_for(frame: pd.DataFrame, side: str) -> dict:
    state = build_runtime_state(symbol="EURUSD", m1=frame)
    m15 = (state.get("structure") or {}).get("M15") or {}
    setup = str(m15.get("kind") or "scan")
    return runtime_signature(state, side=side, setup=setup)


def _measured_records(signature: dict, *, n: int, wins_per_loss: int = 3) -> list[dict]:
    """Records that match ``signature`` exactly, with a real positive payoff shape.

    Outcomes are +0.04 / -0.02, i.e. a payoff ratio of 2 and a 75% win rate - a
    genuinely positive, non-cosmetic distribution.
    """
    rows = []
    for index in range(n):
        hour = index % 24
        day = (index // 24) % 27 + 1
        rows.append(
            {
                "bar_time": f"2025-12-{day:02d}T{hour:02d}:00:00+00:00",
                "symbol": "EURUSD",
                "side": signature["side"],
                "setup": signature["setup"],
                "regime": signature["regime"],
                "structure": signature["structure"],
                "volatility": signature["volatility"],
                "session": signature["session"],
                "h1_direction": signature["h1_direction"],
                "m5_direction": signature["m5_direction"],
                "outcome": -0.02 if index % (wins_per_loss + 1) == 0 else 0.04,
            }
        )
    return rows


def _index(tmp_path: Path, records: list[dict], *, provenance: str) -> Path:
    path = tmp_path / f"analogue_{provenance}.json"
    path.write_text(
        json.dumps(
            {
                "schema": "analogue_index.v1",
                "provenance": provenance,
                "outcome_unit": "usd",
                "n": len(records),
                "records": records,
            }
        ),
        encoding="utf-8",
    )
    return path


def _brain(index_path: Path, **overrides) -> IntelligentFirehoseBrain:
    import hashlib as _hashlib
    from datetime import datetime as _dt, timedelta as _td, timezone as _tz

    canary = {
        "schema": "demo_canary.v1",
        "created_utc": _dt.now(_tz.utc).isoformat(),
        "expires_utc": (_dt.now(_tz.utc) + _td(days=1)).isoformat(),
        "strategy_id": "canary_test",
        "opportunity": {"symbol": "EURUSD"},
        "metrics": {},
        "dataset_hash": "test",
        "validation_hash": "test",
        "index_file_sha256": _hashlib.sha256(index_path.read_bytes()).hexdigest(),
        "risk_fraction": 0.08,
    }
    canary_path = index_path.parent / "demo_canary.json"
    canary_path.write_text(json.dumps(canary), encoding="utf-8")
    cfg = {
        "analogue_index_path": str(index_path),
        "intelligent_champion_path": str(index_path.parent / "no_such_champion.json"),
        "intelligent_firehose_bootstrap": True,
        # These tests target the economics gates, not governance: a valid
        # DEMO_CANARY artifact lets the bootstrap reach the trading stage.
        "intelligent_bootstrap_canary": True,
        "demo_canary_path": str(canary_path),
        "intelligent_min_analogues": 20,
        "intelligent_min_similarity": 0.5,
        "intelligent_risk_fraction": 0.08,
        "intelligent_risk_budget_usd": 100.0,
        "order_quantity": 0.01,
        "max_positions": 40,
    }
    cfg.update(overrides)
    return IntelligentFirehoseBrain(cfg)


def _decide(brain: IntelligentFirehoseBrain, frame: pd.DataFrame, side: str = "buy"):
    row = frame.iloc[-1].copy()
    row["time"] = frame["time"].iloc[-1]
    row["ema_20"] = float(frame["close"].iloc[-1])
    return brain.evaluate(
        symbol="EURUSD",
        row=row,
        completed_m1=frame.iloc[:-1],
        positions=[],
        equity=100.0,
        pip=PIP,
        core_side=side,
        spread_price=HALF_PIP_SPREAD,
        symbol_spec=EURUSD_SPEC,
        entry_price=float(row["close"]),
    )


# --------------------------------------------------------------------------
# Property 1: destructive payoff cannot fire
# --------------------------------------------------------------------------


def test_structural_one_pip_target_over_thirty_pip_stop_is_priced_and_refused(tmp_path):
    """Real M15 structure produces the 1:30 shape; the gate must price and reject it."""
    frame = _ramp_into_resistance()
    signature = _signature_for(frame, "buy")
    records = _measured_records(signature, n=60)
    brain = _brain(_index(tmp_path, records, provenance="mt5_m1"))
    decision = _decide(brain, frame)

    econ = decision.journal
    assert econ["econ_ok"] is False
    # Reward is a fraction of risk: this is the reported failure's shape.
    assert econ["econ_payoff_ratio"] < 0.1
    assert econ["econ_expected_loss_usd"] > 10 * econ["econ_expected_win_usd"]
    # It would need a ~98% win rate merely to break even.
    assert econ["econ_breakeven_wr"] > 0.9
    assert econ["econ_expected_net_usd"] < 0
    assert decision.action != "fire"


def test_high_historical_win_rate_does_not_rescue_destructive_geometry(tmp_path):
    """A 91.9%-win-rate analogue sample must not buy a negative-EV geometry."""
    frame = _ramp_into_resistance()
    signature = _signature_for(frame, "buy")
    # 1 loss in 12 -> 91.7% win rate, and a positive expectancy in the sample.
    records = _measured_records(signature, n=120, wins_per_loss=11)
    brain = _brain(_index(tmp_path, records, provenance="mt5_m1"))
    decision = _decide(brain, frame)
    assert decision.action != "fire"
    assert decision.journal["econ_ok"] is False
    assert decision.journal["econ_payoff_ratio"] < 0.1


# --------------------------------------------------------------------------
# Property 2: the firehose still fires on good geometry + real evidence
# --------------------------------------------------------------------------


def test_firehose_still_fires_on_good_geometry_with_measured_evidence(tmp_path):
    """Guards against 'fixing' expectancy by refusing to trade at all."""
    frame = _basing_above_support()
    signature = _signature_for(frame, "buy")
    records = _measured_records(signature, n=80)
    brain = _brain(_index(tmp_path, records, provenance="mt5_m1"))
    decision = _decide(brain, frame)

    econ = decision.journal
    assert econ["analogue_measured"] is True
    assert decision.analogue_n >= 20, f"evidence not matched: {econ}"
    assert econ["econ_ok"] is True, f"economics refused a good trade: {econ}"
    assert econ["econ_payoff_ratio"] >= 1.0
    assert econ["econ_expected_net_usd"] > 0
    assert decision.action == "fire"
    assert decision.sl is not None and decision.sl < decision.journal["econ_entry"]
    assert decision.tp is not None and decision.tp > decision.journal["econ_entry"]


def test_fire_decision_reports_costs_and_probability_provenance(tmp_path):
    frame = _basing_above_support()
    signature = _signature_for(frame, "buy")
    brain = _brain(_index(tmp_path, _measured_records(signature, n=80), provenance="mt5_m1"))
    decision = _decide(brain, frame)
    econ = decision.journal
    # Cost is charged from the live spread at the size actually being sent.
    lots = decision.quantity
    assert econ["econ_cost_usd"] == pytest.approx(HALF_PIP_SPREAD * 100000.0 * lots)
    # Probability is the conservative bound on the sample, not the point estimate.
    assert econ["econ_p_win_source"] == "analogue_wilson_lower_bound"
    assert econ["econ_p_win"] < 0.75


def test_fire_size_comes_from_validated_risk_not_a_fixed_clip(tmp_path):
    """order_quantity is a fallback, not the size of every trade."""
    frame = _basing_above_support()
    signature = _signature_for(frame, "buy")
    brain = _brain(_index(tmp_path, _measured_records(signature, n=80), provenance="mt5_m1"))
    decision = _decide(brain, frame)
    assert decision.action == "fire"
    assert decision.journal["size_ok"] is True
    assert decision.journal["size_reason"] == "sized_from_validated_risk"
    # Sized from the $100 budget x 8% validated fraction across 5 clips, not 0.01.
    assert decision.quantity != 0.01
    assert decision.journal["size_risk_usd"] <= decision.journal["size_clip_budget_usd"] + 1e-9


def test_edge_sizing_can_be_disabled_back_to_the_fixed_clip(tmp_path):
    frame = _basing_above_support()
    signature = _signature_for(frame, "buy")
    brain = _brain(
        _index(tmp_path, _measured_records(signature, n=80), provenance="mt5_m1"),
        intelligent_edge_sizing=False,
    )
    decision = _decide(brain, frame)
    assert decision.quantity == pytest.approx(0.01)


# --------------------------------------------------------------------------
# Property 3: fabricated evidence cannot authorise a trade
# --------------------------------------------------------------------------


def test_synthetic_proxy_evidence_cannot_authorise_a_fire(tmp_path):
    """The committed offline index is a fixture; it must not validate a strategy.

    Its two outcomes (-0.02 / +0.04) return a 'calibrated' PF of 6.0 for any query
    with 20 matches. A live demo run believed that and finished at PF 0.25.
    """
    frame = _basing_above_support()
    signature = _signature_for(frame, "buy")
    records = _measured_records(signature, n=80)

    real = _decide(_brain(_index(tmp_path, records, provenance="mt5_m1")), frame)
    proxy = _decide(_brain(_index(tmp_path, records, provenance="research_proxy")), frame)

    # Identical records and geometry; only the provenance differs.
    assert real.action == "fire"
    assert proxy.action != "fire"
    assert proxy.reason == "no_validated_strategy_model"
    assert proxy.journal["analogue_measured"] is False


def test_synthetic_evidence_is_allowed_only_behind_an_explicit_opt_in(tmp_path):
    frame = _basing_above_support()
    signature = _signature_for(frame, "buy")
    records = _measured_records(signature, n=80)
    brain = _brain(
        _index(tmp_path, records, provenance="research_proxy"),
        intelligent_allow_synthetic_evidence=True,
    )
    # The opt-in exists for OFFLINE RESEARCH ONLY: synthetic evidence may be
    # evaluated but can never authorise a demo order (P2 governance).
    decision = _decide(brain, frame)
    assert decision.action != "fire"
    assert decision.reason.startswith("shadow:not_trading_stage:")


def test_provenance_classification():
    for label in ("research_proxy", "synthetic_proxy", "unknown", None):
        assert not is_measured_provenance(label)
    for label in ("mt5_m1", "mt5_demo_history"):
        assert is_measured_provenance(label)


def test_store_reads_provenance_from_index(tmp_path):
    path = _index(tmp_path, [], provenance="mt5_m1")
    store = AnalogueStore.load(path)
    assert store.provenance == "mt5_m1"
    assert store.outcome_unit == "usd"
    assert store.is_measured is True


def test_store_treats_legacy_label_as_unmeasured(tmp_path):
    """Old indexes carry label='research_proxy' whether or not they were real."""
    path = tmp_path / "legacy.json"
    path.write_text(
        json.dumps({"schema": "analogue_index.v1", "label": "research_proxy", "records": []}),
        encoding="utf-8",
    )
    store = AnalogueStore.load(path)
    assert store.provenance == "research_proxy"
    assert store.is_measured is False
