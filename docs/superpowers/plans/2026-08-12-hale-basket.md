# HALE Basket Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and honestly measure the Heikin-Ashi Level Exhaustion basket candidate on frozen OHLC snapshots with fixed and variable trading costs.

**Architecture:** A focused `aegis.hale` module produces signal-only Heikin-Ashi and level features, while the existing chronological basket engine executes on next-bar real OHLC. A deterministic tuning script selects on development/validation, opens holdout once, stresses costs/sizing, and emits a config plus report.

**Tech Stack:** Python 3, pandas, NumPy, PyYAML, pytest, existing Aegis risk and basket-backtest modules.

## Global Constraints

- Paper trading remains stopped throughout this research.
- Never execute at synthetic Heikin-Ashi prices.
- Count closed, cost-bearing trades rather than raw signals.
- Use one shared $100 basket and preserve chronological, stop-first execution.
- Search development/validation only and open each selected holdout once.
- Report the observed results without promising a future win rate or daily income.

---

### Task 1: Fixed-dollar commission accounting

**Files:**
- Modify: `bot/tests/test_basket_backtest.py`
- Modify: `bot/aegis/basket_backtest.py`

**Interfaces:**
- Consumes: `run_basket_backtest(data, cfg, prepare_fn=..., signal_fn=...) -> BacktestResult`
- Produces: configuration key `commission_round_trip_usd: float`; trade field `fixed_commission_usd: float`

- [ ] **Step 1: Write the failing behavior test**

Add a test that runs the existing one-trade fixture with zero bps costs and `commission_round_trip_usd=4.0`; assert the gross $1 winner becomes `pnl == -3.0`, `final_equity == 97.0`, `win_rate == 0.0`, and the recorded fixed commission is $4.

- [ ] **Step 2: Run the narrow test and observe RED**

Run `cd bot && pytest -q tests/test_basket_backtest.py::test_fixed_round_trip_commission_is_charged_once` and require a failure showing the commission is currently omitted.

- [ ] **Step 3: Implement the smallest accounting change**

In `close_position`, read `fixed_commission = max(0.0, float(cfg.get("commission_round_trip_usd", 0.0)))`, calculate `pnl = units * (move - variable_cost) - fixed_commission`, and record `fixed_commission_usd` in the closed trade.

- [ ] **Step 4: Run the narrow and basket test files**

Run `cd bot && pytest -q tests/test_basket_backtest.py`; require all basket tests to pass.

### Task 2: HALE feature preparation

**Files:**
- Create: `bot/tests/test_hale_unit.py`
- Create: `bot/aegis/hale.py`
- Modify: `bot/aegis/features.py`

**Interfaces:**
- Produces: `heikin_ashi(df: pd.DataFrame) -> pd.DataFrame`
- Produces: `prepare_hale(df: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame`
- Prepared columns include `hale_ha_open`, `hale_ha_high`, `hale_ha_low`, `hale_ha_close`, `hale_ha_body`, `hale_ha_color`, `hale_prev_day_high`, `hale_prev_day_low`, `hale_session_high_prior`, `hale_session_low_prior`, `hale_round_level`, and lagged `cafb_htf_regime`.

- [ ] **Step 1: Write a hand-derived HA transform test**

Use three literal OHLC rows. Assert the first HA open/close and the recursive second/third HA opens against hand-calculated numeric literals; assert HA high/low contain the real extremes.

- [ ] **Step 2: Run the HA transform test and observe RED**

Run `cd bot && pytest -q tests/test_hale_unit.py::test_heikin_ashi_uses_recursive_signal_prices` and require an import or missing-function failure.

- [ ] **Step 3: Implement `heikin_ashi`**

Implement the four canonical formulas in a loop only for recursive HA open; return a new frame indexed like the input and never overwrite real OHLC.

- [ ] **Step 4: Write no-lookahead level tests**

Create UTC bars spanning two days. Assert every first-day `hale_prev_day_high/low` is missing, the first bar of day two sees only day-one extrema, and `hale_session_high_prior/low_prior` exclude the current bar.

- [ ] **Step 5: Run the level tests and observe RED**

Run `cd bot && pytest -q tests/test_hale_unit.py -k 'level or session'`; require missing-column failures.

- [ ] **Step 6: Implement `prepare_hale`**

Call `enrich_all`, drop/rebuild HALE-prefixed fields, attach HA values, build shifted UTC daily extrema, shifted same-day expanding extrema, configured round levels, impulse helper columns, and the one-bucket-lagged CAFB regime via `_higher_timeframe_context` and `merge_asof`.

- [ ] **Step 7: Make re-preparation idempotent**

Add `"hale_"` to `enrich_all` generated prefixes and assert `prepare_hale(prepare_hale(raw, cfg), cfg)` has no `_x/_y` duplicate columns and identical HA/level outputs.

- [ ] **Step 8: Run HALE unit tests**

Run `cd bot && pytest -q tests/test_hale_unit.py`; require all feature tests to pass.

### Task 3: Separate fade and pullback signals

**Files:**
- Modify: `bot/tests/test_hale_unit.py`
- Modify: `bot/aegis/hale.py`

