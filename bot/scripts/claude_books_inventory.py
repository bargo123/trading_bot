#!/usr/bin/env python3
"""Inventory the trading-book corpus without reading it into an LLM context.

Reports counts, sizes, duplicate content hashes, placeholder/stub files, and
OCR-degradation heuristics. The book files stay the evidence source; this only
produces a compact index to decide what is worth retrieving.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BOOKS = REPO / "docs" / "trading" / "books"

# A page of scanned text that lost its spacing, or a run of OCR gibberish.
LONG_TOKEN = re.compile(r"[A-Za-z]{28,}")
WORD = re.compile(r"[A-Za-z']+")


def classify(path: Path) -> dict:
    raw = path.read_bytes()
    text = raw.decode("utf-8", errors="replace")
    words = WORD.findall(text)
    n_words = len(words)
    alpha = sum(char.isalpha() for char in text)
    printable = sum(char.isprintable() or char in "\n\r\t" for char in text)
    long_tokens = len(LONG_TOKEN.findall(text))
    replacement = text.count("�")
    return {
        "path": str(path.relative_to(REPO)).replace("\\", "/"),
        "bytes": len(raw),
        "words": n_words,
        "lines": text.count("\n") + 1,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "alpha_ratio": round(alpha / max(len(text), 1), 4),
        "nonprintable_ratio": round(1.0 - printable / max(len(text), 1), 5),
        "replacement_chars": replacement,
        "long_token_per_kword": round(long_tokens / max(n_words / 1000, 1e-9), 2) if n_words else 0.0,
        "placeholder": n_words < 200,
        "ocr_suspect": bool(
            n_words > 0
            and (
                replacement / max(len(text), 1) > 0.001
                or (long_tokens / max(n_words / 1000, 1e-9)) > 40
                or alpha / max(len(text), 1) < 0.55
            )
        ),
    }


def main() -> int:
    if not BOOKS.is_dir():
        print(json.dumps({"error": f"missing {BOOKS}"}, indent=2))
        return 1

    files = sorted(p for p in BOOKS.rglob("*") if p.is_file())
    rows = [classify(path) for path in files]

    by_hash: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        by_hash[row["sha256"]].append(row["path"])
    duplicates = {h: paths for h, paths in by_hash.items() if len(paths) > 1}

    total_words = sum(row["words"] for row in rows)
    summary = {
        "books_dir": str(BOOKS.relative_to(REPO)).replace("\\", "/"),
        "file_count": len(rows),
        "extensions": dict(Counter(Path(row["path"]).suffix.lower() for row in rows)),
        "total_bytes": sum(row["bytes"] for row in rows),
        "total_words": total_words,
        "median_words": sorted(row["words"] for row in rows)[len(rows) // 2] if rows else 0,
        "duplicate_groups": len(duplicates),
        "duplicate_files": sorted(p for paths in duplicates.values() for p in paths),
        "placeholders": sorted(row["path"] for row in rows if row["placeholder"]),
        "ocr_suspect": sorted(row["path"] for row in rows if row["ocr_suspect"]),
        "unreadable": [],
        "largest": sorted(rows, key=lambda r: -r["words"])[:10],
        "smallest": sorted(rows, key=lambda r: r["words"])[:10],
    }

    out = REPO / "bot" / "reports" / "claude"
    out.mkdir(parents=True, exist_ok=True)
    (out / "books_inventory.json").write_text(
        json.dumps({"summary": summary, "files": rows}, indent=2), encoding="utf-8"
    )

    lines = [
        "# Trading book corpus inventory",
        "",
        f"- Directory: `{summary['books_dir']}`",
        f"- Files: **{summary['file_count']}**",
        f"- Extensions: {summary['extensions']}",
        f"- Total size: {summary['total_bytes'] / 1_048_576:.1f} MiB",
        f"- Total words: **{summary['total_words']:,}**",
        f"- Median words/file: {summary['median_words']:,}",
        f"- Duplicate content groups: {summary['duplicate_groups']}",
        f"- Placeholder/stub files (<200 words): {len(summary['placeholders'])}",
        f"- OCR-degradation suspects: {len(summary['ocr_suspect'])}",
        "",
        "## Largest sources",
        "",
        "| words | file |",
        "| --- | --- |",
    ]
    for row in summary["largest"]:
        lines.append(f"| {row['words']:,} | `{row['path']}` |")
    if summary["placeholders"]:
        lines += ["", "## Placeholder / stub files", ""]
        lines += [f"- `{p}`" for p in summary["placeholders"]]
    if summary["ocr_suspect"]:
        lines += ["", "## OCR-degradation suspects", ""]
        lines += [f"- `{p}`" for p in summary["ocr_suspect"]]
    if duplicates:
        lines += ["", "## Duplicate content", ""]
        for paths in duplicates.values():
            lines.append(f"- {', '.join(f'`{p}`' for p in paths)}")
    lines += [
        "",
        "## How this corpus is used",
        "",
        "Books are never loaded wholesale into an LLM context. They are indexed into",
        "`bot/intel/knowledge_table.json` as structured, per-concept rows, and the",
        "runtime matches rows by regime/structure via",
        "`aegis.intel.knowledge_runtime.match_knowledge`. The original files remain the",
        "evidence source for any claim.",
    ]
    (out / "books_inventory.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    printable = {k: v for k, v in summary.items() if k not in {"largest", "smallest", "duplicate_files"}}
    print(json.dumps(printable, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
