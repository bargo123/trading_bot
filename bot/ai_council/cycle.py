"""Council cycle driver: run one case through proposal -> critique -> revision.

REAL mode (default) invokes every AVAILABLE configured CLI agent and persists
each actual proposal/critique/revision. DRY_RUN happens ONLY when explicitly
requested (dry_run=True) and is tagged in the case record so it can never be
mistaken for real research.

Unavailable agents are recorded with their real status (UNAVAILABLE_QUOTA,
AUTH_REQUIRED, TIMEOUT, ERROR, UNAVAILABLE_CLI) and never substituted with
fabricated output. The final decision is left to DATA (validation), never to
voting.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ai_council import agents as agent_cli
from ai_council import cases as case_store
from ai_council.knowledge import corpus as knowledge

CASES_DIR = case_store.CASES_DIR

PROPOSAL_PROMPT = (
    "You are a member of the AEGIS trading-system council. "
    "Answer the case question below as a SINGLE short, concrete, falsifiable "
    "proposal (3-6 sentences). You may cite the book corpus by title. "
    "Never propose live-money trading, never propose raising allow_live, never "
    "propose paid services. Case question:\n\n{question}\n\n"
    "Relevant corpus passages:\n{passages}\n\n"
    "Reply with only the proposal text."
)

CRITIQUE_PROMPT = (
    "You are a hostile reviewer on the AEGIS council. Below is a proposal by "
    "another member. Identify concrete flaws: overfitting risk, unmeasurable "
    "claims, missing validation, safety violations. 2-4 sentences.\n\n"
    "Proposal:\n{proposal}\n\n"
    "Reply with only the critique text."
)

_REPLY_KEYS = ("proposal", "critique", "revision", "answer", "text", "response", "reply")


def _gather_passages(question: str, limit: int = 3) -> str:
    hits = knowledge.retrieve(question, limit=limit)
    if not hits:
        return "(no direct corpus passages matched)"
    blocks = []
    for hit in hits:
        blocks.append(f"[{hit['book']}]\n{hit['passage'][:600]}")
    return "\n\n".join(blocks)


def _meta_from_result(result: dict[str, Any], mode: str) -> dict[str, Any]:
    """Persistable per-agent execution metadata (no credentials, no secrets)."""
    return {
        "mode": mode,
        "provider": result.get("provider"),
        "model": result.get("model"),
        "tool_version": result.get("tool_version"),
        "cli_class": result.get("cli_class"),
        "started_utc": result.get("started_utc"),
        "finished_utc": result.get("finished_utc"),
        "duration_s": result.get("duration_s"),
        "returncode": result.get("returncode"),
    }


def _extract_reply(result: dict[str, Any]) -> str:
    """Extract the agent's actual reply text from a real invocation result."""
    parsed = result.get("parsed")
    if isinstance(parsed, dict):
        for key in _REPLY_KEYS:
            value = parsed.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return (result.get("output") or "").strip()


def _is_refusal(text: str) -> bool:
    lowered = (text or "").lower()
    refusal = (
        "question didn't come through", "question appears to be cut off",
        "cut off", "didn't come through", "no actual question", "no proposal",
        "please paste", "no proposal text came through", "nothing for me to attack",
        "haven't included", "don't see a proposal", "i don't see",
        "could you provide", "could you share", "paste the",
    )
    return any(marker in lowered for marker in refusal)


_ACTION_KEYWORDS = (
    "falsifiable", "test", "measure", "validation", "validate", "experiment",
    "backtest", "walk-forward", "holdout", "oos", "bootstrap", "p05",
    "expectancy", "hypothesis", "instrument", "build", "pre-register",
    "candidate", "sample", "cost model", "compare", "reject", "accept",
)
_SUBJECT_KEYWORDS = (
    "state", "session", "regime", "exit", "entry", "algo", "algorithm",
    "indicator", "filter", "tp", "sl", "stop", "flatten", "eurusd", "eurjpy",
    "m1", "m5", "m15", "catalogue", "meta-filter", "rsi", "adx", "atr",
    "volatility", "signal", "strategy",
)
_NEEDS_DATA_MARKERS = (
    "needs backfilling", "needs backfill", "missing", "no data", "cannot be",
    "can't be reconstructed", "requires", "needs more", "need more",
    "insufficient", "not enough", "no timestamps", "{}",
)


