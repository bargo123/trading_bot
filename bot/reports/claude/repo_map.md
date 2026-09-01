# Aegis repo map — live MT5 demo path vs research / dead

Evidence-based, read from code rather than from prior reports. Paths relative to
`bot/`. Entry point:

```bash
.venv/Scripts/python bot/scripts/run_broker_paper.py --config bot/config_mt5_demo_firehose_hw.yaml
```

(`engine: mt5`, `mode: mt5_demo`, `intelligent_firehose: true`, `intel_enabled: false`)

## 1. Execution path: MT5 quote/bar → order

| # | Stage | file:line |
| --- | --- | --- |
| 1 | `load_config` | `scripts/run_broker_paper.py:122` → `aegis/config.py:11` |
| 2 | order-send permission (`paper_execution_enabled`) | `run_broker_paper.py:124` → `paper_control.py:44` |
| 3 | process lock acquire | `run_broker_paper.py:131` → `paper_control.py:94` |
| 4 | engine create + connect (demo gate) | `run_broker_paper.py:134` → `engines/factory.py:9` → `engines/mt5.py:119`, gate `:150` |
| 5 | paper-account assertion | `run_broker_paper.py:198` |
| 6 | Risk / ExecutionCircuit / HighRisk init | `run_broker_paper.py:142-150` |
| 7 | symbol probe (drop untradeable) | `run_broker_paper.py:203` |
| 8 | main loop; account + positions | `run_broker_paper.py:1041` |
| 9 | reconcile closed deals → outcome log | `run_broker_paper.py:1075` → `intel/lifecycle.py:44` → `reconcile.py:239` → `intel/outcome_log.py:12` |
| 10 | heartbeat + brain snapshot | `run_broker_paper.py:1068` |
| 11 | exit management; MFE update/persist | `run_broker_paper.py:1094-1176`; `exits.py:19` |
| 12 | position caps / JPY cluster / margin cooldown | `run_broker_paper.py:1177-1200`; `oms.py:88` |
| 13 | `maybe_enter` | `run_broker_paper.py:1214` → `:445` |
| 14 | fetch bars, prepare frame | `:451` (`engines/mt5.py:400`), `:466` (`strategy.py` `prepare`) |
| 15 | closed bar `row = frame.iloc[-2]`; new-bar dedupe | `:467` |
| 16 | live quote; spread / pip | `:473` → `engines/mt5.py:318` |
| 17 | **stale-quote reject** | `:484-499` → `oms.py` `quote_age_s` |
| 17b | **future-quote reject** (added) | `:500-514` → `oms.py` `quote_future_skew_s` |
| 18-20 | `risk.allow` / `circuit.allow` / `hr.allow` | `:503`, `:512`, `:523` |
| 21 | max-spread skip | `:529` → `config.py` `max_spread_for` |
| 23 | **brain evaluate** | `:573-620` → `intel/firehose_brain.py` `evaluate` |
| 23a | side hint (`intel_enabled` forced False) | `:584` → `strategy.py:74` → `session_algos.py` `sig_firehose` |
| 23b | broker contract spec (for economics) | `:590` → `engines/mt5.py:340` |
| 23c | runtime MarketState + signature | `firehose_brain.py` → `intel/state_runtime.py` |
| 23d | analogue evidence query (point-in-time) | → `intel/analogue_store.py` `query` |
| 23e | book/knowledge match — **journal only** | → `intel/knowledge_runtime.py` `match_knowledge` |
| 23f | portfolio pretrade | → `intel/lifecycle.py` `pretrade_ok` → `portfolio_risk.py` |
| 23g | champion load / evidence bootstrap | `firehose_brain.py` `_load_strategy`, `_bootstrap_from_evidence` |
| 23h | thesis FIRE gate | → `intel/thesis_fire.py` `evaluate_thesis_fire` |
| 23i | **edge sizing** (added) | → `intel/thesis_sizing.py` `size_thesis_clip` |
| 23j | **per-trade economics** (added) | → `intel/trade_economics.py` `evaluate_trade_economics` |
| 23k | action mapping fire/scale/hold/reduce/exit | → `intel/thesis_fire.py` `evaluate_thesis_action` |
| 24 | exit/reduce → `close_ticket` + outcome + memory | `run_broker_paper.py:609-664` → `engines/mt5.py:738` |
| 26 | fire/scale → `Signal` | `run_broker_paper.py:686-695` |
| 29 | brain quantity override | `:780-781` |
| 30 | broker stop-distance normalisation | `:825` |
| 31 | `OrderRequest` + `oms_allows` | `:833`, `:842` → `oms.py` `oms_allows` |
| 34 | **`eng.place_order`** | `:904` → `engines/mt5.py:568`, gate `:562` |
| 35 | journal order; `circuit.observe`; `memory.apply` | `:929-966` |

