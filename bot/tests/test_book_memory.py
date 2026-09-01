"""Tests for the persistent book-memory knowledge system (research-only)."""
from __future__ import annotations

import json
import sqlite3

from aegis.research.book_memory import (
    build_records_from_notes,
    build_sqlite_db,
    retrieve_knowledge,
    sentence_is_trading_relevant,
    extract_quality_sections,
)


def _note(tmp_path, name: str, body_claims: list[str]) -> None:
    path = tmp_path / f"{name}.json"
    path.write_text(
        json.dumps(
            {
                "title": f"{name} (2018)",
                "file_hash": f"hash-{name}",
                "claims": {"headings": [], "body": body_claims},
                "data_required": [],
                "warnings": [],
            }
        ),
        encoding="utf-8",
    )


def test_bogus_and_code_sentences_are_rejected():
    assert not sentence_is_trading_relevant("All the information was entered at the exchanges by hand")
    assert not sentence_is_trading_relevant(
        "import pandas as pd; entry=pd.DataFrame(columns=['dT','w'])"
    )
    assert sentence_is_trading_relevant(
        "Go long when the market closes above the breakout level with volume confirmation."
    )


def test_long_run_is_not_an_entry_signal():
    sections = extract_quality_sections(
        "It is frequently noted that over 90 percent of FX traders do not survive "
        "in the long run, yet you will not find that statistic in the marketing."
    )
    assert sections.get("entry") == ""


def test_build_records_from_notes_writes_validated_records(tmp_path):
    _note(
        tmp_path,
        "range-book",
        [
            "When the market is in a range and price fails at the upper edge, sell "
            "with a stop above the swing high and a target at the lower edge.",
            "The thesis is wrong if price closes above the breakout level.",
        ],
    )
    _note(
        tmp_path,
        "admin-book",
        [
            "All the information was entered at the exchanges by hand by clerks.",
        ],
    )
    records = build_records_from_notes(tmp_path, records_path=tmp_path / "records.jsonl")
    assert any(
        r.entry and "sell" in r.entry.lower() and "stop" in r.stop_logic for r in records
    )
    admin = [r for r in records if "hash-admin" in r.source_hash]
    assert not any(r.entry for r in admin)
    assert not any(r.setup for r in admin)


def test_sqlite_db_and_retrieval(tmp_path):
    _note(
        tmp_path,
        "trend-book",
        [
            "In a strong trend, buy the pullback with a stop below the recent swing "
            "low and a target at the prior high.",
        ],
    )
    _note(
        tmp_path,
        "range-book",
        [
            "When the market is in a range and price fails at the upper edge, sell "
            "with a stop above the swing high.",
        ],
    )
    build_records_from_notes(tmp_path, records_path=tmp_path / "records.jsonl")
    n = build_sqlite_db(tmp_path / "records.jsonl", tmp_path / "book_memory.sqlite")
    assert n >= 2
    with sqlite3.connect(str(tmp_path / "book_memory.sqlite")) as con:
        concepts = con.execute("SELECT DISTINCT concept FROM knowledge").fetchall()
        assert len(concepts) >= 1
    hits = retrieve_knowledge(concept="range_edge_fade", records_path=tmp_path / "records.jsonl")
    assert any("range" in str(r.get("concept") or "") for r in hits)