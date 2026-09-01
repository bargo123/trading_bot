"""Single, research-only adapter for the locally installed Hermes CLI.

Hermes is deliberately kept outside the Firehose tick-to-order path.  This
adapter only runs bounded, non-interactive text requests for Council research;
it never imports MT5, executes repository commands, or authorizes trades.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FREE_MODELS = (
    "x-preview-f-free",
    "hy3-free",
    "laguna-s-2.1-free",
    "nemotron-3-ultra-free",
    "nemotron-3.5-lightning-free",
    "muse-spark-1.2-contributor-free",
)
_QUOTA_MARKERS = ("429", "capacity", "rate limit", "quota", "temporarily unavailable")
_JSON_BLOCK = re.compile(r"\{[\s\S]*\}")


def find_executable() -> Path | None:
    """Find Hermes without assuming it is on PATH."""
    configured = os.environ.get("AEGIS_HERMES_CLI", "").strip()
    candidates = [Path(configured)] if configured else []
    on_path = shutil.which("hermes")
    if on_path:
        candidates.append(Path(on_path))
    candidates.extend(
        (
            Path.home() / "AppData" / "Local" / "hermes" / "bin" / "hermes.exe",
            Path.home() / ".local" / "bin" / "hermes",
        )
    )
    for candidate in candidates:
        if candidate and candidate.is_file():
            return candidate
    return None


def _research_prompt(prompt: str) -> str:
    return (
        "RESEARCH-ONLY COUNCIL REQUEST. Do not execute commands, edit files, "
        "access MT5, place orders, change configuration, or authorize trades. "
        "Return analysis or the requested structured response only.\n\n"
        f"{prompt}"
    )


def build_command(
    executable: Path,
    prompt: str,
    *,
    model: str,
    provider: str | None = None,
    usage_file: Path | None = None,
) -> list[str]:
    """Build Hermes' verified one-shot command without shell interpolation."""
    command = [
        str(executable),
        "--safe-mode",
        "--reasoning",
        "none",
    ]
    if provider:
        command.extend(("--provider", provider))
    if model:
        command.extend(("--model", model))
    if usage_file:
        command.extend(("--usage-file", str(usage_file)))
    command.extend(("-z", _research_prompt(prompt)))
    return command


def _parse_json(text: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(text.strip())
        return parsed if isinstance(parsed, dict) else None
    except (TypeError, json.JSONDecodeError):
        pass
    match = _JSON_BLOCK.search(text or "")
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _is_quota_error(stdout: str, stderr: str) -> bool:
    text = f"{stdout}\n{stderr}".lower()
    return any(marker in text for marker in _QUOTA_MARKERS)


def _base_result(*, status: str, started: float, **extra: Any) -> dict[str, Any]:
    return {
        "agent": "hermes",
        "adapter": "ai_council.hermes",
        "ok": status == "AVAILABLE",
        "status": status,
        "duration_s": round(time.monotonic() - started, 2),
        "streaming": False,
        "structured_output": "json-in-text",
        **extra,
    }


def ask(
    prompt: str,
    *,
    models: Iterable[str] | None = None,
    model: str | None = None,
    provider: str | None = None,
    timeout_s: int = 240,
    cwd: Path | None = None,
    usage_file: Path | None = None,
    line_sink: Callable[[str], Any] | None = None,
) -> dict[str, Any]:
    """Run one bounded Hermes research request using free models only."""
    started = time.monotonic()
    executable = find_executable()
    if executable is None:
        return _base_result(
            status="UNAVAILABLE_CLI",
            started=started,
            error="Hermes executable not found",
        )

    requested = [model] if model else list(models or DEFAULT_FREE_MODELS)
    requested = [str(item).strip() for item in requested if str(item).strip()]
    if not requested:
        requested = list(DEFAULT_FREE_MODELS)

    last: dict[str, Any] | None = None
    for selected_model in requested:
        command = build_command(
            executable,
            prompt,
            model=selected_model,
            provider=provider,
            usage_file=usage_file,
        )
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_s,
                cwd=str(cwd or REPO_ROOT),
                shell=False,
            )
        except subprocess.TimeoutExpired:
            last = _base_result(
                status="TIMEOUT",
                started=started,
                model=selected_model,
                cli=str(executable),
                error=f"timed out after {timeout_s}s",
            )
            continue
        except OSError as exc:
            return _base_result(
                status="UNAVAILABLE_CLI",
                started=started,
                model=selected_model,
                cli=str(executable),
                error=str(exc),
            )

        stdout = (completed.stdout or "").strip()
        stderr = (completed.stderr or "").strip()
        if completed.returncode == 0 and stdout:
            if line_sink is not None:
                for line in stdout.splitlines():
                    try:
                        line_sink(f"[HERMES] {line}")
                    except Exception:
                        pass
            return _base_result(
                status="AVAILABLE",
                started=started,
                model=selected_model,
                cli=str(executable),
                provider=provider or "configured",
                returncode=completed.returncode,
                output=stdout,
                stdout_tail=stdout[-2000:],
                stderr_tail=stderr[-500:],
                parsed=_parse_json(stdout),
            )

        status = "UNAVAILABLE_QUOTA" if _is_quota_error(stdout, stderr) else "ERROR"
        last = _base_result(
            status=status,
            started=started,
            model=selected_model,
            cli=str(executable),
            provider=provider or "configured",
            returncode=completed.returncode,
            error=stderr or stdout or f"non-zero exit {completed.returncode}",
            stdout_tail=stdout[-2000:],
            stderr_tail=stderr[-500:],
        )
        if status != "UNAVAILABLE_QUOTA":
            break
    return last or _base_result(status="ERROR", started=started, error="no model attempted")
