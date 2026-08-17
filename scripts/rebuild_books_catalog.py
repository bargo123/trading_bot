#!/usr/bin/env python3
"""Rebuild docs/trading/BOOKS_FULL.md from docs/trading/books/*.md.

Does not delete extracts. Skips stub/sample files.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOOKS = ROOT / "docs" / "trading" / "books"
OUT = ROOT / "docs" / "trading" / "BOOKS_FULL.md"
SKIP = {"sample-author.md", "market-structure.md"}


def meta(path: Path) -> tuple[str, str, int]:
    text = path.read_text(encoding="utf-8", errors="replace")
    title = path.stem
    author = "Unknown"
    for i, line in enumerate(text.splitlines()[:12]):
        if line.startswith("# "):
            title = line[2:].strip()
        elif line.lower().startswith("- author:"):
            author = line.split(":", 1)[1].strip()
    words = len(re.findall(r"\b\w+\b", text))
    return title, author, words


def main() -> None:
    rows = []
    for path in sorted(BOOKS.glob("*.md")):
        if path.name in SKIP:
            continue
        title, author, words = meta(path)
        if words < 1500:
            continue
        rows.append((title.lower(), title, author, words, path))
    rows.sort()
    lines = [
        "# Full books (usable Cursor extracts)",
        "",
        "Complete cleaned text for Cursor. Attach `@docs/trading/books/<file>.md`.",
        "Do not run `scripts/rebuild_full_books_for_cursor.py` — it deletes extracts",
        "that are not in `cleaned/*.jsonl`.",
        "",
    ]
    total = 0
    for _, title, author, words, path in rows:
        total += words
        kb = path.stat().st_size / 1024
        lines.append(f"- [{title}]({path.name}) — {author} — {words:,} words — {kb:.0f} KB")
    lines.extend(["", f"**Totals:** {len(rows)} usable books, ~{total:,} words", ""])
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUT} ({len(rows)} books, {total:,} words)")


if __name__ == "__main__":
    main()
