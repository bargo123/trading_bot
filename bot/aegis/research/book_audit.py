"""Auditable inventory of locally available trading-book extracts.

This module proves local-file processing (hashing, counting, indexing), not that a
strategy was implemented or that an unavailable source PDF was read in full.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from aegis.research.books_index import BookIndex, PLACEHOLDER_NAMES, extract_provenance, word_count
from aegis.research.reports import book_compliance_matrix
from aegis.research.source_notes import MISSING_EXTRACTS, build_source_notes

USABLE_WORD_MINIMUM = 1_500

# Hand-curated compliance rows are a subset of the catalog. Mapping is explicit.
COMPLIANCE_EXTRACTS = {
    "Coulling VPA": (
        "a-complete-guide-to-volume-price-analysis-coulling.md",
        "stock-trading-investing-using-volume-price-analysis-coulling.md",
    ),
    "Brooks Ranges": ("trading-price-action-ranges-brooks.md",),
    "Damir 2016": ("price-action-breakdown-damir-2016.md",),
    "Jansen ML": ("hands-on-machine-learning-for-algorithmic-trading-jansen.md",),
    "Harris": ("trading-and-exchanges-market-microstructure-for-practitioners---full---2002-oxfo.md",),
    "Steidlmayer": ("steidlmayer-on-markets-trading-with-market-profile-2003-john-wiley-sons---libgen.md",),
    "Chan 2013": ("algorithmic-trading-winning-strategies-chan-2013.md",),
    "Prado AFML": ("advances-in-financial-machine-learning-prado-2018.md",),
    "Frost/Prechter Elliott": ("elliott-wave-principle-frost-prechter-2005.md",),
    "Johnson DMA": ("algorithmic-trading-and-dma-johnson-2010.md",),
    "Gann 1976": ("how-to-make-profits-in-commodities-gann-1976.md",),
    "Zuckerman Medallion": ("the-man-who-solved-the-market-zuckerman-2019.md",),
    "Nison / du Plessis": (
        "beyond-candlesticks-new-japanese-charting-techniques-revealed-wiley-finance-1994.md",
        "the-definitive-guide-to-point-and-figure-2005---libgen-li.md",
    ),
}


def _catalog_paths(catalog_path: Path) -> set[str]:
    text = catalog_path.read_text(encoding="utf-8", errors="replace") if catalog_path.is_file() else ""
    return set(re.findall(r"\]\(([^)]+\.md)\)", text))


def _normalized_title(text: str) -> str:
    title = next((line[2:].strip() for line in text.splitlines() if line.startswith("# ")), "")
    normalized = re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()
    return re.sub(r"\s+\d+$", "", normalized)


def _name_similarity(left: str, right: str) -> float:
    """Use filename similarity only as a conservative candidate signal."""
    return SequenceMatcher(None, Path(left).stem.lower(), Path(right).stem.lower()).ratio()


def _sample_for_similarity(text: str) -> str:
    compact = re.sub(r"\s+", " ", text.lower()).strip()
    if len(compact) <= 16_000:
        return compact
    return compact[:8_000] + compact[-8_000:]


def _near_duplicate_pairs(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flag only conservative candidates; this never replaces exact-hash detection."""
    pairs: list[dict[str, Any]] = []
    for i, left in enumerate(records):
        for right in records[i + 1 :]:
            if left["file_hash"] == right["file_hash"]:
                continue
            high = max(left["word_count"], right["word_count"], 1)
            word_gap = abs(left["word_count"] - right["word_count"]) / high
            names = _name_similarity(left["filename"], right["filename"])
            same_title = left["title_key"] and left["title_key"] == right["title_key"]
            if word_gap > 0.05 or not same_title and names < 0.92:
                continue
            similarity = SequenceMatcher(
                None, left["_similarity_sample"], right["_similarity_sample"], autojunk=False
            ).ratio()
            if similarity >= 0.90 or (names >= 0.92 and word_gap <= 0.01):
                pairs.append(
                    {
                        "left": left["filename"],
                        "right": right["filename"],
                        "similarity": round(similarity, 4),
                        "method": (
                            "same normalized title + sampled normalized text"
                            if similarity >= 0.90
                            else "very similar filenames + near-identical word counts"
                        ),
                    }
                )
    return pairs


