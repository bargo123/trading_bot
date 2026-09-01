from __future__ import annotations

import pytest

from aegis.research.book_reliability import build_book_reliability_artifact
from scripts.build_book_reliability_artifact import build_artifact


def _replay_report() -> dict[str, object]:
    return {
        "schema": "book_strategy_historical_replay.v1",
        "book_record_count": 3,
        "evaluator_group_count": 2,
        "no_lookahead": True,
        "research_only": True,
        "execution_authority": False,
        "evaluator_groups": [
            {
                "group_id": "group-positive",
                "implementation_status": "WATCHER_EXACT_RULE",
                "representative_record_id": "exact-1",
                "record_ids": ["exact-1", "exact-duplicate"],
                "duplicate_count": 2,
            },
            {
                "group_id": "group-negative",
                "implementation_status": "WATCHER_FAMILY_PERSPECTIVE",
                "representative_record_id": "family-1",
                "record_ids": ["family-1"],
                "duplicate_count": 1,
            },
        ],
        "strategies": {
            "exact-1": {
                "signal_samples": 90,
                "wins": 49,
                "losses": 19,
                "draws": 22,
                "net_pnl": 0.00055,
                "expectancy": 0.0000061111,
                "profit_factor": 2.8,
                "p95_loss": -0.00002,
            },
            "exact-duplicate": {
                "signal_samples": 90,
                "wins": 49,
                "losses": 19,
                "draws": 22,
                "net_pnl": 0.00055,
                "expectancy": 0.0000061111,
                "profit_factor": 2.8,
                "p95_loss": -0.00002,
            },
            "family-1": {
                "signal_samples": 90,
                "wins": 40,
                "losses": 50,
                "draws": 0,
                "net_pnl": -0.0002,
                "expectancy": -0.0000022222,
                "profit_factor": 0.8,
                "p95_loss": -0.00003,
            },
        },
    }


def test_reliability_deduplicates_records_and_never_activates_without_split_evidence():
    artifact = build_book_reliability_artifact(_replay_report(), min_signal_samples=50, min_losses=5)

    assert artifact["schema"] == "aegis.book_algorithm_reliability.v1"
    assert artifact["book_record_count"] == 3
    assert artifact["evaluator_group_count"] == 2
    assert artifact["deduplicated_group_count"] == 2
    assert artifact["candidate_count"] == 1
    assert artifact["status"] == "SHADOW_ONLY"
    assert artifact["runtime_activation"] is False
    assert artifact["execution_authority"] is False
    assert artifact["groups"][0]["duplicate_count"] in {1, 2}
    positive = next(item for item in artifact["groups"] if item["group_id"] == "group-positive")
    assert positive["record_ids"] == ["exact-1", "exact-duplicate"]
    assert positive["candidate_status"] == "REQUIRES_INDEPENDENT_SPLITS"


def test_reliability_rejects_non_research_replay():
    report = _replay_report()
    report["execution_authority"] = True

    with pytest.raises(ValueError, match="replay report must be research-only"):
        build_book_reliability_artifact(report)


def test_reliability_rejects_pre_enriched_row_replay():
    report = _replay_report()
    report["pre_enriched_rows"] = True

    with pytest.raises(ValueError, match="pre-enriched row replay is not eligible"):
        build_book_reliability_artifact(report)


def test_reliability_requires_positive_independent_validation_and_sealed_splits():
    report = _replay_report()
    split_template = {
        "no_lookahead": True,
        "research_only": True,
        "execution_authority": False,
        "evaluator_group_count": 2,
    }
    positive = {
        "group_id": "group-positive",
        "signal_samples": 60,
        "wins": 35,
        "losses": 10,
        "expectancy": 0.00001,
        "profit_factor": 2.0,
        "p95_loss": -0.00002,
    }
    negative = {
        "group_id": "group-negative",
        "signal_samples": 60,
        "wins": 20,
        "losses": 30,
        "expectancy": -0.00001,
        "profit_factor": 0.7,
        "p95_loss": -0.00003,
    }
    report["split_replay"] = {
        "train": {**split_template, "groups": [positive, negative]},
        "validation": {**split_template, "groups": [positive, negative]},
        "sealed": {
            **split_template,
            "groups": [{**positive, "expectancy": -0.00001, "profit_factor": 0.7}, negative],
        },
    }

    artifact = build_book_reliability_artifact(report, min_signal_samples=50, min_losses=5)

    assert artifact["independent_split_status"] == "REJECTED"
    assert artifact["independent_candidate_count"] == 0
    positive_group = next(item for item in artifact["groups"] if item["group_id"] == "group-positive")
    assert positive_group["candidate_status"] == "REQUIRES_INDEPENDENT_SPLITS"
    assert positive_group["independent_split_status"] == "REJECTED"
    assert artifact["runtime_activation"] is False


def test_reliability_requires_an_expectancy_confidence_bound_for_independent_splits():
    report = _replay_report()
    split_template = {
        "no_lookahead": True,
        "research_only": True,
        "execution_authority": False,
        "evaluator_group_count": 2,
    }
    positive = {
        "group_id": "group-positive",
        "signal_samples": 60,
        "wins": 35,
        "losses": 10,
        "expectancy": 0.00001,
        "profit_factor": 2.0,
        "p95_loss": -0.00002,
    }
    negative = {
        "group_id": "group-negative",
        "signal_samples": 60,
        "wins": 20,
        "losses": 30,
        "expectancy": -0.00001,
        "profit_factor": 0.7,
        "p95_loss": -0.00003,
    }
    report["split_replay"] = {
        name: {**split_template, "groups": [positive, negative]}
        for name in ("train", "validation", "sealed")
    }

    artifact = build_book_reliability_artifact(report)

    assert artifact["independent_split_status"] == "REJECTED"
    assert artifact["independent_candidate_count"] == 0


def test_artifact_builder_writes_a_reproducible_shadow_file(tmp_path):
    replay_path = tmp_path / "replay.json"
    output_path = tmp_path / "reliability.json"
    replay_path.write_text(__import__("json").dumps(_replay_report()), encoding="utf-8")

    result = build_artifact(replay_path, output_path, min_signal_samples=50, min_losses=5)

    assert result["output"] == str(output_path)
    assert result["status"] == "SHADOW_ONLY"
    assert result["candidate_count"] == 1
    written = __import__("json").loads(output_path.read_text(encoding="utf-8"))
    assert written["runtime_activation"] is False
