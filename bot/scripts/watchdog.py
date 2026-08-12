#!/usr/bin/env python3
"""Hard watchdog: forever restart paper bot + dashboard if they die."""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "reports" / "watchdog.log"
PY = sys.executable


def log(msg: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n"
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line)


def alive(pattern: str) -> bool:
    try:
        r = subprocess.run(["pgrep", "-f", pattern], capture_output=True, text=True)
        return r.returncode == 0 and bool(r.stdout.strip())
    except Exception:
        return False


def spawn(script: str, args: list[str], out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [PY, "-u", str(ROOT / "scripts" / script), *args]
    with out.open("a", encoding="utf-8") as f:
        subprocess.Popen(
            cmd,
            cwd=str(ROOT),
            stdout=f,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )


def main() -> None:
    log("watchdog start pid=%s" % os.getpid())
    while True:
        if not alive("scripts/run_broker_paper.py"):
            log("restart bot")
            spawn(
                "run_broker_paper.py",
                ["--config", "config_ib_paper_eurusd.yaml"],
                ROOT / "reports" / "ib_paper_run.log",
            )
        if not alive("scripts/run_dashboard.py"):
            log("restart dashboard")
            spawn(
                "run_dashboard.py",
                ["--config", "config_ib_paper_eurusd.yaml", "--port", "8787"],
                ROOT / "reports" / "dashboard.log",
            )
        time.sleep(5)


if __name__ == "__main__":
    main()
