from __future__ import annotations

import pytest

from aegis.intel.prediction_fusion import fuse_prediction_evidence
from aegis.research.external_dag.catalog import REQUIRED_EXTERNAL_TOOLS
from aegis.research.external_dag.contracts import content_hash
from aegis.research.watcher_algorithms import ALGORITHM_MODULES


def _model(**overrides):
    model = {
        "p_captured_win": 0.63,
        "probability": 0.63,
        "threshold": 0.55,
        "decision": True,
        "expected_net_pnl": 0.02,
        "expected_net_pnl_lcb95": 0.005,
        "calibration_status": "CALIBRATED",
        "evidence_n": 80,
        "evidence_losses": 18,
        "execution_bundle": {"execution_bundle_hash": "a" * 64},
    }
    model.update(overrides)
    return model


def _book(**overrides):
    value = {
        "status": "AVAILABLE",
        "supporting_count": 8,
        "opposing_count": 2,
        "algorithm_count": 616,
        "execution_authority": False,
        "research_only": True,
        "no_lookahead": True,
    }
    value.update(overrides)
    return value


def test_missing_or_uncalibrated_model_abstains():
    result = fuse_prediction_evidence(None, book_context=_book())

    assert result["status"] == "ABSTAIN"
    assert result["decision"] is False
    assert result["probability"] is None
    assert result["reason"] == "validated_model_missing"


def test_books_are_secondary_and_do_not_change_model_probability():
    result = fuse_prediction_evidence(
        _model(),
        book_context=_book(),
        symbol="EURUSD",
        side="buy",
        mechanism="micro_momentum",
        horizon_s=3,
    )

    assert result["status"] == "AVAILABLE"
    assert result["decision"] is True
    assert result["probability"] == pytest.approx(0.63)
    assert result["book_support_score"] == pytest.approx(0.8)
    assert result["book_evidence_status"] == "SUPPORTING"
    assert result["book_is_secondary"] is True
    assert result["execution_authority"] is False


def test_sparse_book_support_gets_a_lower_secondary_rank_score():
    result = fuse_prediction_evidence(
        _model(),
        book_context=_book(
            evaluated_count=len(ALGORITHM_MODULES),
            applicable_count=10,
            supporting_count=8,
            opposing_count=2,
        ),
        side="BUY",
    )

    assert result["book_support_score"] == pytest.approx(0.8)
    assert 0.5 < result["book_rank_score"] < result["book_support_score"]


def test_conflicting_books_cannot_override_model_abstention():
    result = fuse_prediction_evidence(
        _model(decision=False),
        book_context=_book(supporting_count=100, opposing_count=0),
    )

    assert result["status"] == "ABSTAIN"
    assert result["decision"] is False
    assert result["probability"] == pytest.approx(0.63)
    assert result["book_support_score"] == pytest.approx(1.0)


def test_invalid_book_contract_is_ignored_without_granting_authority():
    result = fuse_prediction_evidence(
        _model(),
        book_context=_book(execution_authority=True),
    )

    assert result["status"] == "AVAILABLE"
    assert result["book_support_score"] is None
    assert result["book_evidence_status"] == "UNAVAILABLE"
    assert result["execution_authority"] is False


def test_malformed_book_counts_fail_closed_without_crashing():
    result = fuse_prediction_evidence(
        _model(),
        book_context=_book(
            algorithm_count="bad",
            supporting_count="bad",
            opposing_count="bad",
            directional_support_ratio=0.8,
        ),
    )

    assert result["book_support_score"] == pytest.approx(0.8)
    assert result["book_evidence"]["algorithm_count"] == 0


def test_external_research_provenance_is_attached_as_validation_context():
    result = fuse_prediction_evidence(
        _model(),
        research_provenance={
            "nodes": [
                {"tool_id": "qlib", "status": "SUCCESS", "execution_authority": False},
                {"tool_id": "ordersim", "status": "SUCCESS", "execution_authority": False},
            ]
        },
    )

    assert result["external_research_status"] == "INCOMPLETE"
    assert result["external_research_node_count"] == 2
    assert result["probability"] == pytest.approx(0.63)


