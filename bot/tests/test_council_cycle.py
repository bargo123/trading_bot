"""Council cycle + agent adapter tests (no real CLI calls)."""
from __future__ import annotations

import json
import subprocess
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai_council import agents as agent_cli  # noqa: E402
from ai_council import cases as case_store  # noqa: E402
from ai_council.cycle import run_council_cycle  # noqa: E402


class FakePopen:
    """Controlled process double: no test can invoke an external CLI."""

    def __init__(self, stdout_lines=(), stderr_lines=(), *, timeout=False, kill_required=False):
        self.stdout = iter(stdout_lines)
        self.stderr = iter(stderr_lines)
        self.returncode = 0
        self.timeout = timeout
        self.kill_required = kill_required
        self.terminated = False
        self.killed = False
        self.pid = 1234
        self.signals = []

    def wait(self, timeout=None):
        if self.timeout and (not self.terminated or self.kill_required and not self.killed):
            raise subprocess.TimeoutExpired(["fake"], timeout)
        return self.returncode

    def poll(self):
        return None if self.timeout and not self.terminated else self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = -15

    def kill(self):
        self.killed = True
        self.returncode = -9

    def send_signal(self, signal):
        self.signals.append(signal)


def _fake_agent_popen(monkeypatch, name, process):
    monkeypatch.setattr(agent_cli, "load_agents_config", lambda: {name: {"ask_cmd": ["ask"]}})
    monkeypatch.setattr(agent_cli, "_agent_argv", lambda agent: [f"fake-{agent}"])
    monkeypatch.setattr(agent_cli.subprocess, "Popen", lambda *args, **kwargs: process)
    monkeypatch.setattr(
        agent_cli,
        "_terminate_process_tree",
        lambda proc, force=False: proc.kill() if force else proc.terminate(),
    )


def test_ask_agent_streams_claude_lines_and_retains_parseable_output(monkeypatch):
    """Missing streamed lines would hide a live Claude response from the operator."""
    process = FakePopen(["first\n", '{"answer": 1}\n'])
    _fake_agent_popen(monkeypatch, "claude", process)
    seen = []

    result = agent_cli.ask_agent("claude", "hi", line_sink=seen.append)

    assert seen == ["[CLAUDE] first", '[CLAUDE] {"answer": 1}']
    assert result["output"] == 'first\n{"answer": 1}\n'
    assert result["parsed"] == {"answer": 1}


def test_ask_agent_streams_codex_lines_with_codex_prefix(monkeypatch):
    """A wrong prefix would make live Codex output indistinguishable in shared logs."""
    process = FakePopen(["review\n"])
    _fake_agent_popen(monkeypatch, "codex", process)
    seen = []

    result = agent_cli.ask_agent("codex", "hi", line_sink=seen.append)

    assert seen == ["[CODEX] review"]
    assert result["output"] == "review\n"


def test_ask_agent_streams_stderr_and_ignores_line_sink_errors(monkeypatch):
    """A failing display sink must not discard later process output."""
    process = FakePopen(["answer\n"], ["warning\n"])
    _fake_agent_popen(monkeypatch, "claude", process)
    seen = []

    def flaky_sink(line):
        seen.append(line)
        if len(seen) == 1:
            raise RuntimeError("display disconnected")

    result = agent_cli.ask_agent("claude", "hi", line_sink=flaky_sink)

    assert set(seen) == {"[CLAUDE] answer", "[CLAUDE] warning"}
    assert result["status"] == "AVAILABLE"
    assert result["stderr_tail"] == "warning\n"


def test_ask_agent_isolates_process_tree_without_shell(monkeypatch):
    """Missing process isolation would let descendants retain the output pipes."""
    process = FakePopen(["answer\n"])
    captured = {}
    monkeypatch.setattr(agent_cli, "load_agents_config", lambda: {"claude": {"ask_cmd": ["ask"]}})
    monkeypatch.setattr(agent_cli, "_agent_argv", lambda agent: [f"fake-{agent}"])

    def fake_popen(*args, **kwargs):
        captured.update(kwargs)
        return process

    monkeypatch.setattr(agent_cli.subprocess, "Popen", fake_popen)
    agent_cli.ask_agent("claude", "hi")

    assert captured.get("shell", False) is False
    if agent_cli.os.name == "nt":
        assert captured["creationflags"] == agent_cli.subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        assert captured["start_new_session"] is True


