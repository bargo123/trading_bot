"""Council case system.

Each case lives in ai_council/cases/case_<ID>/ and walks:
  proposal (independent, one per available agent)
  -> adversarial critique (each agent critiques all other proposals)
  -> revision (author integrates accepted critique)
  -> decision (DATA decides; never vote-trading)

A case is a pure record; the data/validation gate decides what ships.
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CASES_DIR = Path(__file__).resolve().parent / "cases"

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{2,63}$")

PHASES = ("proposal", "critique", "revision", "decision")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _case_dir(case_id: str) -> Path:
    return CASES_DIR / f"case_{case_id}"


def _slugify(question: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", question.lower()).strip("-")
    return (slug or "case")[:40]


def new_case(question: str, *, case_id: str | None = None, mode: str = "REAL") -> dict[str, Any]:
    """Create a case record. Returns the case dict; raises on bad id or mode.

    mode must be REAL (real agent execution) or DRY_RUN (explicitly simulated).
    """
    question = (question or "").strip()
    if not question:
        raise ValueError("case question is required")
    mode = (mode or "").strip().upper()
    if mode not in {"REAL", "DRY_RUN"}:
        raise ValueError(f"mode must be REAL or DRY_RUN, got {mode!r}")
    cid = case_id or f"{_slugify(question)}_{uuid.uuid4().hex[:6]}"
    if not _ID_RE.match(cid):
        raise ValueError(f"invalid case id: {cid!r}")
    case = {
        "id": cid,
        "question": question,
        "mode": mode,
        "phase": "proposal",
        "created_utc": _now(),
        "proposals": [],
        "critiques": {},
        "revisions": {},
        "decision": None,
        "status": "open",
    }
    path = _case_dir(cid)
    path.mkdir(parents=True, exist_ok=True)
    (path / "case.json").write_text(json.dumps(case, indent=2, sort_keys=True), encoding="utf-8")
    return case


def load_case(case_id: str) -> dict[str, Any]:
    path = _case_dir(case_id) / "case.json"
    if not path.exists():
        raise FileNotFoundError(f"no such case: {case_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def _save(case: dict[str, Any]) -> dict[str, Any]:
    path = _case_dir(case["id"]) / "case.json"
    path.write_text(json.dumps(case, indent=2, sort_keys=True), encoding="utf-8")
    return case


def _write_step(case_dir: Path, subdir: str, filename: str, text: str) -> str:
    folder = case_dir / subdir
    folder.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^a-z0-9_.-]+", "-", str(filename).lower()).strip("-") or "step"
    path = folder / f"{safe}.md"
    path.write_text(text, encoding="utf-8")
    return str(path)


def add_proposal(case: dict[str, Any], *, agent: str, text: str,
                 meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """Record one independent proposal. Case must be in proposal phase."""
    if case.get("phase") != "proposal":
        raise ValueError("case is not in proposal phase")
    agent = (agent or "").strip()
    text = (text or "").strip()
    if not agent or not text:
        raise ValueError("agent and text are required")
    for existing in case.get("proposals", []):
        if existing.get("agent") == agent:
            raise ValueError(f"agent {agent!r} already proposed")
    file = _write_step(_case_dir(case["id"]), "proposals", agent, text)
    entry: dict[str, Any] = {"agent": agent, "text": text, "file": file,
                             "submitted_utc": _now()}
    if meta:
        entry["meta"] = dict(meta)
    case.setdefault("proposals", []).append(entry)
    return _save(case)


def add_critique(case: dict[str, Any], *, agent: str, target: str, text: str,
                 meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """Adversarial critique of another agent's proposal. Critique phase only."""
    if case.get("phase") != "critique":
        raise ValueError("case is not in critique phase")
    agents = {p.get("agent") for p in case.get("proposals", [])}
    if agent not in agents or target not in agents:
        raise ValueError(f"unknown agents: {agent!r} -> {target!r}")
    if agent == target:
        raise ValueError("agents cannot critique their own proposal")
    file = _write_step(_case_dir(case["id"]), "critiques", f"{target}--by--{agent}", text)
    entry: dict[str, Any] = {"agent": agent, "text": (text or "").strip(),
                             "file": file, "submitted_utc": _now()}
    if meta:
        entry["meta"] = dict(meta)
    case.setdefault("critiques", {}).setdefault(target, []).append(entry)
    return _save(case)


def add_revision(case: dict[str, Any], *, agent: str, text: str,
                 meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """Author revision incorporating accepted critique. Revision phase only."""
    if case.get("phase") != "revision":
        raise ValueError("case is not in revision phase")
    if agent not in {p.get("agent") for p in case.get("proposals", [])}:
        raise ValueError(f"unknown agent: {agent!r}")
    file = _write_step(_case_dir(case["id"]), "revisions", agent, (text or "").strip())
    entry: dict[str, Any] = {"text": (text or "").strip(), "file": file,
                             "revised_utc": _now()}
    if meta:
        entry["meta"] = dict(meta)
    case.setdefault("revisions", {})[agent] = entry
    return _save(case)


def move_phase(case: dict[str, Any], phase: str) -> dict[str, Any]:
    if phase not in PHASES:
        raise ValueError(f"invalid phase: {phase!r}")
    current = case.get("phase", "proposal")
    if PHASES.index(phase) != PHASES.index(current) + 1:
        raise ValueError(f"cannot move phase {current!r} -> {phase!r}; phases advance one at a time")
    case["phase"] = phase
    return _save(case)


def decide(case: dict[str, Any], *, decision: str, rationale: str,
           evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    """DATA decides: the decision must reference measured evidence.

    `decision` is one of: accept, reject, defer_validation, no_change.
    """
    allowed = {"accept", "reject", "defer_validation", "no_change"}
    decision = (decision or "").strip()
    if decision not in allowed:
        raise ValueError(f"decision must be one of {sorted(allowed)}")
    if case.get("phase") != "decision":
        raise ValueError("case is not in decision phase")
    case["decision"] = {
        "decision": decision,
        "rationale": (rationale or "").strip(),
        "evidence": evidence or {},
        "decided_utc": _now(),
    }
    case["status"] = "decided"
    return _save(case)


def list_cases() -> list[dict[str, Any]]:
    if not CASES_DIR.exists():
        return []
    out = []
    for folder in sorted(CASES_DIR.glob("case_*"), reverse=True):
        case_file = folder / "case.json"
        if case_file.exists():
            out.append(json.loads(case_file.read_text(encoding="utf-8")))
    return out


def summarize(case: dict[str, Any]) -> dict[str, Any]:
    decision = case.get("decision") or {}
    return {
        "id": case["id"],
        "question": case["question"],
        "mode": case.get("mode", "REAL"),
        "phase": case["phase"],
        "status": case["status"],
        "n_proposals": len(case.get("proposals", [])),
        "n_critiques": sum(len(v) for v in case.get("critiques", {}).values()),
        "n_revisions": len(case.get("revisions", {})),
        "decision": decision.get("decision"),
        "created_utc": case.get("created_utc"),
    }