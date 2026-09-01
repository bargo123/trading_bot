# Task 1 Report: Full-Corpus Evidence Packets

## Scope

Added the research-only `build_evidence_packet` interface in
`bot/aegis/research/firehose_basket_evidence.py` and its focused tests.

Packets retrieve sources through `search_full_book_knowledge` and look up the
corresponding `BookIndex` rows before retaining a source. Each supporting and
contradicting record includes its index file hash/source ID, indexed path and
line location, evidence label, and an unmodified source line. The packet is
validated as JSON-serializable. Missing support is explicit as
`BOOK_COVERAGE: INSUFFICIENT`; a direct-source hypothesis with no support is
rejected, while a novel hypothesis must declare
`NOVEL_SYNTHESIZED_HYPOTHESIS`.

## TDD Evidence

- RED: `..\.venv\Scripts\python.exe -m pytest tests\test_firehose_basket_evidence.py -q`
  failed at collection with the expected missing-module import error.
- GREEN focused: the same command completed with `5 passed in 0.53s`.
- Full: `..\.venv\Scripts\python.exe -m pytest -q` completed with
  `1033 passed, 1 warning in 79.66s`.

## Safety

No runtime, Research Factory, AI Council, configuration, MT5, or order code
was modified. No source is synthesized: packet evidence is emitted only for
records returned by the indexed corpus search and found in the `BookIndex`.

## Retrieval Correction

The initial retrieval loop inherited `search_full_book_knowledge`'s default
limit of eight sources and labeled fallback term matches as direct evidence.
The correction derives the retrieval limit from the full indexed corpus and
queries the documented fallback terms through the same API. A complete query
phrase is now required for `SUPPORT` or `CONTRADICTION`; partial-term matches
are retained in `contextual_candidates` with the
`CONTEXTUAL_CANDIDATE` label and cannot make coverage sufficient.

- RED: the focused suite failed with `8 != 9` for nine complete-phrase
  sources and incorrectly reported `SUFFICIENT` coverage for fallback-only
  results.
- GREEN focused: `..\.venv\Scripts\python.exe -m pytest tests\test_firehose_basket_evidence.py -q`
  completed with `7 passed in 0.68s`.
- Full: `..\.venv\Scripts\python.exe -m pytest -q` completed with
  `1035 passed, 1 warning in 89.72s`.
