from __future__ import annotations

from aegis.research.watcher_algorithms import ALGORITHM_MODULES
from aegis.research.watcher_historical_replay import build_pre_entry_state, replay_rows


def _row(*, side: str, net: float, horizon: int = 3) -> dict:
    return {
        "time": "2026-08-25T14:23:36.000Z",
        "symbol": "EURUSD",
        "side": side,
        "session": "new_york",
        "regime": "normal_volatility",
        "structure": "m1_range_or_pullback",
        "family": "universal_quote_entry",
        "horizon_s": horizon,
        "entry_price": 1.1000,
        "entry_spread": 0.00005,
        "quote_age_s": 0.2,
        "return_1s": 0.0001 if side == "buy" else -0.0001,
        "captured_exit_net_pnl": net,
        "mfe": 0.0002,
        "mae": -0.0001,
        "never_green": net <= 0,
    }


def test_historical_state_contains_only_pre_entry_fields():
    state = build_pre_entry_state(_row(side="buy", net=0.25))

    assert state["side"] == "BUY"
    assert state["horizon_s"] == 3
    assert state["tick_direction"] == "up"
    assert "captured_exit_net_pnl" not in state
    assert "mfe" not in state
    assert "mae" not in state
    assert "never_green" not in state


def test_replay_evaluates_every_algorithm_and_attaches_net_outcomes_afterward():
    report = replay_rows([
        _row(side="buy", net=0.25),
        _row(side="sell", net=-0.10, horizon=10),
    ])

    assert report["schema"] == "watcher_algorithm_historical_replay.v1"
    assert report["feature_adapter"] == "watcher_feature_engine.v1"
    assert report["feature_history_order"] == "prior_rows_only"
    assert report["rows_replayed"] == 2
    assert set(report["algorithms"]) == set(ALGORITHM_MODULES)
    scalp = report["algorithms"]["scalping_execution"]
    assert scalp["evaluated"] == 2
    assert scalp["signal_samples"] == 2
    assert scalp["wins"] == 1
    assert scalp["losses"] == 1
    assert scalp["net_pnl"] == 0.15
    assert set(scalp["by_horizon"]) == {"3", "10"}
    assert report["no_lookahead"] is True
    assert report["research_only"] is True
    assert report["book_coverage"]["book_count"] == 77
    assert report["book_coverage"]["all_books_mapped"] is True
    assert report["book_consensus"]["rows"] == 2
    assert report["book_consensus"]["book_algorithm_count"] == len(ALGORITHM_MODULES)
    assert report["book_consensus"]["no_lookahead"] is True
    assert set(report["book_consensus"]["by_rank_bin"]) == {
        "strong_opposition",
        "opposition",
        "neutral",
        "support",
        "strong_support",
    }


def test_selected_replay_supports_purged_chronological_splits_without_full_registry():
    rows = [
        _row(side="buy", net=0.10, horizon=1),
        _row(side="sell", net=-0.05, horizon=2),
        _row(side="buy", net=0.08, horizon=3),
        _row(side="sell", net=-0.02, horizon=5),
        _row(side="buy", net=0.04, horizon=8),
    ]
    report = replay_rows(
        rows,
        algorithm_names=("bollinger_bands", "rsi_reversal"),
        split_ranges={"train": (0, 1), "validation": (2, 3), "sealed": (4, 5)},
        purge_rows=1,
    )

    assert report["algorithm_selection"] == "explicit_selected"
    assert report["algorithm_ids"] == ["bollinger_bands", "rsi_reversal"]
    assert report["algorithm_count"] == 2
    assert set(report["algorithms"]) == {"bollinger_bands", "rsi_reversal"}
    assert report["split_replay_policy"] == "chronological_forward_horizon_purge.v1"
    assert report["split_replay_purge_rows"] == 1
    assert {name: value["rows_replayed"] for name, value in report["split_replay"].items()} == {
        "train": 1, "validation": 1, "sealed": 1,
    }