def _assess_candidate(text: str) -> dict[str, Any]:
    """Classify one agent text as a falsifiable candidate or not."""
    lowered = (text or "").lower()
    if _is_refusal(text) or len(text) < 120:
        return {"candidate": False, "reason": "refusal_or_too_short"}
    actions = [k for k in _ACTION_KEYWORDS if k in lowered]
    subjects = [k for k in _SUBJECT_KEYWORDS if k in lowered]
    if not actions or not subjects:
        return {"candidate": False, "reason": "not_falsifiable"}
    needs_data = [k for k in _NEEDS_DATA_MARKERS if k in lowered]
    return {"candidate": True, "actions": actions[:5], "subjects": subjects[:5],
            "needs_data": needs_data[:3]}


def _duplicate_hypothesis(text: str, *, threshold: float = 0.55) -> dict[str, Any]:
    """Check the candidate against prior experiment/challenger hypotheses."""
    import re as _re

    from aegis.intel.champion import load_champion
    from aegis.intel.paths import INTEL_DIR

    def tokens(blob: str) -> set[str]:
        words = _re.findall(r"[a-z0-9]{3,}", (blob or "").lower())
        stop = {"the", "and", "for", "with", "that", "this", "from", "are",
                "was", "has", "had", "not", "but", "you", "your", "proposal",
                "would", "could", "should", "have", "will", "they", "their"}
        return {w for w in words if w not in stop}

    cand_tokens = tokens(text)
    if len(cand_tokens) < 6:
        return {"duplicate": False}
    prior: list[tuple[str, str, str]] = []
    exp_path = INTEL_DIR / "experiments.jsonl"
    if exp_path.exists():
        for line in exp_path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            hyp = str(row.get("hypothesis") or "")
            if hyp:
                prior.append((str(row.get("id") or "?"), hyp,
                              str(row.get("status") or "?")))
    champion = load_champion()
    if champion:
        hyp = str(champion.get("hypothesis") or champion.get("lesson") or "")
        if hyp:
            prior.append(("champion", hyp, "champion"))
    for pid, hyp, status in prior:
        overlap = len(cand_tokens & tokens(hyp)) / len(cand_tokens)
        if overlap >= threshold:
            return {"duplicate": True, "prior_id": pid, "prior_status": status,
                    "overlap": round(overlap, 2)}
    return {"duplicate": False}


