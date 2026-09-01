from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess


SCRIPT = Path(__file__).parents[1] / "scripts" / "setup_external_research_stack.ps1"


def test_external_setup_script_is_idempotent_and_uses_isolated_roots():
    text = SCRIPT.read_text(encoding="utf-8")

    assert "$projectRoot" in text
    assert "$externalRoot" in text
    assert "$sourceRoot" in text
    assert "$venvRoot" in text
    assert "New-Item -ItemType Directory -Force" in text
    assert ".external" in text
    assert "git clone" in text
    assert "git rev-parse HEAD" in text
    assert "CloneTimeoutSeconds" in text
    assert "SkipRepositoryClone" in text
    assert "BLOCKED_CLONE_TIMEOUT" in text
    assert "external_dependency_manifest.json" in text
    assert "external_dependency_manifest.md" in text
    assert "order_send" not in text.lower()
    assert "allow_live" not in text.lower()


def test_external_setup_script_covers_every_prompt_repository():
    text = SCRIPT.read_text(encoding="utf-8")
    repositories = (
        "OpenAlice",
        "awesome-systematic-trading",
        "qlib",
        "ordersim",
        "hftbacktest",
        "oos-lab",
        "Keystone",
        "algorithmic-trading-research-framework",
        "samvid-trading-core",
        "Vibe-Trading",
        "metatrader5-mcp-server",
        "nautilus_trader",
        "Lean",
        "abides",
    )
    for repository in repositories:
        assert repository in text


def test_external_setup_script_records_blocked_installations_honestly():
    text = SCRIPT.read_text(encoding="utf-8")

    assert "completed" in text.lower()
    assert "blocked" in text.lower()
    assert "test_results" in text
    assert "license" in text.lower()
    assert "commit" in text.lower()


def test_external_setup_script_attempts_missing_safe_prerequisites_via_winget():
    text = SCRIPT.read_text(encoding="utf-8")

    assert "Ensure-Prerequisite" in text
    assert "install --id" in text
    assert "GitHub.cli" in text
    assert "OpenJS.NodeJS.LTS" in text
    assert "astral-sh.uv" in text
    assert "Gyan.FFmpeg" in text
    assert "InstallDocker" in text


def test_external_setup_script_handles_required_windows_native_prerequisites():
    text = SCRIPT.read_text(encoding="utf-8")

    assert "Microsoft.VCRedist.2015+.x64" in text
    assert "Microsoft.VisualStudio.2022.BuildTools" in text
    assert "Microsoft.VisualStudio.Workload.VCTools" in text
    assert "Invoke-NoSpaceJunction" in text
    assert "Ensure-NoSpaceCommandShim" in text
    assert "import torch,pytest,sys" in text
    assert "ABIDES legacy requirements are incompatible" in text


def test_external_setup_script_can_create_legacy_python_env_with_uv_fallback():
    text = SCRIPT.read_text(encoding="utf-8")

    assert "uv venv" in text
    assert "--python" in text
    assert "uv pip install --python" in text
    assert "catch {\n            $pipAvailable = $false" in text


def test_best_effort_classifies_native_exit_code_not_successful_stderr_as_failure():
    text = SCRIPT.read_text(encoding="utf-8")

    assert '$previousErrorActionPreference = $ErrorActionPreference' in text
    assert '$ErrorActionPreference = "Continue"' in text
    assert '$ErrorActionPreference = $previousErrorActionPreference' in text


def test_abides_smoke_exercises_latency_and_disconnect_failure_model():
    text = SCRIPT.read_text(encoding="utf-8")

    assert "from model.LatencyModel import LatencyModel" in text
    assert "get_latency(0,1)" in text
    assert "connected=np.array([[True,False],[True,True]])" in text
    assert "ABIDES_LATENCY_STRESS_OK" in text
    assert "BLOCKED_PYTHON_RUNTIME" in text


def test_external_setup_script_dry_run_emits_complete_install_plan(tmp_path):
    """Missing a repository install branch must be visible in the manifest."""
    powershell = shutil.which("powershell.exe") or shutil.which("pwsh.exe")
    assert powershell is not None
    project_root = tmp_path / "project"

    result = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT),
            "-ProjectRoot",
            str(project_root),
            "-SkipInstalls",
            "-SkipUpstreamTests",
            "-SkipPrerequisites",
            "-SkipRepositoryClone",
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    manifest_path = (
        project_root / "bot" / "reports" / "research"
        / "external_dependency_manifest.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    assert {row["name"] for row in manifest["repositories"]} == {
        "OpenAlice",
        "awesome-systematic-trading",
        "qlib",
        "ordersim",
        "hftbacktest",
        "oos-lab",
        "Keystone",
        "algorithmic-trading-research-framework",
        "samvid-trading-core",
        "Vibe-Trading",
        "metatrader5-mcp-server",
        "nautilus_trader",
        "Lean",
        "abides",
    }
    assert {row["name"] for row in manifest["environments"]} == {
        "qlib",
        "ordersim",
        "hftbacktest",
        "oos-lab",
        "keystone",
        "research-framework",
        "samvid",
        "mt5-mcp",
        "nautilus",
        "lean",
        "abides",
    }
    expected_checks = {
        "OpenAlice pnpm install",
        "OpenAlice tests",
        "OpenAlice dev smoke",
        "awesome-systematic-trading catalog inspection",
        "Qlib install",
        "Qlib import",
        "Qlib pip check",
        "ordersim install",
        "ordersim tests",
        "hftbacktest install",
        "hftbacktest import",
        "hftbacktest synthetic example",
        "oos-lab install",
        "oos-lab tests",
        "oos-lab pip check",
        "Keystone sync",
        "Keystone tests",
        "research-framework install",
        "research-framework tests",
        "research-framework public release check",
        "samvid sync",
        "samvid tests",
        "samvid ruff",
        "samvid compile",
        "Vibe-Trading PR 481 inspection",
        "mt5-mcp install",
        "mt5-mcp tests",
        "NautilusTrader install",
        "NautilusTrader import",
        "NautilusTrader pip check",
        "LEAN install",
        "LEAN help",
        "ABIDES install",
        "ABIDES synthetic simulation",
    }
    checks = {row["name"]: row for row in manifest["install_checks"]}
    assert expected_checks <= checks.keys()
    assert all(checks[name]["status"] == "SKIPPED_INSTALL" for name in expected_checks)
