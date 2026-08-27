from __future__ import annotations

import json

from run_fast_edge_shadow_loop import _extract_experiment_handoff, _write_experiment_handoff


def test_extract_experiment_handoff_keeps_only_research_proposals():
    review = {
        "schema": "fast_edge_council_review.v1",
        "generated_at": "2026-08-26T00:00:00Z",
        "source_report": "generation/fast_edge_leaderboard.json",
        "execution_authority": "NONE",
        "hermes": {
            "status": "AVAILABLE",
            "next_experiments": [{"id": "N1", "description": "gate", "noise": "x" * 10000}],
        },
        "claude": {"status": "AVAILABLE", "parsed": {"next_experiments": [{"id": "C1"}]}},
    }

    handoff = _extract_experiment_handoff(review)

    assert handoff["execution_authority"] == "NONE"
    assert handoff["source_schema"] == "fast_edge_council_review.v1"
    assert handoff["next_experiments"] == [{"id": "N1", "description": "gate"}]
    assert handoff["claude_next_experiments"] == [{"id": "C1"}]
    assert "noise" not in json.dumps(handoff)


def test_write_experiment_handoff_is_atomic_research_artifact(tmp_path):
    destination = tmp_path / "fast_edge_experiment_handoff.json"
    handoff = {"execution_authority": "NONE", "next_experiments": [{"id": "N1"}]}

    written = _write_experiment_handoff(destination, handoff)

    assert written == destination
    assert json.loads(destination.read_text(encoding="utf-8")) == handoff
    assert not list(tmp_path.glob("*.tmp"))
