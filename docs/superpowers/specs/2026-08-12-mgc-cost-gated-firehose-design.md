# MGC Cost-Gated Firehose Design

## Objective

Build and measure a paper-only, one-contract Micro Gold (`MGC`) scalper for IB Gateway port `4002`. The research target is 1,000 or more completed round trips per trading day, but order frequency is subordinate to positive expectancy after commissions, exchange fees, bid/ask spread, and slippage. The system must report the frequency it actually earns; it must never manufacture trades merely to reach the target or describe a historical win rate as guaranteed.

The current EURUSD forced diagnostic is replaced only after the MGC contract, multiplier, cost model, and process controls pass automated tests. Live ports remain blocked and `allow_live` remains `false`.

## Measured constraints

- IB qualified the continuous Micro Gold future as `MGCV6` on 2026-08-12 with multiplier `10` and minimum tick `0.1`, so one MGC tick is `$1.00` per contract.
- The executable order must use a dated `FUT` contract. `CONTFUT` is allowed only for research/history and must never be submitted as an order contract.
- The first 1,000 monthly MGC contract executions currently cost about `$0.25` IB commission, `$0.70` COMEX fee, and `$0.01` regulatory fee per side. The initial round-trip fixed-cost model is therefore `$1.92`, before spread and slippage.
- A one-tick spread adds `$1.00` per round trip. One thousand round trips therefore require at least 2,000 contract executions and approximately `$2,920` per day before additional slippage at the initial tier.
- A real `$100` account cannot safely fund one MGC futures contract. This design is restricted to the existing approximately `$250,000` IB paper account and does not claim that its results transfer to a `$100` live account.
- The existing `GC=F` 1-hour results do not validate sub-minute MGC execution. There is no local MGC tick dataset, so high-frequency promotion requires broker-native capture and replay.

## Approaches considered

1. **Cost-gated, tick-driven MGC momentum — selected.** Capture broker-native bid, ask, last, and sizes; form deterministic one-second records; replay candidate momentum rules with executable-side pricing; and paper-trade only a candidate that passes walk-forward cost and drawdown gates. This can pursue high frequency without confusing activity with edge.
2. **Forced 1,000-round-trip paper spray — rejected.** It can guarantee UI activity but cannot guarantee wins and has a known minimum daily friction near `$2,920`. The previous forced EURUSD firehose already demonstrated that this behavior destroys expectancy.
3. **Multi-instrument futures basket — deferred.** A basket can create more independent opportunities, but it expands contract, margin, fee, and roll risk before the single-instrument execution path is trustworthy.

## Components and boundaries

### Concrete futures contract resolver

`IBKREngine` gains an explicit Micro Gold path. Configuration supplies `symbol: MGC`, `ib_futures_exchange: COMEX`, and `ib_futures_expiry: "202610"`. The engine qualifies a dated `Future`, verifies `secType == "FUT"`, symbol `MGC`, exchange `COMEX`, currency `USD`, multiplier `10`, and minimum tick `0.1`, then caches it.

The engine refuses to place an order when the resolved contract is continuous, expired, missing the configured expiry, has a multiplier other than `10`, or is inside the configured ten-calendar-day roll guard. Historical data may use a continuous contract only when an explicit `historical_continuous_future: true` flag is set.

### Market-data capture

A dedicated collector subscribes once to IB market data instead of repeatedly requesting historical bars. It writes timestamped bid, ask, bid size, ask size, last, last size, and contract identity to append-only JSONL. It also emits one-second records containing first/last midpoint, high/low midpoint, last trade, observed maximum spread, quote count, and trade count.

Records with a missing bid or ask, crossed market, spread above four ticks, stale quote age above two seconds, or contract mismatch are marked unusable. Disconnects stop signal evaluation. Reconnection must requalify the dated contract and resubscribe before data becomes usable again.

### Primary signal: micro-momentum breakout

The sole promoted signal is a directional micro-momentum breakout. It operates only on completed one-second records and never uses future records.

- Candidate lookbacks are `5`, `10`, `20`, and `30` seconds.
- Candidate breakout windows are `3`, `5`, `10`, and `20` seconds.
- Directional efficiency is absolute net midpoint displacement divided by the sum of absolute one-second midpoint changes. Candidate minimums are `0.35`, `0.50`, and `0.65`.
- A long requires positive lookback displacement, efficiency above the candidate minimum, and current ask above the maximum ask of the completed breakout window. A short is symmetric using bid and the completed-window minimum bid.
- Entry is charged at the next observed ask for a long and next observed bid for a short. There is no same-record fill.
- Candidate targets are `5`, `8`, `12`, and `16` ticks. Candidate stops are `4`, `6`, `8`, and `10` ticks. Candidate maximum holds are `5`, `10`, `20`, and `30` seconds.
- Only one position may exist. There is no pyramiding, averaging down, martingale sizing, or overlapping bracket.
- After an exit, the candidate cooldowns are `0`, `1`, `2`, and `5` seconds. The same completed record cannot close one trade and open another.

