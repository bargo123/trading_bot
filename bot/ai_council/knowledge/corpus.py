"""Shared knowledge layer: book corpus manifest + verbatim passage retrieval.

The corpus is the trading-book library (docs/trading/books/*.md) indexed in
research/books_index.sqlite. Retrieval returns ORIGINAL passages verbatim so
council proposals can quote the books directly. Manifest presence is not an
implementation claim — it only records what the corpus contains.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BOT_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BOT_ROOT.parent
BOOKS_DIR = REPO_ROOT / "docs" / "trading" / "books"
KNOWLEDGE_DIR = Path(__file__).resolve().parent
MANIFEST_PATH = KNOWLEDGE_DIR / "corpus_manifest.json"
MANIFEST_SCHEMA = "corpus_manifest.v1"

_TOKEN_RE = re.compile(r"\S+")
_BOOK_TITLE_RE = re.compile(r"^#\s+(.+)$", flags=re.M)


def _import_index():
    import sys

    if str(BOT_ROOT) not in sys.path:
        sys.path.insert(0, str(BOT_ROOT))
    from aegis.research.books_index import BookIndex

    return BookIndex()


def _title_of(body: str) -> str:
    match = _BOOK_TITLE_RE.search(body)
    return match.group(1).strip() if match else ""


def build_manifest() -> dict[str, Any]:
    """Rebuild corpus_manifest.json from the books index. Idempotent."""
    index = _import_index()
    rows = index.all_rows(include_body=False)
    books = []
    for row in rows:
        books.append(
            {
                "path": row.get("path"),
                "title": row.get("title") or "",
                "file_hash": row.get("file_hash"),
                "word_count": row.get("word_count"),
                "placeholder": bool(row.get("placeholder")),
                "duplicate_of": row.get("duplicate_of"),
                "warnings": (row.get("warnings") or "").split(" | ") if row.get("warnings") else [],
                "provenance": row.get("provenance") or {},
                "claims": {
                    "timeframes": row.get("claims", {}).get("timeframes", []),
                    "data_required": row.get("claims", {}).get("data_required", []),
                },
            }
        )
    manifest = {
        "schema": MANIFEST_SCHEMA,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "n_books": len(books),
        "n_placeholders": sum(1 for b in books if b["placeholder"]),
        "books": books,
    }
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest


def load_manifest() -> dict[str, Any]:
    if MANIFEST_PATH.exists():
        try:
            return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    return build_manifest()


def _read_book(path: str) -> str:
    p = Path(path)
    if not p.is_file():
        p = BOOKS_DIR / p.name
    return p.read_text(encoding="utf-8", errors="replace")


def _passage_around(body: str, keyword: str, radius_tokens: int) -> dict[str, Any]:
    """Verbatim window around the first occurrence of keyword. Never paraphrases."""
    idx = body.lower().find(keyword.lower())
    if idx < 0:
        return {"found": False, "passage": ""}
    tokens = list(_TOKEN_RE.finditer(body))
    pos = 0
    while pos < len(tokens) and tokens[pos].start() < idx:
        pos += 1
    start = max(0, pos - radius_tokens)
    end = min(len(tokens), pos + radius_tokens)
    passage = body[tokens[start].start(): tokens[end - 1].end()] if tokens and end > start else ""
    return {"found": True, "passage": passage, "token_start": start, "token_end": end}


def retrieve(query: str, limit: int = 6, radius_tokens: int = 80) -> list[dict[str, Any]]:
    """Search the corpus and return verbatim passages around the query.

    Each hit keeps the original passage text plus book identity and warnings,
    so council proposals can quote precisely without paraphrasing evidence.
    """
    query = (query or "").strip()
    if not query:
        return []
    index = _import_index()
    hits = []
    for row in index.all_rows(include_body=False):
        if row.get("placeholder") or row.get("duplicate_of"):
            continue
        body = _read_book(str(row.get("path") or ""))
        window = _passage_around(body, query, radius_tokens)
        if not window["found"]:
            continue
        hits.append(
            {
                "book": row.get("title") or _title_of(body),
                "path": str(row.get("path")),
                "file_hash": row.get("file_hash"),
                "word_count": row.get("word_count"),
                "warnings": (row.get("warnings") or "").split(" | ") if row.get("warnings") else [],
                "passage": window["passage"],
                "passage_token_count": window["token_end"] - window["token_start"],
            }
        )
        if len(hits) >= limit:
            break
    return hits


def find_book(title_fragment: str) -> dict[str, Any] | None:
    """Locate a manifest book by title fragment."""
    frag = (title_fragment or "").strip().lower()
    if not frag:
        return None
    for book in load_manifest().get("books", []):
        if frag in str(book.get("title") or "").lower():
            return book
    return None


def corpus_stats() -> dict[str, Any]:
    manifest = load_manifest()
    books = manifest.get("books", [])
    total_words = sum(int(b.get("word_count") or 0) for b in books)
    return {
        "schema": manifest.get("schema"),
        "n_books": len(books),
        "n_placeholders": manifest.get("n_placeholders", 0),
        "n_real": sum(1 for b in books if not b.get("placeholder")),
        "total_words": total_words,
        "generated_utc": manifest.get("generated_utc"),
    }