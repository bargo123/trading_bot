# All-Symbol Video-Style Paper Simulator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic, research-only paper simulator that applies a video-style fast-entry and scale-in hypothesis to every symbol supplied in a historical bar set, while recording costed returns and drawdown without placing broker orders.

**Architecture:** A pure simulator consumes completed OHLC bars grouped by symbol and produces virtual trade events plus aggregate metrics. The strategy uses a small initial risk unit, only adds after favorable movement, exits losers at a tight structural stop, and lets winners run to a larger R target or trailing protection; the simulator never imports MT5 execution code. A small CLI loads one CSV per symbol, runs the simulator, and writes JSON/CSV research artifacts.

**Tech Stack:** Python 3.12, dataclasses, pandas, pytest, JSON/CSV artifacts.

**Spec:** `docs/superpowers/specs/2026-08-24-safe-firehose-expansion-design.md` (research-only, measured costs, no lookahead, no fabricated metrics).

## Global Constraints

- The simulator is paper/research only and must expose `placed_orders: false` in every report.
- It must not import or call MT5, broker, OMS, order, or live-config execution paths.
- Bars are completed before evaluation; entry uses the next bar open and exits use only subsequent bar OHLC.
- Every result includes spread/slippage/commission assumptions and cannot claim guaranteed profitability.
- The simulator accepts all supplied symbols generically; it must not hardcode XAUUSD or FX-only behavior.
- Scaling is pyramiding after favorable movement, never adding to a losing position; loss and winner distributions are reported separately.

---

### Task 1: Pure all-symbol video-style simulator

**Files:**
- Create: `bot/aegis/research/video_style_paper.py`
- Create: `bot/tests/test_video_style_paper.py`

**Interfaces:**
- `VideoStyleConfig`: immutable parameters for `starting_equity`, `risk_per_trade`, `reward_to_risk`, `max_layers`, `scale_after_r`, `spread_cost`, `slippage_cost`, `commission_cost`, and `max_hold_bars`.
- `PaperTrade`: immutable virtual entry/exit record with symbol, side, layer, prices, quantity, gross/net P&L, R multiple, and exit reason.
- `VideoStyleResult`: immutable result containing `placed_orders`, trades, ending equity, max drawdown, wins, losses, and per-symbol summaries.
- `simulate_video_style(bars_by_symbol: Mapping[str, pandas.DataFrame], cfg: VideoStyleConfig) -> VideoStyleResult`.

- [x] **Step 1: Write failing tests**

  Add tests proving: all symbols are processed; a completed-bar breakout enters on the next bar; stop losses are small and targets are larger; a second layer occurs only after favorable movement; no layer is added while losing; costs reduce P&L; same-bar stop/target handling is deterministic; malformed/empty data fails closed; and the result always has `placed_orders is False`.

- [x] **Step 2: Run focused tests and verify failure**

  Run from `bot`:

  ```powershell
  ..\.venv\Scripts\python.exe -m pytest -q tests/test_video_style_paper.py
  ```

  Expected: collection or assertion failures because the simulator module does not yet exist.

- [x] **Step 3: Implement the pure simulator**

  Use only completed rows with `time`, `open`, `high`, `low`, and `close`. For each symbol, derive a minimal causal signal from the prior completed bar: long when the current completed close exceeds the prior high, short when it breaks the prior low. Enter at the next bar open. Set the initial stop at `0.5R` and target at `reward_to_risk * R`; define `R` from the signal bar range with a positive floor. Add a layer only when the next completed bar has moved at least `scale_after_r * R` favorably and the current virtual basket is not losing. Apply costs on entry and exit, close at stop before target when both are touched, close at target before time exit otherwise, and force-flat at the end of each symbol stream. Size the initial layer so the configured stop risks `risk_per_trade`; size later layers from the same fixed risk unit rather than multiplying risk.

- [x] **Step 4: Run focused tests and verify pass**

  Run the same focused pytest command and require all tests to pass.

