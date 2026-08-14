# Aegis Firehose and Autonomous Research Design

**Date:** 2026-08-14

**Status:** Proposed for user review

## Purpose

Build a fast, selective MT5 demo trading system and a persistent autonomous
research loop that continually searches for lower loss frequency without
fabricating results, using future data, or promoting negative-expectancy
strategies.

The research aspiration is a loss rate at or below 2% and ultimately a 100%
win-rate experiment. These are research objectives, not promises or shortcuts.
No candidate may achieve them by accepting rare catastrophic losses, ignoring
costs, reducing the sample to a handful of trades, or leaking future data.

## Current-State Findings That Drive the Design

The active demo runner has useful broker connectivity, completed-bar handling,
bid/ask access, order logging, spread checks, broker-native stops and latency
telemetry. These pieces should be retained.

The active strategy itself is unsafe and unsupported: it fires from every
eligible M1 close based primarily on the EMA20 side, uses a fixed 0.01 lot,
configures a 1-pip target against a 30-pip stop, permits correlated stacking,
disables daily and total drawdown halts, and has produced strongly negative
expectancy. The optimizer may promote a result that is merely less negative,
reads short digest snippets instead of the full book library, and lacks a
complete immutable experiment registry.

The existing `.cursor/rules/core-strategy-v1.mdc` freezes this losing geometry.
The approved design supersedes that rule. The old implementation remains a
reproducible legacy baseline, but it is not protected from replacement after a
challenger passes the gates in this document.

The repository has extensive staged, unstaged and untracked user work. All
implementation must preserve it, work in isolation where possible, and avoid
broad cleanup or destructive Git operations.

## Safety Boundary

1. Development and historical testing occur separately from the running demo
   process.
2. No second live runner may be started against the same account.
3. No code path may set `allow_live: true` or silently target real money.
4. Existing demo positions are not flattened merely to deploy code.
5. A demo promotion waits until the account is flat, writes an atomic config and
   version checkpoint, then performs a controlled restart.
6. Real-money promotion is outside this design and always requires a later,
   explicit user decision.
7. Missing external data is reported as a capability gap. It is never invented.

## Architecture

### 1. Data plane

Create a versioned research data layer that records the information the broker
actually supplies:

- Bid/ask ticks with broker symbol, UTC timestamp, millisecond timestamp,
  sequence/order within the captured stream, bid, ask, last, tick volume and
  flags.
- Canonical completed bars at M1, M5, M15, M30, H1, H4 and D1, derived without
  look-ahead and carrying broker-time, UTC and session identifiers.
- Broker capability and contract snapshots: digits, point, pip, tick size,
  tick value, contract size, minimum/maximum/step volume, minimum stop distance,
  freeze level, margin mode and available depth-of-market support.
- Execution facts: request time, quote used, acknowledgment, rejection, partial
  or complete fill, fill price, cancel state, spread, commission, swap, slippage
  and tick-to-order latency.
- Rolling cost distributions by symbol, session and volatility regime.
- Tick-derived volume-at-price and time-at-price profiles. Broker tick volume is
  explicitly labeled as a broker-specific proxy, not centralized FX volume.

All stored datasets receive a content fingerprint and schema version. Research
jobs record the exact fingerprint they used.

Optional providers are capability-gated:

- MT5 depth of market is used only when the broker exposes it. Retail MT5 depth
  does not imply exchange queue position or genuine maker fill priority.
- News/economic calendar, futures volume/open interest/COT, yields, equities,
  commodities, sectors and sentiment require a named external source and its
  credentials or public interface.
- Strategies depending on unavailable data remain disabled and report the
  missing capability.

### 2. Selective firehose strategy plane

"Firehose" means continuous fast observation, not an order on every bar. The
engine scans all configured symbols and each completed bar/tick event, then
passes opportunities through independently testable stages:

1. Data and cost health: reject stale, future-dated, crossed, abnormally wide or
   incomplete quotes.
2. Portfolio health: reject insufficient margin, excessive order rate,
   duplicate exposure or correlated currency concentration.
3. Multi-timeframe state: construct direction and structure from genuine M5,
   M15, M30, H1, H4 and D1 data; use M1 mainly as the execution layer.
4. Regime: classify trend, range, breakout/transition, event shock and no-trade
   noise.
5. Setup: invoke only strategies compatible with the detected regime and
   available data.
6. Confluence: require multiple independent, predeclared reasons. Correlated
   versions of the same indicator count as one reason.
7. Payoff and cost: require positive modeled net expectancy and a target/stop
   profile that does not hide rare catastrophic losses.
8. Risk and execution: size from equity and stop distance, then submit through
   the order-management system.

The legacy EMA-side firehose remains available only as a named baseline for
comparison. It is not the default champion merely because it currently runs.

### 3. Source-faithful strategy modules

Book-derived logic is implemented as separate research modules with a provenance
record rather than blended behind author names:

- Coulling VPA: relative tick-volume proxy plus bar spread, close location,
  preceding context, congestion, tests, breakout state and volume-at-price.
