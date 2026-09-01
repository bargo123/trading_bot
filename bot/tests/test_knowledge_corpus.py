"""Knowledge layer tests: manifest integrity + verbatim passage retrieval."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai_council.knowledge import corpus  # noqa: E402


def test_manifest_is_rebuilt_and_consistent():
    manifest = corpus.build_manifest()
    assert manifest["schema"] == "corpus_manifest.v1"
    assert manifest["n_books"] >= 50
    assert manifest["n_placeholders"] >= 2
    titles = [b["title"] for b in manifest["books"]]
    assert any("Trading In The Zone" in t for t in titles)


def test_manifest_round_trip_matches_build():
    built = corpus.build_manifest()
    loaded = corpus.load_manifest()
    assert loaded["n_books"] == built["n_books"]
    assert loaded["books"][0]["file_hash"] == built["books"][0]["file_hash"]


def test_retrieve_returns_verbatim_passages():
    hits = corpus.retrieve("expectancy", limit=3)
    assert 1 <= len(hits) <= 3
    for hit in hits:
        assert hit["passage"]
        assert hit["book"]
        assert hit["file_hash"]
        assert hit["passage_token_count"] > 0
        # verbatim: the original passage must contain the query (case-insensitive)
        assert "expectancy" in hit["passage"].lower()


def test_retrieve_skips_placeholders():
    manifest = corpus.load_manifest()
    placeholder_paths = {b["path"] for b in manifest["books"] if b["placeholder"]}
    assert placeholder_paths
    hits = corpus.retrieve("market", limit=20)
    for hit in hits:
        assert hit["path"] not in placeholder_paths


def test_retrieve_empty_query_returns_nothing():
    assert corpus.retrieve("") == []
    assert corpus.retrieve("   ") == []


def test_find_book_by_fragment():
    book = corpus.find_book("Trading In The Zone")
    assert book is not None
    assert "Trading In The Zone" in book["title"]
    assert corpus.find_book("zzz-not-a-book") is None


def test_corpus_stats_shape():
    stats = corpus.corpus_stats()
    assert stats["n_real"] == stats["n_books"] - stats["n_placeholders"]
    assert stats["total_words"] > 1_000_000
    assert stats["schema"] == "corpus_manifest.v1"