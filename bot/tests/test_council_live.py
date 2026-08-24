"""Tests for budget-aware live Council asks."""
from __future__ import annotations

import json

import ai_council.live as live


def test_exhausted_codex_budget_blocks_adapter_and_survives_restart(
    monkeypatch, tmp_path
):
    """Removing the exhaustion check must permit a prohibited Codex call."""
    ledger_path = tmp_path / "agent_budgets.json"
    ledger = live.AgentBudgetLedger(ledger_path)

    def forbidden(*args, **kwargs):
        raise AssertionError("an exhausted Codex budget must not create a process")

    monkeypatch.setattr(live, "ask_agent", forbidden)

    result = live.ask_research_agent(
        "codex", "do not invoke", ledger=ledger, line_sink=None, cwd=tmp_path
    )

    assert result["status"] == "BUDGET_EXHAUSTED"
    assert result["ok"] is False
    assert live.AgentBudgetLedger(ledger_path).remaining("codex") == 0


def test_legacy_ledger_without_codex_entry_is_migrated_to_exhausted(
    monkeypatch, tmp_path
):
    """A missing Codex entry must not permit an unapproved process invocation."""
    ledger_path = tmp_path / "agent_budgets.json"
    ledger_path.write_text(
        json.dumps({"agents": {"claude": {"used": 0, "limit": 1}}}),
        encoding="utf-8",
    )
    ledger = live.AgentBudgetLedger(ledger_path)

    def forbidden(*args, **kwargs):
        raise AssertionError("a legacy ledger must not start Codex")

    monkeypatch.setattr(live, "ask_agent", forbidden)
    import ai_council.agents as agent_cli

    monkeypatch.setattr(agent_cli.subprocess, "Popen", forbidden)

    result = live.ask_research_agent(
        "codex", "do not invoke", ledger=ledger, line_sink=None, cwd=tmp_path
    )

    assert result["status"] == "BUDGET_EXHAUSTED"
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
