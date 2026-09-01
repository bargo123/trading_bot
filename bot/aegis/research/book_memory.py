"""Persistent book-memory knowledge records with semantic quality validation.

Turns source-note extracts into durable, machine-readable knowledge records in
`bot/research/book_memory/`. Raw keyword slicing is rejected: a sentence must
carry real trading action to be stored as setup/entry/invalidation/exit.
Records are research hypotheses, never votes.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from aegis.research.paths import BOT_ROOT, ensure_research_dirs

BOOK_MEMORY_DIR = BOT_ROOT / "research" / "book_memory"
DEFAULT_RECORDS_PATH = BOOK_MEMORY_DIR / "knowledge_records.jsonl"
DEFAULT_DB_PATH = BOOK_MEMORY_DIR / "book_memory.sqlite"
DEFAULT_NOTES_DIR = BOT_ROOT / "research" / "source_notes"

_ACTION_TOKENS = (
    "buy", "sell", "enter", "entry", "exit", "stop", "target", "place",
    "position", "breakout", "break", "retest", "pullback", "fade", "reject",
    "invalidation", "invalidat", "risk", "trade", "market", "price", "candle",
    "bar", "support", "resistance", "trend", "range", "volume", "signal",
    "confirmation", "momentum", "session", "order", "profit", "loss", "high",
    "low", "swing", "level", "watch", "look", "set", "trail", "scale", "add",
    "reduce", "hold", "move", "confirm", "trigger", "close", "open", "failed",
    "failure", "false break", "spring", "excess", "value area", "effort",
)

_NEGATIVE_TOKENS = (
    "entered at", "entered by", "was entered", "by hand", "typed", "keyed",
    "data entry", "recorded", "spreadsheet", "was recorded", "all the information",
    "information was", "filled in", "entered into", "exchange floor",
    "at the exchanges", "was passed", "hand-written", "written down", "logged",
    "administrative", "manual entry", "data processing",
)

_CODE_TOKENS = (
    "import ", "def ", "return ", "print(", "columns=", "pd.", "np.",
    "df[", "=pd.", "= np.", "=", "()", "lambda", "self.", ".append(",
    ".copy()", "range(", "len(", "if __name__", "class ", "for ", "while ",
)

_LONG_SHORT_RE = re.compile(
    r"\b(go|going|buy|sell)\s+(long|short)\b|\b(long|short)\s+(position|entry|signal|bias|side|setup)\b"
)

_ENTRY_ACTION_RE = re.compile(
    r"\b(buy|sell)\b.*\b(stop|target|trigger|entry|above|below|break|pullback|retest|signal)\b"
    r"|\b(stop|target|when|if|break)\b.*\b(buy|sell)\b"
)


def _has_action_token(sentence: str) -> bool:
    lower = sentence.lower()
    if any(token in lower for token in _ACTION_TOKENS):
        return True
    if re.search(r"\b(long|short)\b", lower) and _LONG_SHORT_RE.search(lower):
        return True
    return False


def _has_negative_token(sentence: str) -> bool:
    lower = sentence.lower()
    if any(token in lower for token in _NEGATIVE_TOKENS):
        return True
    if any(token in lower for token in _CODE_TOKENS):
        return True
    return False


def sentence_is_trading_relevant(sentence: str) -> bool:
    """Semantic gate: real trading prose, not code or data-entry text."""
    cleaned = " ".join(str(sentence).split())
    if len(cleaned) < 25 or len(cleaned) > 600:
        return False
    if _has_negative_token(cleaned):
        return False
    if re.search(r"=|_|\{\}|\(\)|\[\]", cleaned) and any(
        token in cleaned for token in _CODE_TOKENS
    ):
        return False
    return _has_action_token(cleaned)

_STOPWORDS = frozenset(
    """
    a an the and or but if when while as of to in on at for with without by from
    is are was were be been being have has had do does did will would shall should
    can could may might must not no nor this that these those it its they their
    you your we our he she his her i me my them him
    """.split()
)

_CATEGORY_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("setup", ("setup", "pattern", "look for", "watch for", "when the market", "when price", "if price")),
    ("entry", ("enter", "entry", "buy when", "sell when", "trigger", "initiate", "long", "short")),
    ("invalidation", ("invalidat", "thesis", "failed break", "stop out", "wrong", "closes below", "closes above")),
    ("exit", ("exit", "get out", "close the trade", "abandon", "take profit", "take partial", "scale out")),
    ("stop_logic", ("stop-loss", "stop loss", "protective stop", "place the stop", "stop below", "stop above")),
    ("target", ("target", "take profit", "profit objective", "measured move", "measured target")),
    ("confirmation", ("confirm", "confirmation", "effort versus result", "volume confirms", "verifies")),
    ("scale_in", ("add to", "scale in", "pyramid", "increase exposure", "add on", "add to position")),
    ("scale_out", ("scale out", "take partial", "reduce the position", "bank a portion", "partial profit")),
    ("risk_model", ("risk", "position size", "fraction of capital", "do not risk", "risk percent", "risk management")),
    ("session", ("london", "new york", "asian session", "asia", "overlap", "rth", "open", "close")),
    ("limitations", ("does not work", "fails when", "caveat", "limitation", "discretionary", "do not")),
)


def _sentences(text: str) -> list[str]:
    blob = " ".join(str(text or "").split())
    parts = re.split(r"(?<=[.!?])\s+", blob)
    return [part.strip() for part in parts if part.strip()]


def _categorize_sentence(sentence: str) -> list[str]:
    lower = sentence.lower()
    hits: list[str] = []
    for category, needles in _CATEGORY_KEYWORDS:
        if category == "entry":
            if re.search(r"\b(long|short)\b", lower) and not _LONG_SHORT_RE.search(lower):
                continue
            if _ENTRY_ACTION_RE.search(lower):
                hits.append("entry")
            elif any(needle in lower for needle in needles):
                hits.append("entry")
            continue
        if any(needle in lower for needle in needles):
            hits.append(category)
    return hits


def extract_quality_sections(body: str, *, limit: int = 2, cap: int = 500) -> dict[str, str]:
    """Extract validated sections; empty strings mean nothing usable was found."""
    buckets: dict[str, list[str]] = {name: [] for name, _ in _CATEGORY_KEYWORDS}
    for sentence in _sentences(body):
        if not sentence_is_trading_relevant(sentence):
            continue
        for category in _categorize_sentence(sentence):
            if len(buckets[category]) < limit:
                buckets[category].append(sentence)
    return {name: " ".join(values)[:cap] for name, values in buckets.items()}


def _concepts_from_text(text: str) -> list[str]:
    blob = " ".join(str(text or "").lower().split())
    tags: list[str] = []
    for needle, tag in (
        ("failed break", "failed_breakout"),
        ("false break", "failed_breakout"),
        ("failure", "failed_breakout"),
        ("retest", "breakout_retest"),
        ("pullback", "trend_pullback"),
        ("range", "range_edge_fade"),
        ("breakout", "breakout_continuation"),
        ("mean reversion", "mean_reversion"),
        ("momentum", "momentum"),
        ("volume", "volume_effort_result"),
        ("market profile", "market_profile"),
        ("vwap", "vwap"),
        ("support", "support_resistance"),
        ("resistance", "support_resistance"),
        ("trend", "trend_continuation"),
    ):
        if needle in blob and tag not in tags:
            tags.append(tag)
    return tags


def _stable_id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]


@dataclass
class KnowledgeRecord:
    knowledge_id: str
    source_title: str
    author: str
    source_hash: str
    file_path: str
    provenance: Mapping[str, Any]
    concept: str
    market_type: str
    timeframe: str
    regime: str
    setup: str
    conditions: str
    entry: str
    confirmation: str
    invalidation: str
    stop_logic: str
    target: str
    exit_logic: str
    scale_in_logic: str
    scale_out_logic: str
    risk_model: str
    session_requirements: str
    data_requirements: Sequence[str] = field(default_factory=list)
    limitations: Sequence[str] = field(default_factory=list)
    mechanical: bool = False
    testable_hypothesis: str = ""
    extraction_confidence: str = "extract"
    related_strategies: Sequence[str] = field(default_factory=list)
    related_experiments: Sequence[str] = field(default_factory=list)
    historical_validation: str = "unvalidated"
    label: str = "research_proxy"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_records_from_notes(
    notes_dir: Path | None = None,
    *,
    records_path: Path | None = None,
) -> list[KnowledgeRecord]:
    """Compile one record per trading-relevant concept per hashed source note."""
    notes_dir = Path(notes_dir) if notes_dir is not None else DEFAULT_NOTES_DIR
    records_path = Path(records_path) if records_path is not None else DEFAULT_RECORDS_PATH
    out: list[KnowledgeRecord] = []
    for path in sorted(notes_dir.glob("*.json")):
        if path.name.startswith("_"):
            continue
        try:
            row = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(row, dict) or not row.get("file_hash"):
            continue
        title = str(row.get("title") or "")
        file_hash = str(row["file_hash"])
        body = _flatten_body(row)
        sections = extract_quality_sections(body)
        concepts = _concepts_from_text(body) or ["unclassified"]
        author = _author_from_title(title)
        timeframe = _timeframe_from_text(body)
        related = list(_concepts_from_text(body))
        for concept in concepts[:6]:
            hypothesis = _hypothesis_text(title, concept, sections)
            record = KnowledgeRecord(
                knowledge_id=_stable_id(file_hash, concept),
                source_title=title,
                author=author,
                source_hash=file_hash,
                file_path=path.name,
                provenance={
                    "note_file": path.name,
                    "extractor": (row.get("provenance") or {}).get("extractor") or "unknown",
                    "source_file": (row.get("provenance") or {}).get("source_file") or None,
                    "pages_with_text": (row.get("provenance") or {}).get("pages_with_text"),
                },
                concept=concept,
                market_type=_market_type_from_text(body),
                timeframe=timeframe,
                regime="",
                setup=sections.get("setup") or "",
                conditions=_conditions_text(sections),
                entry=sections.get("entry") or "",
                confirmation=sections.get("confirmation") or "",
                invalidation=sections.get("invalidation") or "",
                stop_logic=sections.get("stop_logic") or "",
                target=sections.get("target") or "",
                exit_logic=sections.get("exit") or "",
                scale_in_logic=sections.get("scale_in") or "",
                scale_out_logic=sections.get("scale_out") or "",
                risk_model=sections.get("risk_model") or "",
                session_requirements=sections.get("session") or "",
                data_requirements=[str(item) for item in (row.get("data_required") or [])],
                limitations=[str(item) for item in (row.get("warnings") or [])][:6],
                mechanical="system" in body.lower() or "rule" in body.lower(),
                testable_hypothesis=hypothesis,
                extraction_confidence="extract" if body else "no_extract",
                related_strategies=related,
                related_experiments=[],
                historical_validation="unvalidated",
                label="research_proxy",
            )
            out.append(record)
    _persist_records(out, records_path)
    return out


def _flatten_body(row: Mapping[str, Any]) -> str:
    parts: list[str] = []
    for key in ("title", "summary", "setup", "entry", "exit", "risk"):
        value = row.get(key)
        if isinstance(value, str) and value:
            parts.append(value)
    claims = row.get("claims") if isinstance(row.get("claims"), dict) else {}
    for value in claims.values():
        if isinstance(value, str) and value:
            parts.append(value)
        elif isinstance(value, list):
            parts.extend(str(item) for item in value if isinstance(item, str))
    return " ".join(parts)


def _author_from_title(title: str) -> str:
    """Best-effort author from the note title; the PDF provenance does not parse it."""
    return "unknown"


def _timeframe_from_text(text: str) -> str:
    lower = text.lower()
    for label in ("weekly", "daily", "h4", "h1", "m30", "m15", "m5", "m1", "intraday"):
        if label in lower:
            return label
    return "unspecified"


def _market_type_from_text(text: str) -> str:
    lower = text.lower()
    if "forex" in lower or "fx" in lower or "currency" in lower:
        return "forex"
    if "futures" in lower or "commodity" in lower:
        return "futures"
    if "equity" in lower or "stock" in lower:
        return "equities"
    return "unspecified"


def _conditions_text(sections: Mapping[str, str]) -> str:
    return sections.get("setup") or sections.get("confirmation") or ""


def _hypothesis_text(title: str, concept: str, sections: Mapping[str, str]) -> str:
    entry = sections.get("entry") or ""
    invalid = sections.get("invalidation") or ""
    parts = [f"{title} ({concept}):"]
    if entry:
        parts.append(f"entry [{entry}]")
    if invalid:
        parts.append(f"invalidation [{invalid}]")
    if not entry and not invalid:
        parts.append("needs operational formulation before testing")
    return " ".join(parts)[:600]


def _persist_records(records: Iterable[KnowledgeRecord], records_path: Path) -> None:
    records_path.parent.mkdir(parents=True, exist_ok=True)
    with records_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record.as_dict(), default=str) + "\n")


def _load_records(records_path: Path | None = None) -> list[dict[str, Any]]:
    target = Path(records_path) if records_path is not None else DEFAULT_RECORDS_PATH
    if not target.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in target.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def build_sqlite_db(
    records_path: Path | None = None,
    db_path: Path | None = None,
) -> int:
    """Mirror the JSONL records into SQLite for fast concept/session queries."""
    records = _load_records(records_path)
    target = Path(db_path) if db_path is not None else DEFAULT_DB_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(target)) as con:
        con.executescript(
            """
            DROP TABLE IF EXISTS knowledge;
            CREATE TABLE knowledge (
                knowledge_id TEXT PRIMARY KEY,
                source_title TEXT,
                author TEXT,
                source_hash TEXT,
                file_path TEXT,
                concept TEXT,
                market_type TEXT,
                timeframe TEXT,
                regime TEXT,
                setup TEXT,
                entry TEXT,
                confirmation TEXT,
                invalidation TEXT,
                stop_logic TEXT,
                target TEXT,
                exit_logic TEXT,
                scale_in_logic TEXT,
                scale_out_logic TEXT,
                risk_model TEXT,
                session_requirements TEXT,
                data_requirements TEXT,
                limitations TEXT,
                mechanical INTEGER,
                testable_hypothesis TEXT,
                extraction_confidence TEXT,
                related_strategies TEXT,
                historical_validation TEXT
            );
            CREATE INDEX idx_knowledge_concept ON knowledge(concept);
            CREATE INDEX idx_knowledge_source ON knowledge(source_hash);
            """
        )
        for record in records:
            con.execute(
                """
                INSERT OR REPLACE INTO knowledge (
                    knowledge_id, source_title, author, source_hash, file_path,
                    concept, market_type, timeframe, regime, setup, entry,
                    confirmation, invalidation, stop_logic, target, exit_logic,
                    scale_in_logic, scale_out_logic, risk_model,
                    session_requirements, data_requirements, limitations,
                    mechanical, testable_hypothesis, extraction_confidence,
                    related_strategies, historical_validation
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    record["knowledge_id"], record["source_title"], record["author"],
                    record["source_hash"], record["file_path"], record["concept"],
                    record["market_type"], record["timeframe"], record["regime"],
                    record["setup"], record["entry"], record["confirmation"],
                    record["invalidation"], record["stop_logic"], record["target"],
                    record["exit_logic"], record["scale_in_logic"],
                    record["scale_out_logic"], record["risk_model"],
                    record["session_requirements"],
                    json.dumps(record["data_requirements"], default=str),
                    json.dumps(record["limitations"], default=str),
                    1 if record["mechanical"] else 0,
                    record["testable_hypothesis"],
                    record["extraction_confidence"],
                    json.dumps(record["related_strategies"], default=str),
                    record["historical_validation"],
                ),
            )
    return len(records)


