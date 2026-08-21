"""Council CHANGE-VOTE workflow (audit fix 11).

The Council does NOT vote BUY/SELL on market bars and does not merely
brainstorm improvements. Workflow:

  RESEARCH/WATCHER/OX proposes a standardized CHANGE PROPOSAL
    -> council members review INDEPENDENTLY
    -> each votes: APPROVE_FOR_TEST | REJECT | REVISE_AND_RESUBMIT |
                   ABSTAIN_INSUFFICIENT_EVIDENCE | VETO_SAFETY
    -> cross critique + revision
    -> FINAL COUNCIL CHANGE DECISION

APPROVE_FOR_TEST authorises implementation as a CHALLENGER/EXPERIMENT only -
DATA validation still decides whether it works (never champion promotion).

Safety vetoes win regardless of majority for changes attempting to:
enable live trading, martingale, recovery sizing, disable stale-quote
protection, disable risk caps, bypass OOS, bypass champion governance.

If fewer than 2 agents genuinely vote: status = DEGRADED_REAL_COUNCIL
(never presented as a multi-agent decision).
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ai_council import paths as council_paths
from ai_council.agents import ask_agent, probe_agent

VOTE_APPROVE = "APPROVE_FOR_TEST"
VOTE_REJECT = "REJECT"
VOTE_REVISE = "REVISE_AND_RESUBMIT"
VOTE_ABSTAIN = "ABSTAIN_INSUFFICIENT_EVIDENCE"
VOTE_VETO_SAFETY = "VETO_SAFETY"
VALID_VOTES = {VOTE_APPROVE, VOTE_REJECT, VOTE_REVISE, VOTE_ABSTAIN, VOTE_VETO_SAFETY}

FORBIDDEN_PATTERNS = (
    r"\ballow_live\s*[:=]\s*true",
    r"\bmartingale\b",
    r"\brecovery\s*sizing\b",
    r"\bdisable\s+(the\s+)?stale[- ]quote",
    r"\bdisable\s+(the\s+)?risk\s+caps?\b",
    r"\bbypass\s+OOS\b",
    r"\bbypass\s+(champion|sealed)",
)

PACK_FIELDS = ("change_id", "problem", "current_evidence", "proposed_change",
               "affected_files", "expected_mechanism", "risks", "tests",
               "falsification_criteria", "rollback", "safety_impact")

_VOTE_PROMPT = """You are a council member reviewing a proposed AEGIS change.
Vote independently. Safety violations override majority.

CHANGE PROPOSAL:
{pack_json}

Respond with ONLY a JSON object:
{{"vote": "APPROVE_FOR_TEST|REJECT|REVISE_AND_RESUBMIT|ABSTAIN_INSUFFICIENT_EVIDENCE|VETO_SAFETY",
  "confidence": 0.0-1.0,
  "reason": "...",
  "concerns": ["..."],
  "requested_revisions": ["..."]}}
