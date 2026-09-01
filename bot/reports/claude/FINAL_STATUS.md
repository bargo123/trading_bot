# Aegis — final implementation status (handoff to OpenCode)

Branch merged to `main`. **527 tests passing, 0 failing** (baseline as cloned:
464 passing / 5 failing). MT5 remains **DEMO-only**; `allow_live: false` everywhere.

## Start the bot

```bash
.venv/Scripts/python bot/scripts/run_broker_paper.py --config bot/config_mt5_demo_firehose_hw.yaml
```

> MT5 currently reports `trade_allowed: false` — Algo Trading is toggled **off** in the
> terminal, so the bot reads quotes but cannot send orders. Enable
> *Tools → Options → Expert Advisors → Allow algorithmic trading* to let it place demo
> orders. Leaving it off is a valid observation-only mode.

## Verified at handoff

| check | result | how verified |
| --- | --- | --- |
| full test suite | **527 passed, 0 failed** | `pytest -q`, saved to `pytest_final.txt` |
| `allow_live` true anywhere | **none** | `grep -rn allow_live --include=*.yaml` → every hit is `false` |
| MT5 account is demo | **DEMO** | live probe: login 111368559, `MetaQuotes-Demo`, `trade_mode_raw: 0` |
| live-account mutation refused | **refused** | `assert_paper_mutation_allowed({mode: live})` → `RuntimeError: MT5 mutations require mode: mt5_demo` |
| engine refuses non-demo login | **guard present** | `aegis/engines/mt5.py:150` |
| exactly one execution runner | **enforced** | the only three scripts calling `place_order` (`run_broker_paper.py`, `run_mgc_firehose.py`, `live_mt5_algo_test.py`) all take the **same** lock `reports/run_broker_paper.lock`; second acquire empirically raised `RuntimeError: another process holds ...` |
| shadow/research places orders | **zero call sites** | `grep place_order\|close_ticket\|flatten_positions\|order_send` over `aegis/research/*.py` + `scripts/research_*.py` → 0 hits |
| stale / crossed / **future** quote rejection | active | `oms.py`; `tests/test_oms_future_quote.py` |
| drawdown circuit breaker | **armed** (10% daily / 25% total) | was `0/0` = fully disabled |
| research isolation | 0 `aegis.research` imports in runtime intel | `tests/test_research_isolation.py` |

## Intelligent Firehose status

**Wired and armed, currently holding fire — correctly.**

The full chain is connected and exercised: MarketState → analogue evidence
(point-in-time) → book knowledge → strategy model → **per-trade economics** →
**edge-derived sizing** → portfolio pretrade → FIRE / SCALE / HOLD / REDUCE / EXIT →
MT5 demo → reconciliation → outcome log.

Verified live read-only across all 26 symbols (`scripts/claude_brain_probe.py`, places
no orders): the economics gate rejected **23 of 26** on `payoff_below_floor`, and the
brain skipped all 26 at `no_validated_strategy_model`. That is the intended behaviour,
not a defect — its two measurably-positive states are Asia-session sells and the probe
ran at 19:30 UTC.

Throughput is protected by test in both directions
(`tests/test_intel_firehose_economics_gate.py`): destructive geometry cannot fire even
at a 91.7% sample win rate, **and** good geometry with measured evidence still fires.

## Champion status

**No promoted champion.** `intel/intelligent_champion.json` is **absent**, so
`_load_strategy` returns `None` and the brain relies on `_bootstrap_from_evidence`,
which requires measured provenance plus a state that clears the 95% lower bound.

`intel/champion.json`, `challenger.json`, `baseline.json` exist but belong to the
separate, demo-inert `intel/champion.py` path — the brain never reads them.

The producer, `research/intelligent_champion.py:save_intelligent_champion`, is
reachable only from `scripts/research_firehose_shadow.py`, which nothing schedules.
**This is the single highest-value remaining connection.**

## Analogue evidence

`intel/analogue_index.json` — `provenance: mt5_m1`, `outcome_unit: pips`,
**9,569 records across 26 symbols**, 2,134 distinct outcomes. The previous synthetic
fixture is preserved as `intel/analogue_index.synthetic_fixture.json`.

Measured population result: WR 47.1%, PF **0.85**, expectancy **−0.56 pips** — negative
before costs. Two states clear the 95% lower bound, both Asia-session sells
(`range/none/asia/sell` n=759 exp +1.39 PF 1.59; `trend/none/asia/sell` n=674 exp +0.86
PF 1.35). See `edge_and_gap.md`.

## Remaining known problems

1. **No promoted champion / nothing schedules the producer** (above). Promotion is also
   not gated by `research/sealed.py`, which is referenced only by tests.
2. **Outcome-learning loop is open.** `append_outcome` writes `intel/outcome_log.jsonl`
   and **no module reads it**. `research/learning.py:attribute_outcomes` and
   `intel/scoreboard.py` are the natural consumers. Live results influence nothing.
3. **Measured expectancy is negative** for the M15 structural-thesis family. This is an
   edge gap, not a capital gap — `$100/day` is reported as *unavailable* because
   leverage multiplies a negative number.
4. **Reconcile cursor not persisted.** `ReconcileCursor.load_json`/`save_json` are never
   called, so a restart re-ingests `history_deals(1)` and duplicates outcome rows.
5. **No MAE tracking.** `exits.py` implements `update_mfe` only; stop distances cannot
   be calibrated from live data.
6. **Book knowledge is decorative.** `knowledge_table.json` has the right 194-row schema
   but its `setup`/`entry` fields are raw keyword-sliced prose (one row's `entry` reads
   *"All the information was entered at the exchanges by hand…"*), and `match_knowledge`
   output reaches only journal fields — it gates nothing.
7. **Index covers ~4 days of M1.** Rebuild periodically for more statistical power:
   `.venv/Scripts/python bot/scripts/build_real_analogue_index.py --bars 6000 --step 15 --workers 10`
8. **Reconcile block is wrapped in a bare `except`**, so failures are silent.
9. `bot/optimizer/optimizer.lock` was tracked upstream and held a stale PID; it is now
   untracked and gitignored. The file remains on disk.
10. **Terminal `trade_allowed: false`** — see the note above the start command.

## Rollback

Per-commit table and config-only disable switches for every new gate are in
`RUNBOOK.md`. Upstream `main` before this work: `c3039d7`.
