"""Index trading-book extracts. Presence in the index is not an implementation claim."""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from aegis.research.paths import REPO_ROOT, DEFAULT_BOOKS_INDEX, ensure_research_dirs

WORKTREE_BOOKS = REPO_ROOT / "docs" / "trading" / "books"
ORIGINAL_BOOKS = Path(r"C:\Users\Raqam\trading_bot\docs\trading\books")

PLACEHOLDER_NAMES = frozenset({"market-structure.md", "sample-author.md"})

_SCHEMA = """
CREATE TABLE IF NOT EXISTS books (
    path TEXT PRIMARY KEY,
    title TEXT,
    headings TEXT,
    file_hash TEXT NOT NULL,
    body TEXT NOT NULL,
    claims_json TEXT,
    warnings TEXT,
    placeholder INTEGER NOT NULL DEFAULT 0,
    duplicate_of TEXT
);
"""

_TF_RE = re.compile(r"\b(M1|M5|M15|M30|H1|H4|D1|daily|weekly|intraday)\b", re.I)
_DATA_HINTS = (
    ("level 2", "mt5_l2"),
    ("level-2", "mt5_l2"),
    ("depth of market", "mt5_l2"),
    ("order book", "mt5_l2"),
    ("news calendar", "news_calendar"),
    ("economic calendar", "news_calendar"),
    ("commitment of traders", "cot"),
    ("open interest", "futures_oi"),
    ("tick volume", "broker_tick_volume_proxy"),
    ("volume", "volume_unspecified"),
)


def discover_books_root() -> Path | None:
    for candidate in (WORKTREE_BOOKS, ORIGINAL_BOOKS):
        if candidate.is_dir() and any(candidate.glob("*.md")):
            return candidate
    return None


def _title_and_headings(text: str) -> tuple[str, str]:
    headings = re.findall(r"^#{1,3}\s+(.+)$", text, flags=re.M)
    title = headings[0].strip() if headings else ""
    return title, " | ".join(h.strip() for h in headings[:40])


def extract_claims(text: str, *, filename: str = "") -> dict[str, Any]:
    headings = re.findall(r"^#{1,3}\s+(.+)$", text, flags=re.M)
    warning_blocks = re.findall(
        r"^#{1,3}\s+.*warn[^\n]*\n((?:.*\n)*?)(?=^#|\Z)",
        text,
        flags=re.I | re.M,
    )
    warning_lines = []
    for block in warning_blocks:
        warning_lines.extend(ln.strip() for ln in block.splitlines() if ln.strip())
    if not warning_lines:
        warning_lines = [
            ln.strip()
            for ln in text.splitlines()
            if re.search(r"\b(do not|warning|never hide)\b", ln, flags=re.I)
        ]
    tfs = sorted({m.group(0).upper() if m.group(0).upper() in {"M1", "M5", "M15", "M30", "H1", "H4", "D1"} else m.group(0).lower() for m in _TF_RE.finditer(text)})
    data_required = []
    blob = text.lower()
    for needle, cap in _DATA_HINTS:
        if needle in blob and cap not in data_required:
            data_required.append(cap)
    return {
        "filename": filename,
        "timeframes": tfs,
        "data_required": data_required,
        "setup": "",
        "entry": "",
        "exit": "",
        "risk": "",
        "warnings": warning_lines[:12],
        "evidence_quality": "extract",
        "placeholder": filename in PLACEHOLDER_NAMES,
        "implemented": False,
        "headings": headings[:40],
    }


class BookIndex:
    def __init__(self, path: Path | None = None) -> None:
        ensure_research_dirs()
        self.path = Path(path) if path is not None else DEFAULT_BOOKS_INDEX
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(self.path)) as con:
            con.executescript(_SCHEMA)
            cols = {r[1] for r in con.execute("PRAGMA table_info(books)").fetchall()}
            if "claims_json" not in cols:
                con.execute("ALTER TABLE books ADD COLUMN claims_json TEXT")
            if "warnings" not in cols:
                con.execute("ALTER TABLE books ADD COLUMN warnings TEXT")
            if "placeholder" not in cols:
                con.execute("ALTER TABLE books ADD COLUMN placeholder INTEGER NOT NULL DEFAULT 0")
            if "duplicate_of" not in cols:
                con.execute("ALTER TABLE books ADD COLUMN duplicate_of TEXT")

    def rebuild(self, books_dir: Path) -> int:
        n = 0
        files: list[tuple[Path, str, str, str, str, dict[str, Any]]] = []
        for md in sorted(books_dir.glob("*.md")):
            body = md.read_text(encoding="utf-8", errors="replace")
            title, headings = _title_and_headings(body)
            digest = hashlib.sha256(body.encode("utf-8", errors="replace")).hexdigest()
            claims = extract_claims(body, filename=md.name)
            files.append((md, title, headings, digest, body, claims))
        with sqlite3.connect(str(self.path)) as con:
            con.execute("DELETE FROM books")
            for md, title, headings, digest, body, claims in files:
                is_ph = md.name in PLACEHOLDER_NAMES or bool(claims.get("placeholder"))
                con.execute(
                    """
                    INSERT INTO books(
                        path, title, headings, file_hash, body,
                        claims_json, warnings, placeholder, duplicate_of
                    ) VALUES (?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        str(md),
                        title,
                        headings,
                        digest,
                        body,
                        json.dumps(claims),
                        " | ".join(claims.get("warnings") or []),
                        1 if is_ph else 0,
                        None,
                    ),
                )
                n += 1
            rows = con.execute("SELECT path, file_hash FROM books ORDER BY path").fetchall()
            first: dict[str, str] = {}
            for path, digest in rows:
                if digest in first:
                    con.execute(
                        "UPDATE books SET duplicate_of = ? WHERE path = ?",
                        (first[digest], path),
                    )
                else:
                    first[digest] = path
        return n

    def search(self, query: str, limit: int = 8) -> list[dict[str, Any]]:
        q = query.strip().lower()
        if not q:
            return []
        out: list[dict[str, Any]] = []
        with sqlite3.connect(str(self.path)) as con:
            con.row_factory = sqlite3.Row
            rows = con.execute(
                "SELECT path, title, headings, file_hash, body, claims_json, warnings, placeholder, duplicate_of FROM books"
            ).fetchall()
        for row in rows:
            blob = f"{row['title']}\n{row['headings']}\n{row['body']}".lower()
            if q not in blob:
                continue
            try:
                claims = json.loads(row["claims_json"] or "{}")
            except json.JSONDecodeError:
                claims = {}
            out.append(
                {
                    "path": row["path"],
                    "title": row["title"],
                    "headings": row["headings"],
                    "file_hash": row["file_hash"],
                    "implemented": False,
                    "warnings": row["warnings"] or "",
                    "placeholder": bool(row["placeholder"]),
                    "duplicate_of": row["duplicate_of"],
                    "claims": claims,
                }
            )
            if len(out) >= limit:
                break
        return out
