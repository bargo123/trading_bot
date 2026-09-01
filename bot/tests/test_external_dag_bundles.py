from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from aegis.research.external_dag.bundles import (
    ExecutionBundleRejected,
    assess_execution_readiness,
    build_execution_bundle,
)
from aegis.research.external_dag.catalog import REQUIRED_EXTERNAL_TOOLS
from aegis.research.external_dag.contracts import (
    ExternalTaskResult,
    ResearchBundle,
    content_hash,
)
from aegis.research.external_dag.status import project_status
from aegis.research.registry import ExperimentRegistry
from aegis.research.watcher_algorithms import ALGORITHM_MODULES


SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64


def _result(node_id: str, tool_id: str, *, status: str = "SUCCESS") -> ExternalTaskResult:
    return ExternalTaskResult(
        request_id=f"request-{node_id}",
        node_id=node_id,
        tool_id=tool_id,
        status=status,
        started_at=1.0,
        finished_at=2.0,
        artifact_hashes=(SHA_A,) if status == "SUCCESS" else (),
        reason="" if status == "SUCCESS" else "fixture_failure",
    )


def _research_bundle(*, failed_tool: str | None = None) -> ResearchBundle:
    rows = [
        _result(f"tool-{index}", tool, status="FAILED" if tool == failed_tool else "SUCCESS")
        for index, tool in enumerate(sorted(REQUIRED_EXTERNAL_TOOLS))
    ]
    rows.append(_result("book-algorithms", "aegis-book-algorithms"))
    return ResearchBundle(
        workflow_id="full_research_validation.v1",
        run_id="run-fixture",
        node_results=tuple(rows),
        complete=failed_tool is None,
    )


def _evidence(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "target_definition": "captured_exit_replay",
        "dataset_hash": SHA_A,
        "validation_hash": SHA_B,
        "model_artifact_hash": SHA_C,
        "created_at": 1_700_000_000.0,
        "expires_at": 4_100_000_000.0,
        "authorized_symbols": ["EURUSD", "GBPUSD"],
        "authorized_horizons_s": [3, 10],
        "book_algorithm_count": len(ALGORITHM_MODULES),
        "book_registry_hash": content_hash(tuple(ALGORITHM_MODULES)),
        "chronological_test": {
            "expectancy": 0.012,
            "profit_factor": 1.22,
            "n_trades": 80,
            "n_losses": 18,
        },
        "sealed_oos": {
            "expectancy": 0.008,
            "profit_factor": 1.14,
            "n_trades": 45,
            "n_losses": 9,
        },
        "validation_oos": {
            "expectancy": 0.006,
            "profit_factor": 1.10,
            "n_trades": 40,
            "n_losses": 8,
        },
        "calibration_ece": 0.07,
        "p95_loss": 0.12,
        "p99_loss": 0.20,
        "abstain_rate": 0.34,
        "perturbation_status": "STABLE",
        "replay_parity_status": "MATCHED",
        "selected_strategy_ids": ["bollinger_bands"],
        "selected_strategy_validation": {
            "algorithm_ids": ["bollinger_bands"],
            "no_lookahead": True,
            "research_only": True,
            "execution_authority": False,
            "rejection_adjustment": {"applied_to_expectancy": True},
            "cost_model_provenance": {
                "schema": "aegis.shadow_cost_model.v1",
                "status": "COMPLETE",
                "rows_checked": 80,
                "rows_complete": 80,
                "per_row": True,
                "spread": "executable_bid_ask_entry_and_liquidation",
                "slippage_bps": 0.1,
                "commission_round_trip_usd": 0.0,
                "entry_latency_s": 0.2,
                "close_latency_s": 0.2,
                "usd_per_price_unit": 100_000.0,
                "outcome_units": "captured_exit_return is broker-unit-normalized after-cost return",
            },
            "split_replay": {
                "validation": {
                    "exact_strategies": {
                        "bollinger_bands|EURUSD|BUY|3|quote_microstructure_v1": {
                            "signal_samples": 40,
                            "wins": 25,
                            "losses": 15,
                            "expectancy": 0.012,
                            "rejection_adjusted_expectancy": 0.01,
                            "profit_factor": 1.4,
                        }
                    }
                },
                "sealed": {
                    "exact_strategies": {
                        "bollinger_bands|EURUSD|BUY|3|quote_microstructure_v1": {
                            "signal_samples": 40,
                            "wins": 25,
                            "losses": 15,
                            "expectancy": 0.011,
                            "rejection_adjusted_expectancy": 0.009,
                            "profit_factor": 1.3,
                        }
                    }
                },
            },
        },
        "models": {
            "EURUSD": {"BUY": {"micro_momentum": {"3": {
                "p_captured_win": 0.63, "threshold": 0.55, "decision": True,
                "expected_net_pnl": 0.02, "expected_net_pnl_lcb95": 0.005,
                "calibration_status": "CALIBRATED", "evidence_n": 80,
                "evidence_losses": 18,
            }}}},
            "GBPUSD": {"SELL": {"failed_breakout": {"10": {
                "p_captured_win": 0.59, "threshold": 0.54, "decision": True,
                "expected_net_pnl": 0.01, "expected_net_pnl_lcb95": 0.002,
                "calibration_status": "CALIBRATED", "evidence_n": 45,
                "evidence_losses": 9,
            }}}},
        },
        # The execution gate accepts only context compiled from the book node.
        "book_context": {
            "status": "AVAILABLE",
            "algorithm_count": len(ALGORITHM_MODULES),
            "algorithm_ids": list(ALGORITHM_MODULES),
            "state_hash": SHA_B,
            "artifact_hash": SHA_A,
            "book_registry_hash": content_hash(tuple(ALGORITHM_MODULES)),
            "supporting_algorithms": [ALGORITHM_MODULES[0]],
            "opposing_algorithms": [],
            "missing_data_algorithms": list(ALGORITHM_MODULES[1:]),
            "supporting_count": 1,
            "opposing_count": 0,
            "missing_data_count": len(ALGORITHM_MODULES) - 1,
            "absolute_views": True,
            "compiled_from_artifact": True,
            "execution_authority": False,
            "research_only": True,
            "no_lookahead": True,
            "order_intent": False,
        },
    }
    value.update(overrides)
    return value


