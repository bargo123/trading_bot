# Aegis takeover — findings and continuation

Branch `claude/intelligent-firehose`, 5 commits on top of upstream `main` (`c3039d7`).
**527 tests passing, 0 failing** (baseline was 464 passing / 5 failing).
`allow_live: false` everywhere; no real-money path was enabled.

---

## 1. The economic failure, root-caused

The reported regression — 1,175 trades, 91.91% win rate, PF 0.71, net −$10.71 — had
**two independent causes**, both confirmed against data in this repo.

### Cause A: nothing priced the trade being sent

`expected_value.py` scored a *population* of outcomes and `analogue_store.py` scored
the *historical state*. Neither looked at the geometry of the order about to go out.

Measured live on real M15 structure, the brain was about to buy EURUSD with:

| | |
| --- | --- |
| invalidation distance | 31.5 pips |
| target distance | 1.1 pips |
| expected win / loss | $0.11 / $3.15 |
| payoff ratio | **0.035** |
| breakeven win rate | **98.2%** |
| expected value | **−$2.03** |

State-level expectancy was positive the entire time. That is precisely how a 92% win
rate coexists with PF < 1.

**Fixed:** `aegis/intel/trade_economics.py` prices entry / invalidation / target
against the live spread and commission using the broker's `tick_value:tick_size` pair
(`contract_size` alone is ~158× wrong on USDJPY), and rejects on a payoff floor or
non-positive EV. Win probability defaults to the **Wilson lower bound** of the
analogue sample, so a thin sample cannot pose as a strong edge.

### Cause B: the evidence was fabricated

`bot/intel/analogue_index.json` was a synthetic fixture — 640 records, exactly two
outcome values (`+0.04` ×480, `−0.02` ×160) on a mechanical time grid — which returned
a **"calibrated" profit factor of 6.0** for any query with 20 matches.
`save_analogue_index` stamped *every* index `label: "research_proxy"` whether built
from MT5 history or from the fixture, so real and fake were indistinguishable on disk.

The live demo journal shows what the bot did while believing that: **1,224 fires,
PF 0.25, expectancy −$0.0437, net −$160.46** — worse than the 0.71 baseline.

**Fixed:** indexes now carry real `provenance` and `outcome_unit`; the brain refuses
to bootstrap a validated strategy model from non-measured provenance.

---

## 2. What the real evidence actually says

A measured index was built from live MT5 M1 history: **9,569 records, 26 symbols,
2,134 distinct outcomes**, `provenance: mt5_m1`.

| | synthetic fixture | measured reality |
| --- | --- | --- |
| win rate | 75% | **47.1%** |
| profit factor | **6.0** | **0.85** |
| expectancy | +0.025 | **−0.56 pips** |
| payoff ratio | 2.0 | 0.95 |

**The M15 structural-thesis family has negative expectancy before costs.** Per-state
analysis: 41 states with ≥20 observations, 14 positive on point estimate, and exactly
**2 that clear the 95% lower-bound test** — both large-sample Asia-session sells:

| state | n | expectancy | PF | lower95 |
| --- | --- | --- | --- | --- |
| range / none / asia / sell | 759 | +1.39 pips | 1.59 | +0.80 |
| trend / none / asia / sell | 674 | +0.86 pips | 1.35 | +0.23 |

Consequently `edge_and_gap.md` reports the $100/day requirement as **unavailable**
rather than inventing a capital figure. This is an *edge* gap, not a capital gap —
leverage multiplies a negative number.

---

## 3. Other defects fixed

| Defect | Why it mattered |
| --- | --- |
| **HALE never routed** — `hale_fade`/`hale_pullback` were implemented in `aegis/hale.py` and tuned by `tune_hale_basket.py`, but neither `prepare()` nor `signal_from_row()` dispatched to them | any HALE config crashed on `KeyError: donchian_period`; no runner could ever execute one |
| **CWD-relative config paths** — `intel/analogue_index.json` resolved against the process CWD | launched from the repo root the brain loaded **zero** analogues and **zero** book rows *silently*; every decision was made on no evidence. Now anchored to `BOT_ROOT`, with explicit warnings in `snapshot()` |
| **Future-dated quotes accepted** — `quote_age_s` clamps at zero, so a tick stamped ahead of local time reported age 0.0 and passed the staleness gate | broker clock skew or corrupt ticks could price a real order. Added `quote_future_skew_s` + `max_quote_future_skew_s` |
| **Fixed lot size** — every fire sent `order_quantity` regardless of stop distance | a 50-pip stop risked 10× a 5-pip stop. `thesis_sizing.py` now sizes from validated risk fraction ÷ invalidation distance, floors to `volume_step`, respects `mt5_max_lots`, and refuses rather than padding up to the broker minimum |
| **Evidence fragmented by symbol** — `query` hard-filtered by symbol | a 759-observation state became ~30 per pair and stopped clearing the lower-bound test, hiding the only two real edges. Pooling is opt-in via `intelligent_pool_across_symbols`; live samples went from 44–275 to 179–4,089 |
| **Drawdown guards disabled** — `max_daily_loss_percent: 0` and `max_total_drawdown_percent: 0` fully disable the breaker | switched off to keep spraying after a 39% drawdown. Restored at loose 10%/25%, and the test now requires an *armed* breaker instead of pinning 0 |
| **IB baseline config drifted** off observation-only (`dry_run: false`, no `paper_trading_enabled`) | restored per spec |
| **`os.getuid()`** is POSIX-only | crashed launchd payload construction on Windows |
| **Vacuous test** — `test_brain_can_fire_with_bootstrap_analogues` was wrapped in `if decision.action in {...}` and its fixture described breakout/london while the data produces retest/asia, so only 7 of 40 records ever matched | passed even when the brain never fired |
| **No conftest** — the suite relied on incidental `sys.path` pollution between modules | targeted test runs failed to collect |

