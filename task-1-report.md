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
