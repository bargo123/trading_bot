#!/usr/bin/env python3
"""Rebuild docs/trading/books/*.md from cleaned/*.jsonl (full book text)."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> None:
    cleaned = ROOT / "cleaned"
    out_root = ROOT / "docs" / "trading" / "books"
    out_root.mkdir(parents=True, exist_ok=True)
    for p in out_root.glob("*.md"):
        p.unlink()

    catalog = [
        "# Full books (from cleaned extracts)",
        "",
        "Complete cleaned text for Cursor. Prefer `@docs/trading/books/<book>.md`.",
        "",
    ]
    total_words = 0
    books = 0

    for path in sorted(cleaned.glob("*.jsonl")):
        sections = []
        for line in path.open(encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            text = (obj.get("text") or "").strip()
            if not text or obj.get("clean_status") == "removed_boilerplate":
                continue
            sections.append(obj)
        if not sections:
            continue

        title = sections[0].get("book_title") or path.stem
        author = sections[0].get("author") or "Unknown"
        source = sections[0].get("source_file") or path.name
        safe = re.sub(r"[^a-zA-Z0-9_-]+", "-", title).strip("-").lower()[:80] or path.stem

        parts = [
            f"# {title}",
            "",
            f"- Author: {author}",
            f"- Source file: `{source}`",
            f"- Sections: {len(sections)}",
            "",
            "---",
            "",
        ]
        words = 0
        for i, sec in enumerate(sections, 1):
            chapter = sec.get("chapter") or f"Section {i}"
            ps, pe = sec.get("page_start"), sec.get("page_end")
            page = ""
            if ps is not None and pe is not None:
                page = f" (pp. {ps}-{pe})"
            elif ps is not None:
                page = f" (p. {ps})"
            body = sec.get("text") or ""
            words += len(re.findall(r"\b\w+\b", body))
            parts.extend([f"## {chapter}{page}", "", body, ""])

        out = out_root / f"{safe}.md"
        if out.exists():
            out = out_root / f"{safe}-{path.stem[-8:]}.md"
        out.write_text("\n".join(parts) + "\n", encoding="utf-8")
        books += 1
        total_words += words
        catalog.append(
            f"- [{title}]({out.name}) — {author} — {words:,} words — {out.stat().st_size/1024:.0f} KB"
        )

    catalog += [
        "",
        f"**Totals:** {books} books, ~{total_words:,} words",
        "",
    ]
    (ROOT / "docs" / "trading" / "BOOKS_FULL.md").write_text("\n".join(catalog) + "\n", encoding="utf-8")
    print(f"Wrote {books} full books (~{total_words:,} words) to {out_root}")


if __name__ == "__main__":
    main()
