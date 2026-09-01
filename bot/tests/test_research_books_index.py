"""Full-book knowledge index. Indexing a file does not implement its strategy."""
from __future__ import annotations

from pathlib import Path

from aegis.research.book_audit import build_book_coverage, markdown_book_coverage
from aegis.research.books_index import BookIndex, discover_books_root
from aegis.research.thousand_day_gap import calculate_thousand_day_gap


def test_index_records_provenance_and_search(tmp_path: Path):
    books = tmp_path / "books"
    books.mkdir()
    (books / "tharp.md").write_text(
        "# Trade Your Way\n\nExpectancy after costs matters more than win rate.\n\n## Warning\nDo not hide large stops.\n",
        encoding="utf-8",
    )
    idx = BookIndex(tmp_path / "idx.sqlite")
    n = idx.rebuild(books)
    assert n == 1
    hits = idx.search("expectancy")
    assert hits
    assert hits[0]["path"].endswith("tharp.md")
    assert hits[0]["title"]
    assert "Warning" in hits[0]["headings"]
    assert hits[0]["file_hash"]


def test_index_extracts_structured_claims_and_placeholders(tmp_path: Path):
    books = tmp_path / "books"
    books.mkdir()
    (books / "sample-author.md").write_text(
        "# Sample\n\nUNIQUE_PLACEHOLDER_TOKEN. Uses M5 ranges. Do not treat as implemented.\n",
        encoding="utf-8",
    )
    (books / "a.md").write_text("# Dup\nduplicate-body-alpha\n", encoding="utf-8")
    (books / "b.md").write_text("# Dup\nduplicate-body-alpha\n", encoding="utf-8")
    idx = BookIndex(tmp_path / "idx.sqlite")
    n = idx.rebuild(books)
    assert n == 3
    hits = [h for h in idx.search("UNIQUE_PLACEHOLDER_TOKEN") if str(h["path"]).endswith("sample-author.md")]
    assert hits
    assert bool(hits[0]["placeholder"])
    assert hits[0]["implemented"] is False
    assert "M5" in (hits[0]["claims"].get("timeframes") or [])
    dups = idx.search("duplicate-body-alpha")
    assert len(dups) == 2
    assert dups[0]["file_hash"] == dups[1]["file_hash"]
    assert any(r.get("duplicate_of") for r in dups)


def test_discover_books_root_prefers_worktree_then_original(tmp_path, monkeypatch):
    missing = tmp_path / "empty"
    monkeypatch.setattr("aegis.research.books_index.WORKTREE_BOOKS", missing / "none")
    orig = tmp_path / "orig" / "docs" / "trading" / "books"
    orig.mkdir(parents=True)
    (orig / "a.md").write_text("# A\n", encoding="utf-8")
    monkeypatch.setattr("aegis.research.books_index.ORIGINAL_BOOKS", orig)
    root = discover_books_root()
    assert root == orig


def test_book_coverage_reconciles_catalog_notes_index_and_near_duplicates(tmp_path: Path):
    books = tmp_path / "books"
    books.mkdir()
    shared = "A" * 2_000
    (books / "alpha.md").write_text(f"# Alpha\n\n{shared}\n", encoding="utf-8")
    (books / "beta.md").write_text(f"# Alpha\n\n{shared[:-1]}B\n", encoding="utf-8")
    (books / "sample-author.md").write_text("# Sample\nplaceholder\n", encoding="utf-8")
    catalog = tmp_path / "BOOKS_FULL.md"
    catalog.write_text("- [Alpha](alpha.md)\n", encoding="utf-8")

    ledger = build_book_coverage(
        books_dir=books,
        catalog_path=catalog,
        index_path=tmp_path / "index.sqlite",
        notes_dir=tmp_path / "notes",
        ledger_path=tmp_path / "ledger.json",
    )

    assert ledger["reconciliation"]["all_extracts_indexed"] is True
    assert ledger["reconciliation"]["all_extracts_noted"] is True
    alpha = next(row for row in ledger["records"] if row["filename"] == "alpha.md")
    placeholder = next(row for row in ledger["records"] if row["filename"] == "sample-author.md")
    assert alpha["cataloged"] is True
    assert alpha["word_count"] == 2
    assert placeholder["coverage_status"] == "placeholder"
    assert placeholder["catalog_exclusion"] == "below_usable_word_minimum"
    assert ledger["near_duplicate_candidates"]
    report = markdown_book_coverage(ledger)
    assert "Indexing a file is not implementation" in report
    assert "Hand-curated compliance join" in report
    idx = BookIndex(tmp_path / "index.sqlite")
    assert len(idx.all_rows()) == 3


def test_thousand_day_gap_refuses_size_up_for_negative_observed_history(tmp_path: Path):
    deals = tmp_path / "deals.jsonl"
    deals.write_text(
        "\n".join(
            [
                '{"source":"mt5_deal","ticket":"1","pnl":-0.10,"qty":0.01,"ts":"2026-01-01T01:00:00+00:00"}',
                '{"source":"mt5_deal","ticket":"2","pnl":0.05,"qty":0.01,"ts":"2026-01-02T01:00:00+00:00"}',
                '{"source":"mt5_deal","ticket":"2","pnl":0.04,"qty":0.01,"ts":"2026-01-02T01:00:00+00:00"}',
            ]
        ),
        encoding="utf-8",
    )
    gap = calculate_thousand_day_gap(deals)
    assert gap["n_trades"] == 2
    assert gap["mean_active_day_pnl_usd"] < 0
    assert gap["required_quantity_if_linear"] is None
    assert "size-up cannot close" in gap["size_conclusion"]
