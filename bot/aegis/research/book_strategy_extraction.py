"""Extract conservative, provenance-linked strategy records from local books.

This module reads source files for research inventory only.  A passage is not
treated as a validated strategy merely because it contains trading vocabulary;
the classifier is deliberately conservative and records unsupported material
as proxy or untestable evidence.
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping

SUPPORTED_SUFFIXES = frozenset({".pdf", ".djvu"})
EXCLUDED_NAMES = frozenset({"my_cv.pdf"})
EXCLUDED_PREFIXES = ("report-", "unconfirmed ")
MAX_EXCERPT_CHARS = 1_600

_DIRECTION_RE = re.compile(r"\b(buy|sell|long|short|bullish|bearish)\b", re.I)
_ENTRY_RE = re.compile(
    r"\b(enter|entry|open|trigger|buy|sell|go long|go short|cross(?:es|ed)?|break(?:out|s)?)\b",
    re.I,
)
_EXIT_RE = re.compile(
    r"\b(exit|exits|close|stop(?:-loss)?|target|take profit|invalidation|scratch|timeout|time stop)\b",
    re.I,
)
_PARAMETER_RE = re.compile(
    r"(?:\d+(?:\.\d+)?\s*(?:%|pips?|ticks?|points?|seconds?|minutes?|periods?|bars?)|\bATR\b|\bSMA\b|\bEMA\b|\bVWAP\b|\bRSI\b|\bMACD\b|\bADX\b|\bBollinger\b|\bstochastic\b)",
    re.I,
)
_MECHANISM_TERMS = (
    ("mean_reversion", ("mean reversion", "mean-reverting", "oversold", "overbought")),
    ("breakout", ("breakout", "break out", "range expansion")),
    ("reversal", ("reversal", "reverse", "rejection", "failed break")),
    ("momentum", ("momentum", "trend following", "continuation")),
    ("order_flow", ("order flow", "order-flow", "market depth", "level 2")),
    ("market_profile", ("market profile", "value area", "point of control")),
    ("volume_price", ("volume price", "volume analysis", "tick volume")),
    ("candlestick", ("candlestick", "candle pattern", "engulfing", "doji")),
    ("statistical_arbitrage", ("statistical arbitrage", "pairs trading", "cointegration")),
    ("volatility", ("volatility", "atr", "volatility breakout")),
    ("scalping", ("scalp", "scalping", "high frequency")),
)
_FEATURE_TERMS = (
    ("spread", ("spread", "bid", "ask")),
    ("volume", ("volume", "order flow", "market depth")),
    ("volatility", ("volatility", "atr")),
    ("momentum", ("momentum", "return", "rate of change")),
    ("moving_average", ("moving average", "sma", "ema")),
    ("oscillator", ("rsi", "stochastic", "macd")),
    ("structure", ("support", "resistance", "market structure", "swing")),
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_strategy_id(source_sha256: str, passage_hash: str) -> str:
    value = f"{source_sha256}:{passage_hash}".encode("utf-8")
    return f"bst_{hashlib.sha256(value).hexdigest()[:24]}"


def discover_book_sources(downloads_dir: Path) -> list[Path]:
    """Return supported source files, including byte-identical duplicates."""
    root = Path(downloads_dir)
    paths = []
    for path in root.iterdir() if root.is_dir() else ():
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_SUFFIXES:
            continue
        name = path.name.lower()
        if name in EXCLUDED_NAMES or any(name.startswith(prefix) for prefix in EXCLUDED_PREFIXES):
            continue
        paths.append(path)
    return sorted(paths, key=lambda item: item.name.lower())


def extract_source_pages(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Read all available pages and return explicit extraction status."""
    source = Path(path)
    file_hash = sha256_file(source)
    base = {"file_sha256": file_hash, "source_path": str(source), "pages_read": 0, "pages_with_text": 0}
    if source.suffix.lower() == ".djvu":
        return [], {**base, "status": "UNSUPPORTED_FORMAT", "reason": "djvu_decoder_unavailable"}
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        return [], {**base, "status": "EXTRACTION_FAILED", "reason": f"missing_dependency:{type(exc).__name__}"}

    pages: list[dict[str, Any]] = []
    try:
        # Some books contain malformed pointing tables that emit thousands of
        # warnings. Suppress parser noise while retaining the final status.
        with contextlib.redirect_stderr(io.StringIO()):
            reader = PdfReader(str(source), strict=False)
            for number, page in enumerate(reader.pages, start=1):
                text = page.extract_text() or ""
                pages.append({"page": number, "text": text})
    except Exception as exc:  # malformed/encrypted PDFs remain auditable
        return pages, {
            **base,
            "status": "EXTRACTION_FAILED",
            "reason": f"{type(exc).__name__}:{str(exc)[:240]}",
            "pages_read": len(pages),
            "pages_with_text": sum(bool(row["text"].strip()) for row in pages),
        }
    pages_with_text = sum(bool(row["text"].strip()) for row in pages)
    status = "READ" if pages_with_text else "EMPTY_TEXT"
    return pages, {**base, "status": status, "pages_read": len(pages), "pages_with_text": pages_with_text}