@pytest.mark.parametrize(
    ("bundle", "evidence", "reason"),
    [
        (_research_bundle(failed_tool="qlib"), _evidence(), "required_node_not_successful"),
        (_research_bundle(), _evidence(chronological_test={"expectancy": -0.01, "profit_factor": 1.2, "n_trades": 80, "n_losses": 18}), "chronological_expectancy_not_positive"),
        (_research_bundle(), _evidence(sealed_oos={"expectancy": -0.01, "profit_factor": 1.2, "n_trades": 45, "n_losses": 9}), "sealed_expectancy_not_positive"),
        (_research_bundle(), _evidence(sealed_oos={"expectancy": 0.01, "profit_factor": 1.0, "n_trades": 45, "n_losses": 9}), "sealed_profit_factor_not_above_one"),
        (_research_bundle(), _evidence(validation_oos={"expectancy": -0.01, "profit_factor": 1.2, "n_trades": 40, "n_losses": 8}), "validation_expectancy_not_positive"),
        (_research_bundle(), _evidence(dataset_hash="not-a-hash"), "invalid_dataset_hash"),
        (_research_bundle(), _evidence(book_algorithm_count=615), "book_algorithm_coverage_incomplete"),
        (_research_bundle(), _evidence(book_algorithm_count="bad"), "book_algorithm_coverage_incomplete"),
        (_research_bundle(), _evidence(replay_parity_status="DISAGREEMENT"), "replay_parity_not_matched"),
    ],
)
def test_incomplete_or_weak_evidence_stays_shadow_only(bundle, evidence, reason):
    decision = assess_execution_readiness(bundle, evidence)
    assert decision.status == "SHADOW_ONLY"
    assert reason in decision.reasons
    with pytest.raises(ExecutionBundleRejected, match=reason):
        build_execution_bundle(bundle, evidence)


