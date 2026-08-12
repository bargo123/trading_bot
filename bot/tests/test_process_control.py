"""Offline tests for launchd payload and process status semantics."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from aegis.paper_control import heartbeat_max_age
from aegis_paper import heartbeat_status, launch_agent_payload, service_label, start_service, stop_service
from watchdog import child_specs, runtime_python_path


def test_launch_agent_runs_watchdog_from_repo():
    config = ROOT / "config_ib_paper_eurusd.yaml"
    payload = launch_agent_payload(ROOT, Path("/usr/bin/python3"), config)
    assert service_label() == "com.aegis.ibpaper"
    assert payload["Label"] == "com.aegis.ibpaper"
    assert payload["RunAtLoad"] is True
    assert payload["KeepAlive"] is True
    assert payload["ProcessType"] == "Interactive"
    assert str(ROOT / "scripts" / "watchdog.py") in payload["ProgramArguments"]
    assert payload["WorkingDirectory"] == str(ROOT)
    assert payload["EnvironmentVariables"]["PYTHONPYCACHEPREFIX"] == "/private/tmp/aegis-paper-pycache"


def test_start_service_preserves_virtualenv_python_launcher_path():
    captured = {}
    with tempfile.TemporaryDirectory() as directory:
        plist_path = Path(directory) / "com.aegis.ibpaper.plist"

        def payload(_root, python, _config):
            captured["python"] = python
            return {"Label": "com.aegis.ibpaper", "ProgramArguments": [str(python)]}

        with patch("aegis_paper._service_loaded", return_value=False), patch(
            "aegis_paper._tcp_up", return_value=False
        ), patch("aegis_paper._read_json", return_value=None), patch(
            "aegis_paper._plist_path", return_value=plist_path
        ), patch("aegis_paper.launch_agent_payload", side_effect=payload), patch(
            "aegis_paper.subprocess.run"
        ), patch("aegis_paper.sys.executable", str(ROOT / ".venv" / "bin" / "python")):
            start_service(ROOT / "config_ib_paper_mgc_shadow.yaml")

    assert captured["python"] == ROOT / ".venv" / "bin" / "python"


def test_status_marks_stale_heartbeat_as_stopped():
    status = heartbeat_status({"pid": 123, "ts": 100.0}, now=200.0, max_age=15.0)
    assert not status["running"]
    assert status["age_seconds"] == 100.0


def test_status_accepts_fresh_heartbeat_without_process_probe():
    status = heartbeat_status({"pid": 123, "ts": 195.0}, now=200.0, max_age=15.0)
    assert status["running"]
    assert status["pid"] == 123


def test_status_freshness_covers_configured_poll_interval():
    max_age = heartbeat_max_age({"poll_seconds": 30})
    assert heartbeat_status({"pid": 123, "ts": 155.0}, now=200.0, max_age=max_age)["running"]
    assert not heartbeat_status({"pid": 123, "ts": 124.0}, now=200.0, max_age=max_age)["running"]


def test_watchdog_specs_own_exactly_bot_and_dashboard_children():
    config = ROOT / "config_ib_paper_eurusd.yaml"
    specs = child_specs(ROOT, Path("/usr/bin/python3"), config)
    assert [spec.name for spec in specs] == ["bot", "dashboard"]
    assert specs[0].command[:2] == ["/usr/bin/python3", "-u"]
    assert str(ROOT / "scripts" / "run_broker_paper.py") in specs[0].command
    assert str(ROOT / "scripts" / "run_dashboard.py") in specs[1].command


def test_watchdog_preserves_virtualenv_python_launcher_path():
    launcher = ROOT / ".venv" / "bin" / "python"
    assert runtime_python_path(str(launcher)) == launcher


def test_watchdog_selects_mgc_runner_from_config():
    config = ROOT / "config_ib_paper_mgc_shadow.yaml"
    specs = child_specs(ROOT, Path("/usr/bin/python3"), config)
    assert str(ROOT / "scripts" / "run_mgc_firehose.py") in specs[0].command


def test_status_surfaces_mgc_heartbeat_gate():
    status = heartbeat_status(
        {
            "pid": 123,
            "ts": 195.0,
            "symbol": "MGC",
            "local_symbol": "MGCV6",
            "feed_usable": True,
            "trades_today": 0,
            "paper_promoted": False,
            "gate_reason": "collecting sample",
        },
        now=200.0,
        max_age=15.0,
    )
    assert status["symbol"] == "MGC"
    assert status["local_symbol"] == "MGCV6"
    assert status["feed_usable"] is True
    assert status["paper_promoted"] is False
    assert status["gate_reason"] == "collecting sample"


def test_stop_quiesces_supervisor_before_flattening():
    actions = []
    cfg = {
        "engine": "ibkr",
        "ib_port": 4002,
        "allow_live": False,
        "paper_trading_enabled": True,
        "dry_run": False,
    }

    def record_launchctl(*_args, **_kwargs):
        actions.append("bootout")

    def record_mutation(_cfg, action):
        actions.append(action)

    with patch("aegis_paper._service_loaded", side_effect=[True, False]), patch(
        "aegis_paper.subprocess.run", side_effect=record_launchctl
    ), patch("aegis_paper._mutate_broker", side_effect=record_mutation):
        stop_service(cfg, process_only=False)

    assert actions == ["bootout", "flatten"]


def test_stop_waits_for_launchd_job_to_finish_unloading():
    cfg = {
        "engine": "ibkr",
        "ib_port": 4002,
        "allow_live": False,
        "paper_trading_enabled": False,
        "dry_run": True,
    }
    loaded_states = [True, True, False]

    with patch("aegis_paper._service_loaded", side_effect=loaded_states) as loaded, patch(
        "aegis_paper.subprocess.run"
    ), patch("aegis_paper.time.sleep"):
        stop_service(cfg, process_only=True)

    assert loaded.call_count == 3


if __name__ == "__main__":
    test_launch_agent_runs_watchdog_from_repo()
    test_status_marks_stale_heartbeat_as_stopped()
    test_status_accepts_fresh_heartbeat_without_process_probe()
    test_status_freshness_covers_configured_poll_interval()
    test_watchdog_specs_own_exactly_bot_and_dashboard_children()
    test_stop_quiesces_supervisor_before_flattening()
    test_stop_waits_for_launchd_job_to_finish_unloading()
    print("OK")