def test_windows_tree_cleanup_breaks_group_then_uses_taskkill_for_force(monkeypatch):
    """Using taskkill first would skip the required graceful process-group stop."""
    process = FakePopen()
    calls = []
    monkeypatch.setattr(agent_cli.os, "name", "nt")
    monkeypatch.setattr(agent_cli.signal, "CTRL_BREAK_EVENT", 123, raising=False)
    monkeypatch.setattr(agent_cli.subprocess, "run", lambda *args, **kwargs: calls.append(args))

    agent_cli._terminate_process_tree(process)
    agent_cli._terminate_process_tree(process, force=True)

    assert process.signals == [123]
    assert calls == [(["taskkill", "/PID", "1234", "/T", "/F"],)]


def test_ask_agent_rejects_stdout_larger_than_retained_buffer(monkeypatch):
    """A truncated answer must not be returned as if it were complete evidence."""
    oversized = "x" * 20_001 + "\n"
    process = FakePopen([oversized])
    _fake_agent_popen(monkeypatch, "claude", process)
    seen = []

    result = agent_cli.ask_agent("claude", "hi", line_sink=seen.append)

    assert seen == [f"[CLAUDE] {oversized.rstrip()}"]
    assert result["ok"] is False
    assert result["status"] == "ERROR"
    assert result["error"] == "OUTPUT_TOO_LARGE"
    assert result["output"] == ""
    assert "[OUTPUT TRUNCATED]" in result["stdout_tail"]


def test_ask_agent_timeout_escalates_terminate_to_kill(monkeypatch):
    """A process that ignores terminate must be force-killed before return."""
    process = FakePopen(timeout=True, kill_required=True)
    _fake_agent_popen(monkeypatch, "claude", process)
    result = agent_cli.ask_agent("claude", "hi", timeout_s=1)

    assert process.terminated is True
    assert process.killed is True
    assert result["status"] == "TIMEOUT"


class BlockingInheritedPipe:
    """Simulates a child that inherited the write end until the parent closes it."""

    def __init__(self):
        self.closed = threading.Event()

    def __iter__(self):
        yield "child output\n"
        self.closed.wait()

    def close(self):
        self.closed.set()


def test_ask_agent_timeout_returns_when_descendant_keeps_pipe_open(monkeypatch):
    """An inherited pipe must not make timeout handling wait forever."""
    process = FakePopen(timeout=True)
    process.stdout = BlockingInheritedPipe()
    process.stderr = BlockingInheritedPipe()
    _fake_agent_popen(monkeypatch, "claude", process)
    result = {}
    finished = threading.Event()

    def ask():
        result.update(agent_cli.ask_agent("claude", "hi", timeout_s=1))
        finished.set()

    worker = threading.Thread(target=ask, daemon=True)
    worker.start()
    worker.join(0.25)

    assert finished.is_set()
    assert result["status"] == "TIMEOUT"


def test_ask_agent_stream_timeout_terminates_popen_without_fabricating_output(monkeypatch):
    """An unresponsive process must report TIMEOUT rather than a successful answer."""
    process = FakePopen(timeout=True)
    _fake_agent_popen(monkeypatch, "claude", process)
    seen = []

    result = agent_cli.ask_agent("claude", "hi", timeout_s=1, line_sink=seen.append)

    assert process.terminated is True
    assert seen == []
    assert result["ok"] is False
    assert result["status"] == "TIMEOUT"


def test_dry_run_cycle_completes_full_round(monkeypatch, tmp_path):
    monkeypatch.setattr(case_store, "CASES_DIR", tmp_path)
    result = run_council_cycle("Should we stack Asia entries?", dry_run=True)
    assert result["n_proposals"] == 5
    assert result["n_critiques"] == 20  # 5 agents x 4 others
    assert result["n_revisions"] == 5
    assert result["decision"] == "defer_validation"
    case = case_store.load_case(result["id"])
    assert case["status"] == "decided"
    assert case["decision"]["evidence"]["n_proposals"] == 5


def test_dry_run_cycle_does_not_invoke_cli(monkeypatch, tmp_path):
    monkeypatch.setattr(case_store, "CASES_DIR", tmp_path)
    called = []
    monkeypatch.setattr(agent_cli, "ask_agent", lambda *a, **k: called.append(a) or {"ok": True})
    run_council_cycle("q", dry_run=True)
    assert called == []


def test_cycle_question_required(monkeypatch, tmp_path):
    monkeypatch.setattr(case_store, "CASES_DIR", tmp_path)
    import pytest

    with pytest.raises(ValueError):
        run_council_cycle("  ", dry_run=True)


def test_ask_agent_unavailable_cli_never_blocks():
    result = agent_cli.ask_agent("definitely-not-a-real-cli-xyz", "hi", timeout_s=10)
    assert result["ok"] is False
    assert result["status"] in {"UNAVAILABLE_CLI", "UNAVAILABLE_QUOTA"}