"""


def validate_pack(pack: Mapping[str, Any]) -> list[str]:
    missing = [f for f in PACK_FIELDS if not str(pack.get(f) or "").strip()]
    return missing


def safety_violation(text: str) -> str | None:
    for pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, text or "", re.I):
            return pattern
    return None


def run_change_vote(
    pack: Mapping[str, Any],
    *,
    agents: list[str] | None = None,
    timeout_s: int = 300,
) -> dict[str, Any]:
    """Run one REAL change-vote round; persist the full artifact."""
    problems = validate_pack(pack)
    if problems:
        return {"ok": False, "error": f"pack incomplete, missing: {problems}"}
    violation = safety_violation(
        json.dumps({k: pack.get(k) for k in ("proposed_change", "safety_impact",
                                             "expected_mechanism")}, default=str)
    )

    agents_env = agents
    if not agents_env:
        env_names = [a.strip() for a in
                     os.environ.get("AEGIS_COUNCIL_AGENTS",
                                    "opencode,gemini,codex,cursor").split(",")
                     if a.strip()]
        agents_env = env_names
    votes: list[dict[str, Any]] = []
    prompt = _VOTE_PROMPT.format(
        pack_json=json.dumps(pack, indent=1, default=str))
    started = datetime.now(timezone.utc).isoformat()
    for name in agents_env:
        probe = probe_agent(name)
        status = probe.get("status")
        if status != "AVAILABLE":
            votes.append({"agent": name, "vote": None, "status": status,
                          "reason": probe.get("error") or status})
            continue
        result = ask_agent(name, prompt, timeout_s=timeout_s)
        parsed = result.get("parsed") or {}
        vote = str(parsed.get("vote") or "").upper()
        if result.get("status") != "AVAILABLE":
            votes.append({"agent": name, "vote": None,
                          "status": result.get("status"),
                          "reason": result.get("error")})
            continue
        if vote not in VALID_VOTES:
            votes.append({"agent": name, "vote": None, "status": "ERROR",
                          "reason": f"unparseable vote: {vote!r}",
                          "raw": (result.get("output") or "")[:400]})
            continue
        votes.append({
            "agent": name,
            "model": result.get("model"),
            "vote": vote,
            "confidence": parsed.get("confidence"),
            "reason": parsed.get("reason"),
            "concerns": parsed.get("concerns") or [],
            "requested_revisions": parsed.get("requested_revisions") or [],
        })

    counted = [v for v in votes if v.get("vote")]
    vetoed = any(v.get("vote") == VOTE_VETO_SAFETY for v in counted) or bool(violation)
    approve_n = sum(1 for v in counted if v["vote"] == VOTE_APPROVE)
    reject_n = sum(1 for v in counted if v["vote"] == VOTE_REJECT)
    revise_n = sum(1 for v in counted if v["vote"] == VOTE_REVISE)
    abstain_n = sum(1 for v in counted if v["vote"] == VOTE_ABSTAIN)

    if violation:
        final = "REJECTED_SAFETY"
        rationale = f"forbidden pattern {violation!r} in proposal"
    elif vetoed:
        final = "REJECTED_SAFETY"
        rationale = "council member cast VETO_SAFETY"
    elif len(counted) < 2:
        final = "DEGRADED_REAL_COUNCIL"
        rationale = "fewer than two members voted; not a multi-agent decision"
    else:
        decisive = approve_n + reject_n + revise_n
        if decisive == 0:
            final = "NO_DECISION"
            rationale = "all votes were abstentions"
        elif approve_n > max(reject_n, revise_n):
            final = "APPROVED_FOR_TEST"
            rationale = (f"majority APPROVE_FOR_TEST ({approve_n}/{decisive}); "
                         "implementation authorised as CHALLENGER/EXPERIMENT only")
        elif revise_n >= reject_n and revise_n > 0:
            final = "REVISE_AND_RESUBMIT"
            rationale = f"plurality requested revisions ({revise_n}/{decisive})"
        else:
            final = "REJECTED"
            rationale = f"majority REJECT ({reject_n}/{decisive})"

    artifact = {
        "schema": "council_change_vote.v1",
        "change_id": pack.get("change_id"),
        "started_utc": started,
        "finished_utc": datetime.now(timezone.utc).isoformat(),
        "pack": dict(pack),
        "votes": votes,
        "totals": {"approve_for_test": approve_n, "reject": reject_n,
                   "revise_and_resubmit": revise_n, "abstain": abstain_n,
                   "counted": len(counted)},
        "safety_violation": violation,
        "final_decision": final,
        "rationale": rationale,
        "degraded_real_council": len(counted) < 2,
    }
    out_dir = Path(council_paths.REPORTS) / "change_votes"
    out_dir.mkdir(parents=True, exist_ok=True)
    cid = re.sub(r"[^a-z0-9_-]+", "-", str(pack.get("change_id") or "change").lower())[:60]
    out_path = out_dir / f"{cid}.json"
    out_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")
    artifact["artifact"] = str(out_path)

    # Live feed visibility.
    try:
        with council_paths.LIVE_JSONL.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "id": f"change-vote-{cid}",
                "kind": "council_change_vote",
                "mode": "REAL",
                "final_decision": final,
                "degraded": artifact["degraded_real_council"],
                "totals": artifact["totals"],
                "finished_utc": artifact["finished_utc"],
            }) + "\n")
    except OSError:
        pass
    return artifact


def load_pack(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))
