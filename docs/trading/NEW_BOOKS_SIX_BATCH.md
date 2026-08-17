# Six-book batch — Frost/Prechter, Gann, Johnson, Chan 2013, Prado, Zuckerman

Educational digest. **No invented win rates.** All six extracts are on disk (Chan/Prado/Zuckerman text PDFs; Frost/Gann/Johnson OCR).

## Source status (this machine)

| Book | PDF on disk | Full extract | Label |
|------|-------------|--------------|-------|
| **Frost & Prechter** — Elliott Wave (2005) | Yes (scanned) | `@docs/trading/books/elliott-wave-principle-frost-prechter-2005.md` (OCR, ~61k words) | extract |
| **W. D. Gann** — Commodities (1976) | Yes (scanned) | `@docs/trading/books/how-to-make-profits-in-commodities-gann-1976.md` (OCR, ~109k words) | extract |
| **Barry Johnson** — DMA (2010) | Yes (scanned) | `@docs/trading/books/algorithmic-trading-and-dma-johnson-2010.md` (OCR, ~237k words) | extract |
| **Ernie Chan** — Algo Trading (2013) | Yes | `@docs/trading/books/algorithmic-trading-winning-strategies-chan-2013.md` (74,529 words) | extract |
| **López de Prado** — AFML (2018) | Yes | `@docs/trading/books/advances-in-financial-machine-learning-prado-2018.md` (126,471 words) | extract |
| **Gregory Zuckerman** — Medallion (2019) | Yes | `@docs/trading/books/the-man-who-solved-the-market-zuckerman-2019.md` (109,403 words) | extract |

## Six-book stack (best WR attempt without faking)

`scripts/research_train.py --stack --days 45 --symbols 26 --purged --round s1`

1. **Primary:** `six_book_stack` — needs ≥3 independent votes (structure, Chan, Elliott, Gann, Prado fdiff, Johnson spread, HTF).
2. **Meta-label (Prado):** ridge filter trained on win/loss, purged holdout.
3. **Gates:** still require sampled losses, bootstrap tail, positive expectancy — **not WR alone**.

## Aegis mapping (shadow only; live YAML frozen)

| Idea | Module |
|------|--------|
| Elliott legs | `aegis.research.elliott` |
| Gann cycles/angle | `aegis.research.gann` |
| Johnson spread gate | `aegis.research.johnson` |
| Chan MR + momentum | `entry_signals.chan_bb_fade`, `chan_momentum` |
| Prado FD + meta-label | `aegis.research.prado`, `train.search_meta_label_filters` |
| Zuckerman ensemble | `aegis.research.six_book.stack_votes`, `six_book_stack` entry |

## 100% win rate

**Not promised.** High WR with negative E already measured on 1/30 firehose. The stack trades **fewer** times on purpose to raise WR; gates reject thin edges.