def test_parse_json_blocks():
    assert agent_cli._parse_json("no json here") is None
    parsed = agent_cli._parse_json('prefix {"proposal": "x"} suffix')
    assert parsed == {"proposal": "x"}


def test_quota_markers_detected():
    assert agent_cli._quota_blocked("429 Too Many Requests", "")
    assert agent_cli._quota_blocked("", "rate limit exceeded")
    assert not agent_cli._quota_blocked("all good", "no problem")


def test_agents_config_has_all_five():
    config = agent_cli.load_agents_config()
    for name in ("opencode", "claude", "gemini", "codex", "cursor"):
        assert name in config


def test_live_feed_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(case_store, "CASES_DIR", tmp_path)
    from ai_council import paths as council_paths
    from ai_council.cycle import dump_live

    monkeypatch.setattr(council_paths, "LIVE_JSONL", tmp_path / "live.jsonl")
    monkeypatch.setattr(council_paths, "LATEST_MD", tmp_path / "latest.md")
    result = run_council_cycle("q?", dry_run=True)
    case = case_store.load_case(result["id"])
    out = dump_live(result, case=case)
    assert out == tmp_path / "latest.md"
    lines = (tmp_path / "live.jsonl").read_text(encoding="utf-8").strip().splitlines()
    record = json.loads(lines[-1])
    assert record["id"] == result["id"]
    assert record["finished_utc"] is not None
    md = (tmp_path / "latest.md").read_text(encoding="utf-8")
    assert "defer_validation" in md


def test_real_mode_invokes_available_agents_and_persists_files(monkeypatch, tmp_path):
    """REAL mode: every AVAILABLE agent is invoked; outputs persisted; honest counts."""
    monkeypatch.setattr(case_store, "CASES_DIR", tmp_path)
    config = {name: {} for name in ("gemini", "claude")}
    monkeypatch.setattr(agent_cli, "load_agents_config", lambda: config)

    calls = []

    def fake_probe(name, **kwargs):
        return {"agent": name, "status": "AVAILABLE", "cli": f"fake-{name}"}

    def fake_ask(name, prompt, timeout_s=240, cwd=None):
        import time as _t

        calls.append(name)
        step = "critique" if "flaw" in prompt or "hostile" in prompt else "proposal"
        step = "revision" if "revised" in prompt else step
        return {
            "agent": name, "ok": True, "status": "AVAILABLE",
            "started_utc": "2026-08-20T00:00:00+00:00",
            "finished_utc": "2026-08-20T00:00:01+00:00",
            "duration_s": 1.0, "returncode": 0,
            "model": "fake-model-x",
            "output": f"REAL {step} by {name}",
            "parsed": None,
        }

    monkeypatch.setattr(agent_cli, "probe_agent", fake_probe)
    monkeypatch.setattr(agent_cli, "ask_agent", fake_ask)

    result = run_council_cycle("Real test question?", dry_run=False)
    assert result["mode"] == "REAL"
    assert result["n_proposals"] == 2
    assert result["n_critiques"] == 2  # each critiques the other
    assert result["n_revisions"] == 2
    assert set(calls) == {"gemini", "claude"}
    case = case_store.load_case(result["id"])
    assert case["mode"] == "REAL"
    # every step persisted to its own file
    for proposal in case["proposals"]:
        assert proposal["file"] and Path(proposal["file"]).exists()
    for target, critiques in case["critiques"].items():
        for critique in critiques:
            assert critique["file"] and Path(critique["file"]).exists()
    for revision in case["revisions"].values():
        assert revision["file"] and Path(revision["file"]).exists()
    # no DRY_RUN anywhere in the real round
    for entry in result["round_log"]:
        assert entry["status"] != "DRY_RUN"
    assert result["duration_s"] > 0
    # per-agent execution metadata persisted (provider/model/times/exit/mode)
    meta = case["proposals"][0]["meta"]
    assert meta["mode"] == "REAL"
    assert meta["returncode"] == 0
    assert meta["started_utc"] and meta["finished_utc"]
    assert meta["duration_s"] == 1.0


