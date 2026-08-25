from __future__ import annotations

from types import SimpleNamespace

from ai_council import hermes
from ai_council import agents as agent_cli
from scripts import research_fast_watcher


def test_build_command_uses_verified_hermes_oneshot_interface(tmp_path):
    command = hermes.build_command(
        tmp_path / "hermes.exe",
        "research question",
        model="hy3-free",
        usage_file=tmp_path / "usage.json",
    )

    assert command[:4] == [
        str(tmp_path / "hermes.exe"),
        "--safe-mode",
        "--reasoning",
        "none",
    ]
    assert "--model" in command
    assert "hy3-free" in command
    assert "--usage-file" in command
    assert command[-2:] == ["-z", command[-1]]
    assert "research-only" in command[-1].lower()


def test_ask_uses_only_free_model_sequence_and_parses_json(monkeypatch, tmp_path):
    calls = []
    responses = iter(
        [
            SimpleNamespace(
                returncode=1,
                stdout="",
                stderr="429 temporarily unavailable",
            ),
            SimpleNamespace(
                returncode=0,
                stdout='{"vote":"SUPPORT_TESTING"}',
                stderr="",
            ),
        ]
    )
    monkeypatch.setattr(hermes, "find_executable", lambda: tmp_path / "hermes.exe")

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return next(responses)

    monkeypatch.setattr(hermes.subprocess, "run", fake_run)

    result = hermes.ask(
        "vote on research",
        models=["x-preview-f-free", "hy3-free"],
        timeout_s=7,
    )

    assert result["ok"] is True
    assert result["status"] == "AVAILABLE"
    assert result["model"] == "hy3-free"
    assert result["parsed"] == {"vote": "SUPPORT_TESTING"}
    assert [command[command.index("--model") + 1] for command, _ in calls] == [
        "x-preview-f-free",
        "hy3-free",
    ]
    assert all(kwargs["timeout"] == 7 and kwargs["shell"] is False for _, kwargs in calls)


def test_ask_fails_closed_when_hermes_is_not_installed(monkeypatch):
    monkeypatch.setattr(hermes, "find_executable", lambda: None)

    result = hermes.ask("research only")

    assert result["ok"] is False
    assert result["status"] == "UNAVAILABLE_CLI"


def test_council_agent_registry_routes_hermes_to_the_single_adapter(monkeypatch):
    calls = []
    monkeypatch.setattr(
        agent_cli,
        "load_agents_config",
        lambda: {"hermes": {"models": ["hy3-free"]}},
    )
    monkeypatch.setattr(
        hermes,
        "ask",
        lambda prompt, **kwargs: calls.append((prompt, kwargs)) or {
            "agent": "hermes",
            "status": "AVAILABLE",
            "ok": True,
        },
    )

    result = agent_cli.ask_agent("hermes", "research question", timeout_s=11)

    assert result["status"] == "AVAILABLE"
    assert calls == [("research question", {"models": ["hy3-free"], "timeout_s": 11,
                                              "cwd": None, "line_sink": None})]


def test_watcher_uses_hermes_free_team_for_normal_rounds(monkeypatch):
    monkeypatch.delenv("AEGIS_COUNCIL_AGENTS", raising=False)

    agents = research_fast_watcher._council_agents_for_trigger("new_closed_trades")

    assert agents[:2] == ["hermes", "opencode"]
    assert "claude" not in agents


def test_watcher_adds_claude_only_for_senior_review_trigger(monkeypatch):
    monkeypatch.delenv("AEGIS_COUNCIL_AGENTS", raising=False)

    agents = research_fast_watcher._council_agents_for_trigger("strategy_degradation")

    assert "hermes" in agents
    assert agents[-1] == "claude"
