"""Generic agent adapters for the AI Council.

Each agent wraps a local CLI (opencode, claude, gemini, codex, cursor). The
adapter is intentionally thin: detect availability, run one non-interactive
ask with a timeout, extract JSON if present. A UNAVAILABLE agent is never
auto-paid and never blocks the cycle.
"""
from __future__ import annotations

import json
import os
import re
import signal
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

BOT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BOT_ROOT.parent
AGENTS_YAML = Path(__file__).resolve().parent / "agents.yaml"

QUOTA_MARKERS = ("429", "quota", "rate limit", "rate_limit", "unauthorized",
                 "authentication", "auth failed", "billing", "payment required",
                 "not found in workspace", "usage limit", "hit your usage",
                 "spend limit", "resource_exhausted", "too many requests")

AUTH_MARKERS = (
    "not authenticated", "authentication required", "must be logged in",
    "please log in", "please sign in", "missing authentication", "auth required",
    "401 unauthorized", "401 unauthorised", "sign in required", "expired token",
    "please run `gemini login`", "run `gemini login`", "login first",
    "you are not logged in", "not logged in",
)

JSON_BLOCK_RE = re.compile(r"\{[\s\S]*?\}")
OUTPUT_TRUNCATION_MARKER = "[OUTPUT TRUNCATED]\n"
MAX_STDOUT_CHARS = 20_000
MAX_STDERR_CHARS = 2_000
STDOUT_TAIL_CHARS = 2_000
STDERR_TAIL_CHARS = 500
PIPE_JOIN_TIMEOUT_S = 1
PROCESS_CLEANUP_TIMEOUT_S = 5

_MODEL_RES = (
    re.compile(r"\b(gemini-[0-9.]+(?:-[a-z0-9]+)*)\b", re.I),
    re.compile(r"\b(claude-[a-z0-9.-]+)\b", re.I),
    re.compile(r"\b(gpt-[0-9a-z.-]+)\b", re.I),
    re.compile(r"\b(o[0-9]+(?:-[a-z0-9]+)*)\b", re.I),
    re.compile(r"\b(deepseek-[a-z0-9.-]+)\b", re.I),
    re.compile(r"(?:^|[\s\[])(model|Model)\s*[:=]\s*([\w./-]+)"),
)

_VERSION_RE = re.compile(
    r"(Gemini CLI [\d.]+|Claude Code [\d.]+|Codex [\d.]+|Cursor [\w.\d]+|opencode [\d.]+)",
    re.I,
)


def _extract_model(text: str, agent: str = "") -> str | None:
    blob = str(text or "")
    for pattern in _MODEL_RES:
        match = pattern.search(blob)
        if match:
            groups = match.groups()
            return groups[-1] if groups else None
    return None


def _tool_version(text: str) -> str | None:
    match = _VERSION_RE.search(str(text or "")[:1500])
    return match.group(1) if match else None


DEFAULT_AGENTS = {
    "opencode": {
        "label": "OpenCode",
        "provider": "opencode",
        "cli": "opencode",
        "ask_cmd": ["run"],
        # Free-model fallbacks: if the default model is rate-limited, retry
        # the same prompt on these (in order). All are local/free - never paid.
        "models": [
            "opencode/x-preview-f-free",
            "opencode/nemotron-3.5-lightning-free",
            "opencode/hy3-free",
            "opencode/mimo-v2.5-free",
        ],
        "available_default": True,
        "hint": "opencode is the orchestrator shell; used for council rounds.",
    },
    "claude": {
        "label": "Claude Code",
        "provider": "Anthropic",
        "cli": "claude",
        "ask_cmd": ["-p"],
        "available_default": False,
        "hint": "Equiti Enterprise subscription; use sparingly, never every 20 min.",
    },
    "gemini": {
        "label": "Gemini CLI",
        "provider": "Google",
        "cli": "gemini",
        "ask_cmd": ["-p"],
        "available_default": False,
        "hint": "Free tier is 429-quota limited; retry later, never auto-paid.",
    },
    "codex": {
        "label": "Codex CLI",
        "provider": "OpenAI",
        "cli": "codex",
        "ask_cmd": ["exec", "--skip-git-repo-check"],
        "available_default": False,
        "hint": "Quota limited; rejoin automatically when quota resets.",
    },
    "cursor": {
        "label": "Cursor Agent",
        "provider": "cursor",
        "cli": "agent",
        "ask_cmd": ["--print", "--trust", "--mode", "ask"],
        "available_default": False,
        "hint": "cursor-agent CLI; quota limited; never auto-paid.",
    },
}

