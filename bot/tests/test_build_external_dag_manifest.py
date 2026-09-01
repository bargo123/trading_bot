from __future__ import annotations

import hashlib
import json

from scripts.build_external_dag_manifest import build_manifest


def test_manifest_builder_copies_real_report_metrics_without_inventing_validation(tmp_path):
    report = tmp_path / "leaderboard.json"
    rows = tmp_path / "rows.jsonl"
    output = tmp_path / "manifest.json"
    report.write_text(
        json.dumps(
            {
                "DATASET_HASH": "a" * 64,
                "VALIDATION_HASH": "b" * 64,
                "TARGET_DEFINITION": "captured_exit_replay",
                "symbols": ["EURUSD"],
                "horizons_s": [3],
                "OOS_TEST_N": 10,
                "OOS_TEST_CAPTURED_EXPECTANCY": -0.1,
                "OOS_TEST_CAPTURED_PF": 0.9,
                "OOS_TEST_EXECUTABLE_CAPTURED_EXPECTANCY": -0.2,
                "OOS_TEST_EXECUTABLE_CAPTURED_PF": 0.8,
                "OOS_TEST_EXECUTABLE_CAPTURED_EXPECTANCY_LOWER_95": -0.3,
                "OOS_TEST_CAPTURED_LOSSES": 6,
                "OOS_SEALED_N": 12,
                "OOS_SEALED_CAPTURED_EXPECTANCY": 0.01,
                "OOS_SEALED_CAPTURED_PF": 1.1,
                "OOS_SEALED_EXECUTABLE_CAPTURED_EXPECTANCY": -0.02,
                "OOS_SEALED_EXECUTABLE_CAPTURED_PF": 0.7,
                "OOS_SEALED_CAPTURED_LOSSES": 7,
                "OOS_SEALED_CALIBRATION_ECE": 0.02,
                "OOS_SEALED_P95_LOSS": -0.03,
                "OOS_SEALED_P99_LOSS": -0.04,
                "OOS_SEALED_ABSTAIN_RATE": 0.5,
            }
        ),
        encoding="utf-8",
    )
    rows.write_text(
        json.dumps(
            {
                "time": "2026-08-31T12:00:00Z",
                "symbol": "EURUSD",
                "side": "buy",
                "horizon_s": 3,
                "bid": 1.1,
                "ask": 1.1001,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = build_manifest(report, rows, output)

    manifest = json.loads(output.read_text(encoding="utf-8"))
    assert result["dataset_hash"] == "a" * 64
    assert manifest["point_in_time_state"]["symbol"] == "EURUSD"
    chronological = manifest["validation_evidence"]["chronological_test"]
    sealed = manifest["validation_evidence"]["sealed_oos"]
    assert chronological["expectancy"] == -0.2
    assert chronological["profit_factor"] == 0.8
    assert chronological["expectancy_lcb95"] == -0.3
    assert chronological["n_losses"] == 6
    assert sealed["expectancy"] == -0.02
    assert sealed["profit_factor"] == 0.7
    assert sealed["n_losses"] == 7
    assert "validation_oos" not in manifest["validation_evidence"]


def test_manifest_builder_propagates_bounded_selected_replay_evidence(tmp_path):
    report = tmp_path / "leaderboard.json"
    rows = tmp_path / "rows.jsonl"
    replay = tmp_path / "selected-replay.json"
    output = tmp_path / "manifest.json"
    report.write_text(
        json.dumps(
            {
                "DATASET_HASH": "a" * 64,
                "VALIDATION_HASH": "b" * 64,
                "TARGET_DEFINITION": "captured_exit_replay",
                "symbols": ["EURUSD"],
                "horizons_s": [5],
            }
        ),
        encoding="utf-8",
    )
    rows.write_text(
        json.dumps(
            {
                "time": "2026-08-31T12:00:00Z",
                "symbol": "EURUSD",
                "side": "buy",
                "horizon_s": 5,
                "bid": 1.1,
                "ask": 1.1001,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    replay.write_text(
        json.dumps(
            {
                "schema": "watcher_algorithm_historical_replay.v1",
                "algorithm_selection": "explicit_selected",
                "algorithm_ids": ["bollinger_bands"],
                "algorithm_count": 1,
                "algorithms": {
                    "bollinger_bands": {
                        "signal_samples": 20,
                        "wins": 8,
                        "losses": 12,
                        "expectancy": -0.01,
                        "rejection_adjusted_expectancy": -0.02,
                    }
                },
                "exact_strategies": {
                    "bollinger_bands|EURUSD|BUY|5|quote_microstructure_v1": {
                        "signal_samples": 20,
                        "wins": 8,
                        "losses": 12,
                        "expectancy": -0.01,
                    }
                },
                "split_replay_ranges": {
                    "train": {"start": 0, "end": 10},
                    "validation": {"start": 15, "end": 20},
                },
                "split_replay_purge_rows": 5,
                "split_replay": {},
                "rejection_adjustment": {"rate": 0.1},
                "cost_model_provenance": {
                    "schema": "aegis.shadow_cost_model.v1",
                    "status": "COMPLETE",
                    "rows_checked": 20,
                    "rows_complete": 20,
                    "per_row": True,
                    "spread": "executable_bid_ask_entry_and_liquidation",
                    "slippage_bps": 0.1,
                    "commission_round_trip_usd": 0.0,
                    "entry_latency_s": 0.2,
                    "close_latency_s": 0.2,
                    "usd_per_price_unit": 100000.0,
                    "outcome_units": "captured_exit_return is broker-unit-normalized after-cost return",
                },
                "no_lookahead": True,
                "research_only": True,
                "execution_authority": False,
            }
        ),
        encoding="utf-8",
    )

    from scripts.build_external_dag_manifest import build_manifest

    build_manifest(report, rows, output, selected_replay_path=replay)

    evidence = json.loads(output.read_text(encoding="utf-8"))["validation_evidence"]
    assert evidence["selected_strategy_ids"] == ["bollinger_bands"]
    assert evidence["selected_strategy_count"] == 1
    assert evidence["selected_strategy_metrics"]["bollinger_bands"]["signal_samples"] == 20
    assert evidence["selected_strategy_validation"]["no_lookahead"] is True
    assert evidence["selected_strategy_validation"]["algorithm_ids"] == ["bollinger_bands"]
    assert evidence["selected_strategy_validation"]["split_replay_ranges"]["train"]["end"] == 10
    assert evidence["selected_strategy_validation"]["cost_model_provenance"]["status"] == "COMPLETE"


def test_manifest_builder_carries_actual_selected_replay_trace(tmp_path):
    report = tmp_path / "leaderboard.json"
    rows = tmp_path / "rows.jsonl"
    replay = tmp_path / "selected-replay.json"
    output = tmp_path / "manifest.json"
    report.write_text(
        json.dumps({"DATASET_HASH": "a" * 64, "VALIDATION_HASH": "b" * 64}),
        encoding="utf-8",
    )
    rows.write_text(
        json.dumps({"time": "2026-08-31T12:00:00Z", "symbol": "EURUSD", "side": "buy", "horizon_s": 5, "bid": 1.1, "ask": 1.1001}) + "\n",
        encoding="utf-8",
    )
    trace = [
        {
            "event_index": index,
            "strategy_id": "bollinger_bands",
            "symbol": "EURUSD",
            "side": "BUY",
            "horizon_s": 5,
            "net_outcome": value,
            "order_intent": {"contract_type": "OrderIntent"},
            "basket_intent": {"contract_type": "BasketIntent"},
        }
        for index, value in enumerate((0.1, -0.05, 0.03, -0.02))
    ]
    replay.write_text(
        json.dumps(
            {
                "schema": "watcher_algorithm_historical_replay.v1",
                "algorithm_selection": "explicit_selected",
                "algorithm_ids": ["bollinger_bands"],
                "algorithm_count": 1,
                "algorithms": {"bollinger_bands": {"signal_samples": 4, "wins": 2, "losses": 2}},
                "execution_traces": {"bollinger_bands": trace},
                "execution_trace_provenance": {
                    "schema": "aegis.replay_execution_trace.v1",
                    "policy": "selected_signal_after_cost_outcome",
                    "max_rows_per_strategy": 8,
                    "outcome_attached_after_evaluation": True,
                },
                "exact_strategies": {},
                "rejection_adjustment": {"rate": 0.1},
                "cost_model_provenance": {"status": "COMPLETE"},
                "no_lookahead": True,
                "research_only": True,
                "execution_authority": False,
            }
        ),
        encoding="utf-8",
    )

    build_manifest(report, rows, output, selected_replay_path=replay)

    evidence = json.loads(output.read_text(encoding="utf-8"))["validation_evidence"]
    selected = evidence["selected_strategy_metrics"]["bollinger_bands"]
    assert selected["returns"] == [0.1, -0.05, 0.03, -0.02]
    assert len(selected["execution_trace"]) == 4
    assert evidence["selected_strategy_validation"]["execution_trace_provenance"]["counts_by_algorithm"] == {"bollinger_bands": 4}


def test_manifest_builder_rejects_selected_replay_bound_to_other_rows(tmp_path):
    report = tmp_path / "leaderboard.json"
    rows = tmp_path / "rows.jsonl"
    replay = tmp_path / "selected-replay.json"
    output = tmp_path / "manifest.json"
    report.write_text(
        json.dumps({"DATASET_HASH": "a" * 64, "VALIDATION_HASH": "b" * 64}),
        encoding="utf-8",
    )
    rows.write_text("{}\n", encoding="utf-8")
    replay.write_text(
        json.dumps(
            {
                "schema": "watcher_algorithm_historical_replay.v1",
                "algorithm_selection": "explicit_selected",
                "algorithm_ids": ["bollinger_bands"],
                "algorithm_count": 1,
                "algorithms": {"bollinger_bands": {}},
                "input_dataset_sha256": hashlib.sha256(b"different").hexdigest(),
            }
        ),
        encoding="utf-8",
    )

    import pytest

    with pytest.raises(ValueError, match="does not match shadow rows"):
        build_manifest(report, rows, output, selected_replay_path=replay)