**Interfaces:**
- Produces: `sig_hale_fade(row: pd.Series, cfg: dict[str, Any]) -> Signal | None`
- Produces: `sig_hale_pullback(row: pd.Series, cfg: dict[str, Any]) -> Signal | None`
- Produces: `_cost_ok_for_sized_trade(...) -> bool` for fixed-plus-variable cost rejection.

- [ ] **Step 1: Write literal fade-signal tests**

Build prepared-row dictionaries for one valid short exhaustion, one valid long exhaustion, one wrong-regime rejection, one missing-level rejection, and one target-too-small-for-cost rejection. Assert exact side, mode, reason, structural stop direction, and target direction.

- [ ] **Step 2: Run fade tests and observe RED**

Run `cd bot && pytest -q tests/test_hale_unit.py -k fade`; require missing-function failures.

- [ ] **Step 3: Implement the fade signal**

Validate required fields, session/hour gates, range regime, impulse direction/count/displacement, body contraction, level distance, first opposite HA color, structural stop, fixed-R target, and the sized dollar cost gate. Return no signal on every invalid boundary.

- [ ] **Step 4: Write literal trend-pullback tests**

Cover a valid trend-up resumption, valid trend-down resumption, range-regime rejection, too-distant EMA rejection, and cost rejection. Assert branch names differ from fade.

- [ ] **Step 5: Run pullback tests and observe RED**

Run `cd bot && pytest -q tests/test_hale_unit.py -k pullback`; require missing-function or wrong-branch failures.

- [ ] **Step 6: Implement the pullback signal**

Require lagged directional regime, configured opposite-color pullback length, real close near EMA20, HA resumption with regime, a real structural stop beyond the pullback extreme, fixed-R target, and the same cost gate.

- [ ] **Step 7: Run focused tests**

Run `cd bot && pytest -q tests/test_hale_unit.py tests/test_basket_backtest.py`; require all tests to pass.

### Task 4: Deterministic tuning and report generation

**Files:**
- Create: `bot/config_hale_basket.yaml`
- Create: `bot/scripts/tune_hale_basket.py`
- Create by script: `bot/config_hale_basket.tuned.yaml`
- Create by script: `bot/reports/hale_search_results.csv`
- Create by script: `bot/reports/HALE_BASKET.md`

**Interfaces:**
- Consumes: cached `1m` and `5m` snapshots, `prepare_hale`, both signal functions, `run_basket_backtest`, and reusable split/metric helpers from `tune_cafb_basket.py`.
- Produces: `stable_score(dev: dict, val: dict, min_dev: int, min_val: int) -> float`
- Produces: one selected fade and one selected pullback configuration per timeframe; only the stronger validated family becomes the tuned config.

- [ ] **Step 1: Add a deterministic score unit test**

In `bot/tests/test_hale_unit.py`, assert a positive-E[R]/PF>1 development-validation pair outranks a high-WR negative-E[R] pair and a below-minimum-trades candidate returns the rejection sentinel.

- [ ] **Step 2: Run the score test and observe RED**

Run `cd bot && pytest -q tests/test_hale_unit.py::test_stable_score_prefers_expectancy_over_raw_win_rate`; require an import or missing-function failure.

- [ ] **Step 3: Implement config, bounded grids, and reporting**

Write an auditable four-symbol base config. Search HA impulse bars, displacement, contraction, level distance, stop buffer, target R, and regime parameters on development/validation only. Store full search rows. Open holdout exactly once for each selected timeframe/family. Stress 1.0x/1.5x/2.0x variable costs, $4 IB fixed commission, and 1/2/5/10/20% nominal risk. Emit every mandatory metric and promotion-gate result.

- [ ] **Step 4: Run the tuning job from immutable cache**

Run `cd bot && python scripts/tune_hale_basket.py`. Do not pass a refresh flag. Capture the printed selected development, validation, holdout, and stress summaries.

- [ ] **Step 5: Inspect generated artifacts for consistency**

Verify the report's selected parameters match the tuned YAML, all rows identify exact UTC windows and costs, trades are closed trades, and the promotion verdict matches the numerical gates.

### Task 5: Verification and paper-safety handoff

**Files:**
- Verify: `bot/reports/HALE_BASKET.md`
- Verify: `bot/config_hale_basket.tuned.yaml`
- Verify: all modified Python files and tests

**Interfaces:**
- Produces: an evidence-backed final result and an explicit paper promotion/rejection decision.

- [ ] **Step 1: Run targeted verification**

Run `cd bot && pytest -q tests/test_hale_unit.py tests/test_basket_backtest.py tests/test_backtest_correctness.py`.

- [ ] **Step 2: Run the full test suite**

Run `cd bot && pytest -q`; require zero failures.

- [ ] **Step 3: Compile touched Python**

Run `cd bot && python -m compileall -q aegis/hale.py aegis/basket_backtest.py scripts/tune_hale_basket.py`.

- [ ] **Step 4: Confirm the paper stack remains stopped**

Run the existing Aegis status command in read-only mode. Confirm no bot process, no new order, and no position was created by research.

- [ ] **Step 5: Deliver measured numbers**

Report the chosen family/timeframe, exact sample window, trades, trades/day, WR and Wilson interval, E[R], PF, max drawdown, $100 start/end, halt reason, variable and fixed costs, and whether every promotion gate passed. If rejected, leave paper stopped and state the exact failed gates.
