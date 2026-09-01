# MGC Cost-Gated Firehose Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build, measure, and start a durable IB paper shadow runner for a one-contract, cost-gated MGC micro-momentum scalper, with order sending blocked until broker-native replay passes promotion.

**Architecture:** Extend the IB engine only at the concrete futures and streaming-market-data boundaries. Keep signal generation and replay in a pure `aegis.mgc_firehose` module so hand-derived tests can prove timing, executable-side pricing, costs, and selection without a broker. A separate runner captures quotes and updates the existing heartbeat/dashboard; the current LaunchAgent chooses that runner through configuration.

**Tech Stack:** Python 3.9, pandas, PyYAML, ib_insync, pytest, macOS launchd, JSONL capture and journal files.

## Global Constraints

- IB Gateway paper port is exactly `4002`; `allow_live` is exactly `false`.
- The only orderable instrument is a dated COMEX `MGC` future with quantity `1`, multiplier `10`, and tick size `0.1`.
- A continuous future may supply history but may never be submitted in an order.
- Every result includes fixed commission/exchange/regulatory fees, observed spread, and configured slippage.
- The target is 1,000 completed round trips/day, but positive cost-adjusted expectancy and risk gates have priority over frequency.
- No pyramiding, averaging down, martingale sizing, overlapping brackets, or overnight position.
- The first launched mode is shadow capture. Order sending remains blocked while `paper_promoted` is false.

---

### Task 1: Dated MGC contract and multiplier-aware cost boundary

**Files:**
- Modify: `bot/aegis/engines/ibkr.py`
- Modify: `bot/aegis/paper_control.py`
- Modify: `bot/scripts/run_broker_paper.py`
- Test: `bot/tests/test_engines_unit.py`
- Test: `bot/tests/test_ibkr_order_hygiene.py`
- Test: `bot/tests/test_paper_control.py`

**Interfaces:**
- Consumes: config keys `ib_futures_exchange`, `ib_futures_expiry`, `contract_multiplier`, `tick_size`, `futures_roll_guard_days`.
- Produces: `IBKREngine.contract_metadata(symbol: str) -> dict[str, object]`; `estimated_target_net_usd(..., contract_multiplier: float = 1.0, spread_price: float = 0.0, slippage_price: float = 0.0) -> float`.

- [ ] **Step 1: Write failing futures-contract tests**

```python
def test_mgc_requires_explicit_dated_contract_configuration():
    engine = IBKREngine({"ib_port": 4002, "symbol": "MGC"})
    assert_raises_value_error(lambda: engine._contract_definition("MGC"))


def test_mgc_contract_definition_is_one_dated_comex_future():
    cfg = {
        "ib_port": 4002,
        "symbol": "MGC",
        "ib_futures_exchange": "COMEX",
        "ib_futures_expiry": "202610",
        "contract_multiplier": 10,
        "tick_size": 0.1,
    }
    definition = IBKREngine(cfg)._contract_definition("MGC")
    assert definition == {
        "sec_type": "FUT",
        "symbol": "MGC",
        "exchange": "COMEX",
        "currency": "USD",
        "expiry": "202610",
        "multiplier": 10.0,
        "tick_size": 0.1,
    }
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `cd bot && .venv/bin/pytest -q tests/test_engines_unit.py tests/test_ibkr_order_hygiene.py`

Expected: FAIL because `_contract_definition` and the continuous-future order rejection do not exist.

- [ ] **Step 3: Implement the dated contract boundary**

Add a pure `_contract_definition` validator. In `_contract`, construct `ib_insync.Future("MGC", "202610", "COMEX", currency="USD")`, qualify it, verify the returned `secType`, symbol, exchange, currency, expiry, and multiplier, and cache it under an expiry-specific key. Add `contract_metadata` returning local symbol, conId, secType, expiry, exchange, currency, multiplier, and configured tick size. In `place_order`, return `OrderResult(ok=False, message="continuous futures are data-only")` before submission if `secType == "CONTFUT"`.

- [ ] **Step 4: Write the failing multiplier-cost test**

```python
def test_one_mgc_ten_tick_target_clears_full_cost_model():
    ok, net = target_clears_costs(
        quantity=1,
        contract_multiplier=10,
        entry=3500.0,
        target=3501.0,
        commission_round_trip_usd=1.92,
        spread_price=0.1,
        slippage_price=0.1,
        spread_bps=0,
        slippage_bps=0,
        min_expected_net_usd=1.0,
    )
    assert ok
    assert round(net, 2) == 6.08
