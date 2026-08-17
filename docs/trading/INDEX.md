# Trading library for Cursor

Local LLM chat/training was removed. Use **full books** with Cursor.

## Full books (usable)
- Catalog: `@docs/trading/BOOKS_FULL.md` (**50 books**, ~5.15M words)
- Folder: `@docs/trading/books/`
- Rebuild catalog (does **not** delete extracts): `python scripts/rebuild_books_catalog.py`
- Extract a Downloads PDF: `python scripts/extract_pdf_to_books.py`

## Digests
- Aegis MT5 FX/session/MM batch: `@docs/trading/NEW_BOOKS_AEGIS_MT5_FOREX_BATCH.md`
- Aziz + Steidlmayer: `@docs/trading/NEW_BOOKS_AZIZ_STEIDLMAYER.md`
- Fuller + Fabris + Brown + Silvani: `@docs/trading/NEW_BOOKS_FULLER_FABRIS_BROWN_SILVANI.md`
- Ponsi + Damir 2012 + DraKoln + Thomas + Afshari + Windsor: `@docs/trading/NEW_BOOKS_PONSI_DAMIR_DRAKOLN_THOMAS_AFSHARI_WINDSOR.md`
- Coulling VPA + Brooks Ranges + Damir 2016: `@docs/trading/NEW_BOOKS_VPA_BROOKS_DAMIR.md`
- Harris microstructure + Jansen ML factors: `@docs/trading/NEW_BOOKS_HARRIS_JANSEN.md`
- Donadio / Ghosh / Rossier HFT systems: `@docs/trading/NEW_BOOKS_DONADIO_HFT.md`

## CORE freeze
- Protected live firehose: `@docs/CORE_STRATEGY_V1.md`
- Cartea + Aldridge + Oreste + Narang + Van Der Post: `@docs/trading/NEW_BOOKS_HFT_CARTEA_ALDRIDGE_ORESTE_NARANG_VANDERPOST.md`
- Davey + Aronson + Chan + Carver + Elder + Tharp + Clenow + Grimes + Schwager + Murphy + Nison + du Plessis: `@docs/trading/NEW_BOOKS_CORE_TWELVE.md`
- Kaufman / Volman / Johnson notes: `@docs/trading/NEW_BOOKS_KAUFMAN_VOLMAN_JOHNSON_CHAN.md`
- Frost/Prechter / Gann / Johnson / Chan 2013 / Prado / Zuckerman: `@docs/trading/NEW_BOOKS_SIX_BATCH.md`

## Newly extracted (full text now in `books/`)
- Anna Coulling — *A Complete Guide To Volume Price Analysis* (2013) — `@docs/trading/books/a-complete-guide-to-volume-price-analysis-coulling.md`
- Anna Coulling — *Stock Trading & Investing Using Volume Price Analysis* — `@docs/trading/books/stock-trading-investing-using-volume-price-analysis-coulling.md`
- Al Brooks — *Trading Price Action Ranges* (2012) — `@docs/trading/books/trading-price-action-ranges-brooks.md`
- Laurentiu Damir — *Price Action Breakdown* (2016) — `@docs/trading/books/price-action-breakdown-damir-2016.md`
- Stefan Jansen — *Hands-On Machine Learning for Algorithmic Trading* (2018) — `@docs/trading/books/hands-on-machine-learning-for-algorithmic-trading-jansen.md`
- Donadio / Ghosh / Rossier — *Developing High-Frequency Trading Systems* — `@docs/trading/books/developing-high-frequency-trading-systems.md`
- Brian Anderson — *The 1 Hour Trade* (2014) — `@docs/trading/books/the-1-hour-trade-anderson.md` (US $1–$10 stock ORB, not FX HFT)
- Frost & Prechter — *Elliott Wave Principle* (2005, OCR) — `@docs/trading/books/elliott-wave-principle-frost-prechter-2005.md`
- Ernie Chan — *Algorithmic Trading* (2013) — `@docs/trading/books/algorithmic-trading-winning-strategies-chan-2013.md`
- Marcos López de Prado — *Advances in Financial Machine Learning* (2018) — `@docs/trading/books/advances-in-financial-machine-learning-prado-2018.md`
- Gregory Zuckerman — *The Man Who Solved the Market* (2019) — `@docs/trading/books/the-man-who-solved-the-market-zuckerman-2019.md`

Attach one book (or a few) per chat, then ask for concrete bot code.

## Not on this machine (no usable text extract yet)
- Perry Kaufman — *Trading Systems and Methods* (any edition)
- Bob Volman — *Forex Price Action Scalping* (digest only)
- Frost & Prechter / Gann / Johnson DMA — Gann and Johnson scans still OCR'ing via `scripts/ocr_pdf_to_books.py`

## Source pipeline
- Do **not** run `scripts/rebuild_full_books_for_cursor.py` — it deletes extracts that are not in `cleaned/*.jsonl`.
- Catalog rebuild: `python scripts/rebuild_books_catalog.py`