def retrieve_knowledge(
    *,
    concept: str = "",
    session: str = "",
    regime: str = "",
    market_type: str = "",
    limit: int = 10,
    records_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Filtered retrieval of durable knowledge records. Retrieval is not a vote."""
    records = _load_records(records_path)
    concept_l = str(concept).lower()
    session_l = str(session).lower()
    regime_l = str(regime).lower()
    market_l = str(market_type).lower()
    hits: list[dict[str, Any]] = []
    for record in records:
        if concept_l and concept_l not in str(record.get("concept") or "").lower():
            continue
        if session_l and session_l not in str(record.get("session_requirements") or "").lower():
            continue
        if regime_l and regime_l not in str(record.get("regime") or "").lower():
            continue
        if market_l and market_l not in str(record.get("market_type") or "").lower():
            continue
        hits.append(record)
    hits.sort(key=lambda r: str(r.get("source_title") or ""))
    return hits[:limit]


def book_memory_summary(records: Iterable[Mapping[str, Any]] | None = None) -> dict[str, Any]:
    rows = list(records) if records is not None else _load_records()
    with_entry = sum(1 for row in rows if str(row.get("entry") or "").strip())
    with_invalidation = sum(1 for row in rows if str(row.get("invalidation") or "").strip())
    concepts: dict[str, int] = {}
    for row in rows:
        concept = str(row.get("concept") or "unclassified")
        concepts[concept] = concepts.get(concept, 0) + 1
    return {
        "schema": "book_memory.v1",
        "label": "research_proxy",
        "n_records": len(rows),
        "n_sources": len({str(row.get("source_hash") or "") for row in rows}),
        "n_with_entry": with_entry,
        "n_with_invalidation": with_invalidation,
        "concepts": dict(sorted(concepts.items(), key=lambda item: -item[1])),
        "built_at": datetime.now(timezone.utc).isoformat(),
    }