def _mechanism_family(text: str) -> str | None:
    lowered = text.lower()
    for family, terms in _MECHANISM_TERMS:
        if any(term in lowered for term in terms):
            return family
    return None


def _required_features(text: str) -> list[str]:
    lowered = text.lower()
    return [name for name, terms in _FEATURE_TERMS if any(term in lowered for term in terms)]


def _side_rule(text: str) -> str | None:
    lowered = text.lower()
    has_buy = bool(re.search(r"\b(buy|long|bullish)\b", lowered))
    has_sell = bool(re.search(r"\b(sell|short|bearish)\b", lowered))
    if has_buy and not has_sell:
        return "BUY"
    if has_sell and not has_buy:
        return "SELL"
    return None


def classify_passage(text: str) -> dict[str, Any]:
    """Classify one passage without assigning performance or execution authority."""
    excerpt = re.sub(r"\s+", " ", str(text or "")).strip()
    lowered = excerpt.lower()
    direction = bool(_DIRECTION_RE.search(excerpt))
    entry = bool(_ENTRY_RE.search(excerpt))
    exit_rule = bool(_EXIT_RE.search(excerpt))
    parameter = bool(_PARAMETER_RE.search(excerpt))
    family = _mechanism_family(excerpt)
    result: dict[str, Any] = {
        "entry_rule": excerpt if entry else None,
        "exit_rule": excerpt if exit_rule else None,
        "side_rule": _side_rule(excerpt),
        "strategy_family": family,
        "required_features": _required_features(excerpt),
        "validation_status": "UNVALIDATED_RESEARCH",
        "evidence_status": "NO_SAMPLES",
        "excerpt": excerpt[:MAX_EXCERPT_CHARS],
    }
    if direction and entry and exit_rule and parameter:
        result.update({"status": "CODED_EXACT", "reason": "explicit_entry_exit_rule"})
    elif direction and entry and exit_rule:
        result.update({"status": "COMPILE_ERROR", "reason": "explicit_rule_missing_parameter"})
    elif family and (entry or exit_rule):
        result.update({"status": "FAMILY_PROXY", "reason": "mechanism_without_complete_rule"})
    else:
        result.update({"status": "UNTESTABLE_SOURCE", "reason": "missing_explicit_entry_exit_rule"})
    # Keep lint/static analysis from treating this as an omitted validation.
    result["source_text_present"] = bool(lowered)
    return result