```

- [ ] **Step 5: Run the cost test and verify RED**

Run: `cd bot && .venv/bin/pytest -q tests/test_paper_control.py::test_one_mgc_ten_tick_target_clears_full_cost_model`

Expected: FAIL because the cost function rejects the new keyword arguments.

- [ ] **Step 6: Implement multiplier-aware cost calculation**

Compute gross as `quantity * contract_multiplier * abs(target - entry)`. Add `quantity * contract_multiplier * (spread_price + slippage_price)` to the existing non-negative bps and fixed costs. Preserve defaults that make every existing FX call calculate exactly as before. Pass the new configuration values from `run_broker_paper.py`.

- [ ] **Step 7: Run Task 1 tests and verify GREEN**

Run: `cd bot && .venv/bin/pytest -q tests/test_engines_unit.py tests/test_ibkr_order_hygiene.py tests/test_paper_control.py`

Expected: all focused tests pass.

### Task 2: Pure MGC quote aggregation, signal, replay, and selector

**Files:**
- Create: `bot/aegis/mgc_firehose.py`
- Create: `bot/tests/test_mgc_firehose.py`

**Interfaces:**
- Consumes: normalized quote dictionaries with `time`, `bid`, `ask`, `bid_size`, `ask_size`, `last`, `last_size`, and `local_symbol`.
- Produces: `SecondQuote`, `MomentumParams`, `MomentumSignal`, `ReplayTrade`, `ReplaySummary`; functions `aggregate_second_quotes`, `momentum_signal`, `replay_momentum`, `summarize_replay`, and `select_candidate`.

- [ ] **Step 1: Write failing aggregation and feed-validity tests**

```python
def test_aggregate_uses_observed_executable_sides_and_rejects_crossed_quotes():
    rows = aggregate_second_quotes([
        quote("2026-08-12T10:00:00.100Z", 3500.0, 3500.1),
        quote("2026-08-12T10:00:00.900Z", 3500.1, 3500.2),
        quote("2026-08-12T10:00:01.100Z", 3500.3, 3500.2),
    ], tick_size=0.1, max_spread_ticks=4)
    assert rows[0].open_mid == 3500.05
    assert rows[0].close_bid == 3500.1
    assert rows[0].close_ask == 3500.2
    assert rows[0].usable
    assert not rows[1].usable
```

- [ ] **Step 2: Run the aggregation test and verify RED**

Run: `cd bot && .venv/bin/pytest -q tests/test_mgc_firehose.py::test_aggregate_uses_observed_executable_sides_and_rejects_crossed_quotes`

Expected: collection error because `aegis.mgc_firehose` does not exist.

- [ ] **Step 3: Implement immutable records and aggregation**

Create frozen dataclasses for normalized quote and one-second records. Group by UTC second, preserve first/last midpoint and executable bid/ask, track high/low midpoint, maximum spread, quote/trade counts, and mark unusable records rather than dropping them.

- [ ] **Step 4: Write failing no-lookahead signal tests**

```python
def test_long_breakout_uses_only_completed_window_and_enters_next_record():
    bars = rising_second_quotes([3500.0, 3500.1, 3500.2, 3500.3, 3500.6, 3500.7])
    params = MomentumParams(lookback_seconds=5, breakout_seconds=3, min_efficiency=0.65,
                            target_ticks=8, stop_ticks=6, max_hold_seconds=10, cooldown_seconds=1)
    signal = momentum_signal(bars, signal_index=4, params=params, tick_size=0.1)
    assert signal.side == "buy"
    assert signal.signal_index == 4
    assert signal.entry_index == 5
    assert signal.entry_price == bars[5].close_ask
```

- [ ] **Step 5: Run the signal test and verify RED**

Run: `cd bot && .venv/bin/pytest -q tests/test_mgc_firehose.py::test_long_breakout_uses_only_completed_window_and_enters_next_record`

Expected: FAIL because `momentum_signal` is absent.

- [ ] **Step 6: Implement the symmetric micro-momentum signal**

Calculate displacement and efficiency from completed midpoint records. Compare the signal record against the prior completed breakout window, set the next usable record as the executable entry, and produce target/stop prices from integer tick distances. Return no signal for gaps, unusable records, inadequate history, zero path length, or spread beyond the configured limit.

- [ ] **Step 7: Write failing replay-cost and stop-first tests**

```python
def test_replay_charges_fixed_and_tick_costs_and_resolves_ambiguous_bar_stop_first():
    summary = replay_momentum(ambiguous_path(), params=PARAMS, quantity=1,
                              multiplier=10, tick_size=0.1,
                              fixed_round_trip_usd=1.92, slippage_ticks=1)
    assert summary.trades == 1
    assert summary.results[0].exit_reason == "ambiguous_stop_first"
    assert summary.total_cost_usd == 2.92
    assert summary.net_pnl_usd < 0
