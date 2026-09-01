# Trading book corpus inventory

- Directory: `docs/trading/books`
- Files: **54**
- Extensions: {'.md': 54}
- Total size: 30.7 MiB
- Total words: **5,162,239**
- Median words/file: 81,111
- Duplicate content groups: 0
- Placeholder/stub files (<200 words): 2
- OCR-degradation suspects: 0

## Largest sources

| words | file |
| --- | --- |
| 319,360 | `docs/trading/books/trading-and-exchanges-market-microstructure-for-practitioners---full---2002-oxfo.md` |
| 317,196 | `docs/trading/books/encyclopedia-of-chart-patterns-2005-john-wiley-sons-inc---libgen-li.md` |
| 251,683 | `docs/trading/books/technical-analysis-of-stock-trends-eleventh-edition-2018-crc-press---libgen-li.md` |
| 250,178 | `docs/trading/books/trading-price-action-ranges-brooks.md` |
| 216,729 | `docs/trading/books/algorithmic-trading-and-dma-johnson-2010.md` |
| 183,675 | `docs/trading/books/evidence-based-technical-analysis-applying-the-scientific-method-and-statistical.md` |
| 181,074 | `docs/trading/books/the-art-and-science-of-technical-analysis-market-structure-price-action-and-trad.md` |
| 163,401 | `docs/trading/books/the-new-market-wizards-conversations-with-america-s-top-traders.md` |
| 144,718 | `docs/trading/books/reminiscences-of-a-stock-operator-2012-john-wiley-sons---libgen-li.md` |
| 141,492 | `docs/trading/books/the-definitive-guide-to-point-and-figure-2005---libgen-li.md` |

## Placeholder / stub files

- `docs/trading/books/market-structure.md`
- `docs/trading/books/sample-author.md`

## How this corpus is used

Books are never loaded wholesale into an LLM context. They are indexed into
`bot/intel/knowledge_table.json` as structured, per-concept rows, and the
runtime matches rows by regime/structure via
`aegis.intel.knowledge_runtime.match_knowledge`. The original files remain the
evidence source for any claim.
