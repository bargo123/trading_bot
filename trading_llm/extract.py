from __future__ import annotations

import hashlib
import json
import logging
import re
import warnings
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterator


SUPPORTED_SUFFIXES = {".pdf", ".epub", ".txt", ".md", ".markdown"}


class _PypdfFloatNoiseFilter(logging.Filter):
    """Drop malformed PDF float warnings; count them for the report."""

    def __init__(self) -> None:
        super().__init__()
        self.count = 0

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        if "FloatObject" in msg or "could not convert string to float" in msg:
            self.count += 1
            return False
        return True


@dataclass
class ExtractedSection:
    book_id: str
    book_title: str
    author: str
    chapter: str
    source_file: str
    page_start: int | None
    page_end: int | None
    text: str
    extraction_status: str = "ok"  # ok | empty | ocr_required | error
    error: str | None = None
    pdf_float_warnings: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def stable_book_id(source_file: str) -> str:
    digest = hashlib.sha1(source_file.encode("utf-8")).hexdigest()[:12]
    stem = Path(source_file).stem
    safe = re.sub(r"[^a-zA-Z0-9_-]+", "-", stem).strip("-").lower()[:40] or "book"
    return f"{safe}-{digest}"


def guess_title_author(path: Path) -> tuple[str, str]:
    stem = path.stem.replace("_", " ").strip()
    # Patterns like "Author - Title" (keep hyphenated words intact)
    if " - " in stem:
        left, right = stem.split(" - ", 1)
        left, right = left.strip(), right.strip()
        if len(left) <= len(right):
            return right, left
        return left, right
    return stem, "Unknown"


def extract_txt(path: Path, book_id: str, title: str, author: str) -> list[ExtractedSection]:
    text = path.read_text(encoding="utf-8", errors="replace")
    chapters = _split_markdownish_chapters(text)
    out: list[ExtractedSection] = []
    for i, (chapter, body) in enumerate(chapters, start=1):
        out.append(
            ExtractedSection(
                book_id=book_id,
                book_title=title,
                author=author,
                chapter=chapter or f"Section {i}",
                source_file=path.name,
                page_start=None,
                page_end=None,
                text=body.strip(),
                extraction_status="ok" if body.strip() else "empty",
            )
        )
    return out


def extract_pdf(path: Path, book_id: str, title: str, author: str) -> list[ExtractedSection]:
    try:
        from pypdf import PdfReader
    except ImportError as e:
        raise RuntimeError("pypdf is required for PDF extraction") from e

    noise = _PypdfFloatNoiseFilter()
    pypdf_loggers = [
        logging.getLogger("pypdf"),
        logging.getLogger("pypdf._reader"),
        logging.getLogger("pypdf.generic"),
        logging.getLogger("pypdf.generic._base"),
    ]
    for lg in pypdf_loggers:
        lg.addFilter(noise)

    try:
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message=".*FloatObject.*")
            warnings.filterwarnings("ignore", message=".*could not convert string to float.*")
            try:
                reader = PdfReader(str(path), strict=False)
            except TypeError:
                reader = PdfReader(str(path))
            except Exception as exc:
                return [
                    ExtractedSection(
                        book_id=book_id,
                        book_title=title,
                        author=author,
                        chapter="(open-failed)",
                        source_file=path.name,
                        page_start=None,
                        page_end=None,
                        text="",
                        extraction_status="error",
                        error=f"Could not open PDF: {exc}",
                        pdf_float_warnings=noise.count,
                    )
                ]

            if getattr(reader, "is_encrypted", False):
                try:
                    reader.decrypt("")
                except Exception as exc:
                    return [
                        ExtractedSection(
                            book_id=book_id,
                            book_title=title,
                            author=author,
                            chapter="(encrypted)",
                            source_file=path.name,
                            page_start=None,
                            page_end=None,
                            text="",
                            extraction_status="error",
                            error=(
                                "PDF appears encrypted/DRM-protected or needs the cryptography "
                                f"package to decrypt. Details: {exc}"
                            ),
                            pdf_float_warnings=noise.count,
                        )
                    ]

            pages: list[tuple[int, str]] = []
            empty_pages = 0
            for i, page in enumerate(reader.pages, start=1):
                try:
                    text = page.extract_text() or ""
                except Exception:
                    text = ""
                    pages.append((i, ""))
                    empty_pages += 1
                    continue
                if not text.strip():
                    empty_pages += 1
                pages.append((i, text))
    finally:
        for lg in pypdf_loggers:
            lg.removeFilter(noise)

    total = len(pages) or 1
    empty_ratio = empty_pages / total
    if empty_ratio >= 0.8:
        return [
            ExtractedSection(
                book_id=book_id,
                book_title=title,
                author=author,
                chapter="(scanned-pdf)",
                source_file=path.name,
                page_start=1,
                page_end=total,
                text="",
                extraction_status="ocr_required",
                error=(
                    f"Text extraction mostly empty ({empty_pages}/{total} pages). "
                    "This looks like a scanned PDF — run optional OCR separately."
                ),
                pdf_float_warnings=noise.count,
            )
        ]

    # Group into chapter-sized windows of ~10 pages while preserving page ranges
    out: list[ExtractedSection] = []
    chunk_size = 10
    for start in range(0, len(pages), chunk_size):
        group = pages[start : start + chunk_size]
        body = "\n\n".join(t for _, t in group if t.strip())
        page_start = group[0][0]
        page_end = group[-1][0]
        chapter = _detect_chapter_heading(body) or f"Pages {page_start}-{page_end}"
        out.append(
            ExtractedSection(
                book_id=book_id,
                book_title=title,
                author=author,
                chapter=chapter,
                source_file=path.name,
                page_start=page_start,
                page_end=page_end,
                text=body.strip(),
                extraction_status="ok" if body.strip() else "empty",
                pdf_float_warnings=noise.count if start == 0 else 0,
            )
        )
    return out