def _decide(case: dict[str, Any], mode: str) -> dict[str, Any]:
    """DATA decides. defer_validation is used ONLY when a falsifiable candidate
    was found and registered as a challenger for the validation pipeline.
    Otherwise a specific reason code is recorded (no generic catch-all).
    DRY_RUN rounds never register challengers: simulated text is not research."""
    revisions = case.get("revisions", {})
    proposals = case.get("proposals", [])
    texts = [r.get("text", "") for r in revisions.values()] or [
        p.get("text", "") for p in proposals
    ]
    if not texts:
        return {
            "decision": "no_change",
            "reason": "NO_ROBUST_CANDIDATE",
            "rationale": f"{mode}: no agent produced a proposal; nothing to decide",
        }
    if mode == "DRY_RUN":
        return {
            "decision": "defer_validation",
            "reason": "DRY_RUN_SIMULATION",
            "rationale": (f"{mode}: simulated round; no challenger registered "
                          "because simulated text can never count as research"),
        }
    assessed = [_assess_candidate(t) for t in texts]
    candidates = [a for a in assessed if a["candidate"]]
    if not candidates:
        needs_data = any(a.get("needs_data") for a in assessed)
        reason = "NEEDS_MORE_DATA" if needs_data else "NO_ROBUST_CANDIDATE"
        rationale = (
            f"{mode}: none of the proposals is a falsifiable, measurable candidate"
            + ("; agents flagged missing data/backfill" if needs_data else "")
        )
        return {"decision": "no_change", "reason": reason, "rationale": rationale}

    best = candidates[0]
    text = texts[assessed.index(best)]
    dup = _duplicate_hypothesis(text)
    if dup.get("duplicate"):
        return {
            "decision": "no_change",
            "reason": "DUPLICATE_FAILED_HYPOTHESIS",
            "rationale": (f"{mode}: candidate hypothesis overlaps prior record "
                          f"{dup.get('prior_id')} ({dup.get('prior_status')}, "
                          f"overlap {dup.get('overlap')}); not re-tested"),
        }

    # A falsifiable, non-duplicate candidate exists -> register the challenger.
    from aegis.intel.champion import append_experiment
    from aegis.intel.paths import INTEL_DIR

    import uuid as _uuid

    cid = case["id"]
    slug = cid.split("_", 1)[0] or "council"
    challenger_id = f"council_{slug}_{_uuid.uuid4().hex[:6]}"
    payload = {
        "id": challenger_id,
        "kind": "council",
        "hypothesis": text[:2000],
        "inspiration": {
            "source": "ai_council",
            "case": cid,
            "question": case.get("question"),
            "agents": [p.get("agent") for p in proposals],
        },
        "decision": "defer_validation",
        "reason": "council candidate queued for the validation pipeline",
        "council_case": cid,
        "role": "CHALLENGER",
        "updated_utc": datetime.now(timezone.utc).isoformat(),
    }
    challenger_log = append_experiment(
        {
            "id": challenger_id,
            "ts_utc": payload["updated_utc"],
            "hypothesis": text[:500],
            "status": "queued",
            "source": "ai_council",
            "council_case": cid,
            "metrics": {},
            "provenance": {"placed_orders": False, "promoted_live_yaml": False},
        }
    )
    return {
        "decision": "defer_validation",
        "reason": "CHALLENGER_CREATED",
        "challenger_id": challenger_id,
        "challenger_log": str(challenger_log),
        "rationale": (f"{mode}: falsifiable candidate registered as challenger "
                      f"{challenger_id} for the validation pipeline"),
    }


