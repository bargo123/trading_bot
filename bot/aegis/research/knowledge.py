"""Book-backed hypothesis inputs with source hashes and explicit limitations.

The full extract remains the evidence source in the local book index.  This module
does not turn author prose into a trading claim: it produces provenance-bound,
testable research hypotheses for a separate challenger cycle.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from aegis.research.books_index import BookIndex

@dataclass(frozen=True)
class SourceKnowledge:
    filename: str
    file_hash: str
    title: str
    concepts: tuple[str, ...]
    data_requirements: tuple[str, ...]
    setup: str
    entry: str
    exit: str
    risk: str
    limitations: tuple[str, ...]
    label: str


@dataclass(frozen=True)
class BookHypothesis:
    hypothesis_id: str
    source: SourceKnowledge
    market_conditions: Mapping[str, Any]
    falsifiable_claim: str
    outcome: str
    label: str = "research_proxy"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_source_knowledge(notes_dir: Path) -> list[SourceKnowledge]:
    """Load locally generated notes; missing/placeholder sources stay unavailable."""
    out: list[SourceKnowledge] = []
    for path in sorted(Path(notes_dir).glob("*.json")):
        if path.name.startswith("_"):
            continue
        try:
            row = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(row, dict) or not row.get("file_hash"):
            continue
        claims = row.get("claims") if isinstance(row.get("claims"), dict) else {}
        out.append(
            SourceKnowledge(
                filename=str(row.get("filename") or path.with_suffix(".md").name),
                file_hash=str(row["file_hash"]),
                title=str(row.get("title") or ""),
                concepts=tuple(str(item) for item in (claims.get("headings") or [])),
                data_requirements=tuple(str(item) for item in (row.get("data_required") or [])),
                setup=str(row.get("setup") or ""),
                entry=str(row.get("entry") or ""),
                exit=str(row.get("exit") or ""),
                risk=str(row.get("risk") or ""),
                limitations=tuple(str(item) for item in (row.get("warnings") or [])),
                label=str(row.get("label") or "research_proxy"),
            )
        )
    return out


def search_full_book_knowledge(index: BookIndex, query: str, *, limit: int = 8) -> list[SourceKnowledge]:
    """Search full indexed extract bodies and retain their immutable file hashes."""
    out: list[SourceKnowledge] = []
    rows = index.search(query, limit=limit)
    if not rows:
        # An exact phrase may be absent even when the full sources discuss its
        # constituent concepts. Keep sources distinct; this is retrieval, not a vote.
        seen: set[str] = set()
        for term in (piece.strip() for piece in query.split() if len(piece.strip()) >= 4):
            for row in index.search(term, limit=limit):
                path = str(row.get("path") or "")
                if path not in seen:
                    rows.append(row)
                    seen.add(path)
                if len(rows) >= limit:
                    break
            if len(rows) >= limit:
                break
    for row in rows:
        if row.get("placeholder"):
            continue
        claims = row.get("claims") if isinstance(row.get("claims"), dict) else {}
        out.append(
            SourceKnowledge(
                filename=Path(str(row["path"])).name,
                file_hash=str(row["file_hash"]),
                title=str(row.get("title") or ""),
                concepts=tuple(str(item) for item in (claims.get("headings") or [])),
                data_requirements=tuple(str(item) for item in (claims.get("data_required") or [])),
                setup=str(claims.get("setup") or ""),
                entry=str(claims.get("entry") or ""),
                exit=str(claims.get("exit") or ""),
                risk=str(claims.get("risk") or ""),
                limitations=tuple(str(item) for item in (claims.get("warnings") or [])),
                label="research_proxy",
            )
        )
    return out


def hypotheses_for_market(
    knowledge: Iterable[SourceKnowledge],
    *,
    regime: str,
    required_data: set[str],
) -> list[BookHypothesis]:
    """Create only testable source-bound proposals; never auto-promote a trade."""
    out: list[BookHypothesis] = []
    for source in knowledge:
        if source.label == "unavailable":
            continue
        needs = set(source.data_requirements)
        data_available = not needs or needs.issubset(required_data)
        conditions = {
            "regime": regime,
            "data_requirements": sorted(needs),
            "data_available": data_available,
        }
        claim = (
            f"Under {regime} conditions, the entry conditions extracted from "
            f"{source.filename} have positive costed expectancy on an untouched holdout."
        )
        out.append(
            BookHypothesis(
                hypothesis_id=f"book:{source.file_hash[:12]}:{regime}",
                source=source,
                market_conditions=conditions,
                falsifiable_claim=claim,
                outcome=(
                    "costed holdout expectancy, loss distribution, and calibration"
                    if data_available
                    else "unavailable until required market data is available"
                ),
                label="research_proxy" if data_available else "unavailable",
            )
        )
    return out


def compile_knowledge_table(sources: Iterable[SourceKnowledge]) -> list[dict[str, Any]]:
    """Deterministic artifact rows. Placeholders and unhashed sources are dropped."""
    rows: list[dict[str, Any]] = []
    for source in sources:
        if source.label == "unavailable" or not str(source.file_hash).strip():
            continue
        rows.append(
            {
                "filename": source.filename,
                "file_hash": source.file_hash,
                "title": source.title,
                "concepts": list(source.concepts),
                "data_requirements": list(source.data_requirements),
                "setup": source.setup,
                "entry": source.entry,
                "invalidation": source.exit,
                "exit": source.exit,
                "risk": source.risk,
                "limitations": list(source.limitations),
                "label": source.label,
                "strategy_modules": list(_modules_for_concepts(source.concepts)),
            }
        )
    return rows


_SECTION_RE_TEMPLATE = r"^#{{1,3}}\s+.*{name}[^\n]*\n((?:.*\n)*?)(?=^#|\Z)"

CONCEPT_KEYWORDS = (
    ("failed break", "failed_break"),
    ("failed-break", "failed_break"),
    ("failure", "failed_break"),
    ("retest", "retest"),
    ("pullback", "pullback"),
    ("range", "range"),
    ("trend", "trend"),
    ("breakout", "breakout"),
    ("volume", "volume"),
    ("market profile", "profile"),
    ("tpo", "profile"),
    ("vwap", "vwap"),
    ("mean reversion", "mean_reversion"),
    ("momentum", "momentum"),
    ("support", "support_resistance"),
    ("resistance", "support_resistance"),
    ("invalidation", "invalidation"),
)

CONCEPT_TO_MODULES = {
    "failed_break": ("brooks_range",),
    "retest": ("damir_retest",),
    "range": ("brooks_range",),
    "volume": ("vpa_effort",),
    "profile": ("profile_excess",),
    "trend": ("htf_bias",),
    "breakout": ("damir_retest",),
}


def extract_named_section(text: str, name: str) -> str:
    """Pull a heading-named section; empty string if the extract has no such heading."""
    import re

    match = re.search(_SECTION_RE_TEMPLATE.format(name=re.escape(name)), text, flags=re.I | re.M)
    if not match:
        return ""
    return " ".join(match.group(1).split())[:400]


def extract_book_sections(body: str) -> dict[str, str]:
    setup = extract_named_section(body, "setup")
    entry = extract_named_section(body, "entry")
    exit_ = extract_named_section(body, "exit") or extract_named_section(body, "invalidation")
    risk = extract_named_section(body, "risk") or extract_named_section(body, "stop")
    prose = extract_prose_snippets(body)
    return {
        "setup": setup or prose.get("setup") or "",
        "entry": entry or prose.get("entry") or "",
        "exit": exit_ or prose.get("invalidation") or prose.get("exit") or "",
        "risk": risk or prose.get("stop") or prose.get("risk") or "",
        "confirmation": prose.get("confirmation") or "",
        "target": prose.get("target") or "",
        "scale_in": prose.get("scale_in") or "",
        "scale_out": prose.get("scale_out") or "",
        "session": prose.get("session") or "",
        "limitations": prose.get("limitations") or "",
    }


_PROSE_BUCKETS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("setup", ("setup", "the pattern", "look for", "when the market", "in a trend", "in a range")),
    ("entry", ("enter", "entry", "buy when", "sell when", "trigger", "initiate")),
    ("invalidation", ("invalidat", "thesis is wrong", "if the market closes", "failed break", "stop out")),
    ("exit", ("exit", "get out", "close the trade", "abandon")),
    ("stop", ("stop-loss", "stop loss", "protective stop", "place the stop")),
    ("risk", ("risk", "position size", "fraction of capital", "do not risk")),
    ("target", ("target", "take profit", "profit objective", "measured move")),
    ("confirmation", ("confirm", "confirmation", "effort versus result", "volume confirms")),
    ("scale_in", ("add to", "scale in", "pyramid", "increase exposure", "add on a pullback")),
    ("scale_out", ("scale out", "take partial", "reduce the position", "bank a portion")),
    ("session", ("london", "new york", "asian session", "overlap", "rth")),
    ("limitations", ("does not work", "fails when", "caveat", "limitation", "discretionary")),
)


def _sentences(text: str) -> list[str]:
    blob = " ".join(str(text or "").split())
    parts = re.split(r"(?<=[.!?])\s+", blob)
    return [part.strip() for part in parts if len(part.strip()) >= 40]


def extract_prose_snippets(body: str, *, limit: int = 3, cap: int = 420) -> dict[str, str]:
    """Mine usable setup/entry/invalidation prose when books lack ## Setup headings."""
    sentences = _sentences(body)
    out: dict[str, str] = {}
    for bucket, needles in _PROSE_BUCKETS:
        hits: list[str] = []
        for sentence in sentences:
            lower = sentence.lower()
            if any(needle in lower for needle in needles):
                hits.append(sentence)
            if len(hits) >= limit:
                break
        if hits:
            out[bucket] = " ".join(hits)[:cap]
    return out


