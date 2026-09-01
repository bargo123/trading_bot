"""Status payload for the optimizer CLI."""
from __future__ import annotations

import time
from typing import Any

from aegis.optimizer.paths import HEARTBEAT, OPTIMIZER_LOCK, PAPER_LOCK
from aegis.optimizer.snapshot import load_heartbeat
from aegis.optimizer.state import (
    ACCEPTED_YAML,
    CANDIDATE_YAML,
    CURRENT_BEST,
    EXPERIMENTS,
    FAILURES,
    OPTIMIZER_DIR,
    PENDING_PROMOTE,
    REJECTED,
    load_opt_config,
    live_config_path,
    read_json,
    read_jsonl,
)
from aegis.paper_control import heartbeat_max_age, lock_appears_held, lock_pid, pid_alive


def mt5_reachable(cfg: dict[str, Any]) -> dict[str, Any]:
    try:
        from aegis.engines import create_engine

        eng = create_engine(cfg)
        if hasattr(eng, "connect_readonly"):
            eng.connect_readonly()
        else:
            eng.connect()
        acct = eng.account()
        return {
            "ok": True,
            "account_id": acct.account_id,
            "equity": acct.equity,
            "is_paper": acct.is_paper,
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def build_status(
    cfg: dict[str, Any],
    *,
    probe_mt5: bool = True,
) -> dict[str, Any]:
    opt_cfg = load_opt_config()
    hb = load_heartbeat()
    age = None
    if hb and hb.get("ts"):
        age = time.time() - float(hb["ts"])
    max_age = heartbeat_max_age(cfg)
    latest = read_json(OPTIMIZER_DIR / "metrics" / "latest.json", {})
    experiments = read_jsonl(OPTIMIZER_DIR / EXPERIMENTS)
    rejected = read_jsonl(OPTIMIZER_DIR / REJECTED)
    failures = read_jsonl(OPTIMIZER_DIR / FAILURES)
    last_exp = experiments[-1] if experiments else None
    return {
        "mt5": mt5_reachable(cfg) if probe_mt5 else {"ok": None, "skipped": True},
        "paper_lock_held": lock_appears_held(PAPER_LOCK),
        "paper_lock_pid": lock_pid(PAPER_LOCK),
        "optimizer_lock_held": lock_appears_held(OPTIMIZER_LOCK),
        "optimizer_lock_pid": lock_pid(OPTIMIZER_LOCK),
        "heartbeat_path": str(HEARTBEAT),
        "heartbeat_age_s": age,
        "heartbeat_stale": bool(age is None or age > max_age),
        "heartbeat_max_age_s": max_age,
        "heartbeat_open": int((hb or {}).get("open") or 0),
        "live_config": str(live_config_path(opt_cfg)),
        "accepted_yaml": str(OPTIMIZER_DIR / ACCEPTED_YAML),
        "candidate_yaml": str(OPTIMIZER_DIR / CANDIDATE_YAML),
        "current_best": read_json(OPTIMIZER_DIR / CURRENT_BEST, {}),
        "pending_promote": read_json(OPTIMIZER_DIR / PENDING_PROMOTE),
        "experiment_count": len(experiments),
        "rejected_count": len(rejected),
        "last_experiment": last_exp,
        "latest_metrics": (latest or {}).get("metrics"),
        "last_failures": failures[-5:],
        "allow_code_edit": bool(opt_cfg.get("allow_code_edit", False)),
        "bot_pid_alive": pid_alive(int((hb or {}).get("pid") or 0)),
    }
