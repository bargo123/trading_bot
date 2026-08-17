"""Persistent optimizer memory under bot/optimizer/."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aegis.config import dump_config, load_config
from aegis.optimizer.paths import DEFAULT_LIVE_CONFIG, OPTIMIZER_DIR, ensure_runtime_dirs

STATE_MD = "optimizer_state.md"
CURRENT_BEST = "current_best.json"
EXPERIMENTS = "experiments.jsonl"
REJECTED = "rejected_experiments.jsonl"
BOOK_CONCEPTS = "book_concepts.json"
FAILURES = "failures.jsonl"
OPEN_EXPERIMENT = "open_experiment.json"
PENDING_PROMOTE = "pending_promote.json"
ACCEPTED_YAML = "accepted.yaml"
CANDIDATE_YAML = "candidate.yaml"
OPT_CONFIG = "config.yaml"


DEFAULT_OPT_CONFIG: dict[str, Any] = {
    "allow_code_edit": False,
    "live_config": "config_mt5_demo_firehose_hw.yaml",
    "lookback_days": 14,
    "min_trades": 20,
    "dd_tolerance_pct": 2.0,
    "is_fraction": 0.7,
    "walk_forward_folds": 3,
    "git_commit": False,
    "pytest_subset": ["tests/test_paper_control.py", "tests/test_optimizer.py"],
    "pytest_extra_args": ["-k", "not test_ib_paper_config_defaults_to_observation_only"],
}


SEED_WEAKNESSES = [
    "EURUSD hunt sample: ~95% WR with negative expectancy — left off live list (Tharp).",
    "MetaQuotes 0-spread quotes can vanish; Harris: do not scalp when spread >= take.",
    "High WR is not the accept gate; OOS expectancy_r must beat baseline.",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, default=str, indent=2), encoding="utf-8")


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, default=str) + "\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def load_opt_config(path: Path | None = None) -> dict[str, Any]:
    cfg_path = path or (OPTIMIZER_DIR / OPT_CONFIG)
    data = dict(DEFAULT_OPT_CONFIG)
    if cfg_path.exists():
        import yaml

        loaded = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        if isinstance(loaded, dict):
            data.update(loaded)
    return data


def live_config_path(opt_cfg: dict[str, Any] | None = None) -> Path:
    opt_cfg = opt_cfg or load_opt_config()
    rel = str(opt_cfg.get("live_config") or DEFAULT_LIVE_CONFIG.name)
    p = Path(rel)
    if not p.is_absolute():
        p = OPTIMIZER_DIR.parent / rel
    return p


def render_state_md(state: dict[str, Any]) -> str:
    lines = [
        "# Optimizer state",
        "",
        f"- version: `{state.get('version', 1)}`",
        f"- updated_utc: `{state.get('updated_utc', '')}`",
        f"- live_config: `{state.get('live_config', '')}`",
        f"- accepted_yaml: `{state.get('accepted_yaml', '')}`",
        f"- best_metrics: `{json.dumps(state.get('best_metrics') or {}, default=str)}`",
        f"- next_step: {state.get('next_step', '')}",
        "",
        "## Weaknesses",
    ]
    for w in state.get("weaknesses") or []:
        lines.append(f"- {w}")
    lines += ["", "## Tested", *(f"- {x}" for x in (state.get("tested") or []) or ["(none)"])]
    lines += ["", "## Rejected", *(f"- {x}" for x in (state.get("rejected") or []) or ["(none)"])]
    lines += ["", "## Promising", *(f"- {x}" for x in (state.get("promising") or []) or ["(none)"])]
    lines += ["", "## Hypotheses", *(f"- {x}" for x in (state.get("hypotheses") or []) or ["(none)"])]
    lines += ["", "## Regimes", *(f"- {x}" for x in (state.get("regimes") or []) or ["(none)"])]
    lines.append("")
    return "\n".join(lines)


def parse_state_md(text: str) -> dict[str, Any]:
    """Best-effort: we persist a JSON sidecar in the markdown HTML comment is overkill.

    The markdown is the human memory; current_best.json is the machine pointer.
    """
    return {"raw": text}


def default_state(live_cfg_path: Path) -> dict[str, Any]:
    return {
        "version": 1,
        "updated_utc": _now(),
        "live_config": str(live_cfg_path),
        "accepted_yaml": str(OPTIMIZER_DIR / ACCEPTED_YAML),
        "best_metrics": {},
        "weaknesses": list(SEED_WEAKNESSES),
        "tested": [],
        "rejected": [],
        "promising": [],
        "hypotheses": [
            "If live WR is high and expectancy <= 0, widen TP or drop fat-spread symbols.",
            "If spread_skip floods the journal, tighten max_spread_pips (Harris).",
            "If stacked losers, cut max_positions.",
        ],
        "regimes": ["mt5_demo_firehose_hw"],
        "next_step": "Run a dry cycle, then enable the Windows supervisor.",
    }


def ensure_memory(opt_cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """Create defaults if missing. Copies live YAML to accepted.yaml once."""
    ensure_runtime_dirs()
    opt_cfg = opt_cfg or load_opt_config()
    live = live_config_path(opt_cfg)
    accepted = OPTIMIZER_DIR / ACCEPTED_YAML
    if not accepted.exists() and live.exists():
        dump_config(load_config(live), accepted)
    if not (OPTIMIZER_DIR / OPT_CONFIG).exists():
        import yaml

        (OPTIMIZER_DIR / OPT_CONFIG).write_text(
            yaml.safe_dump(DEFAULT_OPT_CONFIG, sort_keys=False), encoding="utf-8"
        )
    state_path = OPTIMIZER_DIR / STATE_MD
    state = default_state(live)
    if state_path.exists():
        state["updated_utc"] = _now()
    else:
        state_path.write_text(render_state_md(state), encoding="utf-8")
    best_path = OPTIMIZER_DIR / CURRENT_BEST
    if not best_path.exists():
        write_json(
            best_path,
            {
                "accepted_yaml": str(accepted),
                "live_config": str(live),
                "metrics": {},
                "updated_utc": _now(),
            },
        )
    concepts = OPTIMIZER_DIR / BOOK_CONCEPTS
    if not concepts.exists():
        write_json(
            concepts,
            {
                "investigated": [],
                "notes": "EURUSD 95% WR / negative expectancy recorded from firehose hunt.",
            },
        )
    for name in (EXPERIMENTS, REJECTED, FAILURES):
        (OPTIMIZER_DIR / name).touch(exist_ok=True)
    return {
        "opt_cfg": opt_cfg,
        "live_config": live,
        "accepted": accepted,
        "candidate": OPTIMIZER_DIR / CANDIDATE_YAML,
        "state": state,
        "current_best": read_json(best_path, {}),
        "book_concepts": read_json(concepts, {}),
        "experiments": read_jsonl(OPTIMIZER_DIR / EXPERIMENTS),
        "rejected": read_jsonl(OPTIMIZER_DIR / REJECTED),
    }


def refresh_state_md(updates: dict[str, Any]) -> None:
    live = live_config_path()
    state = default_state(live)
    best = read_json(OPTIMIZER_DIR / CURRENT_BEST, {}) or {}
    state["best_metrics"] = best.get("metrics") or {}
    rejected = read_jsonl(OPTIMIZER_DIR / REJECTED)
    experiments = read_jsonl(OPTIMIZER_DIR / EXPERIMENTS)
    state["rejected"] = [r.get("id") or r.get("hypothesis") for r in rejected[-20:]]
    state["tested"] = [e.get("id") for e in experiments[-20:] if e.get("id")]
    state["promising"] = [
        e.get("id") for e in experiments if e.get("decision") == "accept"
    ][-10:]
    state.update(updates)
    state["updated_utc"] = _now()
    (OPTIMIZER_DIR / STATE_MD).write_text(render_state_md(state), encoding="utf-8")


def rejected_ids() -> set[str]:
    ids: set[str] = set()
    rows = read_jsonl(OPTIMIZER_DIR / REJECTED) + read_jsonl(OPTIMIZER_DIR / EXPERIMENTS)
    for r in rows:
        decision = str(r.get("decision") or r.get("status") or "")
        if decision not in {"reject", "rejected"}:
            continue
        for key in ("id", "hypothesis_id"):
            if r.get(key):
                ids.add(str(r[key]))
    return ids


def stored_best_expectancy() -> float | None:
    """Persisted current_best OOS E so a noisy split cannot 'beat' a weaker sample."""
    best = read_json(OPTIMIZER_DIR / CURRENT_BEST, {}) or {}
    metrics = best.get("metrics") or {}
    if metrics.get("expectancy_r") is not None:
        return float(metrics["expectancy_r"])
    if metrics.get("expectancy") is not None:
        return float(metrics["expectancy"])
    return None


def consumed_hypothesis_ids() -> set[str]:
    """Rejects plus accepted hypothesis ids so we do not re-run a winner as a new patch."""
    ids = rejected_ids()
    for r in read_jsonl(OPTIMIZER_DIR / EXPERIMENTS):
        decision = str(r.get("decision") or r.get("status") or "")
        if decision not in {"accept", "accepted"}:
            continue
        for key in ("id", "hypothesis_id"):
            if r.get(key):
                ids.add(str(r[key]))
    return ids


def record_failure(kind: str, message: str, extra: dict[str, Any] | None = None) -> None:
    row = {"ts": _now(), "kind": kind, "message": message}
    if extra:
        row.update(extra)
    append_jsonl(OPTIMIZER_DIR / FAILURES, row)
