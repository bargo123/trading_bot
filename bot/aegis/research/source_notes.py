"""Source notes from full book extracts. Digests are not the evidence source."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from aegis.research.books_index import (
    PLACEHOLDER_NAMES,
    extract_claims,
    extract_provenance,
    word_count,
)
from aegis.research.paths import RESEARCH_DIR, ensure_research_dirs

MISSING_EXTRACTS = {
    "kaufman": "Perry Kaufman Trading Systems and Methods — no full extract on disk",
    "volman": "Bob Volman Forex Price Action Scalping — digest only",
}


def note_status(author_key: str) -> str:
    if author_key.lower() in MISSING_EXTRACTS:
        return "unavailable"
    return "research_proxy"


def _label(filename: str, claims: dict[str, Any]) -> str:
    if filename in PLACEHOLDER_NAMES or claims.get("placeholder"):
        return "unavailable"
    return "research_proxy"


def build_source_notes(books_dir: Path, out_dir: Path | None = None) -> list[dict[str, Any]]:
    ensure_research_dirs()
    destination = Path(out_dir) if out_dir is not None else RESEARCH_DIR / "source_notes"
    destination.mkdir(parents=True, exist_ok=True)
    notes: list[dict[str, Any]] = []
    hashes: dict[str, str] = {}
    for md in sorted(Path(books_dir).glob("*.md")):
        body = md.read_text(encoding="utf-8", errors="replace")
        digest = hashlib.sha256(body.encode("utf-8", errors="replace")).hexdigest()
        claims = extract_claims(body, filename=md.name)
        provenance = extract_provenance(body)
        setup = _section(body, "setup")
        entry = _section(body, "entry")
        exit_ = _section(body, "exit")
        risk = _section(body, "risk")
        claims["setup"] = setup
        claims["entry"] = entry
        claims["exit"] = exit_
        claims["risk"] = risk
        note = {
            "filename": md.name,
            "title": (claims.get("headings") or [md.stem])[0] if claims.get("headings") else md.stem,
            "file_hash": digest,
            "byte_size": len(body.encode("utf-8", errors="replace")),
            "word_count": word_count(body),
            "label": _label(md.name, claims),
            "placeholder": bool(claims.get("placeholder") or md.name in PLACEHOLDER_NAMES),
            "duplicate_of": hashes.get(digest),
            "timeframes": claims.get("timeframes") or [],
            "data_required": claims.get("data_required") or [],
            "setup": setup,
            "entry": entry,
            "exit": exit_,
            "risk": risk,
            "warnings": claims.get("warnings") or [],
            "evidence_quality": "extract",
            "provenance": provenance,
            "implemented": False,
            "claims": claims,
        }
        if digest not in hashes:
            hashes[digest] = md.name
        notes.append(note)
        (destination / md.name.replace(".md", ".json")).write_text(
            json.dumps(note, indent=2),
            encoding="utf-8",
        )
    missing_path = destination / "_missing_extracts.json"
    missing_path.write_text(
        json.dumps({"label": "unavailable", "missing": MISSING_EXTRACTS}, indent=2),
        encoding="utf-8",
    )
    return notes


def _section(text: str, name: str) -> str:
    import re

    pattern = re.compile(
        rf"^#{{1,3}}\s+.*{name}[^\n]*\n((?:.*\n)*?)(?=^#|\Z)",
        re.I | re.M,
    )
    match = pattern.search(text)
    if not match:
        return ""
    return " ".join(match.group(1).split())[:400]
