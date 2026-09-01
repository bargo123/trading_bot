from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from aegis.optimizer.walk_forward import synthetic_ohlcv
from aegis.research.baseline import replay_firehose_benchmark
from aegis.research.candidate import CandidateReject, CandidateSpec, assert_candidate_complete, size_candidate
from aegis.research.cycle import run_research_cycle
from aegis.research.reports import write_reports
from aegis.research.shadow import ShadowConfigError, validate_shadow_config
from aegis.sizing import ContractSpec
from aegis.config import load_config


def _spec(**over) -> CandidateSpec:
    base = dict(
        name="htf_retest",
        regime="range",
        timeframe="M15",
        data_requirements=("M15", "H4"),
        entry="m15 reject of h4 value",
        invalidation_stop="beyond wick",
        risk_percent=0.25,
        exit="h4 opposite value",
        max_hold="12 M15 bars",
        tp_pips=8.0,
        sl_pips=12.0,
    )
    base.update(over)
    return CandidateSpec(**base)


def test_legacy_payoff_is_rejected_without_evidence():
    with pytest.raises(CandidateReject, match="1/30"):
        assert_candidate_complete(_spec(tp_pips=1.0, sl_pips=30.0))
    assert_candidate_complete(_spec(tp_pips=1.0, sl_pips=30.0, evidence_allows_legacy_payoff=True))


def test_candidate_sizing_reuses_stop_distance_interface():
    spec = _spec()
    contract = ContractSpec(
        symbol="EURUSD",
        tick_size=0.00001,
        tick_value=1.0,
        contract_size=100000.0,
        volume_min=0.01,
        volume_max=100.0,
        volume_step=0.01,
    )
    decision = size_candidate(spec=spec, equity=10_000.0, entry=1.10, stop=1.095, contract=contract)
    assert decision.allowed
    assert decision.lots > 0


def test_firehose_benchmark_replay_is_labeled_not_champion():
    df = synthetic_ohlcv(400, seed=3)
    out = replay_firehose_benchmark(df)
    assert out["name"] == "legacy_firehose_1_30"
    assert out["not_a_champion"] is True
    assert out["costs_applied"] is True
    assert "expectancy_r" in out


def test_research_cycle_rejects_and_never_touches_live(tmp_path: Path):
    hb = tmp_path / "hb.json"
    risk = tmp_path / "risk.json"
    hb.write_text('{"equity": 57.41, "open": 4, "risk_halted": true, "pid": 1}', encoding="utf-8")
    risk.write_text('{"halted": true, "permanent_halt": true, "reason": "max_drawdown 39.11%"}', encoding="utf-8")
    result = run_research_cycle(
        hypothesis="skip 1/30",
        metrics={"expectancy": -0.04, "profit_factor": 0.3, "n_trades": 40, "net_pnl": -2.0, "win_rate": 0.4, "id": "exp_neg"},
        pnls=[-0.1] * 40,
        frame_fingerprint="ds1",
        config={"id": "exp_neg", "tp": 1, "sl": 30},
        db_path=tmp_path / "e.sqlite",
        heartbeat_path=hb,
        risk_path=risk,
    )
    assert result["decision"] == "rejected"
    assert result["placed_orders"] is False
    assert result["mt5_touched"] is False
    assert result["promoted_live_yaml"] is False
    assert result["refuses_live_yaml"] is True
    assert result["live"]["risk_halted"] is True


def test_research_cycle_runs_twice_without_registry_crash(tmp_path: Path):
    hb = tmp_path / "hb.json"
    risk = tmp_path / "risk.json"
    hb.write_text('{"equity": 57.41, "open": 4, "risk_halted": true}', encoding="utf-8")
    risk.write_text('{"halted": true, "permanent_halt": true}', encoding="utf-8")
    db = tmp_path / "e.sqlite"
    metrics = {
        "expectancy": -0.04,
        "profit_factor": 0.3,
        "n_trades": 40,
        "net_pnl": -2.0,
        "win_rate": 0.4,
    }
    first = run_research_cycle(
        hypothesis="observe only",
        metrics={**metrics, "id": "exp_observe_1"},
        pnls=[-0.1] * 40,
        frame_fingerprint="ds1",
        config={"id": "exp_observe_1"},
        db_path=db,
        heartbeat_path=hb,
        risk_path=risk,
    )
    second = run_research_cycle(
        hypothesis="observe only again",
        metrics={**metrics, "id": "exp_observe_2"},
        pnls=[-0.1] * 40,
        frame_fingerprint="ds1",
        config={"id": "exp_observe_2"},
        db_path=db,
        heartbeat_path=hb,
        risk_path=risk,
    )
    assert first["decision"] == "rejected"
    assert second["decision"] == "rejected"
    assert second["placed_orders"] is False


def test_reports_and_shadow_yaml(tmp_path: Path):
    hb = tmp_path / "hb.json"
    risk = tmp_path / "risk.json"
    hb.write_text('{"equity": 57.41, "open": 4, "risk_halted": true, "circuit_ok": true}', encoding="utf-8")
    risk.write_text('{"halted": true, "permanent_halt": true, "reason": "max_drawdown 39.11%"}', encoding="utf-8")
    paths = write_reports(
        tmp_path / "reports",
        heartbeat_path=hb,
        risk_path=risk,
        champion=None,
        baseline={"name": "legacy_firehose_1_30", "total_trades": 10, "expectancy_r": -0.04, "profit_factor": 0.3},
        last_decision={"decision": "rejected"},
    )
    text = paths["champion"].read_text(encoding="utf-8")
    assert "None" in text
    assert "Safety dashboard" in paths["safety"].read_text(encoding="utf-8")
    live_text = paths["live_vs_model"].read_text(encoding="utf-8")
    assert "deals Phase 0 sealed:" in live_text
    assert "legacy_firehose_1_30" in live_text
    cfg = load_config(Path(__file__).resolve().parents[1] / "config_mt5_demo_selective_shadow.yaml")
    validate_shadow_config(cfg)
    with pytest.raises(ShadowConfigError):
        validate_shadow_config({**cfg, "dry_run": False, "allow_live": False})