```

- [ ] **Step 8: Implement deterministic replay and metrics**

Replay one position at a time using long exits against bid and short exits against ask. Resolve simultaneous stop/target crossings stop-first. Charge `$1.92` plus configured slippage ticks, record cooldowns, and calculate trades, trades/day, win rate, net dollars/trade, E[R], profit factor, maximum drawdown, start/end equity, costs, and halt reason.

- [ ] **Step 9: Write and implement the chronological selector test**

```python
def test_selector_rejects_high_frequency_candidate_with_negative_validation_expectancy():
    winner = select_candidate([
        candidate("spray", dev_ev=0.2, val_ev=-0.1, dev_pf=1.2, val_pf=0.9, trades_day=1200),
        candidate("gated", dev_ev=0.1, val_ev=0.08, dev_pf=1.1, val_pf=1.08, trades_day=300),
    ])
    assert winner.name == "gated"
```

Require development and validation expectancy above zero, PF above `1.05`, worst-session PF at least `0.90`, and drawdown below `5%`, then rank by the smaller expectancy and trades/day.

- [ ] **Step 10: Run Task 2 tests and verify GREEN**

Run: `cd bot && .venv/bin/pytest -q tests/test_mgc_firehose.py`

Expected: all pure strategy tests pass.

### Task 3: Shadow collector, search command, configs, and report

**Files:**
- Create: `bot/scripts/run_mgc_firehose.py`
- Create: `bot/scripts/tune_mgc_firehose.py`
- Create: `bot/config_ib_paper_mgc_shadow.yaml`
- Create: `bot/config_ib_paper_mgc_executable.yaml`
- Create: `bot/reports/MGC_FIREHOSE.md`
- Create: `bot/tests/test_mgc_runner.py`
- Modify: `bot/aegis/engines/ibkr.py`

**Interfaces:**
- Consumes: `IBKREngine.subscribe_quote(symbol)` and pure functions from Task 2.
- Produces: `reports/mgc_ticks.jsonl`, `reports/mgc_seconds.jsonl`, `reports/mgc_firehose_journal.jsonl`, `reports/mgc_firehose_state.json`, `reports/bot_heartbeat.json`, and the measured Markdown report.

- [ ] **Step 1: Write failing runner safety and serialization tests**

```python
def test_unpromoted_config_can_capture_but_cannot_send_orders():
    cfg = base_mgc_cfg(dry_run=False, paper_trading_enabled=True, paper_promoted=False)
    mode = execution_mode(cfg)
    assert mode.capture
    assert not mode.send_orders
    assert mode.gate_reason == "paper_promoted is false"


def test_quote_json_round_trip_preserves_contract_and_executable_sides(tmp_path):
    path = tmp_path / "ticks.jsonl"
    append_quote(path, QUOTE)
    assert load_quotes(path) == [QUOTE]
