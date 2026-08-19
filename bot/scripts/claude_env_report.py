#!/usr/bin/env python3
"""Capture the host environment for this machine into bot/reports/claude/.

Written during the new-machine takeover so later sessions can read a compact
environment summary instead of re-probing the host.
"""
from __future__ import annotations

import datetime
import json
import os
import platform
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HOME = Path.home()


def _first_line(cmd: list[str]) -> str:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except Exception as exc:  # noqa: BLE001 - probing arbitrary host tools
        return f"unavailable ({type(exc).__name__})"
    out = (result.stdout or result.stderr or "").strip()
    return out.splitlines()[0] if out else "unavailable (no output)"


def _mt5_python() -> str:
    try:
        import MetaTrader5 as mt5
    except Exception as exc:  # noqa: BLE001
        return f"import failed: {exc}"
    return f"MetaTrader5 {getattr(mt5, '__version__', 'unknown')}"


def _mt5_terminals() -> list[str]:
    candidates = [
        Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "MetaTrader 5" / "terminal64.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) / "MetaTrader 5" / "terminal64.exe",
        Path(os.environ.get("APPDATA", "")) / "MetaQuotes" / "Terminal",
    ]
    return [str(path) for path in candidates if path.exists()]


def collect() -> dict[str, object]:
    return {
        "captured_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "os": f"{platform.system()} {platform.release()} ({platform.version()})",
        "machine": platform.machine(),
        "cpu": platform.processor(),
        "cpu_logical": os.cpu_count(),
        "python": sys.version.split()[0],
        "python_exe": sys.executable,
        "venv": str(REPO / ".venv"),
        "git": _first_line(["git", "--version"]),
        "node": _first_line(["node", "--version"]),
        "uv": _first_line([str(HOME / ".local" / "bin" / "uv.exe"), "--version"]),
        "serena": _first_line([str(HOME / ".local" / "bin" / "serena.exe"), "--version"]),
        "jedi_language_server": _first_line(
            [str(HOME / ".local" / "bin" / "jedi-language-server.exe"), "--version"]
        ),
        "serena_language_backend": "python_jedi (pure-Python LSP, no Node dependency)",
        "metatrader5_python": _mt5_python(),
        "metatrader5_terminals": _mt5_terminals(),
        "repo_root": str(REPO),
        "repo_branch": _first_line(["git", "-C", str(REPO), "branch", "--show-current"]),
        "repo_head": _first_line(["git", "-C", str(REPO), "rev-parse", "HEAD"]),
    }


def main() -> None:
    env = collect()
    out_dir = REPO / "bot" / "reports" / "claude"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "environment.json").write_text(json.dumps(env, indent=2), encoding="utf-8")

    lines = ["# Aegis host environment", "", f"Captured: {env['captured_utc']}", ""]
    for key, value in env.items():
        if key == "captured_utc":
            continue
        lines.append(f"- **{key}**: {value}")
    lines += [
        "",
        "## Setup notes",
        "",
        "- Python 3.12 installed via winget (`Python.Python.3.12`); the Microsoft Store",
        "  `python.exe` alias on PATH is a stub and must not be used.",
        "- Project venv at `.venv`; install with",
        "  `.venv/Scripts/python -m pip install -r requirements.txt -r bot/requirements.txt`.",
        "- Serena uses the `python_jedi` backend. The node-based `python` (pyright) backend",
        "  fails to start on this host. `jedi-language-server` must be on PATH:",
        "  `uv tool install jedi-language-server`.",
        "- Serena MCP server is registered in `.mcp.json` at the repo root.",
    ]
    (out_dir / "environment.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(env, indent=2))


if __name__ == "__main__":
    main()