PROBE_CACHE_PATH = BOT_ROOT / "reports" / "council" / "agent_probes.json"
PROBE_PROMPT = "Reply with exactly: OK"
PROBE_TIMEOUT_S = 90
PROBE_TTL_S = 1800  # cache a REAL availability probe for 30 minutes

_STATUS_ORDER = (
    "AVAILABLE",
    "AUTHENTICATED",
    "CLI_FOUND",
    "UNAVAILABLE_QUOTA",
    "AUTH_REQUIRED",
    "TIMEOUT",
    "ERROR",
    "UNAVAILABLE_CLI",
    "DISABLED",
)


def load_agents_config() -> dict[str, Any]:
    try:
        import yaml
    except ImportError:
        return {k: dict(v) for k, v in DEFAULT_AGENTS.items()}
    if not AGENTS_YAML.exists():
        return {k: dict(v) for k, v in DEFAULT_AGENTS.items()}
    try:
        with AGENTS_YAML.open(encoding="utf-8") as fh:
            payload = yaml.safe_load(fh) or {}
    except (OSError, yaml.YAMLError):
        return {k: dict(v) for k, v in DEFAULT_AGENTS.items()}
    agents = payload.get("agents", {}) or {}
    return agents or {k: dict(v) for k, v in DEFAULT_AGENTS.items()}


def _resolve_cmd_shim(cmd_path: Path) -> list[str] | None:
    """Resolve an npm .CMD shim to the real executable/script it launches.

    npm's .CMD shims pass args through cmd.exe `%*`, which strips quotes and
    mangles multi-word prompts. Invoking the real binary directly preserves
    them. Returns argv (executable + optional script) or None if unresolved.
    """
    try:
        text = cmd_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    import re as _re

    shim_dir = cmd_path.parent
    for target in _re.findall(r'"([^"]+\.(?:exe|js))"\s*%', text):
        target = target.replace("\\", "/")
        relative = target.split("/", 1)[-1] if "/" in target else target
        candidate = shim_dir / relative
        if not candidate.exists():
            candidate = Path(target)
        if not candidate.exists():
            continue
        if candidate.suffix.lower() == ".js":
            return ["node", str(candidate)]
        if candidate.suffix.lower() == ".exe":
            return [str(candidate)]
    # node.exe-based shims that reference the real script after the node binary
    for match in _re.finditer(r'"([^"]*\\node(?:\.exe)?)"\s+"([^"]+\.js)"', text):
        script = Path(match.group(2))
        if script.exists():
            return ["node", str(script)]
    return None


def _agent_argv(name: str) -> list[str] | None:
    """Full argv to invoke an agent (bypasses npm .CMD arg-mangling)."""
    config = load_agents_config().get(name) or {}
    if name == "cursor":
        local = Path.home() / "AppData" / "Local" / "cursor-agent" / "agent.cmd"
        if local.exists():
            resolved = _resolve_cmd_shim(local)
            if resolved:
                return resolved
            return [str(local)]
    cli = shutil.which(name)
    if not cli:
        return None
    if cli.lower().endswith(".cmd") or cli.lower().endswith(".bat"):
        resolved = _resolve_cmd_shim(Path(cli))
        if resolved:
            return resolved
    return [cli]


def detect_status(name: str, config: dict[str, Any]) -> dict[str, Any]:
    """Detect CLI availability. --help output documents auth flags, so auth is
    only judged on a REAL invocation (ask_agent); this probe reports CLI presence."""
    argv = _agent_argv(name)
    if argv is None:
        return {"agent": name, "status": "UNAVAILABLE_CLI", "cli": None,
                "hint": config.get("hint", "")}
    cmd = argv + list(config.get("ask_cmd") or []) + ["--help"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=30)
    except (OSError, subprocess.SubprocessError):
        return {"agent": name, "status": "UNAVAILABLE_CLI", "cli": argv,
                "hint": config.get("hint", "")}
    return {"agent": name, "status": "AVAILABLE", "cli": argv[0] if argv else None}


