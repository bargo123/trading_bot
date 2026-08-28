from __future__ import annotations

import json
from pathlib import Path

import aegis.research.book_strategy_extraction as extraction
from aegis.research.book_strategy_extraction import (
    build_strategy_registry,
    canonical_strategy_id,
    classify_passage,
    discover_book_sources,
)


def test_discovery_excludes_duplicates_and_non_books(tmp_path):
    (tmp_path / "book.pdf").write_bytes(b"pdf")
    (tmp_path / "book-copy.pdf").write_bytes(b"pdf")
    (tmp_path / "partial.crdownload").write_bytes(b"partial")
    (tmp_path / "photo.mp4").write_bytes(b"video")
    (tmp_path / "My_Cv.pdf").write_bytes(b"cv")
    paths = discover_book_sources(tmp_path)
    assert [path.name for path in paths] == ["book-copy.pdf", "book.pdf"]


def test_classification_never_calls_generic_advice_exact():
    result = classify_passage("There are no shortcuts to success.")
    assert result["status"] == "UNTESTABLE_SOURCE"
    assert result["reason"] == "missing_explicit_entry_exit_rule"


def test_explicit_rule_is_measurable_but_not_validated():
    result = classify_passage(
        "Buy when close crosses above the 20-period high. Stop at 1 ATR and exit after 10 seconds."
    )
    assert result["status"] == "CODED_EXACT"
    assert result["validation_status"] == "UNVALIDATED_RESEARCH"
    assert result["side_rule"] == "BUY"
    assert result["compiled_rule"] == {"structure_eq": "breakout"}


def test_explicit_but_underparameterized_rule_is_not_promoted_to_exact():
    result = classify_passage("Buy on a breakout and exit when the setup fails.")
    assert result["status"] == "COMPILE_ERROR"
    assert result["reason"] == "explicit_rule_missing_parameter"


def test_same_source_passage_has_stable_strategy_id():
    assert canonical_strategy_id("a" * 64, "b" * 64) == canonical_strategy_id("a" * 64, "b" * 64)


def test_registry_deduplicates_source_bytes_and_preserves_provenance(tmp_path, monkeypatch):
    first = tmp_path / "book.pdf"
    duplicate = tmp_path / "book-copy.pdf"
    first.write_bytes(b"same source")
    duplicate.write_bytes(b"same source")

    def fake_pages(path: Path):
        return ([{"page": 7, "text": "Buy when close crosses above the 20-period high. Stop at 1 ATR."}], {
            "status": "READ",
            "file_sha256": extraction.sha256_file(path),
            "pages_read": 1,
            "pages_with_text": 1,
        })

    monkeypatch.setattr(extraction, "extract_source_pages", fake_pages)
    output = tmp_path / "registry.jsonl"
    summary_path = tmp_path / "summary.json"
    summary = build_strategy_registry(tmp_path, output, summary_path=summary_path)

    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert summary["sources_seen"] == 2
    assert summary["sources_unique"] == 1
    assert summary["duplicate_count"] == 1
    assert len(rows) == 1
    assert rows[0]["status"] == "CODED_EXACT"
    assert rows[0]["page_start"] == 7
    assert rows[0]["source_sha256"] == extraction.sha256_file(first)
    assert json.loads(summary_path.read_text(encoding="utf-8"))["records_by_status"]["CODED_EXACT"] == 1
