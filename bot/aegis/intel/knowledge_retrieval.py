"""Runtime retrieval over the structured book-knowledge base (spec A: retrieval).

Loads the compiled bot/knowledge/*.jsonl ONCE per corpus version - never rereads
books at runtime. Retrieval is scored keyword overlap between the current state
(regime/session/structure/volatility/family) and record fields, with an LRU
cache keyed by (state_hash, corpus_version). A corpus version change
automatically invalidates every cache entry.
"""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

KNOWLEDGE_DIR = Path(__file__).resolve().parents[1] / "knowledge"
RECORD_FILES = (
    "strategy_hypotheses.jsonl",
    "entry_patterns.jsonl",
    "exit_patterns.jsonl",
    "risk_rules.jsonl",
    "execution_rules.jsonl",
    "validation_rules.jsonl",
)

_STATE_TERMS = {
    "regime": ("trend", "range", "momentum", "mean reversion", "reversal"),
    "session": (),
    "structure": ("breakout", "pullback", "retest", "support", "resistance",
                  "trendline", "range"),
    "volatility": ("volatility", "expansion", "contraction", "atr"),
    "family": (),
}


def corpus_version() -> str:
    try:
        manifest = json.loads((KNOWLEDGE_DIR / "corpus_manifest.json").read_text(encoding="utf-8"))
        return str(manifest.get("corpus_version") or "")
    except (OSError, json.JSONDecodeError):
        return ""


def _load_records(version: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for name in RECORD_FILES:
        path = KNOWLEDGE_DIR / name
        if not path.exists():
            continue
        try:
            with path.open(encoding="utf-8") as fh:
                for line in fh:
                    if not line.strip():
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    rec["_sink"] = name
                    records.append(rec)
        except OSError:
            continue
    return records


def _state_terms(state: Mapping[str, Any]) -> list[str]:
    terms: list[str] = []
    for key, extra in _STATE_TERMS.items():
        value = str(state.get(key) or "").lower()
        if value and value not in {"unknown", "none", ""}:
            terms.append(value)
        for e in extra:
            if e in value or (not value and False):
                terms.append(e)
    family = str(state.get("family") or "").lower()
    if family:
        terms.extend(t for t in family.replace("-", "_").split("_") if len(t) > 3)
    return sorted({t for t in terms if t})


def _score(record: dict[str, Any], terms: list[str]) -> int:
    blob = " ".join([
        str(record.get("chapter") or ""),
        str(record.get("section") or ""),
        str(record.get("passage_excerpt") or ""),
        str(record.get("conflict_topic") or ""),
        ",".join(record.get("exit_categories") or []),
    ]).lower()
    return sum(1 for t in terms if t in blob)


def _state_hash(state: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(dict(state), sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


@lru_cache(maxsize=512)
def _cached_retrieve(state_json: str, version: str, limit: int) -> tuple[dict[str, Any], ...]:
    state = json.loads(state_json)
    terms = _state_terms(state)
    if not terms:
        return ()
    scored = []
    for rec in _load_records(version):
        s = _score(rec, terms)
        if s > 0:
            scored.append((s, rec))
    scored.sort(key=lambda pair: -pair[0])
    out = []
    for s, rec in scored[:limit]:
        copy = dict(rec)
        copy["_score"] = s
        out.append(copy)
    return tuple(out)


def retrieve_for_state(state: Mapping[str, Any], *, limit: int = 6) -> list[dict[str, Any]]:
    """Relevant knowledge records for the current market state.

    Cache key = (state hash, corpus_version): a corpus rebuild changes the
    version and invalidates all cached retrievals automatically.
    """
    version = corpus_version()
    if not version:
        return []
    hits = _cached_retrieve(json.dumps(dict(state), sort_keys=True), version, limit)
    return [dict(h) for h in hits]


def exit_plan_for_state(state: Mapping[str, Any]) -> dict[str, Any] | None:
    """Derive an explicit executable exit plan hint from matched EXIT knowledge."""
    hits = [h for h in retrieve_for_state(state, limit=8)
            if h.get("concept_type") == "EXIT_PRINCIPLE"]
    if not hits:
        return None
    top = hits[0]
    cats = top.get("exit_categories") or []
    plan_type = "structural"
    if "trailing_stops" in cats:
        plan_type = "trailing_structural_stop"
    elif "time_stops" in cats:
        plan_type = "time_stop"
    elif "taking_profits" in cats:
        plan_type = "profit_target"
    return {
        "plan_type": plan_type,
        "source_book": top.get("book"),
        "source_passage_hash": top.get("passage_hash"),
        "exit_categories": cats,
        "excerpt": (top.get("passage_excerpt") or "")[:200],
    }
