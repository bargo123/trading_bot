"""Book-knowledge pipeline tests (spec A: EF-100..106, L: EF-117)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aegis.research.book_knowledge import (  # noqa: E402
    STATUS_INDEXED,
    STATUS_PARTIAL,
    STATUS_PLACEHOLDER,
    STATUS_UNSUPPORTED,
    build_knowledge_base,
    process_book,
)
from aegis.intel import knowledge_retrieval  # noqa: E402


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_every_source_gets_explicit_status(tmp_path):
    """No silent skips: placeholder/unsupported/partial all reported."""
    books = tmp_path / "books"
    _write(books / "real_book.md",
           "# Chapter One\n\n" + ("Trailing stops protect open profit while "
                                  "letting winners run toward the target. " * 40))
    _write(books / "tiny.md", "# note\n\nalmost empty")
    (books / "binary.pdf").write_bytes(b"%PDF-1.4 not a book")
    result = build_knowledge_base(books, tmp_path / "knowledge")
    statuses = {f["file"]: f["status"] for f in result_files(tmp_path / "knowledge")}
    assert statuses[str(Path("books") / "real_book.md")] == STATUS_INDEXED
    assert statuses[str(Path("books") / "tiny.md")] == STATUS_PLACEHOLDER
    assert statuses[str(Path("books") / "binary.pdf")] == STATUS_UNSUPPORTED


def result_files(knowledge_dir: Path):
    idx = json.loads((knowledge_dir / "source_index.json").read_text(encoding="utf-8"))
    return idx["files"]


def test_restart_safety_same_hash_skips_reprocessing(tmp_path):
    books = tmp_path / "books"
    _write(books / "book.md", "# Ch\n\n" + ("Breakout entry with stop below level. " * 30))
    first = build_knowledge_base(books, tmp_path / "knowledge")
    # Second run without changes: manifest reuse keeps records identical.
    second = build_knowledge_base(books, tmp_path / "knowledge")
    assert first["corpus_version"] == second["corpus_version"]
    assert second["records"] == first["records"]


def test_structured_records_preserve_provenance(tmp_path):
    books = tmp_path / "books"
    body = (
        "# Chapter 3 - Exits\n\n"
        "A trailing stop lets winners run while protecting open profit. "
        "Move the stop behind each new swing high and never loosen it. "
        "If momentum decays after a failed breakout, exit at the structural "
        "level rather than waiting for the original stop.\n"
    )
    _write(books / "Brooks Exits 2012.md", body)
    build_knowledge_base(books, tmp_path / "knowledge")
    exits = [
        json.loads(line)
        for line in (tmp_path / "knowledge" / "exit_patterns.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    assert exits, "exit knowledge must be extracted"
    rec = exits[0]
    for field in ("book", "author", "file_hash", "chapter", "location",
                  "passage_hash", "passage_excerpt", "concept_type"):
        assert rec.get(field) not in (None, ""), field
    assert rec["author"] == "Brooks"
    assert any("trailing" in c for c in rec.get("exit_categories", []))


def test_conflicting_authors_stay_distinct_hypotheses(tmp_path):
    """Continuation vs failed-breakout-fade are TWO hypotheses; never merged."""
    books = tmp_path / "books"
    cont = ("A strong breakout continuation setup: buy the breakout and hold "
            "while momentum builds. Stop below the breakout level. ")
    fade = ("A failed breakout is a fade opportunity: sell the false breakout "
            "trap back into the range. Stop above the trap high. ")
    _write(books / "Author Continuation.md",
           "# Trend\n\n" + cont * 25)
    _write(books / "Author Fade.md",
           "# Traps\n\n" + fade * 25)
    build_knowledge_base(books, tmp_path / "knowledge")
    hyps = [
        json.loads(line)
        for line in (tmp_path / "knowledge" / "strategy_hypotheses.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    polarities = {h.get("polarity") for h in hyps if h.get("polarity")}
    assert {"continuation", "fade"} <= polarities or len(hyps) >= 2
    # Records are never merged into one majority-vote record.
    assert len({h["passage_hash"] for h in hyps}) == len(hyps)


def test_retrieval_matches_state_and_invalidates_on_corpus_change(tmp_path, monkeypatch):
    books = tmp_path / "books"
    body = ("Use a time stop when a trade stalls: exit if the move does not "
            "progress within your holding period. ")
    _write(books / "Exit Book.md", "# Exits\n\n" + body * 30)
    knowledge_dir = tmp_path / "knowledge"
    v1 = build_knowledge_base(books, knowledge_dir)["corpus_version"]

    monkeypatch.setattr(knowledge_retrieval, "KNOWLEDGE_DIR", knowledge_dir)
    knowledge_retrieval._cached_retrieve.cache_clear()
    state = {"regime": "range", "session": "asia", "structure": "retest",
             "volatility": "stable", "family": "time_stop"}
    hits = knowledge_retrieval.retrieve_for_state(state, limit=4)
    assert hits, "state-relevant exit knowledge must be retrievable"
    assert any(h.get("concept_type") == "EXIT_PRINCIPLE" for h in hits)

    plan = knowledge_retrieval.exit_plan_for_state(state)
    assert plan is not None and plan.get("plan_type")

    # Corpus change -> version bump -> cache invalidated.
    body2 = ("Completely rewritten exit guidance about scaling out of open "
             "positions at structure targets with reduced size. ")
    _write(books / "Exit Book.md", "# Exits v2\n\n" + body2 * 30)
    v2 = build_knowledge_base(books, knowledge_dir)["corpus_version"]
    assert v1 != v2
    knowledge_retrieval._cached_retrieve.cache_clear()
    hits2 = knowledge_retrieval.retrieve_for_state(state, limit=4)
    assert all(h.get("passage_hash") for h in hits2)


def test_exit_categories_cover_spec_L_topics():
    from aegis.research.book_knowledge import EXIT_CATEGORIES

    required = {
        "taking_profits", "letting_winners_run", "trailing_stops",
        "structural_exits", "time_stops", "failed_breakouts", "momentum_decay",
        "mfe_mae", "risk_reward", "volatility_exits", "scaling_out",
        "trend_termination", "mean_reversion_completion",
    }
    assert required <= set(EXIT_CATEGORIES.keys())
