# Safe Firehose Expansion Design

## Goal

Create a high-throughput MT5 DEMO Firehose that trades only independently
validated, costed mechanisms and gathers bounded evidence on plausible
undercovered mechanisms. It must expose every live funnel rejection instead
of reporting a scan as a fire.

## Safety Constraints

- Keep `engine: mt5`, `mode: mt5_demo`, `allow_live: false`, and
  `paper_trading_enabled: true`.
- Do not force orders, martingale, relax quote freshness, or remove measured
  spread, positive net-EV, geometry, portfolio, or risk gates.
- Keep exploration limits unchanged: two positions, one per symbol, `$1.00`
  daily loss, `$0.15` per trade, five trades per hypothesis, and 1800-second
  post-failure cooldown.
- A candidate may be promoted only after real, chronological, costed
  walk-forward and sealed OOS evidence. Missing broker-native execution
  evidence produces `NO_EVIDENCE`, never a synthetic approval.

## Two Trading Lanes

### Validated Firehose

The runtime may send a DEMO order only when an artifact authorizes the exact
`symbol`, `strategy_family`, `strategy_version`, `side`, `session`, `regime`,
and `structure` combination. Each permission carries reproducible rule,
dataset, cost-profile, contract, and code fingerprints. A family cannot use a
different family's result merely because their market-state labels match.

### Exploration Firehose

The runtime may create a bounded DEMO experiment only after fresh quotes,
measured session spread, positive candidate economics, valid micro geometry,
minimum-lot risk sizing, portfolio safety, self-hedge protection, and all
exploration limits pass. It remains a research lane, not an alternate route
around validation.

## Book and Research Mechanisms

Book-derived mechanisms are executable only when their source passage hash,
mechanism, rule fingerprint, falsification condition, and rule version are
stored with the candidate and replay result. The first research families are:

- Ponsi failed-breakout fade: completed M1 break through a confirmed M15 range
  edge followed by a completed return inside the range; test quiet-session and
  liquidity filters as pre-registered variants.
- Chan Bollinger midpoint reversion: use the existing parameterized Bollinger
  rule as a distinct family rather than relabeling an M15 range snapback.
- Existing micro momentum, range snapback, and compression-breakout families:
  retain only if their rule provenance is explicit; otherwise label them
  `DATA_DERIVED` or `BOOK_COVERAGE=INSUFFICIENT`.

Book disagreements are preserved in a conflict record and evaluated as
separate pre-registered variants. No family is added because its name sounds
plausible.

## Historical Validation

Validation consumes executable trade facts rather than a simulated outcome
alone. Every record includes decision timestamp, source bar/quote fingerprint,
entry, stop, target, exit, exit reason, gross and net PnL, itemized spread,
slippage, commission, MFE, MAE, holding time, and R-normalized loss geometry.

For each dynamically discovered family/state bucket, the pipeline uses
chronological timestamp-purged expanding walk-forward folds and one persistent
sealed evaluation. Measured costs resolve at least by symbol and session. A
family must pass net expectancy, profit factor, conservative lower confidence
bound, full-stop stress, tail-loss geometry, and per-symbol OOS gates. Pooling
may improve estimates but cannot authorize an unproven symbol/family.

The present M1 analogue index lacks executable quote/fill facts, so it cannot
create a new DEMO permission by itself. The pipeline must emit `NO_EVIDENCE`
until source data meets the replay contract.

## Funnel Telemetry

Each evaluated completed bar receives a stable scan identifier and one
terminal funnel outcome. The heartbeat and throughput report expose:

`SCANS`, `MICRO_CANDIDATES`, `BOOK_SUPPORTED`, `VALIDATED_MATCH`,
`EXPLORATION_ELIGIBLE`, `SPREAD_REJECT`, `ECONOMICS_REJECT`,
`GEOMETRY_REJECT`, `RISK_REJECT`, `STALE_REJECT`, `OTHER_REJECT`, `FIRES`, and
`FILLS`.

`FIRES` means the runner invoked the broker submission boundary. `FILLS` means
the broker confirmed execution or a confirmed position. Existing brain intent
remains observable but cannot be counted as either. Micro-family diagnostics
must distinguish missing data, no trigger, invalid geometry, and an internal
exception while continuing to fail closed.

## Fast Harvest and Reentry

Entry and exit remain separate. Confirmed tickets use existing FastExit
liquidation-side pricing, peak-profit protection, no-progress scratch, and
remaining-EV checks. Profit-harvest policy activation still requires a
complete costed OOS policy artifact. Close journals must preserve numeric
costs, realized net PnL, exit reason, MFE, MAE, and ticket identity so the
research loop can evaluate win/loss geometry and release a slot only after a
confirmed close.

## Services and Operations

The runner is the only broker-order submitter. The singleton watcher regenerates
artifacts on evidence changes, the factory records `NO_EVIDENCE` honestly when
replay data is inadequate, Council can approve testing only, and the Book Brain
supplies provenance rather than authorization. Watcher ingest errors are
terminally visible and tested. The complete DEMO stack is healthy only when
MT5, runner, watcher, factory cycle, Council cadence, and Book Brain readiness
are separately reported.
