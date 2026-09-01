"""YAML-first experiment: checkpoint, patch candidate, accept or revert."""
from __future__ import annotations

import copy
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aegis.config import dump_config, load_config
from aegis.optimizer.paths import OPTIMIZER_DIR, ensure_runtime_dirs
from aegis.optimizer.state import (
    ACCEPTED_YAML,
    CANDIDATE_YAML,
    CURRENT_BEST,
    EXPERIMENTS,
    OPEN_EXPERIMENT,
    PENDING_PROMOTE,
    REJECTED,
    append_jsonl,
    read_json,
    write_json,
)


def new_experiment_id(slug: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in slug)[:40]
    return f"exp_{stamp}_{safe}"


def apply_patch(cfg: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(cfg)
    for key, value in patch.items():
        cur: Any = out
        parts = str(key).split(".")
        for part in parts[:-1]:
            nxt = cur.get(part)
            if not isinstance(nxt, dict):
                nxt = {}
                cur[part] = nxt
            cur = nxt
        cur[parts[-1]] = copy.deepcopy(value)
    return out


def checkpoint_dir(exp_id: str) -> Path:
    return OPTIMIZER_DIR / "checkpoints" / exp_id


def start_experiment(
    *,
    exp_id: str,
    accepted_src: Path,
    patch: dict[str, Any],
    meta: dict[str, Any],
) -> dict[str, Any]:
    """Copy accepted YAML to checkpoint + candidate; apply declared patch only."""
    ensure_runtime_dirs()
    dest = checkpoint_dir(exp_id)
    dest.mkdir(parents=True, exist_ok=True)
    baseline_cfg = load_config(accepted_src)
    dump_config(baseline_cfg, dest / "baseline.yaml")
    candidate_cfg = apply_patch(baseline_cfg, patch)
    dump_config(candidate_cfg, dest / "candidate.yaml")
    dump_config(candidate_cfg, OPTIMIZER_DIR / CANDIDATE_YAML)
    record = {
        "id": exp_id,
        "ts": datetime.now(timezone.utc).isoformat(),
        "status": "open",
        "patch": patch,
        "checkpoint": str(dest),
        "accepted_src": str(accepted_src),
        **meta,
    }
    write_json(OPTIMIZER_DIR / OPEN_EXPERIMENT, record)
    write_json(dest / "meta.json", record)
    return record


def restore_checkpoint(exp_id: str) -> Path:
    dest = checkpoint_dir(exp_id)
    baseline = dest / "baseline.yaml"
    if not baseline.exists():
        raise FileNotFoundError(f"missing checkpoint {baseline}")
    shutil.copy2(baseline, OPTIMIZER_DIR / CANDIDATE_YAML)
    return baseline


def accept_experiment(record: dict[str, Any], metrics: dict[str, Any], *, bot_open: int) -> dict[str, Any]:
    exp_id = str(record["id"])
    cand = checkpoint_dir(exp_id) / "candidate.yaml"
    accepted = OPTIMIZER_DIR / ACCEPTED_YAML
    shutil.copy2(cand, accepted)
    record = dict(record)
    record["status"] = "accepted"
    record["decision"] = "accept"
    record["candidate_metrics"] = metrics
    record["accepted_yaml"] = str(accepted)
    write_json(
        OPTIMIZER_DIR / CURRENT_BEST,
        {
            "accepted_yaml": str(accepted),
            "experiment_id": exp_id,
            "metrics": metrics,
            "updated_utc": datetime.now(timezone.utc).isoformat(),
        },
    )
    if int(bot_open) > 0:
        pending = {
            "experiment_id": exp_id,
            "accepted_yaml": str(accepted),
            "reason": "heartbeat.open > 0; wait until flat",
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        write_json(OPTIMIZER_DIR / PENDING_PROMOTE, pending)
        record["pending_promote"] = True
    else:
        record["pending_promote"] = False
        pending_path = OPTIMIZER_DIR / PENDING_PROMOTE
        if pending_path.exists():
            pending_path.unlink()
    append_jsonl(OPTIMIZER_DIR / EXPERIMENTS, record)
    open_path = OPTIMIZER_DIR / OPEN_EXPERIMENT
    if open_path.exists():
        open_path.unlink()
    return record


def reject_experiment(record: dict[str, Any], metrics: dict[str, Any], reason: str) -> dict[str, Any]:
    exp_id = str(record["id"])
    restore_checkpoint(exp_id)
    record = dict(record)
    record["status"] = "rejected"
    record["decision"] = "reject"
    record["reason"] = reason
    record["candidate_metrics"] = metrics
    append_jsonl(OPTIMIZER_DIR / REJECTED, record)
    append_jsonl(OPTIMIZER_DIR / EXPERIMENTS, record)
    open_path = OPTIMIZER_DIR / OPEN_EXPERIMENT
    if open_path.exists():
        open_path.unlink()
    return record


def record_dry_run(record: dict[str, Any], extra: dict[str, Any] | None = None) -> dict[str, Any]:
    record = dict(record)
    record["status"] = "dry_run"
    record["decision"] = "dry_run"
    if extra:
        record.update(extra)
    append_jsonl(OPTIMIZER_DIR / EXPERIMENTS, record)
    open_path = OPTIMIZER_DIR / OPEN_EXPERIMENT
    if open_path.exists():
        open_path.unlink()
    return record


def load_open_experiment() -> dict[str, Any] | None:
    data = read_json(OPTIMIZER_DIR / OPEN_EXPERIMENT)
    return data if isinstance(data, dict) else None
