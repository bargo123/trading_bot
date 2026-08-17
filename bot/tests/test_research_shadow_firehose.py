from __future__ import annotations

from pathlib import Path

import pytest

from aegis.intel.strategy_model import ValidatedStrategyModel
from aegis.intel.thesis_fire import ThesisFireDecision
from aegis.research.intelligent_champion import load_intelligent_champion, save_intelligent_champion
from aegis.research.sealed import SealedHoldoutError, SealedHoldoutStore, freeze_candidate
from aegis.research.shadow_firehose import aligned_shadow_rows, compare_bar, shadow_thesis_decision


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


def test_sealed_holdout_rejects_second_evaluation_of_same_frozen_id(tmp_path: Path):
    frozen = freeze_candidate(
        strategy_id="failed_break_v1",
        code_hash="code1",
        config={"tp": 8, "sl": 8},
        artifact_hash="art1",
    )
    store = SealedHoldoutStore(tmp_path / "sealed.jsonl")
    first = store.evaluate_once(
        frozen,
        holdout_fingerprint="hold-a",
        evaluate=lambda: {"expectancy": 0.02, "n_trades": 40},
    )
    assert first["frozen_hash"] == frozen.frozen_hash
    with pytest.raises(SealedHoldoutError):
        store.evaluate_once(
            frozen,
            holdout_fingerprint="hold-a",
            evaluate=lambda: {"expectancy": 0.99},
        )


def test_intelligent_champion_save_refuses_unready_model(tmp_path: Path):
    path = tmp_path / "intelligent_champion.json"
    assert load_intelligent_champion(path)["status"] == "none"
    thin = _ready_model()
    thin = ValidatedStrategyModel(**{**thin.__dict__, "n_losses": 1})
    with pytest.raises(ValueError, match="loss"):
        save_intelligent_champion(thin, path=path)
    save_intelligent_champion(_ready_model(), path=path)
    loaded = load_intelligent_champion(path)
    assert loaded["id"] == "failed_break_v1"
    assert loaded["n_losses"] == 12


def test_shadow_compare_joins_same_symbol_and_timestamp():
    row = compare_bar(
        symbol="EURUSD",
        bar_time="2026-01-01T12:00:00+00:00",
        old_side="buy",
        new_decision=ThesisFireDecision("skip", "no_validated_strategy_model"),
    )
    assert row["placed_orders"] is False
    assert row["old"]["action"] == "buy"
    assert row["new"]["action"] == "skip"
    aligned = aligned_shadow_rows(
        [{"symbol": "EURUSD", "bar_time": "t1", "side": "sell"}, {"symbol": "GBPUSD", "bar_time": "t1", "side": None}],
        [
            {"symbol": "EURUSD", "bar_time": "t1", "action": "fire", "reason": "ok", "expected_net_value": 0.04},
            {"symbol": "GBPUSD", "bar_time": "t1", "action": "skip", "reason": "state_ev_not_positive"},
        ],
    )
    assert [item["symbol"] for item in aligned] == ["EURUSD", "GBPUSD"]
    assert aligned[0]["old"]["action"] == "sell"
    assert aligned[0]["new"]["action"] == "fire"


def test_aligned_shadow_rows_refuse_mismatched_windows():
    with pytest.raises(ValueError, match="same symbol/bar_time"):
        aligned_shadow_rows(
            [{"symbol": "EURUSD", "bar_time": "t1", "side": "buy"}],
            [{"symbol": "GBPUSD", "bar_time": "t1", "action": "skip"}],
        )


def test_shadow_thesis_can_fire_without_five_local_losses():
    decision = shadow_thesis_decision(
        strategy=_ready_model(),
        state_expected_net_value=0.03,
        analogue_n=40,
        analogue_n_losses=0,
        uncertainty="calibrated",
        eligible=True,
    )
    assert decision.action == "fire"


def test_structural_invalidation_is_not_a_fixed_thirty_pip_stop():
    from aegis.research.exit_hypotheses import structural_exit_hypothesis

    long_exit = structural_exit_hypothesis(
        side="buy",
        swing_level=1.1000,
        buffer=0.0002,
        structure_target=1.1050,
    )
    assert long_exit.invalidation_price == pytest.approx(1.0998)
    assert long_exit.target_price == pytest.approx(1.1050)
    assert long_exit.invalidation_kind == "structural_swing"
    assert long_exit.invalidation_price != pytest.approx(1.1000 - 0.0030)
