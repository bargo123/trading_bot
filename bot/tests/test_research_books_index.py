"""Full-book knowledge index. Indexing a file does not implement its strategy."""
from __future__ import annotations

from pathlib import Path

from aegis.research.books_index import BookIndex, discover_books_root


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