def test_valid_fixture_builds_minimal_execution_bundle_without_authority_inflation():
    research = _research_bundle()
    execution = build_execution_bundle(research, _evidence())

    assert execution.promotion_status == "EXECUTION_CANDIDATE"
    assert execution.authorized_symbols == ("EURUSD", "GBPUSD")
    assert execution.authorized_horizons_s == (3, 10)
    assert execution.target_definition == "captured_exit_replay"
    assert execution.expires_at == pytest.approx(4_100_000_000.0)
    assert execution.book_algorithm_count == len(ALGORITHM_MODULES)
    payload = execution.as_dict()
    assert "command" not in str(payload).lower()
    assert "book_consensus_probability" not in str(payload).lower()
    assert payload["models"]["EURUSD"]["BUY"]["micro_momentum"]["3"]["p_captured_win"] == pytest.approx(0.63)


def test_execution_candidate_requires_exact_selected_strategy_oos_evidence():
    decision = assess_execution_readiness(
        _research_bundle(), _evidence(selected_strategy_ids=None, selected_strategy_validation=None)
    )

    assert decision.status == "SHADOW_ONLY"
    assert "selected_strategy_evidence_missing" in decision.reasons


def test_execution_candidate_requires_complete_selected_cost_provenance():
    selected = dict(_evidence()["selected_strategy_validation"])
    selected.pop("cost_model_provenance")
    decision = assess_execution_readiness(
        _research_bundle(), _evidence(selected_strategy_validation=selected)
    )

    assert decision.status == "SHADOW_ONLY"
    assert "selected_strategy_cost_model_missing" in decision.reasons


def test_exact_selected_strategy_oos_must_stay_inside_authorized_scope():
    evidence = _evidence()
    selected = evidence["selected_strategy_validation"]
    selected["split_replay"]["validation"]["exact_strategies"] = {
        "bollinger_bands|XAUUSD|BUY|3|quote_microstructure_v1": {
            "signal_samples": 40,
            "wins": 25,
            "losses": 15,
            "rejection_adjusted_expectancy": 0.01,
            "profit_factor": 1.4,
        }
    }
    selected["split_replay"]["sealed"]["exact_strategies"] = {
        "bollinger_bands|XAUUSD|BUY|3|quote_microstructure_v1": {
            "signal_samples": 40,
            "wins": 25,
            "losses": 15,
            "rejection_adjusted_expectancy": 0.009,
            "profit_factor": 1.3,
        }
    }
    decision = assess_execution_readiness(_research_bundle(), evidence)

    assert decision.status == "SHADOW_ONLY"
    assert "selected_exact_strategy_oos_not_positive" in decision.reasons


def test_book_registry_hash_must_match_authoritative_algorithm_registry():
    decision = assess_execution_readiness(
        _research_bundle(), _evidence(book_registry_hash=SHA_A)
    )

    assert decision.status == "SHADOW_ONLY"
    assert "book_registry_hash_mismatch" in decision.reasons


def test_execution_candidate_requires_compiled_book_context():
    decision = assess_execution_readiness(_research_bundle(), _evidence(book_context={}))

    assert decision.status == "SHADOW_ONLY"
    assert "book_context_missing_or_invalid" in decision.reasons


def test_execution_candidate_requires_positive_validation_oos():
    decision = assess_execution_readiness(
        _research_bundle(),
        _evidence(validation_oos={
            "expectancy": 0.01,
            "profit_factor": 1.0,
            "n_trades": 40,
            "n_losses": 8,
        }),
    )

    assert decision.status == "SHADOW_ONLY"
    assert "validation_profit_factor_not_above_one" in decision.reasons


@pytest.mark.parametrize(
    ("context", "reason"),
    [
        ({"compiled_from_artifact": False}, "book_context_not_compiled"),
        ({"execution_authority": True}, "book_context_not_read_only"),
        ({"research_only": False}, "book_context_not_research_only"),
        ({"no_lookahead": False}, "book_context_not_causal"),
        ({"book_registry_hash": SHA_A}, "book_context_registry_mismatch"),
        ({"artifact_hash": SHA_B}, "book_context_artifact_not_from_book_node"),
        ({"algorithm_ids": [ALGORITHM_MODULES[0]]}, "book_context_algorithm_coverage_incomplete"),
    ],
)
def test_book_context_cannot_be_manually_overridden(context, reason):
    base = _evidence()["book_context"]
    merged = dict(base)
    merged.update(context)
    decision = assess_execution_readiness(_research_bundle(), _evidence(book_context=merged))

    assert decision.status == "SHADOW_ONLY"
    assert reason in decision.reasons


