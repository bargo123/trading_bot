from __future__ import annotations

import json

import pytest

from aegis.intel.outcome_memory import (
    OutcomeMemoryStore,
    classify_lifecycle,
    replay_counterfactual,
)
from aegis.intel.firehose_turnover import TurnoverMetrics


def test_lifecycle_classifier_separates_fast_loser_and_good_entry_bad_exit():
    fast_loser = classify_lifecycle(
        realized_net_usd=-0.12,
        mfe_usd=0.01,
        mae_usd=-0.10,
        time_to_green_s=None,
        selected_horizon_s=5,
    )
    assert fast_loser["classification"] == "BAD_ENTRY"
    assert fast_loser["speed_label"] == "FAST_LOSER"
    assert fast_loser["never_green"] is True

    bad_exit = classify_lifecycle(
        realized_net_usd=-0.02,
        mfe_usd=0.40,
        mae_usd=-0.04,
        time_to_green_s=2.0,
        selected_horizon_s=5,
    )
    assert bad_exit["classification"] == "GOOD_ENTRY_BAD_EXIT"
    assert bad_exit["speed_label"] is None
    assert bad_exit["green_then_loser"] is True

    incomplete = classify_lifecycle(
        realized_net_usd=-0.10,
        mfe_usd=None,
        mae_usd=None,
        time_to_green_s=None,
        selected_horizon_s=5,
    )
    assert incomplete["classification"] == "AMBIGUOUS"
    assert incomplete["speed_label"] is None


def test_outcome_memory_persists_state_and_suppresses_similar_fast_loser(tmp_path):
    store = OutcomeMemoryStore(tmp_path / "outcome_memory.json")
    row = store.record_closed(
        outcome_id="T1",
        features={
            "symbol": "EURUSD", "side": "buy", "mechanism": "pullback",
            "horizon_s": 5, "session": "london", "regime": "trend",
        },
        realized_net_usd=-0.12,
        mfe_usd=0.01,
        mae_usd=-0.10,
        time_to_green_s=None,
    )

    assert row["classification"] == "BAD_ENTRY"
    assert row["speed_label"] == "FAST_LOSER"
    assert store.should_suppress(
        {"symbol": "EURUSD", "side": "buy", "mechanism": "pullback",
         "horizon_s": 5, "session": "london", "regime": "trend"}
    ) is True

    reloaded = OutcomeMemoryStore(tmp_path / "outcome_memory.json")
    snapshot = reloaded.snapshot()
    assert snapshot["fast_loser_count"] == 1
    assert snapshot["bad_entry_count"] == 1
    assert snapshot["counterfactual_status"] == "UNAVAILABLE"


def test_winner_memory_does_not_suppress_unrelated_state(tmp_path):
    store = OutcomeMemoryStore(tmp_path / "outcome_memory.json")
    row = store.record_closed(
        outcome_id="T2",
        features={
            "symbol": "GBPUSD", "side": "sell", "mechanism": "breakout",
            "horizon_s": 10, "session": "new_york", "regime": "trend",
        },
        realized_net_usd=0.10,
        mfe_usd=0.14,
        mae_usd=-0.01,
        time_to_green_s=1.0,
    )
    assert row["classification"] == "GOOD_ENTRY_GOOD_EXIT"
    assert row["speed_label"] == "FAST_WINNER"
    assert store.should_suppress(
        {"symbol": "EURUSD", "side": "buy", "mechanism": "pullback",
         "horizon_s": 5, "session": "london", "regime": "trend"}
    ) is False


def test_turnover_exposes_confirmed_lifecycle_excursions_for_learning():
    turnover = TurnoverMetrics()
    turnover.record_open("T3", opened_at=100.0, slot_capacity=2)
    turnover.record_exit_trace("T3", observed_at=101.0, mfe_usd=0.0, pnl_usd=-0.05)
    turnover.record_exit_trace("T3", observed_at=103.0, mfe_usd=0.20, pnl_usd=0.20)
    turnover.record_close(
        "T3", closed_at=104.0, gross_pnl_usd=0.12, net_pnl_usd=0.10,
        cost_usd=0.02, confirmed=True, exit_reason="fast_take",
    )
    detail = turnover.close_detail("T3")
    assert detail["mfe_usd"] == 0.20
    assert detail["mae_usd"] == -0.05
    assert detail["first_green_s"] == 3.0
    metrics = turnover.snapshot(105.0)
    assert metrics["captured_net_win_rate"] == 1.0
    assert metrics["net_pnl"] == 0.10
    assert metrics["never_green_rate"] == 0.0