def _passage_windows(pages: Iterable[Mapping[str, Any]]) -> Iterable[tuple[int, str]]:
    for page in pages:
        number = int(page.get("page") or 0)
        text = str(page.get("text") or "")
        if not text.strip() or not (_DIRECTION_RE.search(text) or _MECHANISM_TERMS and _mechanism_family(text)):
            continue
        paragraphs = [re.sub(r"\s+", " ", item).strip() for item in re.split(r"\n\s*\n", text) if item.strip()]
        if not paragraphs:
            paragraphs = [re.sub(r"\s+", " ", text).strip()]
        for paragraph in paragraphs:
            if len(paragraph) > MAX_EXCERPT_CHARS:
                paragraph = paragraph[:MAX_EXCERPT_CHARS]
            yield number, paragraph


def _source_title(path: Path, pages: Iterable[Mapping[str, Any]]) -> str:
    for page in pages:
        for line in str(page.get("text") or "").splitlines():
            line = re.sub(r"\s+", " ", line).strip()
            if len(line) >= 4:
                return line[:240]
    return path.stem.replace("_", " ").strip()


def build_strategy_registry(
    downloads_dir: Path,
    output_path: Path,
    *,
    summary_path: Path | None = None,
) -> dict[str, Any]:
    """Read the corpus and write canonical strategy records as JSONL."""
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    paths = discover_book_sources(downloads_dir)
    seen_sources: dict[str, str] = {}
    seen_passages: dict[str, str] = {}
    records: list[dict[str, Any]] = []
    source_statuses: list[dict[str, Any]] = []
    duplicate_count = 0
    duplicate_passage_count = 0
    for path in paths:
        file_hash = sha256_file(path)
        if file_hash in seen_sources:
            duplicate_count += 1
            source_statuses.append({"path": str(path), "status": "DUPLICATE", "duplicate_of": seen_sources[file_hash], "file_sha256": file_hash})
            continue
        seen_sources[file_hash] = str(path)
        pages, metadata = extract_source_pages(path)
        source_statuses.append({"path": str(path), **metadata})
        if metadata.get("status") != "READ":
            continue
        title = _source_title(path, pages)
        source_id = f"src_{file_hash[:24]}"
        for page_number, passage in _passage_windows(pages):
            passage_hash = hashlib.sha256(passage.encode("utf-8", errors="replace")).hexdigest()
            if passage_hash in seen_passages:
                duplicate_passage_count += 1
                continue
            seen_passages[passage_hash] = source_id
            classified = classify_passage(passage)
            records.append({
                "record_type": "strategy",
                "strategy_id": canonical_strategy_id(file_hash, passage_hash),
                "source_id": source_id,
                "source_title": title,
                "source_path": str(path),
                "source_sha256": file_hash,
                "passage_hash": passage_hash,
                "page_start": page_number,
                "page_end": page_number,
                "extraction_method": "pypdf_text",
                "status": classified.pop("status"),
                "reason": classified.pop("reason"),
                **classified,
            })

    with output.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")
    records_by_status: dict[str, int] = {}
    for record in records:
        status = str(record["status"])
        records_by_status[status] = records_by_status.get(status, 0) + 1
    summary: dict[str, Any] = {
        "schema": "book_strategy_registry.v1",
        "downloads_dir": str(downloads_dir),
        "sources_seen": len(paths),
        "sources_unique": len(seen_sources),
        "pages_read": sum(int(item.get("pages_read") or 0) for item in source_statuses),
        "pages_with_text": sum(int(item.get("pages_with_text") or 0) for item in source_statuses),
        "records": len(records),
        "records_by_status": records_by_status,
        "duplicate_count": duplicate_count,
        "duplicate_passage_count": duplicate_passage_count,
        "unsupported_count": sum(item.get("status") == "UNSUPPORTED_FORMAT" for item in source_statuses),
        "extraction_failures": sum(item.get("status") == "EXTRACTION_FAILED" for item in source_statuses),
        "source_hashes": sorted(seen_sources),
        "sources": source_statuses,
    }
    if summary_path is not None:
        target = Path(summary_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return summary


__all__ = [
    "build_strategy_registry",
    "canonical_strategy_id",
    "classify_passage",
    "discover_book_sources",
    "extract_source_pages",
    "sha256_file",
]
