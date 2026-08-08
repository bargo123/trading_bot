# Trading library for Cursor

Local LLM chat/training was removed. Use **full books** with Cursor.

## Full books
- Catalog: `@docs/trading/BOOKS_FULL.md`
- Folder: `@docs/trading/books/`
- Digest (Aziz + Steidlmayer): `@docs/trading/NEW_BOOKS_AZIZ_STEIDLMAYER.md`
- Digest (Fuller + Fabris + Brown + Silvani): `@docs/trading/NEW_BOOKS_FULLER_FABRIS_BROWN_SILVANI.md`
- Digest (Ponsi + Damir + DraKoln + Thomas + Afshari + Windsor): `@docs/trading/NEW_BOOKS_PONSI_DAMIR_DRAKOLN_THOMAS_AFSHARI_WINDSOR.md`

Attach one book (or a few) per chat, then ask for concrete bot code.

## Source pipeline
- Originals: `books/`
- Cleaned JSONL: `cleaned/`
- Rebuild markdown: `python scripts/rebuild_full_books_for_cursor.py`