def _parse_json(text: str) -> dict[str, Any] | None:
    for match in JSON_BLOCK_RE.finditer(text or ""):
        try:
            obj = json.loads(match.group(0))
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    return None


def _quota_blocked(stdout: str, stderr: str) -> bool:
    blob = f"{stdout or ''}\n{stderr or ''}".lower()
    return any(marker in blob for marker in QUOTA_MARKERS)


def _auth_required(stdout: str, stderr: str) -> bool:
    blob = f"{stdout or ''}\n{stderr or ''}".lower()
    return any(marker in blob for marker in AUTH_MARKERS)


class _BoundedBuffer:
    """Keep only a bounded tail while the caller still receives every line."""

    def __init__(self, limit: int):
        self.limit = limit
        self.text = ""
        self.truncated = False

    def append(self, chunk: str) -> None:
        combined = self.text + chunk
        if len(combined) > self.limit:
            self.text = combined[-self.limit:]
            self.truncated = True
        else:
            self.text = combined

    def tail(self, limit: int) -> str:
        if not self.truncated:
            return self.text[-limit:]
        available = max(0, limit - len(OUTPUT_TRUNCATION_MARKER))
        return OUTPUT_TRUNCATION_MARKER + self.text[-available:]


def _close_pipe(stream: Any) -> None:
    close = getattr(stream, "close", None)
    if close is not None:
        try:
            close()
        except OSError:
            pass


def _terminate_process_tree(proc: Any, *, force: bool = False) -> None:
    """Signal the isolated process group, falling back to the direct process."""
    try:
        if os.name == "nt" and getattr(proc, "pid", None):
            if not force:
                break_signal = getattr(signal, "CTRL_BREAK_EVENT", None)
                if break_signal is not None:
                    proc.send_signal(break_signal)
                    return
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=PROCESS_CLEANUP_TIMEOUT_S, check=False,
            )
            return
        if os.name != "nt" and getattr(proc, "pid", None):
            os.killpg(proc.pid, signal.SIGKILL if force else signal.SIGTERM)
            return
    except (OSError, subprocess.SubprocessError):
        pass
    if force:
        proc.kill()
    else:
        proc.terminate()


def ask_agent(
    name: str,
    prompt: str,
    *,
    timeout_s: int = 240,
    cwd: Path | None = None,
    line_sink: Any = None,
) -> dict[str, Any]:
    """Run one non-interactive ask against an agent. Never blocks the cycle.

    If the config lists alternative ``models``, a quota/timeout failure on the
    default model retries once per fallback model (free/local only - never a
    paid credential). ``line_sink`` receives every complete prefixed line.
    Returned stdout/stderr are bounded tails; a stdout overflow returns
    ``ERROR``/``OUTPUT_TOO_LARGE`` with empty ``output`` rather than partial
    parseable content. The model that actually answered is recorded.
    """
    import time

    config = load_agents_config().get(name) or {}
    argv = _agent_argv(name)
    started = time.time()
    started_utc = datetime.now(timezone.utc).isoformat()
    base: dict[str, Any] = {"agent": name, "ok": False, "started_utc": started_utc}
    if argv is None:
        base.update({"status": "UNAVAILABLE_CLI", "error": "CLI not found",
                     "finished_utc": started_utc, "duration_s": 0.0})
        return base
    variants: list[str | None] = [None] + [str(m) for m in (config.get("models") or [])]
    result: dict[str, Any] | None = None
    for attempt_index, variant in enumerate(variants):
        cmd = argv + list(config.get("ask_cmd") or [])
        if variant:
            cmd += ["--model", variant]
        cmd += [prompt]
        result = _run_ask(
            name, cmd, argv=argv, config=config, prompt=prompt,
            timeout_s=timeout_s, cwd=cwd, started=started,
            started_utc=started_utc, requested_model=variant,
            line_sink=line_sink,
        )
        if result.get("ok") or attempt_index == len(variants) - 1:
            break
        # Only quota/timeout failures justify burning a fallback attempt.
        if result.get("status") not in {"UNAVAILABLE_QUOTA", "TIMEOUT"}:
            break
    assert result is not None
    return result