Before every paper order, the target must clear the actual observed spread plus configured slippage and the fixed round-trip fee by at least `$1.00`. The cost calculation is `quantity × multiplier × price_distance`; the existing FX-only cost formula must not be reused without the multiplier.

## Replay and selection protocol

The collector runs in shadow mode first. A minimum usable dataset is five complete MGC trading sessions and at least 250,000 one-second records. Sessions are kept in chronological order: first three development, fourth validation, fifth frozen holdout. Parameter selection uses development and validation only; holdout is opened once for the selected candidate.

Replay uses executable-side bid/ask prices. If both stop and target can be crossed between usable records, the trade is counted stop-first. Every fill includes `$1.92` fixed round-trip fees plus the recorded entry/exit spread and stress slippage of `0`, `1`, and `2` ticks per round trip. The primary result uses one tick of slippage.

Selection first requires positive net expectancy and profit factor above `1.05` in both development and validation, no session with negative profit factor below `0.90`, and maximum drawdown below `5%` of the paper account. Among passing candidates, rank by the smaller of development and validation expectancy, then trades per day. Frequency never overrides a failed expectancy gate.

Promotion to order-sending paper mode requires on frozen holdout:

- at least 500 completed trades and at least three trades per hour during eligible market hours;
- positive net dollars per trade after the primary cost model;
- profit factor above `1.05`;
- maximum drawdown below `5%`;
- positive performance under two-tick slippage stress;
- no individual hour responsible for more than `35%` of positive P&L;
- no bankruptcy, risk halt, unresolved order, duplicate bracket, or orphan order.

The requested 1,000 trades/day is reported as a target, not a promotion requirement. A candidate producing fewer trades remains valid if it passes every expectancy gate; a candidate producing 1,000 trades but losing money is rejected.

## Paper execution and risk controls

The executable configuration is separate from every EURUSD configuration and uses `order_quantity: 1`, `contract_multiplier: 10`, `tick_size: 0.1`, `paper_trading_enabled: true`, `dry_run: false`, `allow_live: false`, and port `4002`.

Every entry uses a broker bracket with one parent and one stop/target OCA pair. The runner waits for the parent acknowledgement, verifies both protective children, and refuses another entry while any MGC position or working order exists. Any rejection, disconnect, stale quote, missing child, contract-roll warning, or order-state timeout cancels all MGC orders, flattens MGC, and disables new entries until a healthy synchronization cycle completes.

Hard paper limits are one contract, one open position, no overnight position, maximum 100 completed round trips per hour, maximum `$250` realized daily loss, maximum five consecutive losses, and maximum `$100` unexpected cost/slippage divergence from the model. These safety limits may prevent 1,000 daily trades and cannot be relaxed automatically by tuning.

## Process and UI behavior

The existing LaunchAgent remains the single process owner. Switching instruments uses the existing stop path with cancel-all and flatten verification, changes the LaunchAgent config atomically, and starts exactly one runner. The dashboard remains read-only on client ID `71` and must display the concrete contract local symbol, multiplier, tick value, signal mode, usable/stale feed state, completed trades today, modeled costs today, realized P&L, and the reason entries are gated.

The single status command reports Gateway reachability, runner/dashboard/watchdog state, concrete MGC contract, position, truly working orders, last fill, equity, feed age, trades today, costs today, promotion state, and halt reason.

## Required outputs

- Futures-aware contract resolution and cost calculations with offline unit tests.
- MGC quote/one-second data collector and deterministic replay tests.
- Micro-momentum candidate search with chronological selection and one-time holdout.
- Separate shadow and executable MGC paper configurations.
- A report containing sample window, records, trades, trades/day, win rate, net dollars/trade, E[R], profit factor, maximum drawdown, start/end equity, modeled costs, halt reason, and promotion result.
- Dashboard and status visibility for the MGC contract and cost/frequency gates.

## Non-goals

- No live trading or live-port support.
- No claim of 100% future win rate, guaranteed daily income, or conversion of `$100` into a futures-capable account.
- No order generation solely to satisfy the 1,000-trade target.
- No use of Yahoo `GC=F` OHLC as proof of MGC tick execution quality.
- No MT5 implementation and no unrelated engine rewrite.