def _status(*, filename: str, duplicate_of: str | None, provenance: dict[str, Any]) -> str:
    if filename in PLACEHOLDER_NAMES:
        return "placeholder"
    if duplicate_of:
        return "duplicate"
    if provenance.get("extraction_kind") == "ocr":
        return "ocr_degraded"
    return "full_extract"


def _indexed_rows(index_path: Path) -> dict[str, dict[str, Any]]:
    with sqlite3.connect(str(index_path)) as con:
        cols = {row[1] for row in con.execute("PRAGMA table_info(books)").fetchall()}
        needed = {"path", "file_hash", "word_count"}
        if not needed.issubset(cols):
            raise RuntimeError(f"book index missing audit columns: {sorted(needed - cols)}")
        rows = con.execute("SELECT path, file_hash, word_count FROM books").fetchall()
    return {Path(path).name: {"file_hash": digest, "word_count": words} for path, digest, words in rows}


def build_book_coverage(
    *,
    books_dir: Path,
    catalog_path: Path,
    index_path: Path,
    notes_dir: Path,
    ledger_path: Path,
) -> dict[str, Any]:
    """Rebuild local artifacts and write a reconciled JSON coverage ledger."""
    books_dir = Path(books_dir)
    cataloged = _catalog_paths(Path(catalog_path))
    index = BookIndex(index_path)
    index.rebuild(books_dir)
    build_source_notes(books_dir, notes_dir)
    indexed = _indexed_rows(index.path)

    records: list[dict[str, Any]] = []
    hashes: dict[str, str] = {}
    for md in sorted(books_dir.glob("*.md")):
        body = md.read_text(encoding="utf-8", errors="replace")
        digest = hashlib.sha256(body.encode("utf-8", errors="replace")).hexdigest()
        duplicate_of = hashes.get(digest)
        hashes.setdefault(digest, md.name)
        provenance = extract_provenance(body)
        words = word_count(body)
        note_path = Path(notes_dir) / md.with_suffix(".json").name
        row = {
            "filename": md.name,
            "file_hash": digest,
            "hash_prefix": digest[:12],
            "byte_size": len(body.encode("utf-8", errors="replace")),
            "word_count": words,
            "cataloged": md.name in cataloged,
            "catalog_exclusion": (
                None
                if md.name in cataloged
                else "below_usable_word_minimum"
                if words < USABLE_WORD_MINIMUM
                else "not_listed_in_catalog"
            ),
            "source_note_exists": note_path.is_file(),
            "indexed": (
                md.name in indexed
                and indexed[md.name]["file_hash"] == digest
                and indexed[md.name]["word_count"] == words
            ),
            "duplicate_of": duplicate_of,
            "placeholder": md.name in PLACEHOLDER_NAMES,
            "provenance": provenance,
            "coverage_status": _status(
                filename=md.name, duplicate_of=duplicate_of, provenance=provenance
            ),
            "title_key": _normalized_title(body),
            "_similarity_sample": _sample_for_similarity(body),
        }
        records.append(row)

    near_duplicates = _near_duplicate_pairs(records)
    for row in records:
        row.pop("_similarity_sample", None)
        row.pop("title_key", None)
    reconciliation = {
        "extracts_on_disk": len(records),
        "catalog_entries": len(cataloged),
        "indexed_rows": len(indexed),
        "source_note_rows": sum(1 for row in records if row["source_note_exists"]),
        "all_extracts_indexed": all(row["indexed"] for row in records),
        "all_extracts_noted": all(row["source_note_exists"] for row in records),
        "catalog_missing_on_disk": sorted(cataloged - {row["filename"] for row in records}),
    }
    ledger = {
        "schema_version": 1,
        "claim": (
            "Every on-disk markdown extract was hashed, counted, source-noted, and indexed. "
            "This is not a claim that every strategy was implemented or every source PDF was complete."
        ),
        "usable_word_minimum": USABLE_WORD_MINIMUM,
        "reconciliation": reconciliation,
        "near_duplicate_candidates": near_duplicates,
        "records": records,
        "unavailable": [
            {"key": key, "coverage_status": "unavailable", "reason": reason}
            for key, reason in sorted(MISSING_EXTRACTS.items())
        ],
    }
    Path(ledger_path).parent.mkdir(parents=True, exist_ok=True)
    Path(ledger_path).write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8")
    return ledger