def test_selected_replay_prefers_normalized_cost_aware_returns_and_reports_exact_identities():
    rows = [
        {
            **_row(side="buy", net=100.0, horizon=5),
            "captured_exit_return": 0.001,
            "family_version": "quote_microstructure_v1",
            "entry_latency_s": 0.2,
            "close_latency_s": 0.2,
        },
        {
            **_row(side="buy", net=100.0, horizon=5),
            "time": "2026-08-25T14:23:37.000Z",
            "captured_exit_return": -0.0005,
            "family_version": "quote_microstructure_v1",
        },
    ]
    report = replay_rows(
        rows,
        algorithm_names=("scalping_execution",),
        rejection_rate=0.25,
        rejection_evidence={"source": "runner-wide_observation"},
    )

    item = report["algorithms"]["scalping_execution"]
    assert item["net_pnl"] == 0.0005
    assert item["rejection_adjusted_expectancy"] == 0.0001875
    key = "scalping_execution|EURUSD|BUY|5|quote_microstructure_v1"
    assert report["exact_strategies"][key]["signal_samples"] == 2
    assert report["rejection_adjustment"]["classification_counts_unchanged"] is True


def test_replay_reports_incomplete_cost_provenance_for_legacy_rows():
    report = replay_rows(
        [_row(side="buy", net=0.10)],
        algorithm_names=("scalping_execution",),
    )

    provenance = report["cost_model_provenance"]
    assert provenance["schema"] == "aegis.shadow_cost_model.v1"
    assert provenance["status"] == "INCOMPLETE"
    assert provenance["rows_checked"] == 1
    assert provenance["rows_complete"] == 0


def test_pre_enriched_replay_is_explicit_and_sanitizes_outcomes():
    rows = [{
        **_row(side="buy", net=0.10),
        "feature_provenance": {"all_features_available_at_or_before_decision": True},
        "future_alias": "must_not_become_a_feature",
    }]
    report = replay_rows(
        rows,
        algorithm_names=("scalping_execution",),
        pre_enriched=True,
    )

    assert report["input_feature_mode"] == "pre_enriched_causal_row"
    assert report["no_lookahead"] is True


def test_selected_replay_can_omit_universe_context_explicitly():
    report = replay_rows(
        [_row(side="buy", net=0.10)],
        algorithm_names=("rsi_reversal",),
        include_universe_context=False,
    )

    assert report["universe_context"] == "omitted_for_selected_replay"
    assert report["no_lookahead"] is True


def test_selected_replay_exports_bounded_after_cost_execution_trace():
    report = replay_rows(
        [
            _row(side="buy", net=0.10, horizon=3),
            {**_row(side="buy", net=-0.05, horizon=3), "time": "2026-08-25T14:23:37.000Z"},
        ],
        algorithm_names=("scalping_execution",),
        capture_execution_trace=True,
        execution_trace_limit=8,
    )

    trace = report["execution_traces"]["scalping_execution"]
    assert len(trace) == 2
    assert trace[0]["event_index"] == 0
    assert trace[0]["net_outcome"] == 0.10
    assert trace[0]["order_intent"]["contract_type"] == "OrderIntent"
    assert trace[0]["basket_intent"]["contract_type"] == "BasketIntent"
    assert report["execution_trace_provenance"] == {
        "schema": "aegis.replay_execution_trace.v1",
        "policy": "selected_signal_after_cost_outcome",
        "max_rows_per_strategy": 8,
        "outcome_attached_after_evaluation": True,
    }


def test_same_quote_context_reuse_preserves_selected_decisions():
    rows = [
        _row(side="buy", net=0.10, horizon=3),
        {**_row(side="sell", net=-0.05, horizon=10), "time": "2026-08-25T14:23:36.000Z"},
    ]
    baseline = replay_rows(
        rows, algorithm_names=("rsi_reversal",), include_universe_context=False
    )
    reused = replay_rows(
        rows,
        algorithm_names=("rsi_reversal",),
        include_universe_context=False,
        reuse_same_quote_context=True,
    )

    assert reused["same_quote_context_reuse"] is True
    assert reused["algorithms"] == baseline["algorithms"]