def run_council_cycle(question: str, *, agents: list[str] | None = None,
                      timeout_s: int = 240, dry_run: bool = False) -> dict[str, Any]:
    """Run one full council round for a question. REAL execution by default.

    dry_run=True is the ONLY way to get simulated output; it is tagged DRY_RUN
    in the case record and can never be mistaken for real research.
    """
    question = (question or "").strip()
    if not question:
        raise ValueError("question is required")
    mode = "DRY_RUN" if dry_run else "REAL"
    config = agent_cli.load_agents_config()
    default_names = ("hermes", "opencode", "gemini", "codex", "cursor")
    if agents is not None:
        names = list(agents)
    elif "hermes" in config:
        names = [name for name in default_names if name in config]
    else:
        # Preserve custom/test registries that intentionally declare a smaller
        # agent set; the production registry is the one with Hermes enabled.
        names = list(config.keys())
    started = datetime.now(timezone.utc).isoformat()
    t_start = time.time()

    case = case_store.new_case(question, mode=mode)
    round_log: list[dict[str, Any]] = []

    def log(step: str, result: dict[str, Any], **extra: Any) -> None:
        entry: dict[str, Any] = {"step": step, "mode": mode, **result, **extra}
        entry.pop("output", None)
        entry.pop("parsed", None)
        round_log.append(entry)

    # Phase 1: independent proposals from AVAILABLE agents only.
    proposers = []
    for name in names:
        if dry_run:
            text = _dry_proposal(name, question)
            case = case_store.add_proposal(case, agent=name, text=text)
            proposers.append(name)
            log("proposal", {"agent": name, "status": "DRY_RUN",
                             "file": case["proposals"][-1].get("file"),
                             "duration_s": 0.0})
            continue
        probe = agent_cli.probe_agent(name)
        if probe.get("status") != "AVAILABLE":
            log("proposal", {"agent": name, "status": probe.get("status"),
                             "error": f"probe: {probe.get('status')}"
                                      + (f" ({probe.get('error')})" if probe.get("error") else "")})
            continue
        passages = _gather_passages(question)
        prompt = PROPOSAL_PROMPT.format(question=question, passages=passages)
        result = agent_cli.ask_agent(name, prompt, timeout_s=timeout_s)
        if not result.get("ok"):
            log("proposal", result)
            continue
        text = _extract_reply(result)[:4000]
        if not text:
            log("proposal", {**result, "status": "ERROR",
                             "error": "agent returned empty output"})
            continue
        case = case_store.add_proposal(case, agent=name, text=text,
                                       meta=_meta_from_result(result, mode))
        proposers.append(name)
        log("proposal", {**result, "file": case["proposals"][-1].get("file")})

    if not case.get("proposals"):
        case = case_store.move_phase(case, "critique")
        case = case_store.move_phase(case, "revision")
        case = case_store.move_phase(case, "decision")
        decision = _decide(case, mode)
        case = case_store.decide(
            case,
            decision=decision["decision"],
            rationale=decision["rationale"],
            evidence={"mode": mode, "available_agents": 0, **{k: v for k, v in decision.items()
                                                             if k not in {"decision", "rationale"}}},
        )
        return _result(case, started, t_start, round_log)

    # Phase 2: adversarial critique (each proposer critiques every other proposal).
    case = case_store.move_phase(case, "critique")
    for target in case.get("proposals", []):
        target_text = target.get("text", "")
        for author in proposers:
            if author == target.get("agent"):
                continue
            if dry_run:
                text = _dry_critique(author, target_text)
                case = case_store.add_critique(case, agent=author,
                                               target=target.get("agent"), text=text)
                log("critique", {"agent": author, "status": "DRY_RUN",
                                 "target": target.get("agent"),
                                 "file": case["critiques"][target.get("agent")][-1].get("file"),
                                 "duration_s": 0.0})
                continue
            result = agent_cli.ask_agent(
                author, CRITIQUE_PROMPT.format(proposal=target_text), timeout_s=timeout_s
            )
            if not result.get("ok"):
                log("critique", {**result, "target": target.get("agent")})
                continue
            text = _extract_reply(result)[:2000]
            if not text:
                continue
            case = case_store.add_critique(case, agent=author,
                                           target=target.get("agent"), text=text,
                                           meta=_meta_from_result(result, mode))
            log("critique", {**result, "target": target.get("agent"),
                             "file": case["critiques"][target.get("agent")][-1].get("file")})

    # Phase 3: revision (author revises only when critique exists).
    case = case_store.move_phase(case, "revision")
    for proposal in case.get("proposals", []):
        author = proposal.get("agent")
        critiques = case.get("critiques", {}).get(author, [])
        if dry_run:
            case = case_store.add_revision(case, agent=author,
                                           text=f"revised: {proposal.get('text')[:500]}")
            log("revision", {"agent": author, "status": "DRY_RUN",
                             "file": case["revisions"][author].get("file"),
                             "duration_s": 0.0})
            continue
        if not critiques:
            log("revision", {"agent": author, "status": "SKIPPED",
                             "error": "no critiques received for this proposal"})
            continue
        combined = "\n".join(c.get("text") for c in critiques)
        result = agent_cli.ask_agent(
            author,
            "You are the author of this proposal. Address the critique and "
            f"return a revised proposal (3-6 sentences).\n\nProposal:\n{proposal.get('text')}\n\n"
            f"Critique:\n{combined}\n\nReply with only the revised text.",
            timeout_s=timeout_s,
        )
        if not result.get("ok"):
            log("revision", result)
            continue
        text = _extract_reply(result)[:4000]
        if not text:
            continue
        case = case_store.add_revision(case, agent=author, text=text,
                                       meta=_meta_from_result(result, mode))
        log("revision", {**result, "file": case["revisions"][author].get("file")})

    # Phase 4: DATA decides. defer_validation means a challenger was registered;
    # otherwise a specific reason code is recorded (no generic catch-all).
    case = case_store.move_phase(case, "decision")
    decision = _decide(case, mode)
    case = case_store.decide(
        case,
        decision=decision["decision"],
        rationale=decision["rationale"],
        evidence={
            "mode": mode,
            "n_proposals": len(case.get("proposals", [])),
            "n_critiques": sum(len(v) for v in case.get("critiques", {}).values()),
            "n_revisions": len(case.get("revisions", {})),
            **{k: v for k, v in decision.items() if k not in {"decision", "rationale"}},
        },
    )
    return _result(case, started, t_start, round_log)


