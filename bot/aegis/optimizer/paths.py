"""Runtime paths for the optimizer (separate from the paper-runner lock)."""
from __future__ import annotations

from pathlib import Path

BOT_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BOT_ROOT.parent
OPTIMIZER_DIR = BOT_ROOT / "optimizer"
REPORTS_DIR = BOT_ROOT / "reports"
PAPER_LOCK = REPORTS_DIR / "run_broker_paper.lock"
OPTIMIZER_LOCK = OPTIMIZER_DIR / "optimizer.lock"
SUPERVISOR_PID = OPTIMIZER_DIR / "supervisor.pid"
HEARTBEAT = REPORTS_DIR / "bot_heartbeat.json"
DEFAULT_LIVE_CONFIG = BOT_ROOT / "config_mt5_demo_firehose_hw.yaml"
DEFAULT_OPTIMIZER_CONFIG = OPTIMIZER_DIR / "config.yaml"
AGENT_PROMPT = OPTIMIZER_DIR / "AGENT_PROMPT.md"


def ensure_runtime_dirs() -> None:
    (OPTIMIZER_DIR / "metrics").mkdir(parents=True, exist_ok=True)
    (OPTIMIZER_DIR / "checkpoints").mkdir(parents=True, exist_ok=True)