def test_execution_bundle_carries_complete_research_provenance_for_prediction():
    execution = build_execution_bundle(_research_bundle(), _evidence())

    provenance = execution.validation["research_provenance"]
    assert provenance["book_registry_hash"] == content_hash(tuple(ALGORITHM_MODULES))
    assert len(provenance["nodes"]) == len(REQUIRED_EXTERNAL_TOOLS) + 1
    assert {row["tool_id"] for row in provenance["nodes"]} == (
        set(REQUIRED_EXTERNAL_TOOLS) | {"aegis-book-algorithms"}
    )
    assert all(row["status"] == "SUCCESS" for row in provenance["nodes"])
    assert all(row["execution_authority"] is False for row in provenance["nodes"])


def test_external_status_declares_github_books_scope_and_no_authority():
    research = _research_bundle()
    promotion = assess_execution_readiness(research, _evidence())
    status = project_status(research, promotion=promotion, execution_bundle=None)

    assert status["prediction_scope"] == "GITHUB_TOOLS_AND_BOOK_ALGORITHMS_ONLY"
    assert status["execution_authority"] is False
    assert status["research_only"] is True
    assert status["order_intent"] is False
    assert status["council_influence"] is False
    assert status["research_factory_influence"] is False
    assert all(node["execution_authority"] is False for node in status["nodes"])


def test_external_status_attests_versioned_input_consumption():
    research = _research_bundle()
    first = replace(
        research.node_results[0],
        payload={
            "input_artifacts_verified": True,
            "input_consumed": True,
            "input_manifest_hash": SHA_A,
            "input_dataset_schema": "aegis.frozen_dataset_manifest.v1",
            "input_state_field_count": 6,
        },
    )
    research = replace(research, node_results=(first, *research.node_results[1:]))
    promotion = assess_execution_readiness(research, _evidence())

    status = project_status(research, promotion=promotion, execution_bundle=None)
    node = next(item for item in status["nodes"] if item["node_id"] == first.node_id)

    assert node["input_artifacts_verified"] is True
    assert node["input_consumed"] is True
    assert node["input_manifest_hash"] == SHA_A
    assert node["input_dataset_schema"] == "aegis.frozen_dataset_manifest.v1"
    assert node["input_state_field_count"] == 6


def test_registry_records_external_bundle_and_nodes_atomically_and_idempotently(tmp_path: Path):
    registry = ExperimentRegistry(tmp_path / "experiments.sqlite")
    research = _research_bundle()
    first = registry.record_external_workflow(
        research_bundle=research,
        dataset_hash=SHA_A,
        promotion_status="SHADOW_ONLY",
    )
    second = registry.record_external_workflow(
        research_bundle=research,
        dataset_hash=SHA_A,
        promotion_status="SHADOW_ONLY",
    )

    assert first == second
    stored = registry.get_external_workflow(first)
    assert stored is not None
    assert stored["bundle_hash"] == research.bundle_hash
    assert len(stored["nodes"]) == len(REQUIRED_EXTERNAL_TOOLS) + 1


def test_registry_rejects_run_identity_mutation(tmp_path: Path):
    registry = ExperimentRegistry(tmp_path / "experiments.sqlite")
    research = _research_bundle()
    registry.record_external_workflow(
        research_bundle=research,
        dataset_hash=SHA_A,
        promotion_status="SHADOW_ONLY",
    )
    changed = replace(research, run_id="run-fixture", complete=False, bundle_hash="")
    with pytest.raises(ValueError, match="immutable external workflow run"):
        registry.record_external_workflow(
            research_bundle=changed,
            dataset_hash=SHA_A,
            promotion_status="SHADOW_ONLY",
        )