## 2. Component status

| Component | Status | Note |
| --- | --- | --- |
| runner | ACTIVE | sole demo entry |
| config loading | ACTIVE | hot reload forces `allow_live=False` (`:1008`) |
| MT5 engine | ACTIVE | `engines/ibkr.py` imported via `__init__` but never instantiated |
| strategy/signal routing | ACTIVE (hint only) | supplies `core_side` only in intelligent mode |
| `intel/state_runtime.py` (MarketState) | ACTIVE | |
| `research/market_state.py`, `MarketStateCache` | RESEARCH-ONLY | shadow observer only |
| `intel/thesis_fire.py` | ACTIVE | |
| `intel/expected_value.py` | ACTIVE (transitive) | |
| `intel/trade_economics.py` | **ACTIVE** | computed + journaled every bar; gates FIRE |
| `intel/thesis_sizing.py` | ACTIVE when a strategy model exists | guarded by `strategy is not None` |
| `intel/strategy_model.py` | ACTIVE | rejects PF ≤ 1 and `n_losses < 5` |
| `intel/analogue_store.py` | ACTIVE | index now `provenance: mt5_m1` (see §5) |
| `intel/knowledge_runtime.py` | ACTIVE but **advisory only** | gates nothing |
| `intel/books.py` | DEAD | only `intel/runner.py` imports it |
| `portfolio_risk.py` | ACTIVE | via `lifecycle.pretrade_ok` |
| `reconcile.py` | ACTIVE | cursor not persisted; wrapped in bare `except` |
| MFE tracking | ACTIVE (**MFE only**) | no MAE recorder exists in `exits.py` |
| `risk.py` | ACTIVE | limits restored to 10% / 25% |
| `execution_circuit.py` | ACTIVE | |
| oms / pretrade | ACTIVE | stale + crossed + **future** quote rejection |
| shadow observer | RESEARCH-ONLY, separate process | read-only attach, zero order calls |
| experiment registry, `optimizer/` | RESEARCH-ONLY | |
| `intel/champion.py` | DEAD in demo | writes `intel/champion.json`, which the brain never reads |
| `research/intelligent_champion.py` | RESEARCH-ONLY | produces the artifact the brain needs |
| `research/sealed.py` (sealed holdout) | effectively DEAD | referenced only by tests |
| `intel/outcome_log.py` | ACTIVE but **write-only** | no module reads `outcome_log.jsonl` |
| `intel/scoreboard.py`, `research/intelligence_cycle.py` | RESEARCH-ONLY | |

## 3. Wiring gaps, ranked

1. **No promoted `intelligent_champion.json`.** `_load_strategy` returns `None`, so the
   brain depends entirely on `_bootstrap_from_evidence`. `save_intelligent_champion`
   is reachable only from `scripts/research_firehose_shadow.py`, which nothing
   schedules. This is the single highest-value remaining connection.
2. **Outcome learning loop is open.** `append_outcome` writes `intel/outcome_log.jsonl`
   and **no module reads it**. `research/learning.py:attribute_outcomes` and
   `intel/scoreboard.py` are the natural consumers; neither is fed that file. Live
   results currently influence nothing.
3. **Reconcile cursor not persisted.** `ReconcileCursor.load_json`/`save_json` are
   never called; the runner uses a fresh `new_cursor()`, so a restart re-ingests
   `history_deals(1)` and duplicates outcome rows.