def extract_epub(path: Path, book_id: str, title: str, author: str) -> list[ExtractedSection]:
    try:
        import ebooklib
        from ebooklib import epub
        from bs4 import BeautifulSoup
    except ImportError as e:
        raise RuntimeError("ebooklib and beautifulsoup4 are required for EPUB extraction") from e

    book = epub.read_epub(str(path))
    meta_title = book.get_metadata("DC", "title")
    meta_creator = book.get_metadata("DC", "creator")
    if meta_title:
        title = meta_title[0][0] or title
    if meta_creator:
        author = meta_creator[0][0] or author

    out: list[ExtractedSection] = []
    idx = 0
    for item in book.get_items():
        if item.get_type() != ebooklib.ITEM_DOCUMENT:
            continue
        idx += 1
        soup = BeautifulSoup(item.get_content(), "lxml")
        for tag in soup(["script", "style"]):
            tag.decompose()
        text = soup.get_text("\n")
        heading = ""
        h = soup.find(["h1", "h2", "h3"])
        if h:
            heading = h.get_text(" ", strip=True)
        out.append(
            ExtractedSection(
                book_id=book_id,
                book_title=title,
                author=author,
                chapter=heading or f"Document {idx}",
                source_file=path.name,
                page_start=None,
                page_end=None,
                text=text.strip(),
                extraction_status="ok" if text.strip() else "empty",
            )
        )
    if not out:
        out.append(
            ExtractedSection(
                book_id=book_id,
                book_title=title,
                author=author,
                chapter="(empty-epub)",
                source_file=path.name,
                page_start=None,
                page_end=None,
                text="",
                extraction_status="empty",
                error="No document items found in EPUB",
            )
        )
    return out


def extract_file(path: Path) -> list[ExtractedSection]:
    if not path.is_file():
        raise FileNotFoundError(path)
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise ValueError(f"Unsupported file type: {suffix}")

    book_id = stable_book_id(path.name)
    title, author = guess_title_author(path)
    if suffix in {".txt", ".md", ".markdown"}:
        return extract_txt(path, book_id, title, author)
    if suffix == ".pdf":
        return extract_pdf(path, book_id, title, author)
    if suffix == ".epub":
        return extract_epub(path, book_id, title, author)
    raise ValueError(f"Unsupported file type: {suffix}")


def extract_books_dir(books_dir: Path, out_dir: Path) -> dict[str, Any]:
    books_dir = Path(books_dir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(
        p for p in books_dir.iterdir() if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES
    )
    report: dict[str, Any] = {
        "books_found": len(files),
        "books_processed": 0,
        "sections_written": 0,
        "failures": [],
        "ocr_required": [],
        "pdf_malformed_float_warnings": 0,
        "files": [],
        "note": (
            "Malformed PDF float warnings (e.g. '100.-54') are common in some books; "
            "pypdf substitutes 0.0 and extraction usually continues."
        ),
    }

    if not files:
        report["failures"].append(
            {
                "file": None,
                "error": f"No supported books found in {books_dir}. Place PDF/EPUB/TXT/MD files there.",
            }
        )
        return report

    for path in files:
        file_info: dict[str, Any] = {"file": path.name, "status": "ok", "sections": 0, "pdf_float_warnings": 0}
        try:
            sections = extract_file(path)
            out_path = out_dir / f"{stable_book_id(path.name)}.jsonl"
            float_warns = sum(int(getattr(sec, "pdf_float_warnings", 0) or 0) for sec in sections)
            file_info["pdf_float_warnings"] = float_warns
            report["pdf_malformed_float_warnings"] += float_warns
            with out_path.open("w", encoding="utf-8") as f:
                for sec in sections:
                    f.write(json.dumps(sec.to_dict(), ensure_ascii=False) + "\n")
                    report["sections_written"] += 1
                    if sec.extraction_status == "ocr_required":
                        report["ocr_required"].append(path.name)
                    if sec.extraction_status == "error":
                        report["failures"].append({"file": path.name, "error": sec.error})
            file_info["sections"] = len(sections)
            report["books_processed"] += 1
        except Exception as exc:
            file_info["status"] = "error"
            file_info["error"] = str(exc)
            report["failures"].append({"file": path.name, "error": str(exc)})
        report["files"].append(file_info)

    return report


def _split_markdownish_chapters(text: str) -> list[tuple[str, str]]:
    parts = re.split(r"(?m)^(#{1,3}\s+.+)$", text)
    if len(parts) == 1:
        return [("", text)]
    chapters: list[tuple[str, str]] = []
    # parts[0] is preface before first heading
    if parts[0].strip():
        chapters.append(("Preface", parts[0]))
    i = 1
    while i < len(parts):
        heading = parts[i].lstrip("#").strip()
        body = parts[i + 1] if i + 1 < len(parts) else ""
        chapters.append((heading, body))
        i += 2
    return chapters


def _detect_chapter_heading(text: str) -> str | None:
    for line in text.splitlines()[:20]:
        s = line.strip()
        if re.match(r"^(chapter|part)\s+\d+", s, re.I):
            return s[:120]
        if re.match(r"^#{1,3}\s+", s):
            return s.lstrip("#").strip()[:120]
    return None


def iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    with Path(path).open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)
