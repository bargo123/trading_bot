# Trading book library for Cursor

This project stores your legally owned trading books and converts them into text Cursor can use while building bots.

Local LLM training / TradeForge chat has been **removed**. Use **Cursor** + `@docs/trading/books/...`.

## Layout

- `books/` — original PDF/EPUB/MD files
- `extracted/` — raw extraction
- `cleaned/` — cleaned sections (JSONL)
- `docs/trading/books/` — **full book markdown for Cursor**
- `docs/trading/BOOKS_FULL.md` — catalog

## Rebuild book text for Cursor

```bash
cd ~/trading-llm
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python scripts/extract_books.py
python scripts/clean_books.py
python scripts/rebuild_full_books_for_cursor.py
```

## Bot (Aegis)
Library-synthesized systematic bot:

```bash
cd ~/trading-llm/bot
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python scripts/run_backtest.py
```

See `bot/README.md` and `bot/DESIGN.md`.