---

## 4. The firehose was not made timid

Throughput was explicitly protected. `test_intel_firehose_economics_gate.py` asserts
**both** directions, so a future change cannot satisfy one by breaking the other:

- destructive geometry cannot fire *even at a 91.7% sample win rate*, and
- good geometry with measured evidence **still fires**, with edge-derived size.

The brain currently holds fire on all 26 symbols. That is correct, not broken: its two
edge states are Asia-session sells and the probe ran at 19:30 UTC. Verified live,
read-only, by `scripts/claude_brain_probe.py`.

---

## 5. Verified state

| check | result |
| --- | --- |
| repository current | `main` @ `c3039d7`, work on `claude/intelligent-firehose` |
| Serena | official `oraios/serena`, `python_jedi` backend, **280 files indexed, health check passed** |
| dependencies | `.venv`, Python 3.12.10, all root + bot requirements |
| full tests | **527 passed, 0 failed** |
| books | 54 files, 5.16M words, 0 duplicates, 0 OCR-damaged, 2 stubs |
| MT5 demo connects | login 111368559, `MetaQuotes-Demo`, `trade_mode: DEMO`, 26/26 symbols live |
| `allow_live=false` | 4 enforcement layers (startup, connect, session, per-mutation) |
| exactly one execution runner | `ProcessLock`, non-blocking, shared by all order-placing scripts |
| shadow observer cannot trade | 0 order-call sites; read-only attach |
| MarketState / analogue / EV / Thesis / FIRE / SCALE / HOLD / REDUCE / EXIT | active |
| portfolio risk, reconciliation | active (reconcile cursor not persisted — see below) |
| research isolation | 0 `aegis.research` imports in runtime intel, test-enforced |
| rollback | documented per-commit in `RUNBOOK.md`, plus config-only disable switches |

> **MT5 terminal reports `trade_allowed: false`** — Algo Trading is toggled off, so the
> bot can read quotes but cannot send orders. Enable *Tools → Options → Expert
> Advisors → Allow algorithmic trading* when you want it to place demo orders.

---

## 6. Continuation — highest value first

1. **Produce a promoted `intelligent_champion.json`.** The brain falls back to
   `_bootstrap_from_evidence` because no champion artifact exists.
   `research/intelligent_champion.py:save_intelligent_champion` is reachable only from
   `scripts/research_firehose_shadow.py`, which nothing schedules. Gate it behind
   `research/sealed.py` (currently referenced only by tests) so promotion requires a
   sealed holdout.
2. **Close the outcome-learning loop.** `append_outcome` writes
   `intel/outcome_log.jsonl` and **no module reads it**.
   `research/learning.py:attribute_outcomes` and `intel/scoreboard.py` are the natural
   consumers. Live results currently influence nothing.
3. **Research the two real edge states.** Asia-session sells are the only measurably
   positive pockets. Build a strategy family around them, walk-forward it, and let it
   compete as a challenger rather than trading the negative-expectancy population.
4. **Persist the reconcile cursor.** `ReconcileCursor.load_json`/`save_json` are never
   called, so a restart re-ingests `history_deals(1)` and duplicates outcome rows.
5. **Add MAE tracking.** `exits.py` implements `update_mfe` only; without adverse
   excursion, stop distances cannot be calibrated from live data.
6. **Improve book extraction.** `knowledge_table.json` has the right 194-row schema
   (`hypothesis_id`, `invalidation`, `stop_logic`, `claims_requiring_validation`), but
   the `setup`/`entry` fields are raw keyword-sliced prose — one row's `entry` reads
   *"All the information was entered at the exchanges by hand…"*. It also gates
   nothing: `match_knowledge` output reaches only journal fields.
7. **Rebuild the index on a schedule.** It covers ~4 days of M1. `build_real_analogue_index.py`
   takes ~15 min for 26 symbols; a longer history would give the per-state tests more power.

## Reports written

`environment.md/json`, `repo_map.md/json`, `RUNBOOK.md`, `books_inventory.md/json`,
`firehose_comparison.md/json`, `edge_and_gap.md/json`, `brain_probe.json`,
`analogue_index_real.json`, `economics_scan.json`, `mt5_demo_check.json`,
`pytest_baseline.txt` → `pytest_final.txt`.