4. **Shadow observer not supervised.** `supervisor_keepalive.ps1` and `watchdog.py`
   supervise only `run_broker_paper.py`, which is the root cause of gap 1.
5. **Sealed holdout not in any promotion path**, so a future champion could be
   promoted without holdout protection.
6. **Book knowledge is decorative.** `match_knowledge` output reaches only journal
   fields; the 1.6 MB knowledge table gates nothing.
7. **Two unlinked champion stores** — `intel/champion.json` exists and is read by
   nobody; the brain reads `intel/intelligent_champion.json`.
8. **No MAE tracking**, so stop distances cannot be calibrated from live data.

## 4. Safety invariants

| Invariant | Verdict | Evidence |
| --- | --- | --- |
| Exactly one process can execute orders | **PASS** | `ProcessLock` before engine connect, `run_broker_paper.py:131`; non-blocking `msvcrt.locking`/`flock` raising, `paper_control.py:100-115`. All three order-placing scripts share the lock file. |
| Shadow observer places zero orders | **PASS** | grep for `place_order\|close_ticket\|flatten_positions\|order_send` over `aegis/research/*.py` and `scripts/research_*.py` → 0 hits; read-only attach via `engines/mt5.py:176`. |
| `allow_live` gating prevents live trading | **PASS** (4 layers) | startup `paper_control.py:25-34`; connect `engines/mt5.py:150`; session `run_broker_paper.py:199`; per-mutation `engines/mt5.py:562` on every `place_order`/`close_ticket`/`flatten`. Hot reload forces `allow_live=False`. |
| Reconciliation invoked in demo loop | **PASS with caveats** | `run_broker_paper.py:1075` each cycle; silent bare `except`, cursor not persisted. |
| Stale quote rejection | **PASS** | `run_broker_paper.py:484` and `oms.py` |
| Crossed quote rejection | **PASS** | `oms.py` `oms_allows` |
| Future-dated quote rejection | **PASS** (was FAIL) | `quote_age_s` clamped at zero, so a future tick reported age 0.0 and passed. Fixed by `quote_future_skew_s` + `max_quote_future_skew_s`; see `tests/test_oms_future_quote.py`. |
| `aegis/research/*` never imported by runtime intel | **PASS** | zero import statements in `aegis/intel/`, `aegis/*.py`, `aegis/engines/*.py`; enforced by `tests/test_research_isolation.py`. |

## 5. Analogue index provenance

The committed index was a **synthetic fixture** — 640 records, exactly two outcome
values (`+0.04` ×480, `-0.02` ×160) on a mechanical time grid, reporting a fabricated
profit factor of 6.0 for any query with 20 matches. It is preserved as
`intel/analogue_index.synthetic_fixture.json`.

It has been replaced with a **measured** index built from real MT5 M1 history:
`provenance: mt5_m1`, `outcome_unit: pips`, **9,569 records across 26 symbols**,
2,134 distinct outcomes. See `edge_and_gap.md` for what that evidence actually says.

## 6. Module reachability

Static AST closure of `scripts/run_broker_paper.py`, following `aegis.*` imports
including function-local ones:

- **43** of **139** `bot/aegis/**.py` files reachable (≈31%); 45 counting the two
  implicit package `__init__.py` files.
- Unreached: all 64 `research/`, all 14 `optimizer/`, 9 `intel/`, 9 top-level.
- "Reachable by import" is a superset of "reachable at runtime": `intel/decide.py`,
  `intel/score.py`, `intel/similarity.py`, `intel/mega_book.py`, `accuracy.py`,
  `direction.py`, `chart_read.py` are imported but bypassed because
  `intel_enabled: false` and the runner forces `hint_cfg["intel_enabled"] = False`.
  `pa_select.py` is imported but `pa_select_mode` is False.

## Unverified

- Module-status claims come from static reading plus artifact inspection; the brain's
  decision path *was* additionally exercised live against the demo terminal by
  `scripts/claude_brain_probe.py` (see `brain_probe.json`).
- Whether an external Windows scheduled task runs the research/shadow scripts is
  unverified; only in-repo `.ps1` and `watchdog.py` were checked.
