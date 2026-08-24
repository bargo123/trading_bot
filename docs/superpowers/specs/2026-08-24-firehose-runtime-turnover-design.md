# Firehose Runtime Turnover Design

## Status

Approved for planning. This specification does not authorize an MT5 runner
launch. A fresh explicit approval is required immediately before any DEMO
runner launch.

## Goal

Make the Firehose runtime capable of controlled, evidence-driven fast turnover:
exact ticket/basket ownership, fast observation after confirmed fills, safe
harvest/scratch/extension decisions only when a governed research artifact
validates them, confirmed close cleanup, and fresh-trigger re-entry.

No profitability, win-rate, or live-execution claim is made by this work.

## Binding Safety Rules

- `engine: mt5`, `mode: mt5_demo`, `allow_live: false`,
  `paper_trading_enabled: true`, and
  `exploration_max_risk_per_trade_usd: 0.15` remain unchanged.
- No live account access, order placement by this work, runner launch, merge,
  or push. DEMO runner operation requires separate fresh approval.
- Research Factory, AI Council, Book Brain, ML/replay, governance, failed
  hypothesis memory, and existing DEMO safeguards remain separate and intact.
- Missing trusted book, lifecycle, cost, feature, policy, or OOS evidence
  returns `NO_EVIDENCE` or `NOT_IMPLEMENTED`; it never creates a trading
  decision or fabricated metric.
- Existing entry gates, stale-signal protection, spread/economics gates,
  margin controls, self-hedge protection, and per-trade risk remain unchanged.

## Observed Root Cause

The current intelligent path can retain a profitable ticket because:

- legacy USD quick-winner flattening is disabled and suppressed in intelligent
  mode;
- generic max-hold is configured as zero;
- Profit Manager arms after profit but normally protects with a 50% MFE
  giveback/lock rather than closing;
- FastExit has no supplied validated harvest policy or complete cost/spread
  evidence, so it cannot issue `QUICK_TAKE`;
- structural exits run on closed M1 bars, not every intrabar observation;
- exact basket ownership exists in isolation but is not wired into the runner.

Current local data cannot validate a replacement: the Firehose journal has no
confirmed `firehose_open`/`firehose_exit_trace`/`firehose_close` lifecycle,
complete cost fields, or usable policy artifact. Candidate `pm_exit` rows are
close attempts, not confirmed realized outcomes. The valid conclusion is
`NO_EVIDENCE`.

## Evidence Basis

Every material policy proposal is represented by a full-corpus Book Brain
evidence packet using `build_evidence_packet`. Packets retain support,
contradiction, source hash, indexed path/location, verbatim passage, local data
observation, and falsification rule.

Relevant discovered priors include conditional MFE/giveback diagnostics,
target-to-breakeven/profit protection, time/no-progress exits, momentum-aware
stop tightening, adverse-selection/inventory risk, and transaction-cost
hurdles. Contradictions are retained: MFE optimization does not itself improve
a system, trailing stops can exit early, time stops cut winners, and momentum
divergence alone is unreliable. Therefore no universal USD threshold,
percentage giveback, time limit, or clip count is embedded in runtime code.

Novel hypotheses are allowed only as `NOVEL_SYNTHESIZED_HYPOTHESIS`; absent a
separately governed stronger empirical gate, they remain `NO_EVIDENCE`.

## Components And Data Flow

### 1. Research Policy Artifact

Research owns policy generation, chronological replay, walk-forward, sealed
OOS comparison, and policy artifacts. Runtime reads an artifact only when it
has trusted provenance, complete policy evidence, governed thresholds, and
complete costed OOS evidence.

The artifact contains normalized parameters and policy identity only. It never
contains fixed universal USD exits. It must specify the supported decision
families: quick harvest, short momentum extension, profit floor, remaining-EV
abort, early scratch, and optional confirmed clip addition.

### 2. Exact Basket Lifecycle

After a broker-confirmed fill, the runner creates or updates exact persistent
ownership through existing `TicketMetadataStore` and `BasketMetadataStore`.
Each clip records basket ID, ticket ID, hypothesis/family, symbol/side,
trigger ID, sequence, entry geometry, initial broker-native risk, spread/cost
evidence, regime, and session. It never infers ownership from symbol/side.

Adds remain unavailable without a valid artifact. When available, every add is
same-side, fresh-triggered, positive-continuation-only, non-losing, within the
shared broker-native basket risk budget and clip cap, and rejects self hedges.