### Task 2: Research CLI and artifacts

**Files:**
- Create: `bot/scripts/run_video_style_paper.py`
- Create: `bot/tests/test_run_video_style_paper.py`

**Interfaces:**
- CLI arguments: `--bars-dir`, `--output-dir`, `--starting-equity`, `--risk-per-trade`, `--reward-to-risk`, `--max-layers`, `--spread-cost`, `--slippage-cost`, `--commission-cost`, and `--max-hold-bars`.
- Input: CSV files in `--bars-dir`; filename stem is normalized to the symbol and each CSV must contain `time,open,high,low,close`.
- Outputs: `video_style_paper_result.json`, `video_style_paper_trades.csv`, and `video_style_paper_summary.md`; every output states `placed_orders: false`.

- [x] **Step 1: Write failing CLI tests**

  Use `tmp_path` with two symbol CSVs and assert the CLI returns zero, writes all three artifacts, includes both symbols, and reports `placed_orders: false`. Add a malformed CSV test that returns nonzero without producing fabricated trades.

- [x] **Step 2: Run focused CLI tests and verify failure**

  ```powershell
  ..\.venv\Scripts\python.exe -m pytest -q tests/test_run_video_style_paper.py
  ```

- [x] **Step 3: Implement the CLI**

  Load only CSV files from the requested directory, validate required columns, normalize timestamps, call `simulate_video_style`, and serialize the result. Do not read YAML live configs or call broker code. Exit nonzero on malformed input and print the exception without writing a success report.

- [x] **Step 4: Run focused CLI tests and verify pass**

  Run the same command and require all tests to pass.

### Task 3: Verification and handoff

**Files:**
- Modify: `docs/superpowers/plans/2026-08-25-all-symbol-paper-simulator.md` (check off completed steps only)

- [x] **Step 1: Run focused simulator and CLI tests**

  ```powershell
  ..\.venv\Scripts\python.exe -m pytest -q tests/test_video_style_paper.py tests/test_run_video_style_paper.py
  ```

- [x] **Step 2: Run static safety checks**

  Confirm the new module and script contain no imports or calls for `MetaTrader`, `mt5`, `order_send`, `send_order`, `OMS`, or `allow_live`, and confirm `placed_orders` is always false in the generated result.

- [x] **Step 3: Report honestly**

  Report test counts and simulator outputs. Do not run or restart the existing MT5 stack for this research simulator, and do not commit or push unless separately requested.

### Task 4: Read-only MT5 live feed mode

**Files:**
- Modify: `bot/scripts/run_video_style_paper.py`
- Modify: `bot/tests/test_run_video_style_paper.py`

**Interfaces:**
- `collect_mt5_bars(engine, symbols, timeframe, lookback_days) -> dict[str, pandas.DataFrame]` fetches completed bar data through the existing engine interface only.
- CLI options: `--mt5-config`, `--timeframe`, `--lookback-days`, `--interval-s`, and `--once`.

- [x] **Step 1: Write failing read-only connector tests**

  Use a fake engine whose `connect_readonly()` and `bars()` are observable and whose order methods raise if called; assert all supplied symbols are fetched and converted to the simulator frame.

- [x] **Step 2: Run the connector tests and verify failure**

  ```powershell
  ..\.venv\Scripts\python.exe -m pytest -q tests/test_run_video_style_paper.py
  ```

- [x] **Step 3: Implement one-shot and looping MT5 read-only mode**

  Load the requested YAML read-only, instantiate `MT5Engine`, call `connect_readonly()`, fetch bars, run the virtual simulator, and write the same artifacts. `--once` exits after one fetch; without it, poll at the requested interval. Never call any mutation method or import the broker runner.

- [x] **Step 4: Run focused tests and full verification**

  Run the focused tests, static safety checks, and the full pytest suite once. Do not start the live mode automatically; hand off the exact command for user approval.