- Brooks ranges: completed 5-minute sequence, range location, signal bar,
  entry/follow-through, failed break, structural invalidation and a positive
  cost-adjusted trader equation.
- Damir structure: H4 value/structure context with M15/M30 rejection and retest;
  no claim that a rolling M1 range percentile is the author's method.
- Steidlmayer profile: 30-minute TPO/time-at-price, initial balance, value area,
  excess, range extension and day type. Order-flow extensions require the
  relevant feed.
- Multi-timeframe trend/range modules from Ponsi, Elder and Grimes are encoded
  with real resampled timeframes, not same-row EMA aliases.
- Formal pattern and transformed-chart modules are independently tested before
  use; daily-stock statistics are never imported as FX M1 probabilities.

`jansen_score` and `harris_jump` are renamed as local heuristics unless replaced
by faithful implementations. A genuine Jansen-style ML candidate requires a
point-in-time feature set, train/validation/test separation, purged walk-forward
evaluation, model serialization and probability calibration. Harris supplies
microstructure and cost constraints, not a named one-bar signal.

Conflicting author methods stay configurable and are compared as separate
experiments. The live trading loop does not read entire books on each tick.

### 4. Full-library knowledge system

Build an offline, persistent knowledge index from every file under
`docs/trading/books/`:

- one immutable source record per file, including hash, title, author, chapter
  headings and duplicate/placeholder status;
- structured claims for required data, timeframe, setup, entry, exit, risk,
  warnings and evidence quality;
- explicit author disagreements and data-capability requirements;
- provenance links from each experiment and strategy module back to the exact
  sources used.

The two Tendler files are recorded as duplicate extracts, and
`market-structure.md`/`sample-author.md` are recorded as placeholders. Digests
may aid navigation but cannot be the authoritative evidence source.

The optimizer retrieves only relevant indexed passages for a hypothesis. This
uses the complete library without repeatedly loading millions of words into
every cycle.

### 5. Risk and execution control

Replace cosmetic risk settings with enforced controls:

- Position units/lots derive from current equity, entry, structural stop and
  broker contract metadata. The live runner must call the same tested sizing
  interface as the simulator.
- Enforce configurable per-trade risk, total open risk, symbol exposure,
  currency-factor exposure, correlated-basket risk, gross notional, used/free
  margin, maximum positions and order rate.
- Enable persistent daily-loss, total-drawdown, consecutive-loss and execution-
  failure halts. A restart cannot reset the loss budget.
- Block stacking into losing positions. Pyramiding is a separate module that may
  add only to winners while aggregate worst-case risk stays within budget.
- Reject recovery sizing, Martingale and uncapped DCA.
- Future-dated quote timestamps are errors, not age zero. Clock skew has a small
  explicit tolerance and generates telemetry.
- Reconcile broker-native SL/TP closures and all deal events back into internal
  position, trade and experiment state.
- Repeated insufficient-margin rejections trigger a halt and diagnosis rather
  than continued order spam.

### 6. Persistent experiment and optimizer system

Replace ad hoc JSON/digest memory with an append-only experiment registry backed
by SQLite and exportable JSONL. Each experiment records:

- immutable experiment ID and parent/champion ID;
- hypothesis, book provenance and creator type (parameter search, generated
  algorithm or manual change);
- code revision/diff hash, configuration hash, feature schema and dataset
  fingerprints;
- all searched parameters and total family/search count;
- train, validation, walk-forward, untouched holdout, stress and demo results;
- costs, fill assumptions, random seed and environment versions;
- rejection/promotion reason and similarity fingerprint;
- artifacts and checkpoint paths.

The registry prevents exact and materially equivalent failed experiments from
being rerun unless a new dataset, cost model or documented reason invalidates the
old result. The current champion is a pointer to an immutable accepted
experiment, never an overwritten anonymous YAML file.

The optimizer loop performs:

1. ingest latest MT5 deals, order failures, positions, heartbeat and execution
   telemetry;
2. attribute wins, losses and rejects to the exact strategy/configuration;
3. cluster failure modes by symbol, session, regime, setup and execution cause;
4. select one falsifiable hypothesis using full-library provenance;
5. generate a bounded parameter or algorithm candidate;
6. run unit/invariant tests and deterministic replay;
7. run walk-forward and untouched holdout evaluation after realistic costs;
8. apply multiple-search correction and Monte Carlo/bootstrap stress;
9. reject, quarantine or promote to shadow/demo incubation;
10. monitor demo-versus-model divergence and automatically roll back a degraded
    demo champion.

Code-generating experiments occur in isolated branches/worktrees. Generated
code cannot self-promote merely because it compiles; it passes the same review
and evidence pipeline as handwritten code.

### 7. Promotion objective and gates

Loss frequency is minimized subject to survival and expectancy constraints. A
candidate is never promoted solely for a higher win rate.

Hard gates include:

- net expectancy greater than zero on every required holdout aggregate;
- profit factor greater than 1 after all modeled costs;
- no single loss or small group of losses dominates total historical profit;
- minimum sample size and regime coverage configured before viewing holdout;
- drawdown, tail loss, margin use and correlation within fixed limits;
- no look-ahead, overlapping-label leakage, same-bar fictional fill or changed
  holdout after seeing results;
