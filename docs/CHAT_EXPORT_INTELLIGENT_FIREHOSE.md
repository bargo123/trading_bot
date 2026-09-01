# Intelligent Firehose — chat context export

Exported: 2026-08-18 (Windows session). Open in Cursor after cloning for full implementation context.

Transcript ID: `4639743f-90bb-4f66-af0a-46224dbd3707`

---

## Mission

Transform Aegis MT5 **demo** firehose from:

- CORE EMA-side spray → heuristic intel → 1-pip TP / 30-pip SL → ~92% WR but negative expectancy

Into **Intelligent Firehose**:

- MARKET STATE → THESIS → BOOK EVIDENCE → POINT-IN-TIME ANALOGUES → CALIBRATED EV → PORTFOLIO EXPOSURE → FIRE / SCALE / HOLD / REDUCE / EXIT → OUTCOME LEARNING

Keep continuous multi-symbol scanning. Do **not** make the bot afraid to trade. Optimize expectancy and payoff, not win rate alone.

Hard safety: `allow_live: false` always. Exactly one `run_broker_paper.py`. Shadow observer never places orders.

---

## Central failure to fix

Observed baseline (~$100 demo account):

| Metric | Value |
|--------|-------|
| Trades | 1,175 |
| Win rate | 91.91% |
| Gross profit | +$26.33 |
| Gross loss | -$37.09 |
| Net | -$10.71 |
| Profit factor | ~0.71 |

A 91.91% WR model with negative EV must **never** be promoted. Regression test: `test_9191_wr_negative_ev_model_never_promotes`.

---

## What was implemented

### Phase 0 — Safety snapshot

- Recorded HEAD, git status, config, runner PID, rollback doc at `bot/reports/research/intelligent_firehose_rollback.md`.

### Phase 1 — Analogue evidence

- Point-in-time analogue index and query (`aegis/research/analogues.py`, `aegis/intel/analogue_store.py`).
- Shadow observer wired with `analogue_records` and `total_risk_budget_usd`.
- Synthetic index for CI/offline (`research_build_analogues.py --synthetic`).

### Phase 2 — Book knowledge

- Full prose extraction from `docs/trading/books/` via `extract_prose_snippets` in `aegis/research/knowledge.py`.
- Competing hypotheses stored independently (`expand_strategy_hypotheses`).
- Runtime loader: `aegis/intel/knowledge_runtime.py`.

### Phase 3–4 — Strategy models + demo brain

- `IntelligentFirehoseBrain` in `aegis/intel/firehose_brain.py`.
- Demo runner (`run_broker_paper.py`) uses brain for FIRE/SCALE/HOLD/REDUCE/EXIT when `intelligent_firehose: true`.
- Old CORE signal path preserved for baseline comparison.

### Phase 5–9 — Exposure, sizing, portfolio

- Thesis clips tracked in `ThesisMemory`; sync from live MT5 positions.
- `lifecycle.py` wraps portfolio_risk + reconcile without research imports.
- Currency-direction exposure enforced via `pretrade_ok`.

### Phase 10 — Outcome learning

- `outcome_log.py` append-only closed-trade log.
- Deal ingestion in demo runner loop.

### Phase 11 — Reporting

- `scoreboard.py` old vs intelligent metrics.
- Dashboard section for Intelligent Firehose in `bot/dashboard/index.html`.
- Reports: `old_vs_intelligent.md`, `knowledge_table.md`.

### MT5 fixes (post-integration)

1. **Invalid comment (-2):** `sanitize_mt5_comment` in `aegis/engines/mt5.py` — alphanumeric, max 16 chars, `aegis` prefix.
2. **Invalid stops (10016):** `normalize_protective_stops` in `run_broker_paper.py` — respects `trade_stops_level` / `trade_freeze_level`.

---

## Key config (`bot/config_mt5_demo_firehose_hw.yaml`)

```yaml
intelligent_firehose: true
intelligent_firehose_bootstrap: true
intel_enabled: false          # old heuristic intel off
flatten_if_profit_usd: 0      # no 1-cent flatten for intelligent trades
intelligent_risk_budget_usd: ...
intelligent_risk_fraction: ...
intelligent_min_analogues: ...
intelligent_max_clips_per_thesis: ...
knowledge_table_path: ...
intelligent_champion_path: ...
max_currency_direction_positions: 10
allow_live: false             # NEVER change on demo work
```

---

## Architecture rules

- Runtime (`aegis/intel/*`) must **not** import research (`aegis/research/*`).
- CORE `sig_firehose` EMA-side logic is **frozen** — intelligence wraps it, does not replace it on live YAML until challenger wins.
- Research cycle: one falsifiable hypothesis per cycle; no invented metrics; no look-ahead in analogues.

---

## Key files

| Path | Role |
|------|------|
| `bot/scripts/run_broker_paper.py` | Demo runner; intelligent brain integration |
| `bot/aegis/intel/firehose_brain.py` | FIRE/SCALE/HOLD/REDUCE/EXIT decisions |
| `bot/aegis/intel/analogue_store.py` | Runtime analogue lookup |
| `bot/aegis/intel/knowledge_runtime.py` | Book hypothesis matching |
| `bot/aegis/intel/lifecycle.py` | Portfolio + deal reconciliation |
| `bot/aegis/intel/outcome_log.py` | Closed-trade learning log |
| `bot/aegis/intel/scoreboard.py` | Old vs intelligent metrics |
| `bot/aegis/research/knowledge.py` | Book compile + prose extraction |
| `bot/aegis/research/analogues.py` | Analogue index build/query |
| `bot/scripts/research_firehose_shadow.py` | Read-only shadow observer |
| `docs/trading/books/` | Full book extracts (local library) |
| `docs/trading/INDEX.md` | Book catalog |

---

## Commits on main (this work)

1. `7b1c3eb` — Intelligent Firehose shadow observer and research stack
2. `4e13bcf` — Wire Intelligent Firehose into demo runner with analogue evidence
3. `d957566` — Complete demo loop: exits, books, learning, reporting
4. *(this push)* — Stop normalization fix, helper tests, books force-added, chat export

---

## Rollback

See `bot/reports/research/intelligent_firehose_rollback.md`.

Quick: checkout pre-brain config/runner, set `intelligent_firehose: false`, restart **one** runner.

---

## Definition of done (status at export)

- [x] Point-in-time analogue history
- [x] Structured book knowledge (setup/entry/invalidation/exit)
- [x] Demo runner consumes Intelligent Firehose
- [x] FIRE / SCALE / HOLD / REDUCE / EXIT wired
- [x] Portfolio / currency exposure
- [x] Outcome learning + reconciliation
- [x] Old vs intelligent reporting
- [x] 91.91% WR negative-EV regression test
- [x] MT5 comment + stop-distance fixes
- [ ] Full book corpus validated champion promoted (research ongoing)
- [ ] $100/day target (gap analysis only — not claimed reached)

---

## User standing orders

- Demo (`allow_live: false`): may open/close 0.01-lot probes when testing hypotheses.
- Do not start second `run_broker_paper.py`.
- Do not edit live firehose YAML or set `allow_live: true` without explicit user request.
- Push everything to main including books and this context.