STRATEGY_FAMILIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("trend_continuation", ("trend", "continuation", "with-trend", "momentum")),
    ("trend_pullback", ("pullback", "retracement", "dip")),
    ("failed_breakout", ("failed break", "failure", "false break", "spring")),
    ("range_edge_fade", ("range", "fade", "mean reversion")),
    ("breakout_continuation", ("breakout", "break-out")),
    ("breakout_retest", ("retest", "backtest")),
    ("volatility_expansion", ("expansion", "volatility break")),
    ("volatility_compression", ("compression", "squeeze", "narrow range")),
    ("volume_effort_result", ("effort versus result", "volume spread", "vsa")),
    ("market_profile_rejection", ("market profile", "excess", "value area")),
    ("session_breakout", ("london", "new york open", "session")),
    ("multi_timeframe_alignment", ("higher timeframe", "multiple time frame", "htf")),
)


def expand_strategy_hypotheses(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """One book may yield many competing hypotheses. Disagreement is stored, never averaged."""
    expanded: list[dict[str, Any]] = []
    for row in rows:
        blob = " ".join(
            [
                str(row.get("title") or ""),
                " ".join(str(item) for item in (row.get("concepts") or [])),
                str(row.get("setup") or ""),
                str(row.get("entry") or ""),
                str(row.get("invalidation") or ""),
            ]
        ).lower()
        matched = [name for name, needles in STRATEGY_FAMILIES if any(needle in blob for needle in needles)]
        families = matched or ["unclassified_scan"]
        for family in families:
            item = dict(row)
            item["strategy_family"] = family
            item["hypothesis_id"] = f"{str(row.get('file_hash') or '')[:12]}:{family}"
            item["classification"] = "mechanical" if "rule" in blob or "system" in blob else "mixed"
            item["claims_requiring_validation"] = True
            expanded.append(item)
    return expanded


def extract_concepts(headings: str, body: str, claim_headings: Iterable[str] | None = None) -> tuple[str, ...]:
    blob = f"{headings}\n{body}".lower()
    found: list[str] = []
    for needle, tag in CONCEPT_KEYWORDS:
        if needle in blob and tag not in found:
            found.append(tag)
    extra = [
        str(item).strip()
        for item in (claim_headings or [])
        if str(item).strip() and not re.match(r"^page\s+\d+$", str(item).strip(), flags=re.I)
    ]
    return tuple(dict.fromkeys([*found, *extra[:12]]))


def _modules_for_concepts(concepts: Iterable[str]) -> tuple[str, ...]:
    out: list[str] = []
    for concept in concepts:
        key = str(concept).lower().replace(" ", "_")
        for module in CONCEPT_TO_MODULES.get(key, ()):
            if module not in out:
                out.append(module)
    return tuple(out)


def compile_from_index(index: BookIndex, notes_dir: Path | None = None) -> list[dict[str, Any]]:
    """Compile hashed extracts into strategy-hypothesis rows. Indexing is not implementation."""
    notes_by_hash: dict[str, SourceKnowledge] = {}
    if notes_dir is not None:
        notes_by_hash = {source.file_hash: source for source in load_source_knowledge(notes_dir)}
    sources: list[SourceKnowledge] = []
    extras: dict[str, dict[str, str]] = {}
    for row in index.all_rows(include_body=True):
        if row.get("placeholder") or row.get("duplicate_of"):
            continue
        file_hash = str(row.get("file_hash") or "").strip()
        if not file_hash:
            continue
        claims = row.get("claims") if isinstance(row.get("claims"), dict) else {}
        body = str(row.get("body") or "")
        sections = extract_book_sections(body)
        extras[file_hash] = sections
        note = notes_by_hash.get(file_hash)
        concepts = extract_concepts(
            str(row.get("headings") or ""),
            body,
            claims.get("headings") if isinstance(claims.get("headings"), list) else None,
        )
        sources.append(
            SourceKnowledge(
                filename=Path(str(row.get("path") or "")).name,
                file_hash=file_hash,
                title=str(row.get("title") or ""),
                concepts=concepts,
                data_requirements=tuple(str(item) for item in (claims.get("data_required") or [])),
                setup=sections["setup"] or str(claims.get("setup") or "") or (note.setup if note else ""),
                entry=sections["entry"] or str(claims.get("entry") or "") or (note.entry if note else ""),
                exit=sections["exit"] or str(claims.get("exit") or "") or (note.exit if note else ""),
                risk=sections["risk"] or str(claims.get("risk") or "") or (note.risk if note else ""),
                limitations=tuple(str(item) for item in (claims.get("warnings") or []))
                or tuple(filter(None, [sections.get("limitations") or ""])),
                label="research_proxy",
            )
        )
    table = compile_knowledge_table(sources)
    for item in table:
        extra = extras.get(str(item.get("file_hash") or ""), {})
        item["confirmation"] = extra.get("confirmation") or ""
        item["stop_logic"] = extra.get("stop") or item.get("risk") or ""
        item["target_logic"] = extra.get("target") or ""
        item["scale_in_logic"] = extra.get("scale_in") or ""
        item["scale_out_logic"] = extra.get("scale_out") or ""
        item["session_requirements"] = extra.get("session") or ""
        item["market_type"] = "fx_futures_equities_unspecified"
        item["expected_holding_period"] = "state_dependent"
    return expand_strategy_hypotheses(table)


def select_knowledge_for_state(
    rows: Iterable[Mapping[str, Any]],
    *,
    regime: str,
    structure_kind: str,
    limit: int = 8,
) -> list[dict[str, Any]]:
    """Filter compiled rows by overlapping regime/structure tags. Not a trading vote."""
    tags = {str(regime).lower(), str(structure_kind).lower()}
    tags.discard("")
    tags.discard("unknown")
    tags.discard("none")
    scored: list[tuple[int, dict[str, Any]]] = []
    for row in rows:
        concepts = [str(item).lower() for item in (row.get("concepts") or [])]
        blob = " ".join(concepts)
        overlap = 0
        for tag in tags:
            if any(tag in concept or concept in tag for concept in concepts) or tag in blob:
                overlap += 1
        if overlap:
            scored.append((overlap, dict(row)))
    scored.sort(key=lambda item: (-item[0], str(item[1].get("filename") or "")))
    return [row for _, row in scored[:limit]]


def knowledge_markdown(rows: Iterable[Mapping[str, Any]]) -> str:
    items = list(rows)
    with_setup = sum(1 for row in items if str(row.get("setup") or "").strip())
    with_exit = sum(1 for row in items if str(row.get("invalidation") or row.get("exit") or "").strip())
    lines = [
        "# Compiled book knowledge table",
        "",
        "Label: `research_proxy`. Presence here is not an implemented strategy.",
        "",
        f"- hashed_sources: {len({str(row.get('file_hash') or '') for row in items})}",
        f"- hypothesis_rows: {len(items)}",
        f"- with_setup_section: {with_setup}",
        f"- with_invalidation_section: {with_exit}",
        "",
        "| file | hash | concepts | modules | setup |",
        "|---|---|---|---|---|",
    ]
    for row in items[:80]:
        concepts = ", ".join(str(item) for item in (row.get("concepts") or [])[:6])
        modules = ", ".join(str(item) for item in (row.get("strategy_modules") or [])[:4])
        setup = str(row.get("setup") or "")[:80].replace("|", "/")
        lines.append(
            f"| {row.get('filename')} | `{str(row.get('file_hash') or '')[:12]}` | {concepts} | {modules} | {setup} |"
        )
    if len(items) > 80:
        lines.append(f"| … | {len(items) - 80} more hashed extracts | | | |")
    lines.append("")
    return "\n".join(lines)


def write_knowledge_table(
    rows: Iterable[Mapping[str, Any]],
    *,
    json_path: Path,
    markdown_path: Path | None = None,
) -> dict[str, Any]:
    payload = {
        "schema": "knowledge_table.v1",
        "label": "research_proxy",
        "implemented": False,
        "n": 0,
        "rows": list(rows),
    }
    payload["n"] = len(payload["rows"])
    json_path = Path(json_path)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    if markdown_path is not None:
        markdown_path = Path(markdown_path)
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(knowledge_markdown(payload["rows"]), encoding="utf-8")
    return payload


def load_knowledge_table(path: Path) -> list[dict[str, Any]]:
    target = Path(path)
    if not target.is_file():
        return []
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    rows = payload.get("rows") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict) and row.get("file_hash")]