def compliance_join(ledger: dict[str, Any]) -> tuple[list[dict[str, str]], list[str]]:
    """Left-join hand-curated compliance rows onto hashed extracts. Not an implementation claim."""
    on_disk = {row["filename"] for row in ledger.get("records") or []}
    missing = {row["key"] for row in ledger.get("unavailable") or []}
    rows = []
    for item in book_compliance_matrix():
        book = item["book"]
        files = COMPLIANCE_EXTRACTS.get(book, ())
        present = [name for name in files if name in on_disk]
        if book.lower() in missing and not present:
            status = "missing_extract"
        elif present:
            status = "covered_proxy"
        else:
            status = "indexed_only_unmapped"
        rows.append(
            {
                "book": book,
                "status": status,
                "extracts": ", ".join(present) if present else (item.get("gap") or ""),
                "claim": item.get("claim") or "",
            }
        )
    mapped = {name for files in COMPLIANCE_EXTRACTS.values() for name in files}
    indexed_only = [
        row["filename"]
        for row in ledger.get("records") or []
        if row.get("cataloged") and row["filename"] not in mapped and not row.get("placeholder")
    ]
    return rows, indexed_only


def markdown_book_coverage(ledger: dict[str, Any]) -> str:
    """Render the ledger without overstating OCR or strategy completeness."""
    recon = ledger["reconciliation"]
    lines = [
        "# Book coverage audit",
        "",
        "Label: `research_proxy`. Indexing a file is not implementation of its strategy.",
        "",
        ledger["claim"],
        "",
        "## Reconciliation",
        "",
        f"- extracts on disk: {recon['extracts_on_disk']}",
        f"- catalog entries: {recon['catalog_entries']}",
        f"- indexed rows: {recon['indexed_rows']}",
        f"- source-note rows: {recon['source_note_rows']}",
        f"- every on-disk extract indexed: {recon['all_extracts_indexed']}",
        f"- every on-disk extract noted: {recon['all_extracts_noted']}",
        f"- catalog entries missing on disk: {recon['catalog_missing_on_disk'] or 'none'}",
        "",
        "## Extracts",
        "",
        "| file | words | hash | status | catalog | index/note | provenance |",
        "| --- | ---: | --- | --- | --- | --- | --- |",
    ]
    for row in ledger["records"]:
        provenance = row["provenance"]
        source = provenance.get("extractor") or provenance.get("extraction_kind") or "unknown"
        lines.append(
            f"| {row['filename']} | {row['word_count']:,} | {row['hash_prefix']} | "
            f"{row['coverage_status']} | {'yes' if row['cataloged'] else row['catalog_exclusion']} | "
            f"{'yes' if row['indexed'] and row['source_note_exists'] else 'no'} | {source} |"
        )
    lines.extend(["", "## Exact duplicates", ""])
    exact = [row for row in ledger["records"] if row["duplicate_of"]]
    if exact:
        lines.extend(f"- `{row['filename']}` duplicates `{row['duplicate_of']}`" for row in exact)
    else:
        lines.append("- none")
    lines.extend(["", "## Near-duplicate candidates", ""])
    if ledger["near_duplicate_candidates"]:
        lines.extend(
            f"- `{pair['left']}` / `{pair['right']}`: similarity={pair['similarity']} ({pair['method']})"
            for pair in ledger["near_duplicate_candidates"]
        )
    else:
        lines.append("- none")
    lines.extend(["", "## Unavailable full extracts", ""])
    lines.extend(f"- `{row['key']}`: {row['reason']}" for row in ledger["unavailable"])
    compliance_rows, indexed_only = compliance_join(ledger)
    lines.extend(
        [
            "",
            "## Hand-curated compliance join",
            "",
            "The compliance matrix is a named subset. Most catalog files are `indexed_only` until a module proof exists.",
            "",
            "| book | join | extracts / gap | claim |",
            "| --- | --- | --- | --- |",
        ]
    )
    for row in compliance_rows:
        lines.append(f"| {row['book']} | {row['status']} | {row['extracts']} | {row['claim']} |")
    lines.extend(["", f"Catalog extracts without a compliance row: {len(indexed_only)}", ""])
    lines.extend(f"- `{name}`" for name in indexed_only)
    lines.extend(
        [
            "",
            "## Limits",
            "",
            "- OCR page metadata is recorded only from extract headers. No source-PDF hash/page-total means OCR completeness is unproven.",
            "- Catalog exclusions are reported, so short files do not silently disappear.",
            "- `NEW_BOOKS_*` digests are not evidence for this audit.",
            "",
        ]
    )
    return "\n".join(lines)