`BasketMetadataStore` is single-contract by design. The multi-symbol runner
therefore uses one persisted store per normalized symbol, constructed from that
symbol's fresh broker `ContractSpec`; it never combines symbols behind one
untrusted shared store.

### 3. Runtime Observation Snapshot

For every exact owned ticket/basket, the monitor builds a point-in-time
snapshot using executable liquidation marks: BID for BUY, ASK for SELL. It
includes current net PnL, normalized R/pips, MFE/MAE, peak net profit, age,
giveback, return/momentum windows, spread, cost evidence, remaining EV,
regime, session, and fresh-trigger state.

Missing marks, costs, features, or trustworthy policy inputs yield a trace
reason and no new policy action. Snapshot fields are append-only observations,
not synthetic outcomes.

### 4. Policy Decision Adapter

The adapter consumes a trusted artifact and point-in-time snapshot. It returns
one of `QUICK_HARVEST`, `MOMENTUM_EXTENSION`, `PROFIT_LOCK`, `HOLD`, `SCRATCH`,
`ABORT`, `STOP`, `TIME_EXIT`, or `NO_EVIDENCE`.

- `QUICK_HARVEST` requires validated normalized profit after costs plus evidence
  that continuation weakens or remaining EV decays.
- `MOMENTUM_EXTENSION` is limited to the artifact's short horizon and requires
  favorable momentum, normal spread, positive remaining EV, and no material
  giveback.
- `PROFIT_LOCK` uses artifact-normalized protection; it never substitutes a
  hardcoded USD floor.
- `SCRATCH`/`ABORT` require validated adverse-selection, no-progress, or
  negative-EV evidence; the catastrophe stop remains independent protection.

Without an artifact, the adapter records `NO_EVIDENCE` and does not alter the
existing decision path. Existing exits continue unchanged until activation is
governed.

### 5. Confirmed Close And Fresh Re-entry

All runtime-initiated closes use the existing exact-ticket MT5 close path.
Cleanup occurs only after position re-fetch confirms zero remaining exact-ticket
volume. Then the runner persists the final outcome, clears exact metadata,
updates basket closure/slot state, writes turnover evidence, refreshes market
state, and permits scanning.

Profitable closure has no arbitrary cooldown. Re-entry requires a fresh trigger
or state transition; the existing fingerprint/re-arm gate rejects stale signals.
Failed or partial closes preserve ownership and emit a failure observation.

## Evidence And Metrics

Append-only outcome records include exact identifiers, executable marks,
MFE/MAE, peak/realized net, capture ratio, duration, clips, decision reason,
remaining EV, costs, regime, session, giveback, and loss-erasure statistics.

Turnover reporting derives basket/clip round trips per hour, hold-time
quantiles, close-to-entry time, slot utilization, clip count, winner/loss rate,
capture, cost/basket, gross/net hourly PnL, payoff, tail losses, drawdown, and
wins erased by average/tail/max loss. Values unavailable from confirmed broker
evidence remain unavailable.

## Research Validation

Research compares current structural, quick-harvest, extension, profit-floor,
remaining-EV, scratch, and combined policies chronologically. It uses
point-in-time features, recorded costs, TRAIN/VALIDATION/rolling walk-forward,
and sealed OOS. Selection evaluates costed expectancy, PF, payoff, tail loss,
drawdown, capture, turnover, cost sensitivity, and sample size, never win rate
alone. Sealed/OOS rows never tune the winner.

No runtime activation occurs unless a governed artifact passes every required
gate. Insufficient current journal data is reported honestly as `NO_EVIDENCE`.

## Testing

Tests will first prove failing behavior for policy decisions, artifact absence,
exact metadata/restart recovery, basket risk/caps/add gates, executable BID/ASK
marks, confirmed close cleanup, slot release, fresh versus stale re-entry,
append-only traces, missing-evidence behavior, Book Brain provenance, costs,
and preserved Research Factory/Council imports and DEMO safety.

Focused Firehose, Book Brain, Factory, Council, and full pytest suites run
after meaningful changes. Historical analysis and replay use only local
legitimate data; absent lifecycle/cost/OOS data reports `NO_EVIDENCE`.

## Out Of Scope

- Changing entry quality, lot sizing, risk caps, YAML risk configuration, or
  live-money settings.
- Martingale, averaging down, arbitrary universal USD exits, unvalidated
  policy activation, strategy promotion, or automatic Council/Factory changes.
- Launching or operating MT5 DEMO without a new explicit approval.