- challenger beats the champion on the predeclared multi-objective score and
  survives statistical/search-bias correction;
- demo incubation remains within configured confidence bounds for enough trades
  and elapsed market regimes.

The research dashboard reports observed win rate, its confidence interval, net
expectancy, profit factor, average win/loss, tail loss, drawdown and opportunity
count together. An observed 98% or 100% rate is labeled experimental until it
survives these gates.

### 8. Cursor workflow and memory

Update project rules and prompts so Cursor/Codex agents:

- begin from the experiment registry and current champion rather than chat
  memory;
- query full-book indexed evidence and attach exact provenance;
- state one falsifiable hypothesis per experiment;
- never invent performance, silently modify holdout data or promote a negative
  candidate;
- preserve user changes and use isolated worktrees for generated algorithms;
- write tests before implementation and record every result, including failures;
- distinguish unavailable data, local heuristics and faithful book methods;
- produce a structured candidate manifest that the deterministic Python
  validator can accept or reject;
- never place trades directly from an unattended language-model response.

The deterministic optimizer, not the chat session, owns scheduling, locking,
testing, promotion and rollback. Cursor may propose code and hypotheses; Python
enforces the safety and evidence gates.

## Error Handling and Recovery

- Every ingest cycle is idempotent and checkpoints its last processed broker
  deal/order ID.
- Partial/corrupt data files are quarantined; the previous valid snapshot stays
  active.
- Optimizer and runner use separate locks and cannot launch duplicate processes.
- Atomic file/database writes and versioned migrations protect against power
  loss.
- Failed tests, data-quality checks, broker capability loss, stale heartbeat,
  clock skew, margin rejection floods or demo/model divergence block promotion
  and create a durable incident record.
- Rollback restores the prior immutable champion and configuration. It never
  deletes the failed experiment because failure memory is required.

## Testing Strategy

- Unit tests: tick/bar ordering, multi-timeframe aggregation, session/DST
  boundaries, cost calculations, position sizing, exposure aggregation,
  timestamp skew and each strategy state machine.
- Property/invariant tests: no future reads, risk never exceeds budget, duplicate
  events are idempotent, no order without a valid quote, and no promotion with
  negative expectancy.
- Replay tests: deterministic reconstruction from recorded ticks, orders and
  deals including rejects, partial fills and broker SL/TP closures.
- Statistical tests: purged walk-forward splits, fixed untouched holdout,
  bootstrap/Monte Carlo paths and family-wise search accounting.
- Integration tests: MT5 capability detection and read-only snapshots by
  default; explicit demo probes live in a separately invoked suite.
- Failure-injection tests: process crash, corrupt checkpoint, clock skew, missing
  feed, spread spike, margin exhaustion and interrupted promotion.

## Delivery Sequence

1. Preserve and baseline the dirty repository; establish an isolated worktree.
2. Add safety invariants and repair live sizing, halts, timestamps, margin and
   reconciliation before strategy invention.
3. Build the tick/cost/multi-timeframe data plane and deterministic replay.
4. Build the experiment registry, champion pointer, duplicate detection and
   promotion/rollback gates.
5. Build the full-library knowledge index and update Cursor rules/prompts.
6. Replace every-bar ordering with the selective firehose pipeline.
7. Add source-faithful strategy modules incrementally using tests and isolated
   experiments.
8. Add a genuine Jansen-style ML track only after sufficient point-in-time data
   exists.
9. Add optional external news/depth/futures/intermarket adapters when sources are
   available.
10. Run historical, stress and shadow/demo incubation. Promote only a passing
    candidate; otherwise retain the prior champion and continue research.

## Acceptance Criteria

- The running demo is not modified during development and no second runner is
  started.
- The live/demo runner uses stop-based risk sizing and enabled persistent loss
  limits; fixed-lot cosmetic risk is eliminated.
- No-money rejection floods, future-timestamp freshness bypasses and unreconciled
  broker closes have tested handling.
- Every strategy consumes only data available at the decision timestamp.
- Every experiment is reproducible from immutable code/config/data fingerprints
  and remains in persistent memory whether accepted or rejected.
- A negative-expectancy candidate can never be promoted merely for improving
  win rate or being less negative.
- Cursor-generated ideas use the full indexed book library with exact provenance
  and cannot bypass deterministic tests and promotion gates.
- The system always identifies the current champion and can atomically roll back
  to its predecessor.
- Unsupported HFT, Level 2, centralized-volume, author-method and win-rate claims
  are absent from code, prompts and reports.
- All applicable automated tests pass before any demo promotion.

## Explicit Non-Goals

- Guaranteeing profit or a 98%/100% future win rate.
- Calling retail MT5 M1 execution genuine exchange HFT.
- Combining all books into one contradictory signal.
- Allowing an LLM to place unattended trades or bypass deterministic controls.
- Fabricating Level 2, queue position, centralized FX volume, news or cross-asset
  data when no provider supplies it.
- Enabling or promoting to a real-money account.
