#!/usr/bin/env python3
"""Extract owned trading PDFs into docs/trading/books/*.md for Cursor.

Does not delete existing extracts. Skips a PDF if the target markdown
already has more than min_words. Educational/systems library only.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "trading" / "books"

JOBS = [
    {
        "src": Path(r"C:\Users\Raqam\Downloads\Anna Coulling - A Complete Guide To Volume Price Analysis_ Read the book then read the market (2013, Marinablu International Ltd) - libgen.li.pdf"),
        "out": "a-complete-guide-to-volume-price-analysis-coulling.md",
        "title": "A Complete Guide To Volume Price Analysis (2013)",
        "author": "Anna Coulling",
    },
    {
        "src": Path(r"C:\Users\Raqam\Downloads\Anna Coulling - Stock Trading & Investing Using Volume Price Analysis_ Over 200 worked examples - libgen.li.pdf"),
        "out": "stock-trading-investing-using-volume-price-analysis-coulling.md",
        "title": "Stock Trading & Investing Using Volume Price Analysis (200+ examples)",
        "author": "Anna Coulling",
    },
    {
        "src": Path(r"C:\Users\Raqam\Downloads\Al Brooks - Trading Price Action Ranges Technical Analysis of Price Charts Bar by Bar for the Serious Trader (2012, Wiley Trading) - libgen.li.pdf"),
        "out": "trading-price-action-ranges-brooks.md",
        "title": "Trading Price Action Ranges (2012)",
        "author": "Al Brooks",
    },
    {
        "src": Path(r"C:\Users\Raqam\Downloads\Laurentiu Damir - Price Action Breakdown_ Exclusive Price Action Trading Approach to Financial Markets (2016, CreateSpace Independent Publishing Platform) - libgen.li.pdf"),
        "out": "price-action-breakdown-damir-2016.md",
        "title": "Price Action Breakdown (2016)",
        "author": "Laurentiu Damir",
    },
    {
        "src": Path(r"C:\Users\Raqam\Downloads\Jansen, Stefan - Hands-on machine learning for algorithmic trading design and implement investment strategies based on smart algorithms that lea (2018, Packt Publishing) - libgen.li.pdf"),
        "out": "hands-on-machine-learning-for-algorithmic-trading-jansen.md",
        "title": "Hands-On Machine Learning for Algorithmic Trading (2018)",
        "author": "Stefan Jansen",
    },
    {
        "src": Path(r"C:\Users\Raqam\Downloads\Developing High-Frequency Trading Systems_ Learn How to Implemen - Developing High-Frequency Trading Systems_ Learn How to Implement High-Frequency Trading From Scratch With C++ or Java Basics - libgen.li.pdf"),
        "out": "developing-high-frequency-trading-systems.md",
        "title": "Developing High-Frequency Trading Systems",
        "author": "Sebastien Donadio / Sourav Ghosh / Romain Rossier",
    },
    {
        "src": ROOT / "docs" / "trading" / "extra_hft_pdfs" / "Brian_Anderson_The_1_Hour_Trade_2014.pdf",
        "out": "the-1-hour-trade-anderson.md",
        "title": "The 1 Hour Trade (2014)",
        "author": "Brian Anderson",
        "skip_if_exists": True,
    },
    {
        "src": Path(
            r"C:\Users\Raqam\Downloads\A.J. Frost, Robert R. Prechter - Elliott Wave Principle_ Key To Market Behavior (2005, New Classics Library) - libgen.li.pdf"
        ),
        "out": "elliott-wave-principle-frost-prechter-2005.md",
        "title": "Elliott Wave Principle: Key To Market Behavior (2005)",
        "author": "A.J. Frost / Robert R. Prechter",
    },
    {
        "src": Path(
            r"C:\Users\Raqam\Downloads\W. D. Gann - How to Make Profits In Commodities (1976, Lambert Gann Publishing Company) - libgen.li.pdf"
        ),
        "out": "how-to-make-profits-in-commodities-gann-1976.md",
        "title": "How to Make Profits In Commodities (1976)",
        "author": "W. D. Gann",
    },
    {
        "src": Path(
            r"C:\Users\Raqam\Downloads\Barry Johnson - Algorithmic Trading and DMA_ An introduction to direct access trading strategies (2010, 4Myeloma Press) - libgen.li.pdf"
        ),
        "out": "algorithmic-trading-and-dma-johnson-2010.md",
        "title": "Algorithmic Trading and DMA (2010)",
        "author": "Barry Johnson",
    },
    {
        "src": Path(
            r"C:\Users\Raqam\Downloads\[Wiley Trading] Ernie Chan - Algorithmic Trading_ Winning Strategies and Their Rationale (2013, Wiley) - libgen.li.pdf"
        ),
        "out": "algorithmic-trading-winning-strategies-chan-2013.md",
        "title": "Algorithmic Trading: Winning Strategies and Their Rationale (2013)",
        "author": "Ernie Chan",
    },
    {
        "src": Path(
            r"C:\Users\Raqam\Downloads\Marcos Lopez de Prado - Advances in Financial Machine Learning (2018, Wiley) - libgen.li.pdf"
        ),
        "out": "advances-in-financial-machine-learning-prado-2018.md",
        "title": "Advances in Financial Machine Learning (2018)",
        "author": "Marcos López de Prado",
    },
    {
        "src": Path(
            r"C:\Users\Raqam\Downloads\Zuckerman, Gregory - The Man Who Solved the Market (2019) - libgen.li.pdf"
        ),
        "out": "the-man-who-solved-the-market-zuckerman-2019.md",
        "title": "The Man Who Solved the Market (2019)",
        "author": "Gregory Zuckerman",
    },
]


def _extract_pypdf(src: Path) -> tuple[list[tuple[int, str]], int]:
    from pypdf import PdfReader

    reader = PdfReader(str(src))
    pages: list[tuple[int, str]] = []
    empty = 0
    for i, page in enumerate(reader.pages):
        try:
            raw = page.extract_text() or ""
        except Exception:
            raw = ""
        text = re.sub(r"[ \t]+", " ", raw).strip()
        text = re.sub(r"\n{3,}", "\n\n", text)
        if text:
            pages.append((i + 1, text))
        else:
            empty += 1
    return pages, empty


def _extract_fitz(src: Path) -> tuple[list[tuple[int, str]], int]:
    import pymupdf as fitz  # type: ignore

    doc = fitz.open(str(src))
    pages: list[tuple[int, str]] = []
    empty = 0
    for i, page in enumerate(doc):
        raw = page.get_text("text") or ""
        text = re.sub(r"[ \t]+", " ", raw).strip()
        text = re.sub(r"\n{3,}", "\n\n", text)
        if text:
            pages.append((i + 1, text))
        else:
            empty += 1
    return pages, empty


def extract_pages(src: Path) -> tuple[list[tuple[int, str]], int, str]:
    try:
        pages, empty = _extract_fitz(src)
        if pages:
            return pages, empty, "fitz"
    except Exception:
        pass
    pages, empty = _extract_pypdf(src)
    return pages, empty, "pypdf"


def write_md(job: dict, pages: list[tuple[int, str]], empty: int, engine: str) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    dest = OUT / job["out"]
    parts = [
        f"# {job['title']}",
        "",
        f"- Author: {job['author']}",
        f"- Source file: `{job['src'].name}`",
        f"- Pages with text: {len(pages)}",
        f"- Empty pages: {empty}",
        f"- Extractor: {engine}",
        "",
        "---",
        "",
    ]
    for num, body in pages:
        parts.extend([f"## Page {num}", "", body, ""])
    dest.write_text("\n".join(parts) + "\n", encoding="utf-8")
    return dest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-words", type=int, default=2000)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    rc = 0
    for job in JOBS:
        src: Path = job["src"]
        dest = OUT / job["out"]
        print(f"== {job['title']}", flush=True)
        if not src.exists():
            print(f"  MISSING PDF: {src}", flush=True)
            rc = 1
            continue
        if dest.exists() and not args.force:
            words = len(re.findall(r"\b\w+\b", dest.read_text(encoding="utf-8", errors="replace")))
            if job.get("skip_if_exists") or words >= args.min_words:
                print(f"  skip existing {dest.name} ({words} words)", flush=True)
                continue
        pages, empty, engine = extract_pages(src)
        words = sum(len(re.findall(r"\b\w+\b", t)) for _, t in pages)
        print(f"  pdf={src.name} engine={engine} text_pages={len(pages)} empty={empty} words={words}", flush=True)
        if words < 500:
            print("  IMAGE-ONLY or failed extract — needs OCR", flush=True)
            rc = 1
            continue
        out = write_md(job, pages, empty, engine)
        print(f"  wrote {out} ({out.stat().st_size / 1024:.0f} KB)", flush=True)
    return rc


if __name__ == "__main__":
    sys.exit(main())
