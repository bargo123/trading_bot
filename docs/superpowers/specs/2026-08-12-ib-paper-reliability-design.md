# IBKR Paper Reliability and Order Hygiene Design

Date: 2026-08-12

## Objective

Make the existing IBKR EURUSD paper stack reliable and operationally safe without rewriting the broker abstraction. One command must start, stop, inspect, or flatten the paper stack. The default configuration must not spray orders, and no control action may operate on a live IB port.

## Observed state and root causes

- IB Gateway is available on the configured paper port, while the bot, dashboard, and watchdog are stopped. The paper account is flat with no open orders.
- The latest bot and dashboard logs end without an application traceback. No LaunchAgent is installed, so the detached watchdog itself has no durable owner.
- The current watchdog uses `pgrep` and detached children. This permits races, duplicate starts, and children that outlive or lose their supervisor.
- The IB order engine leaves the parent TIF to an IB preset, submits children after the parent has reported cancellation, and returns `ok=True` regardless of terminal parent status. The log contains repeated error 10349 events.
- The dashboard refreshes all orders but renders the broader `openTrades()` cache, allowing stale cross-client orders to remain visible.
- The engine falls back from `accountValues()` to `accountSummary()` and tries to cancel that subscription with a method not provided by the installed `ib_insync`. Repeated fallback calls can cause error 322.

## Chosen architecture

Use one macOS LaunchAgent to run `watchdog.py`. The watchdog owns the bot and dashboard `Popen` children, records exit codes, restarts failed children, and terminates both on shutdown. Launchd owns and restarts the watchdog. A file lock in each long-running process prevents manual duplicate instances.

Add `scripts/aegis_paper.py` as the single operator command:

- `start`: create/load the user LaunchAgent and start the supervised stack.
- `stop`: cancel working paper orders, flatten configured paper positions, unload the LaunchAgent, and verify the stack stopped. A safety flag permits process-only stop when Gateway is unavailable.
- `restart`: perform the safe stop and start sequence.
- `status`: read-only report of Gateway reachability, LaunchAgent state, heartbeat freshness, dashboard reachability, paper account equity, positions, truly working orders, and last fill.
- `flatten`: paper-only cancel-all, flatten, cancel-all, then verify no position or working order remains.

No command writes credentials. Runtime plist and lock files contain only local paths, PIDs, and configuration paths.

## Order lifecycle

Create one shared definition of a working order. `PendingSubmit`, `ApiPending`, `PreSubmitted`, and `Submitted` are working. `PendingCancel` is shown separately as cancelling and is not counted as working. `Filled`, `Cancelled`, `ApiCancelled`, and `Inactive` are terminal.

`IBKREngine.place_order()` will:

1. Set the configured TIF explicitly on parent and children.
2. Allocate parent/child IDs before submission.
3. Submit the complete transmit chain without an intermediate parent sleep.
4. Wait for parent acknowledgement.
5. Return success only for acknowledged active or filled status.
6. Cancel the bracket and return failure if the parent becomes terminal or acknowledgement times out.

`cancel_all_orders()` will issue IB global cancel, repeatedly refresh `reqAllOpenOrders()`, and return success only when no working or cancelling orders remain. Dashboard and status will render the list returned by the latest refresh, deduplicated by permanent ID or client/order ID, rather than the persistent `openTrades()` cache.

Flatten is ordered: cancel all orders, close positions with unbracketed market orders, wait for fills, cancel again, and verify convergence. It refuses live ports even if `allow_live` is accidentally true.

## Account and process reliability

Account polling uses cached `accountValues()` only. If the required value is not available after connection warm-up, the caller reports an unavailable account snapshot instead of opening repeated summary subscriptions.

The supervisor uses child handles rather than process-name matching. It logs start time, PID, exit code, and restart. SIGTERM triggers bounded graceful termination followed by forced termination only if a child ignores the deadline.

The checked-in paper config will default to:

- `allow_live: false`
- Gateway paper port 4002
- `paper_trading_enabled: false`
- `dry_run: true`
- `firehose_every_bar: false`
- no forced maximum-hold churn

Starting the services therefore starts observation and the dashboard, not order spray.

## Cost guard and strategy direction

Before any paper order is eligible, the runner estimates gross target dollars for the USD-quoted pair and subtracts configured round-trip commission plus spread/slippage. It skips orders below a configurable minimum expected net amount. It never increases size automatically to make a bad target pass.

The recommended research path is Option A only after real tape movement appears: breakout/pullback signals plus the cost gate and strict activity limits. Every-bar mode remains an explicit demonstration switch and is disabled by default. Option B, a slower tuned strategy, remains the fallback when the 5-second signal cannot pass frozen, costed paper validation. Neither path is described as an edge until measured fills show positive net expectancy.

## Testing and acceptance

- Pure tests prove working/cancelling/terminal status classification and cross-client deduplication.
- Engine tests prove account polling never calls `accountSummary`, brackets set explicit TIF/transmit/parent IDs, rejected parents return failure, and global cancel waits for convergence.
- Control tests prove live-port mutations are refused, the LaunchAgent payload points to the repository supervisor, cost-negative targets are skipped, and status aggregation handles unavailable Gateway/dashboard state.
- Existing engine and strategy tests continue to pass.
- Read-only live verification may query paper account state. Implementation verification must not start the supervisor, enable paper trading, place an order, cancel an order, or flatten an already-flat account.

## Out of scope

- Live trading.
- Full MT5 implementation.
- Claiming or manufacturing a profitable firehose strategy.
- Replacing the dashboard UI or the entire broker abstraction.
