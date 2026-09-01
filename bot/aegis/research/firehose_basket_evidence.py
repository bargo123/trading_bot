"""Full-corpus evidence packets for research-only Firehose basket hypotheses."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from aegis.research.books_index import BookIndex
from aegis.research.knowledge import search_full_book_knowledge


_ALLOWED_ORIGINS = frozenset({"BOOK_DIRECT", "NOVEL_SYNTHESIZED_HYPOTHESIS"})


def build_evidence_packet(
    index: BookIndex,
    hypothesis: Mapping[str, Any],
    support_query: str,
    contradiction_query: str,
    data_observation: Any,
    falsification: Any,
) -> dict[str, Any]:
    """Return a JSON-serializable packet with verbatim, index-backed provenance."""
    hypothesis_id = str(hypothesis.get("hypothesis_id") or hypothesis.get("id") or "").strip()
    origin = str(hypothesis.get("origin") or "").strip()
    if not hypothesis_id:
        raise ValueError("hypothesis_id is required")
    if origin not in _ALLOWED_ORIGINS:
        raise ValueError(f"origin must be one of {sorted(_ALLOWED_ORIGINS)}")

    supporting_evidence, support_candidates = _evidence_for_query(index, support_query, "SUPPORT")
    contradicting_evidence, contradiction_candidates = _evidence_for_query(
        index, contradiction_query, "CONTRADICTION"
    )
    coverage = "SUFFICIENT" if supporting_evidence else "INSUFFICIENT"
    if origin == "BOOK_DIRECT" and not supporting_evidence:
        raise ValueError("direct-source hypothesis requires supporting book evidence")

    packet = {
        "hypothesis_id": hypothesis_id,
        "origin": origin,
        "BOOK_COVERAGE": coverage,
        "supporting_evidence": supporting_evidence,
        "contradicting_evidence": contradicting_evidence,
        "contextual_candidates": support_candidates + contradiction_candidates,
        "data_observation": data_observation,
        "falsification": falsification,
    }
    try:
        json.dumps(packet)
    except (TypeError, ValueError) as exc:
        raise ValueError("evidence packet inputs must be JSON-serializable") from exc
    return packet


def _evidence_for_query(
    index: BookIndex, query: str, evidence_label: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    query = str(query or "").strip()
    if not query:
        return [], []

    rows = {
        (Path(str(row["path"])).name, str(row["file_hash"])): row
        for row in index.all_rows(include_body=True)
    }
    evidence: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for source in _sources_for_query(index, query, max(len(rows), 1)):
        key = (source.filename, source.file_hash)
        if key in seen:
            continue
        row = rows.get(key)
        if row is None:
            continue
        body = str(row.get("body") or "")
        passage = _complete_phrase_match(body, query)
        label = evidence_label
        if passage is None:
            passage = _fallback_term_match(body, query)
            label = "CONTEXTUAL_CANDIDATE"
        if passage is not None:
            line_number, text = passage
            record = {
                "filename": source.filename,
                "file_hash": source.file_hash,
                "source_id": source.file_hash,
                "evidence_label": label,
                "location": {"path": str(row["path"]), "line_start": line_number, "line_end": line_number},
                "passage": text,
            }
            if label == "CONTEXTUAL_CANDIDATE":
                record["query_role"] = evidence_label
                candidates.append(record)
            else:
                evidence.append(record)
        seen.add(key)
    return evidence, candidates


def _sources_for_query(index: BookIndex, query: str, limit: int):
    """Retrieve complete-query and fallback-term hits without a fixed corpus cap."""
    seen: set[tuple[str, str]] = set()
    for search_query in [query, *(piece for piece in query.split() if len(piece) >= 4)]:
        for source in search_full_book_knowledge(index, search_query, limit=limit):
            key = (source.filename, source.file_hash)
            if key not in seen:
                seen.add(key)
                yield source


def _complete_phrase_match(body: str, query: str) -> tuple[int, str] | None:
    phrase = query.casefold()
    for line_number, line in enumerate(body.splitlines(), start=1):
        if phrase in line.casefold():
            return line_number, line
    return None


def _fallback_term_match(body: str, query: str) -> tuple[int, str] | None:
    terms = [piece.casefold() for piece in query.split() if len(piece) >= 4]
    for line_number, line in enumerate(body.splitlines(), start=1):
        if any(term in line.casefold() for term in terms):
            return line_number, line
    return None