def test_outcome_memory_exposes_rich_winner_and_loser_similarity(tmp_path):
    store = OutcomeMemoryStore(tmp_path / "outcome_memory.json")
    base = {
        "symbol": "EURUSD", "side": "buy", "mechanism": "pullback",
        "horizon_s": 5, "session": "london", "regime": "trend",
        "volatility": "normal", "structure": "retest", "momentum": 0.8,
        "compression": 0.2, "spread_pips": 0.2, "stop_pips": 2.0,
        "target_pips": 4.0,
    }
    store.record_closed(
        outcome_id="WIN", features=base, realized_net_usd=0.12,
        mfe_usd=0.15, mae_usd=-0.01, time_to_green_s=1.0,
    )
    store.record_closed(
        outcome_id="LOSS", features={**base, "momentum": -0.8},
        realized_net_usd=-0.12, mfe_usd=0.01, mae_usd=-0.12,
        time_to_green_s=None,
    )

    summary = store.similarity_summary(base)
    assert summary["winner_similarity"] > 0.8
    assert summary["loser_similarity"] > 0.8
    assert summary["winner_count"] == 1
    assert summary["loser_count"] == 1


def test_counterfactual_replay_uses_sequential_executable_quotes():
    result = replay_counterfactual(
        quotes=[
            {"timestamp": 100.0, "bid": 1.1000, "ask": 1.1002},
            {"timestamp": 101.0, "bid": 1.1008, "ask": 1.1010},
            {"timestamp": 102.0, "bid": 1.1006, "ask": 1.1008},
        ],
        entry_time=100.0,
        side="buy",
        stop=1.0990,
        target=1.1007,
        horizon_s=5,
        cost_usd=0.02,
        usd_per_price_unit=1000.0,
    )

    assert result["status"] == "REPLAYED"
    assert result["chosen_net_usd"] == pytest.approx(0.58)
    assert result["abstain_net_usd"] == 0.0


def test_counterfactual_replay_rejects_geometry_that_is_not_executable():
    result = replay_counterfactual(
        quotes=[{"timestamp": 100.0, "bid": 1.1000, "ask": 1.1002}],
        entry_time=100.0,
        side="buy",
        stop=1.1010,
        target=1.1020,
        horizon_s=5,
    )

    assert result == {
        "status": "UNAVAILABLE",
        "reason": "counterfactual_geometry_invalid",
    }


def test_import_prior_autopsy_only_reconstructs_complete_rows(tmp_path):
    report = tmp_path / "fast_trade_autopsy.json"
    report.write_text(json.dumps({"trades": [
        {
            "ticket": 101, "symbol": "EURUSD", "side": "buy",
            "pnl": -0.12, "evidence_status": "COMPLETE",
            "hold_s": 4.0, "time_to_green_s": None,
            "mfe_usd": 0.01, "mae_usd": -0.10,
        },
        {"ticket": 102, "symbol": "EURUSD", "side": "sell",
         "pnl": -0.10, "evidence_status": "PARTIAL"},
    ]}), encoding="utf-8")

    store = OutcomeMemoryStore(tmp_path / "outcome_memory.json")
    result = store.import_prior_autopsy(report)

    assert result == {"imported": 1, "skipped": 1, "unavailable": 0}
    assert len(store.records) == 1
    assert store.records[0]["features"]["source"] == "prior_autopsy"
    assert store.records[0]["classification"] == "BAD_ENTRY"


def test_sparse_prior_autopsy_loser_does_not_suppress_rich_candidate(tmp_path):
    report = tmp_path / "fast_trade_autopsy.json"
    report.write_text(json.dumps({"trades": [{
        "ticket": 103, "symbol": "EURUSD", "side": "buy",
        "pnl": -0.12, "evidence_status": "COMPLETE",
        "hold_s": 4.0, "time_to_green_s": None,
        "mfe_usd": 0.01, "mae_usd": -0.10,
    }]}), encoding="utf-8")

    store = OutcomeMemoryStore(tmp_path / "outcome_memory.json")
    store.import_prior_autopsy(report)

    assert store.should_suppress({
        "symbol": "EURUSD", "side": "buy", "mechanism": "pullback",
        "horizon_s": 5, "session": "london", "regime": "trend",
    }) is False
