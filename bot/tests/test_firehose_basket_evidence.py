import json

import pytest

from aegis.research.books_index import BookIndex
from aegis.research.firehose_basket_evidence import build_evidence_packet


def _index_books(tmp_path, books):
    books_dir = tmp_path / "books"
    books_dir.mkdir()
    for filename, body in books.items():
        (books_dir / filename).write_text(body, encoding="utf-8")
    index = BookIndex(tmp_path / "books.sqlite")
    index.rebuild(books_dir)
    return index


def test_packet_preserves_each_supporting_source_hash_location_and_passage(tmp_path):
    index = _index_books(
        tmp_path,
        {
            "alpha.md": "# Alpha\nUse a volume spike to confirm a breakout.\n",
            "beta.md": "# Beta\nA volume spike confirms breakout participation.\n",
        },
    )

    packet = build_evidence_packet(
        index,
        {"hypothesis_id": "basket:volume", "origin": "BOOK_DIRECT"},
        "volume spike",
        "",
        {"symbol": "EURUSD", "observed": "volume expansion"},
        "Reject if costed holdout expectancy is non-positive.",
    )

    assert packet["BOOK_COVERAGE"] == "SUFFICIENT"
    assert {item["filename"] for item in packet["supporting_evidence"]} == {"alpha.md", "beta.md"}
    for item in packet["supporting_evidence"]:
        assert len(item["file_hash"]) == 64
        assert item["source_id"] == item["file_hash"]
        assert item["evidence_label"] == "SUPPORT"
        assert item["location"]["path"].endswith(item["filename"])
        assert item["location"]["line_start"] == 2
        assert "volume spike" in item["passage"].lower()
    json.dumps(packet)


def test_packet_stores_contradictory_source_provenance(tmp_path):
    index = _index_books(
        tmp_path,
        {
            "support.md": "# Support\nUse a volume spike to confirm a breakout.\n",
            "contradiction.md": "# Contradiction\nAvoid a failed breakout after a volume spike.\n",
        },
    )

    packet = build_evidence_packet(
        index,
        {"hypothesis_id": "basket:volume", "origin": "BOOK_DIRECT"},
        "volume spike",
        "failed breakout",
        {"symbol": "EURUSD"},
        "Reject on a failed breakout.",
    )

    assert [item["filename"] for item in packet["contradicting_evidence"]] == ["contradiction.md"]
    contradiction = packet["contradicting_evidence"][0]
    assert len(contradiction["file_hash"]) == 64
    assert contradiction["source_id"] == contradiction["file_hash"]
    assert contradiction["evidence_label"] == "CONTRADICTION"
    assert contradiction["location"]["line_start"] == 2
    assert contradiction["passage"] == "Avoid a failed breakout after a volume spike."


def test_novel_hypothesis_without_matches_is_explicitly_insufficient_and_has_no_sources(tmp_path):
    index = _index_books(tmp_path, {"unrelated.md": "# Unrelated\nMean reversion only.\n"})

    packet = build_evidence_packet(
        index,
        {"hypothesis_id": "basket:new", "origin": "NOVEL_SYNTHESIZED_HYPOTHESIS"},
        "unseen liquidity pattern",
        "unseen contradiction",
        {"symbol": "EURUSD"},
        "Reject without sealed out-of-sample evidence.",
    )

    assert packet["BOOK_COVERAGE"] == "INSUFFICIENT"
    assert packet["supporting_evidence"] == []
    assert packet["contradicting_evidence"] == []
    assert packet["origin"] == "NOVEL_SYNTHESIZED_HYPOTHESIS"
    json.dumps(packet)


def test_direct_source_hypothesis_rejects_empty_book_coverage(tmp_path):
    index = _index_books(tmp_path, {"unrelated.md": "# Unrelated\nMean reversion only.\n"})

    with pytest.raises(ValueError, match="direct-source hypothesis requires supporting book evidence"):
        build_evidence_packet(
            index,
            {"hypothesis_id": "basket:unsupported", "origin": "BOOK_DIRECT"},
            "unseen liquidity pattern",
            "",
            {"symbol": "EURUSD"},
            "Reject without evidence.",
        )


def test_only_explicit_book_or_novel_origins_are_accepted(tmp_path):
    index = _index_books(tmp_path, {"source.md": "# Source\nA volume spike confirms a breakout.\n"})

    with pytest.raises(ValueError, match="origin"):
        build_evidence_packet(
            index,
            {"hypothesis_id": "basket:guess", "origin": "ANALYST_GUESS"},
            "volume spike",
            "",
            {"symbol": "EURUSD"},
            "Reject without evidence.",
        )


def test_packet_keeps_more_than_eight_complete_phrase_sources(tmp_path):
    index = _index_books(
        tmp_path,
        {
            f"source-{number}.md": f"# Source {number}\nA volume spike confirms breakout {number}.\n"
            for number in range(9)
        },
    )

    packet = build_evidence_packet(
        index,
        {"hypothesis_id": "basket:all-sources", "origin": "BOOK_DIRECT"},
        "volume spike",
        "",
        {"symbol": "EURUSD"},
        "Reject without costed evidence.",
    )

    assert len(packet["supporting_evidence"]) == 9
    assert packet["contextual_candidates"] == []


def test_fallback_term_matches_are_contextual_and_do_not_supply_coverage(tmp_path):
    index = _index_books(
        tmp_path,
        {
            "support-context.md": "# Support context\nA volume imbalance appeared.\n",
            "contradiction-context.md": "# Contradiction context\nA failed auction followed.\n",
        },
    )

    packet = build_evidence_packet(
        index,
        {"hypothesis_id": "basket:novel", "origin": "NOVEL_SYNTHESIZED_HYPOTHESIS"},
        "volume spike",
        "failed breakout",
        {"symbol": "EURUSD"},
        "Reject without sealed evidence.",
    )

    assert packet["BOOK_COVERAGE"] == "INSUFFICIENT"
    assert packet["supporting_evidence"] == []
    assert packet["contradicting_evidence"] == []
    assert {item["filename"] for item in packet["contextual_candidates"]} == {
        "support-context.md",
        "contradiction-context.md",
    }
    assert {item["evidence_label"] for item in packet["contextual_candidates"]} == {
        "CONTEXTUAL_CANDIDATE"
    }
