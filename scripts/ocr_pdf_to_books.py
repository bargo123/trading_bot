#!/usr/bin/env python3
"""OCR scanned trading PDFs into docs/trading/books/*.md.

Uses RapidOCR (onnx) + PyMuPDF render. For image-only libgen scans.
Checkpoints every 10 pages so a crash can resume.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "trading" / "books"

JOBS = [
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
]


def _cap_max_side(img, max_side: int):
    import cv2

    h, w = img.shape[:2]
    long_side = max(h, w)
    if long_side <= max_side or max_side <= 0:
        return img
    ratio = max_side / long_side
    return cv2.resize(img, (max(1, int(w * ratio)), max(1, int(h * ratio))))


def _page_gray(page, scale: float, max_side: int):
    import cv2
    import numpy as np
    import pymupdf

    best = None
    best_area = 0
    for im in page.get_images() or []:
        area = int(im[2]) * int(im[3])
        if area > best_area:
            best_area = area
            best = im
    if best is not None and best_area >= 80 * 80:
        info = page.parent.extract_image(best[0])
        arr = np.frombuffer(info["image"], dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
        if img is not None:
            return _cap_max_side(img, max_side)
    pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), colorspace=pymupdf.csGRAY, alpha=False)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w)
    return _cap_max_side(img, max_side)


def _ocr_page(ocr, page, scale: float, use_cls: bool, max_side: int) -> str:
    native = (page.get_text("text") or "").strip()
    if len(re.findall(r"\b\w+\b", native)) >= 40:
        return native
    img = _page_gray(page, scale, max_side)
    result, _ = ocr(img, use_cls=use_cls)
    if not result:
        return native
    lines = []
    for item in result:
        if not item or len(item) < 2:
            continue
        text = item[1]
        if isinstance(text, str) and text.strip():
            lines.append(text.strip())
    return "\n".join(lines).strip() or native


def _checkpoint_path(dest: Path) -> Path:
    return dest.with_suffix(".partial.json")


def _load_checkpoint(dest: Path) -> dict:
    path = _checkpoint_path(dest)
    if not path.exists():
        return {"next_page": 0, "pages": [], "empty": 0}
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("next_page", 0)
    data.setdefault("pages", [])
    data.setdefault("empty", 0)
    return data


def _save_checkpoint(dest: Path, next_page: int, pages: list, empty: int) -> None:
    payload = {"next_page": next_page, "pages": pages, "empty": empty}
    _checkpoint_path(dest).write_text(json.dumps(payload), encoding="utf-8")


def _write_markdown(job: dict, dest: Path, src: Path, pages: list, empty: int, scale: float) -> None:
    parts = [
        f"# {job['title']}",
        "",
        f"- Author: {job['author']}",
        f"- Source file: `{src.name}`",
        f"- Pages with text: {len(pages)}",
        f"- Empty pages: {empty}",
        f"- Extractor: rapidocr scale={scale}",
        "",
        "---",
        "",
    ]
    for num, body in pages:
        parts.extend([f"## Page {num}", "", body, ""])
    dest.write_text("\n".join(parts) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scale", type=float, default=1.5)
    parser.add_argument("--max-side", type=int, default=1400)
    parser.add_argument("--min-words", type=int, default=2000)
    parser.add_argument("--only", default="")
    parser.add_argument("--use-cls", action="store_true")
    args = parser.parse_args()
    os.environ.setdefault("OMP_NUM_THREADS", "2")
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    os.environ.setdefault("MKL_NUM_THREADS", "1")
    import pymupdf
    from rapidocr_onnxruntime import RapidOCR

    ocr = RapidOCR(intra_op_num_threads=2, inter_op_num_threads=1)
    OUT.mkdir(parents=True, exist_ok=True)
    rc = 0
    for job in JOBS:
        if args.only and args.only.lower() not in job["out"] and args.only.lower() not in job["title"].lower():
            continue
        src: Path = job["src"]
        dest = OUT / job["out"]
        print(f"== {job['title']}", flush=True)
        if not src.exists():
            print(f"  MISSING PDF: {src}", flush=True)
            rc = 1
            continue
        if dest.exists():
            words = len(re.findall(r"\b\w+\b", dest.read_text(encoding="utf-8", errors="replace")))
            if words >= args.min_words:
                print(f"  skip existing {dest.name} ({words} words)", flush=True)
                ck = _checkpoint_path(dest)
                if ck.exists():
                    ck.unlink()
                continue
        doc = pymupdf.open(str(src))
        ck = _load_checkpoint(dest)
        pages: list[tuple[int, str]] = [(int(n), str(t)) for n, t in ck["pages"]]
        empty = int(ck["empty"])
        start = int(ck["next_page"])
        if start:
            print(f"  resume at page {start + 1}/{doc.page_count} words={sum(len(re.findall(r'\b\w+\b', t)) for _, t in pages)}", flush=True)
        for i in range(start, doc.page_count):
            page = doc[i]
            t0 = time.time()
            text = _ocr_page(ocr, page, args.scale, use_cls=args.use_cls, max_side=args.max_side)
            text = re.sub(r"[ \t]+", " ", text).strip()
            text = re.sub(r"\n{3,}", "\n\n", text)
            if text:
                pages.append((i + 1, text))
            else:
                empty += 1
            elapsed = time.time() - t0
            if i < start + 2 or (i + 1) % 5 == 0 or i + 1 == doc.page_count:
                _save_checkpoint(dest, i + 1, pages, empty)
                words_so_far = sum(len(re.findall(r"\b\w+\b", t)) for _, t in pages)
                print(
                    f"  page {i + 1}/{doc.page_count} {elapsed:.1f}s text_pages={len(pages)} words={words_so_far}",
                    flush=True,
                )
        words = sum(len(re.findall(r"\b\w+\b", t)) for _, t in pages)
        print(f"  ocr_pages={len(pages)} empty={empty} words={words}", flush=True)
        if words < 500:
            print("  OCR produced too little text", flush=True)
            rc = 1
            continue
        _write_markdown(job, dest, src, pages, empty, args.scale)
        ck_path = _checkpoint_path(dest)
        if ck_path.exists():
            ck_path.unlink()
        print(f"  wrote {dest} ({dest.stat().st_size / 1024:.0f} KB)", flush=True)
    return rc


if __name__ == "__main__":
    sys.exit(main())