def _dry_proposal(agent: str, question: str) -> str:
    return (
        f"Local deterministic proposal by {agent}: treat '{question}' as a "
        "falsifiable rule candidate; before any live change, run an OOS validation "
        "window on the analogue index and require bootstrap_p05 > 0 and positive "
        "expectancy before promotion. No live-money changes."
    )


def _dry_critique(author: str, proposal: str) -> str:
    return (
        f"Review by {author}: the proposal lacks a concrete measurement window "
        "and does not state the rejection threshold; require a predefined "
        "validation sample and pre-registered accept/reject criteria."
    )


def _result(case: dict[str, Any], started: str, t_start: float,
            round_log: list[dict[str, Any]]) -> dict[str, Any]:
    summary = case_store.summarize(case)
    summary.update(
        {
            "mode": case.get("mode", "REAL"),
            "started_utc": started,
            "finished_utc": datetime.now(timezone.utc).isoformat(),
            "duration_s": round(time.time() - t_start, 2),
            "round_log": round_log,
            "case_file": str(CASES_DIR / f"case_{case['id']}" / "case.json"),
        }
    )
    return summary


def dump_live(case_summary: dict[str, Any], *, case: dict[str, Any] | None = None) -> Path:
    """Append the round (with per-agent activity) to live.jsonl and latest.md."""
    from ai_council import paths as council_paths

    record = dict(case_summary)
    if case is not None and record.get("finished_utc") is None:
        record["finished_utc"] = case.get("decision", {}).get("decided_utc")
    activity = []
    for entry in case_summary.get("round_log", []):
        activity.append(
            {
                "step": entry.get("step"),
                "agent": entry.get("agent"),
                "target": entry.get("target"),
                "status": entry.get("status"),
                "mode": entry.get("mode"),
                "model": entry.get("model"),
                "duration_s": entry.get("duration_s"),
                "file": entry.get("file"),
                "error": entry.get("error"),
            }
        )
    record["activity"] = activity
    council_paths.LIVE_JSONL.parent.mkdir(parents=True, exist_ok=True)
    with council_paths.LIVE_JSONL.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")
    latest = council_paths.LATEST_MD
    decision = record.get("decision")
    reason = ""
    challenger_id = ""
    if isinstance(decision, dict):
        evidence = decision.get("evidence") or {}
        reason = evidence.get("reason") or ""
        challenger_id = evidence.get("challenger_id") or ""
    lines = [
        "# AEGIS council - latest round",
        "",
        f"- id: {record.get('id')}",
        f"- question: {record.get('question')}",
        f"- mode: {record.get('mode')}",
        f"- phase: {record.get('phase')}",
        f"- status: {record.get('status')}",
        f"- decision: {decision.get('decision') if isinstance(decision, dict) else decision}",
        f"- decision_reason: {reason}",
        f"- challenger: {challenger_id or '-'}",
        f"- proposals: {record.get('n_proposals')}",
        f"- critiques: {record.get('n_critiques')}",
        f"- revisions: {record.get('n_revisions')}",
        f"- duration_s: {record.get('duration_s')}",
        f"- finished: {record.get('finished_utc')}",
        "",
    ]
    latest.write_text("\n".join(lines), encoding="utf-8")
    return council_paths.LATEST_MD
