from __future__ import annotations

from aegis.research.rapid_benchmark import (
    run_deterministic_rapid_lifecycle,
    run_synthetic_benchmark,
)


def test_synthetic_benchmark_proves_causal_and_lifecycle_invariants():
    report = run_synthetic_benchmark(
        event_count=64,
        intervals_s=(0.25, 0.01),
    )

    assert report["scope"] == "transport_and_lifecycle_only"
    assert report["no_dropped_events"] is True
    assert report["no_reordering"] is True
    assert report["duplicate_event_rejected"] is True
    assert report["out_of_order_rejected"] is True
    assert report["duplicate_intent_rejected"] is True
    assert report["duplicate_order_rejected"] is True
    assert report["no_premature_fill"] is True
    assert report["no_premature_close"] is True
    assert report["no_reversal_before_reconciliation"] is True
    assert report["all_intervals"]["0.25"]["accepted_events"] == 64
    assert report["all_intervals"]["0.01"]["accepted_events"] == 64
    rapid = report["rapid_lifecycle"]
    assert rapid["broker_called"] is False
    assert rapid["four_leg_rapid_opening"] is True
    assert rapid["four_leg_count"] == 4
    assert rapid["four_leg_independent_states"] is True
    assert all(
        state["preflight"] and state["acknowledgement"] and state["fill"]
        for state in rapid["leg_states"].values()
    )
    assert rapid["pending_order_ladder"] is True
    assert rapid["pending_order_scenarios"]["replaced_then_filled"]["status"] == "FILLED"
    assert rapid["pending_order_scenarios"]["cancelled"]["status"] == "CANCELLED"
    assert rapid["pending_order_scenarios"]["expired"]["status"] == "EXPIRED"
    assert rapid["partial_fill"] is True
    assert rapid["partial_reduction"] is True
    assert rapid["restart_recovery"]["positions_reconstructed"] is True
    assert rapid["restart_recovery"]["pending_orders_reconstructed"] is True
    assert rapid["restart_recovery"]["idempotent_reconciliation"] is True
    assert rapid["position_safety"]["no_martingale"] is True
    assert rapid["position_safety"]["no_uncontrolled_averaging_down"] is True
    assert rapid["complete_basket_close"] is True
    assert rapid["confirmed_reconciliation"] is True
    assert rapid["reversal_results"]["reversal_buy_to_sell_after_reconciliation"] is True
    assert rapid["reversal_results"]["reversal_sell_to_buy_after_reconciliation"] is True
    assert rapid["immediate_post_close_rescan"] is True
    assert rapid["duplicate_suppression"] is True
    assert rapid["all_fake_events_accepted_except_duplicate"] is True
    assert set(rapid["timings_ms"]) == {
        "event_to_decision",
        "decision_to_intent",
        "intent_to_preflight",
        "preflight_to_send",
        "send_to_acknowledgement",
        "close_decision_to_request",
        "close_request_to_confirmation",
        "close_confirmation_to_rescan",
    }
    assert all(value >= 0.0 for value in rapid["timings_ms"].values())


def test_deterministic_rapid_lifecycle_is_independently_repeatable():
    first = run_deterministic_rapid_lifecycle()
    second = run_deterministic_rapid_lifecycle()
    assert first["schema"] == "aegis.rapid_fake_broker_lifecycle.v1"
    assert first["timings_ms"] == second["timings_ms"]
    assert first["ledger"]["reason_counts"] == second["ledger"]["reason_counts"]


def test_synthetic_benchmark_reports_the_local_decision_to_intent_target():
    report = run_synthetic_benchmark(event_count=32, intervals_s=(0.25,))

    result = report["all_intervals"]["0.25"]
    assert result["decision_to_intent_p95_ms"] >= 0.0
    assert result["target_ms"] == 50.0
    assert result["target_met"] is (result["decision_to_intent_p95_ms"] <= 50.0)
