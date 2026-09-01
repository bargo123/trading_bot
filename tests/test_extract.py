from __future__ import annotations

from pathlib import Path

from trading_llm.extract import extract_file, guess_title_author


def test_guess_title_author():
    title, author = guess_title_author(Path("Alice - Risk Book.md"))
    assert "Risk" in title
    assert author == "Alice"


def test_extract_markdown(tmp_path: Path):
    p = tmp_path / "Author - Demo.md"
    p.write_text("# Chapter 1\n\nHello risk management and position sizing content here.\n")
    sections = extract_file(p)
    assert sections
    assert sections[0].book_title