def _run_ask(
    name: str,
    cmd: list[str],
    *,
    argv: list[str],
    config: Mapping[str, Any],
    prompt: str,
    timeout_s: int,
    cwd: Path | None,
    started: float,
    started_utc: str,
    requested_model: str | None,
    line_sink: Any,
) -> dict[str, Any]:
    import time
    from threading import Thread

    base: dict[str, Any] = {"agent": name, "ok": False, "started_utc": started_utc}
    out_buffer = _BoundedBuffer(MAX_STDOUT_CHARS)
    err_buffer = _BoundedBuffer(MAX_STDERR_CHARS)

    def drain(stream: Any, buffer: _BoundedBuffer) -> None:
        for line in stream:
            buffer.append(line)
            if line_sink is not None:
                try:
                    line_sink(f"[{name.upper()}] {line.rstrip(chr(10)).rstrip(chr(13))}")
                except Exception:
                    pass

    try:
        popen_kwargs: dict[str, Any] = {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": True,
            "encoding": "utf-8",
            "errors": "replace",
            "cwd": str(cwd or REPO_ROOT),
        }
        if os.name == "nt":
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            popen_kwargs["start_new_session"] = True
        proc = subprocess.Popen(cmd, **popen_kwargs)
    except OSError as exc:
        base.update({"status": "UNAVAILABLE_CLI", "error": str(exc),
                     "finished_utc": datetime.now(timezone.utc).isoformat(),
                     "duration_s": round(time.time() - started, 2)})
        return base

    out_thread = Thread(target=drain, args=(proc.stdout, out_buffer), daemon=True)
    err_thread = Thread(target=drain, args=(proc.stderr, err_buffer), daemon=True)
    out_thread.start()
    err_thread.start()
    try:
        proc.wait(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        _terminate_process_tree(proc)
        try:
            proc.wait(timeout=PROCESS_CLEANUP_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            _terminate_process_tree(proc, force=True)
            try:
                proc.wait(timeout=PROCESS_CLEANUP_TIMEOUT_S)
            except subprocess.TimeoutExpired:
                pass
        _close_pipe(proc.stdout)
        _close_pipe(proc.stderr)
        out_thread.join(PIPE_JOIN_TIMEOUT_S)
        err_thread.join(PIPE_JOIN_TIMEOUT_S)
        base.update({"status": "TIMEOUT",
                      "error": f"timed out after {timeout_s}s",
                      "finished_utc": datetime.now(timezone.utc).isoformat(),
                      "duration_s": round(time.time() - started, 2)})
        return base
    out_thread.join(PIPE_JOIN_TIMEOUT_S)
    err_thread.join(PIPE_JOIN_TIMEOUT_S)
    if out_thread.is_alive() or err_thread.is_alive():
        _close_pipe(proc.stdout)
        _close_pipe(proc.stderr)
        out_thread.join(PIPE_JOIN_TIMEOUT_S)
        err_thread.join(PIPE_JOIN_TIMEOUT_S)
        if out_thread.is_alive() or err_thread.is_alive():
            base.update({"status": "ERROR", "error": "OUTPUT_DRAIN_TIMEOUT",
                         "finished_utc": datetime.now(timezone.utc).isoformat(),
                         "duration_s": round(time.time() - started, 2)})
            return base
    finished = time.time()
    out = out_buffer.text
    err = err_buffer.text
    duration = round(finished - started, 2)
    finished_utc = datetime.now(timezone.utc).isoformat()
    base.update({
        "finished_utc": finished_utc,
        "duration_s": duration,
        "returncode": proc.returncode,
        "model": requested_model or _extract_model(f"{out}\n{err}", name),
        "cli_class": _cli_class(argv),
        "provider": config.get("provider"),
        "tool_version": _tool_version(f"{err}\n{out}"),
        "output": "" if out_buffer.truncated else out,
        "stdout_tail": out_buffer.tail(STDOUT_TAIL_CHARS),
        "stderr_tail": err_buffer.tail(STDERR_TAIL_CHARS),
    })
    if out_buffer.truncated:
        base["status"] = "ERROR"
        base["error"] = "OUTPUT_TOO_LARGE"
        return base
    if _auth_required(out, err):
        base["status"] = "AUTH_REQUIRED"
        base["error"] = "authentication required (login needed)"
        return base
    if _quota_blocked(out, err):
        base["status"] = "UNAVAILABLE_QUOTA"
        base["error"] = "quota/rate-limit blocked"
        return base
    if proc.returncode != 0:
        base["status"] = "ERROR"
        base["error"] = f"non-zero exit {proc.returncode}"
        return base
    base["ok"] = True
    base["status"] = "AVAILABLE"
    base["parsed"] = _parse_json(out) or _parse_json(err)
    return base


def _cli_class(argv: list[str]) -> str:
    """CLI command class: native exe, node script, or cmd shim."""
    if not argv:
        return "none"
    head = str(argv[0]).lower()
    if head.endswith(".exe"):
        return "native-exe"
    if head.endswith(".cmd") or head.endswith(".bat"):
        return "cmd-shim"
    if head == "node" or head.endswith("node.exe"):
        return "node-script"
    return "shell"


def _load_probe_cache() -> dict[str, Any]:
    try:
        return json.loads(PROBE_CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_probe_cache(cache: dict[str, Any]) -> None:
    try:
        PROBE_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        PROBE_CACHE_PATH.write_text(
            json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8"
        )
    except OSError:
        pass


def probe_agent(name: str, *, force: bool = False, timeout_s: int = PROBE_TIMEOUT_S) -> dict[str, Any]:
    """Minimal REAL model invocation to prove availability, cached.

    Status vocabulary:
      AVAILABLE        - real model call succeeded (also AUTHENTICATED)
      AUTHENTICATED    - alias for AVAILABLE (probe returned model output)
      CLI_FOUND        - executable exists but no real call made yet
      UNAVAILABLE_QUOTA- real call hit a quota/rate-limit message
      AUTH_REQUIRED    - real call reported a login/auth failure
      TIMEOUT          - real call exceeded the probe timeout
      ERROR            - real call failed for another reason
      UNAVAILABLE_CLI  - no executable resolved
      DISABLED         - disabled in config
    """
    config = load_agents_config().get(name) or {}
    if config.get("disabled"):
        return {"agent": name, "status": "DISABLED", "cli": None,
                "probed_utc": datetime.now(timezone.utc).isoformat()}
    cache = _load_probe_cache()
    cached = cache.get(name)
    if cached and not force:
        probed = cached.get("probed_utc")
        try:
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(probed)).total_seconds()
        except (TypeError, ValueError):
            age = float("inf")
        # Transient failures are retried sooner than hard states.
        ttl = PROBE_TTL_S if cached.get("status") not in {"TIMEOUT", "ERROR"} else PROBE_TTL_S // 3
        if age < ttl:
            return cached
    result = ask_agent(name, PROBE_PROMPT, timeout_s=timeout_s)
    entry = {
        "agent": name,
        "status": result.get("status"),
        "cli": result.get("cli_class"),
        "provider": config.get("provider"),
        "model": result.get("model"),
        "tool_version": result.get("tool_version"),
        "returncode": result.get("returncode"),
        "duration_s": result.get("duration_s"),
        "error": result.get("error"),
        "probed_utc": datetime.now(timezone.utc).isoformat(),
    }
    cache[name] = entry
    _save_probe_cache(cache)
    return entry


def all_statuses(*, probe: bool = False) -> dict[str, Any]:
    """Detect every configured agent.

    probe=True performs a cached REAL minimal model invocation (default false:
    returns CLI detection only, which never spends model quota).
    """
    config = load_agents_config()
    statuses = {}
    for name, cfg in config.items():
        if probe:
            statuses[name] = probe_agent(name)
            continue
        argv = _agent_argv(name)
        if cfg.get("disabled"):
            statuses[name] = {"agent": name, "status": "DISABLED", "cli": None,
                              "hint": cfg.get("hint", "")}
        elif argv is None:
            statuses[name] = {"agent": name, "status": "UNAVAILABLE_CLI", "cli": None,
                              "hint": cfg.get("hint", "")}
        else:
            statuses[name] = {"agent": name, "status": "CLI_FOUND",
                              "cli": argv[0], "hint": cfg.get("hint", "")}
    return {"agents": statuses, "detected_utc": datetime.now(timezone.utc).isoformat()}
