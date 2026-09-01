#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rich import print

from trading_llm.extract import extract_books_dir
from trading_llm.paths import ensure_dirs, save_json


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract text from books/ into extracted/")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    root = ensure_dirs(args.root)
    report = extract_books_dir(root / "books", root / "extracted")
    out = root / "reports" / "extraction.json"
    save_json(out, report)
    print(report)
    if report.get("pdf_malformed_float_warnings"):
        print(
            f"[yellow]Suppressed {report['pdf_malformed_float_warnings']} malformed PDF float "
            f"warnings (harmless layout junk in some PDFs).[/yellow]"
        )
    if report["failures"]:
        print(f"[yellow]Failures recorded: {len(report['failures'])} (see {out})[/yellow]")
    if report["ocr_required"]:
        print(f"[yellow]OCR required for: {report['ocr_required']}[/yellow]")
    print(f"Saved report: {out}")


if __name__ == "__main__":
    main()