def test_real_mode_records_unavailable_agents_without_stopping(monkeypatch, tmp_path):
    """Quota/auth failures on some agents never block the rest or fabricate output."""
    monkeypatch.setattr(case_store, "CASES_DIR", tmp_path)
    config = {name: {} for name in ("gemini", "claude", "codex")}
    monkeypatch.setattr(agent_cli, "load_agents_config", lambda: config)
    probes = {
        "gemini": {"agent": "gemini", "status": "AVAILABLE", "cli": "g"},
        "claude": {"agent": "claude", "status": "UNAVAILABLE_QUOTA", "cli": "c"},
        "codex": {"agent": "codex", "status": "AUTH_REQUIRED", "cli": "x"},
    }
    monkeypatch.setattr(agent_cli, "probe_agent", lambda name, **k: probes[name])

    def fake_ask(name, prompt, timeout_s=240, cwd=None):
        return {"agent": name, "ok": True, "status": "AVAILABLE", "duration_s": 0.5,
                "output": f"proposal by {name}", "parsed": None}

    monkeypatch.setattr(agent_cli, "ask_agent", fake_ask)
    result = run_council_cycle("Quota test?", dry_run=False)
    assert result["mode"] == "REAL"
    assert result["n_proposals"] == 1  # only gemini proposed
    statuses_seen = {e["agent"]: e["status"] for e in result["round_log"] if e["step"] == "proposal"}
    assert statuses_seen == {"gemini": "AVAILABLE", "claude": "UNAVAILABLE_QUOTA",
                             "codex": "AUTH_REQUIRED"}


def test_real_mode_with_no_available_agents_decides_no_change(monkeypatch, tmp_path):
    monkeypatch.setattr(case_store, "CASES_DIR", tmp_path)
    config = {"gemini": {}, "claude": {}}
    monkeypatch.setattr(agent_cli, "load_agents_config", lambda: config)
    monkeypatch.setattr(
        agent_cli, "probe_agent",
        lambda name, **k: {"agent": name, "status": "UNAVAILABLE_CLI", "cli": None},
    )
    result = run_council_cycle("Nothing available?", dry_run=False)
    assert result["mode"] == "REAL"
    assert result["n_proposals"] == 0
    assert result["decision"] == "no_change"


def test_probe_agent_uses_cache_and_real_invocation(monkeypatch, tmp_path):
    """probe_agent performs a REAL minimal invocation and caches it (quota-safe)."""
    monkeypatch.setattr(agent_cli, "PROBE_CACHE_PATH", tmp_path / "probes.json")
    calls = []

    def fake_ask(name, prompt, timeout_s=90, cwd=None):
        calls.append((name, prompt))
        return {"agent": name, "ok": True, "status": "AVAILABLE",
                "cli_class": "native-exe", "provider": "X", "model": "m-1",
                "tool_version": None, "returncode": 0, "duration_s": 0.2,
                "error": None}

    monkeypatch.setattr(agent_cli, "ask_agent", fake_ask)
    first = agent_cli.probe_agent("opencode")
    second = agent_cli.probe_agent("opencode")
    assert len(calls) == 1  # second call served from cache
    assert first["status"] == "AVAILABLE"
    assert second["status"] == "AVAILABLE"
    assert "OK" in calls[0][1]
    forced = agent_cli.probe_agent("opencode", force=True)
    assert len(calls) == 2  # force bypasses cache
    assert forced["model"] == "m-1"


def test_disabled_agent_reports_disabled(monkeypatch, tmp_path):
    monkeypatch.setattr(agent_cli, "load_agents_config",
                        lambda: {"cursor": {"disabled": True}})
    result = agent_cli.probe_agent("cursor")
    assert result["status"] == "DISABLED"


def test_decide_reason_codes_without_falsifiable_candidate(monkeypatch, tmp_path):
    """A real round whose texts are not falsifiable records a specific reason."""
    monkeypatch.setattr(case_store, "CASES_DIR", tmp_path)
    config = {"opencode": {}}
    monkeypatch.setattr(agent_cli, "load_agents_config", lambda: config)
    monkeypatch.setattr(
        agent_cli, "probe_agent",
        lambda name, **k: {"agent": name, "status": "AVAILABLE", "cli": "o"},
    )
    monkeypatch.setattr(
        agent_cli, "ask_agent",
        lambda name, prompt, timeout_s=240, cwd=None: {
            "agent": name, "ok": True, "status": "AVAILABLE", "duration_s": 0.1,
            "output": "I think the system is fine and nothing needs attention.",
            "parsed": None,
        },
    )
    result = run_council_cycle("Vague question?", dry_run=False)
    decision = case_store.load_case(result["id"])["decision"]
    assert decision["decision"] == "no_change"
    assert decision["evidence"]["reason"] in {"NO_ROBUST_CANDIDATE", "NEEDS_MORE_DATA"}


def test_dry_run_is_explicit_and_tagged(monkeypatch, tmp_path):
    monkeypatch.setattr(case_store, "CASES_DIR", tmp_path)
    result = run_council_cycle("Explicit dry?", dry_run=True)
    assert result["mode"] == "DRY_RUN"
    case = case_store.load_case(result["id"])
    assert case["mode"] == "DRY_RUN"
    for entry in result["round_log"]:
        assert entry["mode"] == "DRY_RUN"
        assert entry["status"] == "DRY_RUN"
