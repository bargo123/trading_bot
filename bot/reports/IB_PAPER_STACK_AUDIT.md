# IBKR Paper Stack Audit

Date: 2026-08-12

Scope: IB Gateway paper 4002, EURUSD runner, dashboard, order lifecycle, and local process control

## Outcome

The stack now defaults to observation-only and has one operator command:

```bash
cd bot
python3 scripts/aegis_paper.py status
python3 scripts/aegis_paper.py start
python3 scripts/aegis_paper.py stop
python3 scripts/aegis_paper.py restart
python3 scripts/aegis_paper.py cancel-all
python3 scripts/aegis_paper.py flatten
```

No service was started and no broker mutation was performed during implementation or verification.

## Diagnosis

### Process reliability

- There was no user LaunchAgent. The detached watchdog had no durable owner, so terminal/session death also killed supervision.
- The old watchdog used `pgrep` and detached children. This allowed duplicate/manual starts and could not prove which processes it owned.
- `reports/bot_supervise.log` contains `(eval):10: command not found: setsid`, and the last bot/dashboard logs ended without an application traceback.
- The journal contains repeated adjacent `start` events, consistent with duplicate/repeated launches.

### Orders and dashboard

- The parent bracket order inherited IB's DAY preset while children used GTC. `ib_paper_run.log` contains 154 Error 10349 matches.
- The runner could report `ok=True` after a parent reached `Cancelled`, then submit children after an intermediate sleep.
- Max-hold cleanup called a private IB object, swallowed cancellation errors, and submitted a close without verifying order or position convergence.
- The dashboard called `reqAllOpenOrders()` but discarded its returned list and displayed `openTrades()` cache, allowing stale cross-client orders to remain visible.
- `PendingCancel` was counted as open/working even though it should be shown separately as cancellation in progress.

### Account polling

- The engine fell back to `accountSummary()` and tried `cancelAccountSummary(9001)`. The installed `ib_insync` object has no such cancellation method, so repeated fallback polling could stack subscriptions and cause Error 322.

### Strategy/cost mismatch

- Forced `firehose_every_bar` plus 45-second max-hold churn generated activity but not an edge. The journal records 34 entry-order events and 15 max-hold flatten events across mixed experiments; this is not a clean performance sample.
- A paper-account reference moved from $250,602.56 in the journal to $250,526.06 in the verified live snapshot, a $76.50 decline across those mixed experiments.
- At 20,000 EUR, a 3-pip target is about $6 gross. Configured 0.7 bps round-trip spread/slippage is about $3.23 at EURUSD 1.1543, and commission is about $4 round trip. Modeled target net is therefore **-$1.23 before adverse fill variation**. Size cannot repair negative per-dollar expectancy.

## Implemented controls

- A shared order-state module defines working, cancelling, and terminal states and deduplicates cross-client orders by permanent ID or client/order ID.
- IB brackets allocate all IDs first, set explicit GTC on every leg, submit one atomic transmit chain, wait for acknowledgement, and fail/clean up on rejection or timeout.
- `cancel_all_orders()` performs global cancel and refreshes until neither working nor cancelling orders remain.
- `flatten_positions()` refuses non-paper ports and performs cancel → close → cancel → verify.
- Account polling uses `accountValues()` only and never opens a summary subscription.
- Runner and dashboard use non-blocking process locks to prevent duplicate instances.
- The dashboard renders only the latest `reqAllOpenOrders()` result; cancelling orders are separate from working orders.
- One macOS LaunchAgent owns the watchdog. The watchdog owns exact bot/dashboard `Popen` handles, records PIDs and exit codes, restarts failed children, and terminates them on shutdown.
- The config now defaults to `paper_trading_enabled: false`, `dry_run: true`, `firehose_every_bar: false`, and `max_hold_seconds: 0`.
- Real paper execution requires both explicit gates on a known paper port. The runner skips a target that cannot clear modeled round-trip costs and never increases quantity to force it through.

## Verification

Fresh offline verification:

- All 12 `bot/tests/test_*.py` scripts exited 0.
- Python compilation of `bot/aegis`, `bot/scripts`, and `bot/tests` exited 0.
- `git diff --check` and the changed-file trailing-whitespace scan exited 0.

Fresh read-only IB verification through `python3 scripts/aegis_paper.py status --json`:

| Item | Result |
|---|---:|
| Gateway paper 4002 | Up |
| Broker connection | Connected, paper |
| Equity | $250,526.06 |
| Available funds | $249,923.50 |
| Positions | 0 |
| Working orders | 0 |
| Cancelling orders | 0 |
| Bot | Stopped; heartbeat stale |
| Dashboard | Stopped |
| LaunchAgent | Not loaded |
| Last fill | 20,000 EURUSD sell at 1.15428; $2 side commission |

## Primary strategy path: Option A, gated tape-active firehose research

Option A is the only path aligned with the requested frequency, but it is **not an activated edge**. Keep every-bar spray disabled. Use the existing real firehose breakout/pullback signal only when the 5-second tape has enough movement to create a target beyond all round-trip costs.

Promotion protocol:

1. Run observation-only first and record actual bid/ask, signal time, target distance, and cost-gate decision.
2. Permit a bounded paper trial only for signals that clear commission, spread, slippage, and the configured minimum net target at fixed quantity.
3. Collect at least 200 closed, real paper bracket outcomes across multiple sessions. Forced time exits count as exits, not wins.
4. Report net trades, trades/day, win rate, net E[R], profit factor, max drawdown, start/end equity, and halt reason.
5. Continue only if out-of-sample net expectancy remains positive and PF is above 1 after all costs. A stricter research promotion threshold such as PF > 1.2 is preferable; it is a gate, not a promise.
6. If the tape-active mode cannot meet that gate, reject firehose execution and move to Option B: the slower `hw_range`/gold-style research path using a separately costed broker/config trial.

The current evidence rejects forced every-bar execution. It does not establish positive expectancy for the filtered firehose yet.

## Remaining limitations

- The LaunchAgent code is tested but intentionally not installed or started by this audit; the user requested that the stack remain stopped.
- Broker cancel/flatten convergence is covered by offline fakes but was not exercised against the live paper account because the verified account was already flat and broker mutation was outside verification scope.
- IB paper fills and commissions can differ from live execution. A paper pass is necessary but not sufficient for live deployment.
- MT5 remains a stub.
