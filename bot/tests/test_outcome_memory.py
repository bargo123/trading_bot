from __future__ import annotations

from aegis.intel.outcome_memory import OutcomeMemoryStore, classify_lifecycle
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
