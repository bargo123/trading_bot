# Zero-Trade Starvation Repair Design

## Goal

Restore legitimate DEMO-only Firehose throughput without weakening validated-state authorization, economics, stale-quote, spread, portfolio, or risk controls.

## Constraints

- Do not merge this branch.
- Do not enable live trading or increase any configured risk limit.
- Keep `intelligent_gate_validated_states: true`.
- Keep exploration limits at two positions, one position per symbol, $1.00 daily loss, $0.15 per trade, five trades per hypothesis, and 1800-second failure cooldown.
- Only the MT5 DEMO runner may submit broker orders. Research Factory, Research Fast Watcher, AI Council, and Book Brain are order-free.
- Validation and promotion use measured source data and measured cost evidence only. Missing evidence fails closed.

## Root Cause

MT5 timestamps M1 bars at their open time. Research aggregates completed M1 bars with start-labelled, left-closed windows, while runtime uses end-labelled, right-closed windows and drops the last output bucket. Equal-looking M5/M15/H1 labels therefore contain different M1 candles. Runtime state signatures cannot reliably match research validation artifacts.

The undercovered-state route is disabled and is also returned around by legacy structural invalidation. The global 0.3-pip spread cap contradicts measured GBPUSD Asia costs used by the only canary. Research Factory has an unreachable governed replay path and production-callable placeholder/legacy implementations.

## Architecture

### Neutral State Semantics

Create a pandas-only neutral module under `aegis` with no broker, filesystem, configuration, or research-package dependency. It accepts a sorted UTC frame of completed M1 OHLCV bars and produces M5/M15/H1 period-start labelled bars using `label="left"` and `closed="left"`. A bucket is emitted only when its final required M1 open timestamp is present.

Move or re-export the pure session, direction, structure, regime, and state-signature functions used by both research and runtime into this module. Runtime and research must return identical values for identical completed M1 inputs. Runtime must reject non-M1 input on this path rather than silently treating another timeframe as M1.

### Execution Lanes

Champion/canary authorization remains exact and fail-closed. A decision must match the artifact symbol, regime, structure, session, and side. Its spread cap comes from measured per-symbol/session cost evidence and it must remain net-positive after live spread, commission, and measured slippage.

Exploration is a separate DEMO-only lane for registered undercovered hypotheses. It preserves stale quote, measured spread, post-cost economics, portfolio, failure-memory, position, daily-loss, cooldown, and $0.15 sizing checks. A candidate whose minimum broker size exceeds $0.15 is a shadow observation, never an order or simulated fill.

### Evidence and Research

Validation artifacts share a manifest binding the current code revision, config hash, dataset/index hash, cost-profile hash and age, contract evidence, and walk-forward measurements. Runtime rejects missing, stale, or mismatched dependencies. The watcher rebuilds the relevant measured evidence and refreshes artifacts atomically when inputs change.

Research Factory feeds only provenance-complete Book Brain support/contradiction evidence and broker-native costed replay data through chronological splits, walk-forward, and OOS evaluation. Missing broker-native replay evidence produces explicit `NO_EVIDENCE`. Legacy fabricated replay and placeholder analysis paths are removed from production reachability.

### Service Boundaries

The runner is the only MT5 order submitter. The watcher, Factory, Council, and Book Brain expose research artifacts and logs only. One Council budget ledger covers all Council paths; a fresh session begins Codex at 0/1 and locks at 1/1 after a real call.

## Validation

Tests are written first for exact M5/M15/H1 bars, all state dimensions/signature, lane authorization, all non-bypassable exploration gates, measured spread policy, artifact freshness, watcher refresh, Research Factory fail-closed/governed replay behavior, service order isolation, and live-trading refusal. Focused tests, the full test suite, and the repository verifier run before commit.

Only after validation artifacts are regenerated from current measured evidence will the full DEMO stack start. Its status output reports lane configuration and live funnel counts; it does not claim success merely because it starts.
