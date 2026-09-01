from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from trading_llm.extract import iter_jsonl


COPYRIGHT_PATTERNS = [
    r"all rights reserved",
    r"copyright\s+©",
    r"copyright\s+\d{4}",
    r"published by",
    r"no part of this (book|publication)",
    r"isbn[\s:-]",
]
TOC_PATTERNS = [
    r"^contents$",
    r"^table of contents$",
    r"^\s*\d+(\.\d+)*\s+.+\s+\d+\s*$",
]
HEADER_FOOTER_PATTERNS = [
    r"^\s*\d+\s*$",
    r"^\s*page\s+\d+\s*$",
]


def normalize_whitespace(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Fix broken line wrapping: join lines that look mid-sentence
    lines = text.split("\n")
    merged: list[str] = []
    for line in lines:
        s = line.strip()
        if not merged:
            merged.append(s)
            continue
        prev = merged[-1]
        if (
            prev
            and s
            and not prev.endswith((".", "?", "!", ":", ";", "\"", "'"))
            and s[0].islower()
        ):
            merged[-1] = prev + " " + s
        else:
            merged.append(s)
    return "\n".join(merged).strip()


def is_boilerplate(text: str) -> bool:
    low = text.lower().strip()
    if len(low) < 40:
        # short sections handled separately
        return False
    hits = sum(1 for p in COPYRIGHT_PATTERNS if re.search(p, low))
    if hits >= 2 and len(low) < 1500:
        return True
    if re.search(r"^table of contents$", low, re.M) and low.count("\n") > 10:
        # crude TOC detection
        digit_lines = sum(1 for ln in low.splitlines() if re.search(r"\d+\s*$", ln))
        if digit_lines / max(1, len(low.splitlines())) > 0.4:
            return True
    return False


def strip_headers_footers(text: str) -> str:
    kept: list[str] = []
    for line in text.splitlines():
        if any(re.match(p, line.strip(), re.I) for p in HEADER_FOOTER_PATTERNS):
            continue
        kept.append(line)
    return "\n".join(kept)


def paragraph_hash(p: str) -> str:
    norm = re.sub(r"\s+", " ", p.strip().lower())
    return hashlib.sha1(norm.encode("utf-8")).hexdigest()


def clean_section(section: dict[str, Any]) -> dict[str, Any]:
    out = dict(section)
    status = section.get("extraction_status", "ok")
    text = section.get("text") or ""
    notes: list[str] = []

    if status in {"ocr_required", "error"}:
        out["clean_status"] = status
        out["clean_notes"] = [section.get("error") or status]
        out["text"] = ""
        return out

    text = strip_headers_footers(text)
    text = normalize_whitespace(text)

    if is_boilerplate(text):
        out["text"] = ""
        out["clean_status"] = "removed_boilerplate"
        out["clean_notes"] = ["Likely copyright/TOC/publisher boilerplate removed"]
        return out

    # Deduplicate paragraphs within section
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    seen: set[str] = set()
    unique: list[str] = []
    dup = 0
    for p in paras:
        h = paragraph_hash(p)
        if h in seen:
            dup += 1
            continue
        seen.add(h)
        unique.append(p)
    text = "\n\n".join(unique)
    if dup:
        notes.append(f"Removed {dup} duplicate paragraphs in section")

    words = len(re.findall(r"\b\w+\b", text))
    out["text"] = text
    out["word_count"] = words
    if words < 20:
        out["clean_status"] = "suspicious_short"
        notes.append(f"Only {words} words after cleaning")
    else:
        out["clean_status"] = "ok"
    out["clean_notes"] = notes
    return out


def clean_extracted_dir(extracted_dir: Path, cleaned_dir: Path) -> dict[str, Any]:
    extracted_dir = Path(extracted_dir)
    cleaned_dir = Path(cleaned_dir)
    cleaned_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(extracted_dir.glob("*.jsonl"))
    report: dict[str, Any] = {
        "books_processed": 0,
        "sections_in": 0,
        "sections_out_ok": 0,
        "removed_boilerplate": 0,
        "suspicious_short": 0,
        "ocr_required": 0,
        "errors": 0,
        "total_words": 0,
        "duplicate_paragraph_events": 0,
        "chapters_detected": 0,
        "per_book": [],
        "never_silently_discarded": True,
    }

    global_para_hashes: Counter[str] = Counter()

    for path in files:
        book_report: dict[str, Any] = {
            "file": path.name,
            "sections": [],
            "kept_sections": 0,
            "flagged_sections": 0,
        }
        out_path = cleaned_dir / path.name
        with out_path.open("w", encoding="utf-8") as out_f:
            for sec in iter_jsonl(path):
                report["sections_in"] += 1
                cleaned = clean_section(sec)
                out_f.write(json.dumps(cleaned, ensure_ascii=False) + "\n")
                status = cleaned.get("clean_status")
                words = int(cleaned.get("word_count") or 0)
                report["total_words"] += words
                if cleaned.get("chapter"):
                    report["chapters_detected"] += 1

                for p in re.split(r"\n\s*\n", cleaned.get("text") or ""):
                    if p.strip():
                        global_para_hashes[paragraph_hash(p)] += 1

                entry = {
                    "chapter": cleaned.get("chapter"),
                    "status": status,
                    "words": words,
                    "notes": cleaned.get("clean_notes"),
                }
                book_report["sections"].append(entry)

                if status == "ok":
                    report["sections_out_ok"] += 1
                    book_report["kept_sections"] += 1
                else:
                    book_report["flagged_sections"] += 1
                    if status == "removed_boilerplate":
                        report["removed_boilerplate"] += 1
                    elif status == "suspicious_short":
                        report["suspicious_short"] += 1
                    elif status == "ocr_required":
                        report["ocr_required"] += 1
                    elif status == "error":
                        report["errors"] += 1
        report["books_processed"] += 1
        report["per_book"].append(book_report)

    dup_paras = sum(1 for _, c in global_para_hashes.items() if c > 1)
    total_paras = sum(global_para_hashes.values()) or 1
    report["duplicate_paragraph_percentage"] = round(100.0 * dup_paras / max(1, len(global_para_hashes)), 2)
    report["approx_tokens"] = int(report["total_words"] * 1.3)
    report["total_paragraphs"] = total_paras
    return report
