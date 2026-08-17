"""Promote accepted.yaml onto the live runner config only when flat."""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from aegis.config import dump_config, load_config
from aegis.optimizer.hypothesis import preserve_core_live_keys
from aegis.optimizer.paths import BOT_ROOT, PAPER_LOCK, REPO_ROOT
from aegis.optimizer.snapshot import load_heartbeat
from aegis.optimizer.state import ACCEPTED_YAML, OPTIMIZER_DIR, PENDING_PROMOTE, write_json
from aegis.paper_control import lock_appears_held, pid_alive

logger = logging.getLogger(__name__)

# Unattended optimizer must never overwrite the running demo YAML.
PROTECTED_LIVE_NAMES = frozenset({"config_mt5_demo_firehose_hw.yaml"})


def bot_open_count(heartbeat: dict[str, Any] | None = None) -> int:
    hb = heartbeat if heartbeat is not None else load_heartbeat()
    if not hb:
        return 0
    return int(hb.get("open") or 0)


def promote_if_flat(
    *,
    live_config: Path,
    accepted: Path | None = None,
    restart: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    accepted = accepted or (OPTIMIZER_DIR / ACCEPTED_YAML)
    hb = load_heartbeat()
    open_n = bot_open_count(hb)
    result: dict[str, Any] = {
        "promoted": False,
        "open": open_n,
        "live_config": str(live_config),
        "accepted": str(accepted),
    }
    if not accepted.exists():
        result["message"] = "accepted.yaml missing"
        return result
    if Path(live_config).name in PROTECTED_LIVE_NAMES:
        result["message"] = (
            "refuses to overwrite active firehose YAML; use ChampionStore, not YAML copy"
        )
        return result
    if open_n > 0:
        pending_path = OPTIMIZER_DIR / PENDING_PROMOTE
        prior = {}
        if pending_path.exists():
            try:
                prior = json.loads(pending_path.read_text(encoding="utf-8")) or {}
            except (OSError, json.JSONDecodeError):
                prior = {}
        if not isinstance(prior, dict):
            prior = {}
        prior.update(
            {
                "reason": "not flat",
                "open": open_n,
                "accepted_yaml": str(accepted),
                "live_config": str(live_config),
            }
        )
        write_json(pending_path, prior)
        result["message"] = "bot in trade; pending_promote written"
        return result
    if dry_run:
        result["message"] = "dry-run: would copy accepted.yaml over live config"
        return result
    live_cfg = load_config(live_config)
    acc_cfg = load_config(accepted)
    dump_config(preserve_core_live_keys(live_cfg, acc_cfg), live_config)
    pending = OPTIMIZER_DIR / PENDING_PROMOTE
    if pending.exists():
        pending.unlink()
    result["copied"] = True
    if restart:
        if lock_appears_held(PAPER_LOCK) or Path(live_config).name in PROTECTED_LIVE_NAMES:
            result["restart_skipped"] = True
        else:
            result.update(_restart_runner(live_config, hb))
    result["promoted"] = True
    result["message"] = "copied accepted.yaml onto live config"
    return result


def _restart_runner(live_config: Path, hb: dict[str, Any] | None) -> dict[str, Any]:
    info: dict[str, Any] = {"restarted": False}
    old_pid = int((hb or {}).get("pid") or 0)
    if old_pid and pid_alive(old_pid):
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(old_pid), "/F"],
                    check=False,
                    capture_output=True,
                    text=True,
                )
            else:
                os.kill(old_pid, 15)
        except OSError as exc:
            info["kill_error"] = str(exc)
            return info
        deadline = time.time() + 20
        while time.time() < deadline and (pid_alive(old_pid) or lock_appears_held(PAPER_LOCK)):
            time.sleep(0.4)
    script = BOT_ROOT / "scripts" / "run_broker_paper.py"
    py = sys.executable
    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    proc = subprocess.Popen(
        [py, str(script), "--config", str(live_config)],
        cwd=str(BOT_ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        creationflags=creationflags,
        start_new_session=(os.name != "nt"),
    )
    info["restarted"] = True
    info["new_pid"] = proc.pid
    info["repo"] = str(REPO_ROOT)
    return info
