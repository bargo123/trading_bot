"""Compile hashed book extracts into strategy-hypothesis rows."""
from __future__ import annotations

from pathlib import Path

from aegis.research.books_index import BookIndex
from aegis.research.knowledge import compile_from_index, select_knowledge_for_state


def test_compile_from_index_skips_placeholders_and_extracts_sections(tmp_path: Path):
    books = tmp_path / "books"
    books.mkdir()
    (books / "retest.md").write_text(
        "\n".join(
            [
                "# Retest Playbook",
                "",
                "## Setup",
                "Wait for a completed breakout then a retest of the broken level.",
                "",
                "## Entry",
                "Enter after the retest bar closes back in the direction of the break.",
                "",
                "## Exit",
                "Invalidate on a completed close back through the retest low.",
                "",
                "## Risk",
                "Risk is defined by the invalidation, not a fixed pip count.",
            ]
        ),
        encoding="utf-8",
    )
    (books / "sample-author.md").write_text("# Sample\nplaceholder\n", encoding="utf-8")
    (books / "a.md").write_text("# Dup\nsame-body-xyz\n", encoding="utf-8")
    (books / "b.md").write_text("# Dup\nsame-body-xyz\n", encoding="utf-8")
    index = BookIndex(tmp_path / "idx.sqlite")
    index.rebuild(books)
    rows = compile_from_index(index)
    names = {row["filename"] for row in rows}
    assert "retest.md" in names
    assert "sample-author.md" not in names
    assert len([row for row in rows if row["filename"] in {"a.md", "b.md"}]) == 1
    retest = next(row for row in rows if row["filename"] == "retest.md")
    assert "retest" in retest["concepts"]
    assert retest["setup"]
    assert retest["invalidation"]
    assert retest["file_hash"]
    assert "damir_retest" in retest["strategy_modules"]
    matched = select_knowledge_for_state(rows, regime="range", structure_kind="retest")
    assert matched
    assert matched[0]["filename"] == "retest.md"