```

- [ ] **Step 2: Run runner tests and verify RED**

Run: `cd bot && .venv/bin/pytest -q tests/test_mgc_runner.py`

Expected: collection error because the runner helpers do not exist.

- [ ] **Step 3: Add one persistent IB market-data subscription**

Add `IBKREngine.subscribe_quote("MGC")` returning the qualified dated contract and its `reqMktData` ticker, plus `cancel_quote`. The runner calls `ib.sleep(0.1)` instead of opening repeated requests and serializes only changed quote states. Missing subscriptions or stale data update the heartbeat gate reason and never generate an order.

- [ ] **Step 4: Implement capture-only runner behavior**

The runner acquires the existing bot process lock, validates the paper port and exact quantity/multiplier/tick size, writes raw quote and one-second JSONL, and publishes heartbeat fields `symbol`, `local_symbol`, `contract_multiplier`, `tick_value_usd`, `feed_age_seconds`, `feed_usable`, `trades_today`, `modeled_costs_today`, `paper_promoted`, `gate_reason`, and `status`. On SIGTERM it cancels market data, removes the heartbeat, disconnects, and releases the lock.

- [ ] **Step 5: Implement promoted paper behavior without enabling it**

When and only when `dry_run: false`, `paper_trading_enabled: true`, and `paper_promoted: true`, evaluate the selected parameters, require one synchronized position/order view, run the multiplier-aware pre-trade cost gate, and submit one bracket. Apply limits of one position, 100 round trips/hour, `$250` daily realized loss, five consecutive losses, `$100` cost divergence, and session-end flatten. Both supplied configs keep `paper_promoted: false`; the shadow config additionally has `dry_run: true` and `paper_trading_enabled: false`.

- [ ] **Step 6: Implement deterministic search and promotion report**

`tune_mgc_firehose.py` loads `mgc_seconds.jsonl`, rejects fewer than five sessions or 250,000 usable records, evaluates the exact parameter grid from the specification, selects on sessions one through four, opens session five once, and writes all mandated metrics plus `paper_promoted: true/false` to `MGC_FIREHOSE.md`. It never edits the executable config automatically.

- [ ] **Step 7: Run Task 3 tests and one offline CLI smoke test**

Run: `cd bot && .venv/bin/pytest -q tests/test_mgc_runner.py tests/test_mgc_firehose.py`

Run: `cd bot && .venv/bin/python scripts/tune_mgc_firehose.py --config config_ib_paper_mgc_shadow.yaml`

Expected: tests pass; the search exits successfully with a report stating that the current dataset is insufficient and paper promotion is false.

### Task 4: Durable process selection, trustworthy UI/status, and shadow launch

**Files:**
- Modify: `bot/scripts/watchdog.py`
- Modify: `bot/scripts/aegis_paper.py`
- Modify: `bot/scripts/run_dashboard.py`
- Modify: `bot/dashboard/index.html`
- Modify: `bot/tests/test_process_control.py`
- Modify: `bot/tests/test_dashboard_order_state.py`
- Modify: `docs/IB_PAPER_SETUP.md`

**Interfaces:**
- Consumes: config `runner_kind: mgc_firehose` and MGC heartbeat/state files.
- Produces: LaunchAgent-owned MGC shadow process and UI/status fields that distinguish capture, gated, and order-sending modes.

- [ ] **Step 1: Write failing watchdog and status tests**

```python
def test_watchdog_selects_mgc_runner_from_config():
    specs = child_specs(ROOT, Path("/usr/bin/python3"), MGC_CONFIG)
    assert str(ROOT / "scripts" / "run_mgc_firehose.py") in specs[0].command


def test_status_surfaces_mgc_heartbeat_gate():
    status = heartbeat_status({"pid": 123, "ts": 195.0, "symbol": "MGC",
                               "local_symbol": "MGCV6", "gate_reason": "collecting sample"},
                              now=200.0, max_age=15.0)
    assert status["local_symbol"] == "MGCV6"
    assert status["gate_reason"] == "collecting sample"
```

- [ ] **Step 2: Run process tests and verify RED**

Run: `cd bot && .venv/bin/pytest -q tests/test_process_control.py tests/test_dashboard_order_state.py`

Expected: FAIL because watchdog always starts `run_broker_paper.py` and heartbeat status drops MGC fields.

- [ ] **Step 3: Implement runner selection and status propagation**

Load the config in `child_specs`; select `run_mgc_firehose.py` only for `runner_kind: mgc_firehose`, otherwise preserve the existing runner. Preserve the full normalized heartbeat in status and print the concrete contract, feed state, trades, costs, promotion state, and gate reason.

- [ ] **Step 4: Make dashboard marking contract-aware**

For FX retain `Forex`. For MGC qualify the same dated `Future` as the bot and compute futures open P&L using multiplier `10`. Add cards for local symbol, tick value, feed age/state, trades today, modeled costs today, promotion state, and gate reason. Continue building orders exclusively from fresh `reqAllOpenOrders` results.

- [ ] **Step 5: Run the focused and full offline suites**

Run: `cd bot && .venv/bin/pytest -q tests/test_process_control.py tests/test_dashboard_order_state.py`

Run: `cd bot && .venv/bin/pytest -q`

Expected: every test passes with no traceback or warning caused by the new code.

- [ ] **Step 6: Safely replace the running EURUSD process with MGC shadow capture**

Run: `cd bot && .venv/bin/python scripts/aegis_paper.py stop --config config_ib_paper_eurusd_hale_forced.yaml`

Verify: Gateway remains up, positions are zero, working orders are zero, and the LaunchAgent is unloaded.

Run: `cd bot && .venv/bin/python scripts/aegis_paper.py start --config config_ib_paper_mgc_shadow.yaml`

Verify with `status --json`, the dashboard API, heartbeat, logs, and growing capture files that the concrete dated MGC feed is usable, `paper_promoted` is false, zero MGC orders were submitted, and the dashboard is up at `http://127.0.0.1:8787/`.

- [ ] **Step 7: Record the initial measured state**

Update `bot/reports/MGC_FIREHOSE.md` with the exact start timestamp, contract, records captured, usable records, current trades/day result if any, costs, position/order counts, equity, and `halt reason: collecting five-session broker-native sample`. Do not invent E[R], PF, or drawdown before trades exist; label them unavailable.

