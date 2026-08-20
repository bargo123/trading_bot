"""Council case system tests: lifecycle, independence, data-decides."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ai_council.cases as cases  # noqa: E402


def test_new_case_creates_record(tmp_path, monkeypatch):
    monkeypatch.setattr(cases, "CASES_DIR", tmp_path)
    case = cases.new_case("Should FIRE ever be a pending order?")
    assert case["phase"] == "proposal"
    assert case["status"] == "open"
    assert (tmp_path / f"case_{case['id']}" / "case.json").exists()
    loaded = cases.load_case(case["id"])
    assert loaded["question"] == case["question"]


def test_new_case_rejects_bad_id(tmp_path, monkeypatch):
    monkeypatch.setattr(cases, "CASES_DIR", tmp_path)
    import pytest

    with pytest.raises(ValueError):
        cases.new_case("q", case_id="UPPER BAD!")


def test_proposals_are_independent_and_unique(tmp_path, monkeypatch):
    monkeypatch.setattr(cases, "CASES_DIR", tmp_path)
    case = cases.new_case("Which exit rule is best?")
    cases.add_proposal(case, agent="gemini", text="proposal A")
    cases.add_proposal(case, agent="claude", text="proposal B")
    import pytest

    with pytest.raises(ValueError):
        cases.add_proposal(case, agent="gemini", text="duplicate")


def test_critique_is_adversarial_only(tmp_path, monkeypatch):
    monkeypatch.setattr(cases, "CASES_DIR", tmp_path)
    case = cases.new_case("Which exit rule is best?")
    cases.add_proposal(case, agent="gemini", text="A")
    cases.add_proposal(case, agent="claude", text="B")
    cases.move_phase(case, "critique")
    import pytest

    with pytest.raises(ValueError):
        cases.add_critique(case, agent="gemini", target="gemini", text="self")
    cases.add_critique(case, agent="gemini", target="claude", text="flaw: X")
    with pytest.raises(ValueError):
        cases.add_critique(case, agent="codex", target="gemini", text="not a proposer")


def test_phase_transitions_and_data_decides(tmp_path, monkeypatch):
    monkeypatch.setattr(cases, "CASES_DIR", tmp_path)
    case = cases.new_case("Which exit rule is best?")
    cases.add_proposal(case, agent="gemini", text="A")
    cases.add_proposal(case, agent="claude", text="B")
    cases.move_phase(case, "critique")
    cases.add_critique(case, agent="gemini", target="claude", text="flaw")
    cases.move_phase(case, "revision")
    cases.add_revision(case, agent="gemini", text="revised A")
    cases.move_phase(case, "decision")
    cases.decide(
        case,
        decision="accept",
        rationale="measured expectancy gain on validation",
        evidence={"oos_expectancy": 0.85, "n": 120},
    )
    loaded = cases.load_case(case["id"])
    assert loaded["status"] == "decided"
    assert loaded["decision"]["decision"] == "accept"
    assert loaded["decision"]["evidence"]["oos_expectancy"] == 0.85


def test_data_decides_requires_valid_decision(tmp_path, monkeypatch):
    monkeypatch.setattr(cases, "CASES_DIR", tmp_path)
    case = cases.new_case("q")
    cases.add_proposal(case, agent="gemini", text="A")
    cases.move_phase(case, "critique")
    cases.move_phase(case, "revision")
    cases.move_phase(case, "decision")
    import pytest

    with pytest.raises(ValueError):
        cases.decide(case, decision="vibes", rationale="no")


def test_cannot_skip_ahead_of_phase(tmp_path, monkeypatch):
    monkeypatch.setattr(cases, "CASES_DIR", tmp_path)
    case = cases.new_case("q")
    import pytest

    with pytest.raises(ValueError):
        cases.move_phase(case, "decision")


def test_list_and_summarize(tmp_path, monkeypatch):
    monkeypatch.setattr(cases, "CASES_DIR", tmp_path)
    a = cases.new_case("question one")
    b = cases.new_case("question two")
    all_cases = cases.list_cases()
    assert len(all_cases) == 2
    summary = cases.summarize(a)
    assert summary["id"] == a["id"]
    assert summary["n_proposals"] == 0
    assert summary["decision"] is None