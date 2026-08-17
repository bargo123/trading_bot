# Phase 1 freeze — 2026-08-17

Read-only inventory taken before intelligent-firehose implementation.
No reset, no merge, no live YAML change, no runner restart.

## HEADs

| Tree | SHA | Branch |
|---|---|---|
| main worktree `C:\Users\Raqam\trading_bot` | `96b54c6c709ce8d18ed4fee11ca350b8cca9cc5b` | `main` (dirty) |
| Codex worktree `C:\Users\Raqam\Documents\Codex\2026-08-14\ma\work\aegis-firehose` | `965ddab0e28e13061409ba049f7af4d61081cd7e` | `codex/aegis-firehose-autonomous-research` (dirty) |

Local backup branch already present from earlier work: `backup/aegis-phase1-6555c10`.

## Dirty main (tracked)

- `bot/aegis/exits.py`
- `bot/aegis/intel/decide.py`
- `bot/aegis/paper_control.py`
- `bot/aegis/research/books_index.py`
- `bot/aegis/research/reports.py`
- `bot/aegis/research/source_notes.py`
- `bot/config_mt5_demo_firehose_hw.yaml` — **do not rewrite in this implementation; live firehose stays running**
- `bot/reports/firehose_mfe.json`
- `bot/reports/research/current_best.md`
- `bot/reports/research/entry_families.md`
- `bot/reports/research/live_vs_model.md`
- `bot/reports/research/ml_filter.md`
- `bot/reports/research/safety_dashboard.md`
- `bot/scripts/run_broker_paper.py`
- `bot/tests/test_exits.py`
- `bot/tests/test_intel.py`
- `bot/tests/test_paper_control.py`
- `bot/tests/test_research_books_index.py`
- `docs/trading/INDEX.md`
- `docs/trading/NEW_BOOKS_KAUFMAN_VOLMAN_JOHNSON_CHAN.md`
- `docs/trading/NEW_BOOKS_SIX_BATCH.md`
- `scripts/ocr_pdf_to_books.py`

## Untracked main (research/intelligence already in progress)

- `bot/aegis/intel/mega_book.py`
- `bot/aegis/research/{book_audit,intelligence,intelligence_cycle,knowledge,learning,market_state,market_state_history,portfolio,strategy_audit,thesis,thousand_day_gap}.py`
- `bot/reports/research/{book_coverage,intelligence_cycle,strategy_assumption_audit,thousand_day_gap}.md`
- `bot/scripts/research_{book_audit,intelligence_audit,intelligence_cycle}.py`
- `bot/tests/test_research_intelligence.py`

## Dirty Codex (not blindly merged)

- `.gitignore`
- `bot/aegis/features.py`
- `bot/aegis/optimizer/cycle.py`
- `bot/aegis/optimizer/promote.py`
- `bot/optimizer/AGENT_PROMPT.md`
- `bot/optimizer/config.yaml`
- `bot/research/.gitkeep`

Codex still owns `bot/aegis/portfolio_risk.py` and `bot/aegis/reconcile.py` on that worktree. Port later; do not merge the branch.

## Hard constraints kept

- CORE `sig_firehose` not rewritten
- `run_broker_paper.py` must not import `aegis.research`
- `allow_live` untouched
- Intelligent firehose remains `placed_orders=false` until a later explicit authorization