def test_partial_github_provenance_cannot_claim_complete_validation():
    result = fuse_prediction_evidence(
        _model(),
        research_provenance={
            "nodes": [
                {"tool_id": "qlib", "status": "SUCCESS", "execution_authority": False},
                {"tool_id": "ordersim", "status": "SUCCESS", "execution_authority": False},
            ]
        },
    )

    assert result["external_research_status"] == "INCOMPLETE"


def test_complete_github_and_book_provenance_is_attached_as_complete():
    nodes = [
        {
            "tool_id": tool_id,
            "status": "SUCCESS",
            "execution_authority": False,
        }
        for tool_id in sorted(REQUIRED_EXTERNAL_TOOLS | {"aegis-book-algorithms"})
    ]
    result = fuse_prediction_evidence(
        _model(),
        research_provenance={
            "book_registry_hash": content_hash(tuple(ALGORITHM_MODULES)),
            "nodes": nodes,
        },
    )

    assert result["external_research_status"] == "COMPLETE"
    assert result["external_research_node_count"] == len(nodes)


def test_prediction_scope_excludes_council_and_research_factory():
    result = fuse_prediction_evidence(
        _model(),
        research_provenance={
            "book_registry_hash": content_hash(tuple(ALGORITHM_MODULES)),
            "nodes": [
                {"tool_id": "council", "status": "SUCCESS", "execution_authority": False},
                {"tool_id": "research-factory", "status": "SUCCESS", "execution_authority": False},
            ],
        },
    )

    assert result["prediction_scope"] == "GITHUB_TOOLS_AND_BOOK_ALGORITHMS_ONLY"
    assert result["council_influence"] is False
    assert result["research_factory_influence"] is False
    assert result["external_research_status"] == "INCOMPLETE"

@pytest.mark.parametrize(
    "field",
    ("council_influence", "research_factory_influence"),
)
def test_model_declared_council_or_factory_influence_abstains(field):
    result = fuse_prediction_evidence(_model(**{field: True}), book_context=_book())

    assert result["status"] == "ABSTAIN"
    assert result["decision"] is False
    assert result["reason"] == "model_scope_excluded"

def test_model_declared_non_github_scope_abstains():
    result = fuse_prediction_evidence(
        _model(prediction_scope="COUNCIL_AND_RESEARCH_FACTORY"),
        book_context=_book(),
    )

    assert result["status"] == "ABSTAIN"
    assert result["decision"] is False
    assert result["reason"] == "model_scope_excluded"

def test_nested_execution_bundle_scope_conflict_abstains():
    result = fuse_prediction_evidence(
        _model(execution_bundle={"prediction_scope": "RESEARCH_FACTORY"}),
        book_context=_book(),
    )

    assert result["status"] == "ABSTAIN"
    assert result["decision"] is False
    assert result["reason"] == "model_scope_excluded"


def test_absolute_book_views_are_oriented_to_candidate_side():
    result = fuse_prediction_evidence(
        _model(),
        book_context=_book(absolute_views=True),
        side="sell",
    )

    assert result["book_support_score"] == pytest.approx(0.2)
    assert result["book_evidence_status"] == "OPPOSING"


def test_compiled_book_algorithm_lists_drive_side_specific_secondary_score():
    context = {
        "status": "AVAILABLE",
        "algorithm_count": 4,
        "algorithm_ids": ["a", "b", "c", "d"],
        "supporting_algorithms": ["a", "b"],
        "opposing_algorithms": ["c"],
        "missing_data_algorithms": ["d"],
        "absolute_views": True,
        "execution_authority": False,
        "research_only": True,
        "no_lookahead": True,
    }

    buy = fuse_prediction_evidence(_model(), book_context=context, side="BUY")
    sell = fuse_prediction_evidence(_model(), book_context=context, side="SELL")

    assert buy["book_support_score"] == pytest.approx(2 / 3)
    assert sell["book_support_score"] == pytest.approx(1 / 3)
