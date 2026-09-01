"""Tests for budget-aware live Council asks."""
from __future__ import annotations

import json

import ai_council.live as live


def test_fresh_codex_budget_allows_one_adapter_call_then_locks(monkeypatch, tmp_path):
    """A new research session has exactly one Codex review available."""
    ledger_path = tmp_path / "agent_budgets.json"
    ledger = live.AgentBudgetLedger(ledger_path)
    assert ledger.usage("codex") == (0, 1)

    calls = []

    monkeypatch.setattr(
        live,
        "ask_agent",
        lambda *args, **kwargs: calls.append((args, kwargs)) or {"agent": "codex", "ok": True},
    )

    result = live.ask_research_agent(
        "codex", "review", ledger=ledger, line_sink=None, cwd=tmp_path
    )
    assert result["ok"] is True
    assert len(calls) == 1
    assert ledger.usage("codex") == (1, 1)

    locked = live.ask_research_agent(
        "codex", "second review", ledger=ledger, line_sink=None, cwd=tmp_path
    )
    assert locked["status"] == "BUDGET_EXHAUSTED"
    assert len(calls) == 1
    assert live.AgentBudgetLedger(ledger_path).usage("codex") == (1, 1)


def test_ledger_without_codex_entry_is_migrated_to_fresh_session_budget(
    monkeypatch, tmp_path
):
    """A missing Codex entry represents an unused one-call research session."""
    ledger_path = tmp_path / "agent_budgets.json"
    ledger_path.write_text(
        json.dumps({"agents": {"claude": {"used": 0, "limit": 1}}}),
        encoding="utf-8",
    )
    ledger = live.AgentBudgetLedger(ledger_path)

    calls = []

    monkeypatch.setattr(
        live,
        "ask_agent",
        lambda *args, **kwargs: calls.append((args, kwargs)) or {"agent": "codex", "ok": True},
    )

    result = live.ask_research_agent(
        "codex", "review", ledger=ledger, line_sink=None, cwd=tmp_path
    )

    assert result["ok"] is True
    assert len(calls) == 1
    assert json.loads(ledger_path.read_text(encoding="utf-8"))["agents"]["codex"] == {
        "used": 1,
        "limit": 1,
    }


def test_failed_ask_consumes_limited_budget_before_adapter_failure(monkeypatch, tmp_path):
    """Moving consumption after an ask would allow a failed paid ask to repeat."""
    ledger_path = tmp_path / "agent_budgets.json"
    ledger_path.write_text(
        json.dumps({"agents": {"claude": {"used": 0, "limit": 1}}}),
        encoding="utf-8",
    )
    ledger = live.AgentBudgetLedger(ledger_path)

    monkeypatch.setattr(
        live,
        "ask_agent",
        lambda *args, **kwargs: {
            "agent": "claude",
            "ok": False,
            "status": "UNAVAILABLE_CLI",
            "error": "CLI not found",
        },
    )

    result = live.ask_research_agent(
        "claude", "research", ledger=ledger, line_sink=None, cwd=tmp_path
    )

    assert result["status"] == "UNAVAILABLE_CLI"
    assert live.AgentBudgetLedger(ledger_path).remaining("claude") == 0
    assert not ledger_path.with_suffix(".json.tmp").exists()
