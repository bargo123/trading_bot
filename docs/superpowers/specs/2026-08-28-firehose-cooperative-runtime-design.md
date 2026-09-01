# Firehose Cooperative Runtime and Canonical Close Design

Date: 2026-08-28  
Branch: `opencode/exploration-firehose`

## Objective

Keep the MT5 DEMO Firehose continuously able to discover and execute qualified
opportunities while ensuring expensive global candidate generation cannot
starve open-position management, heartbeat freshness, confirmed-close cleanup,
or immediate slot reuse.

The system must remain evidence-driven. This work does not guarantee winning
trades, force entries, raise risk, remove broker safeguards, or enable live
money.

## Observed Defects

1. The global scan evaluates 26 symbols and many mechanism/horizon variants in
   one synchronous runner loop. One symbol can occupy the loop for tens of
   seconds.
2. `run_rapid_exit_recheck_if_due()` is called between symbol scans, but cannot
   run while a single expensive symbol evaluation is in progress. Its nominal
   one-second interval therefore does not bound exit latency.
3. The heartbeat is primarily written around full scan cycles and may appear
   stale while the runner is actively computing candidates.
4. The rapid-close path confirms broker closure and releases TradeController
   state, but does not consistently execute the complete normal-close workflow:
   turnover truth, lifecycle journal, metadata/basket cleanup, reentry release,
   and broker-confirmed outcome learning.
5. Repeated scan computations contribute to long candidate-discovery latency.

## Constraints

- Exactly one broker execution owner remains
  `bot/scripts/run_broker_paper.py`.
- Council, Factory, Watcher, Book Brain, and research processes remain
  read-only.
- `engine=mt5`, `mode=mt5_demo`, `allow_live=false`,
  `paper_trading_enabled=true`, and `dry_run=false` remain unchanged.
- No second trading brain or broker-mutating background thread.
- No martingale, forced trades, increased loss-recovery sizing, or manual
  symbol authorization.
- Existing fresh-quote, geometry, spread/economics, margin, per-trade risk,
  portfolio, OMS, and self-hedge protections remain.
- Candidate confidence below 95% may still use the governed DEMO exploration
  lane; 95% remains an optimization target, not an entry threshold.

## Design

### 1. Cooperative Runtime Checkpoint

Add one runner-owned cooperative checkpoint callable from long-running scan
work. It executes only in the existing runner thread and owns no independent
strategy logic.

The checkpoint will:

1. honor explicit `STOP FIREHOSE`;
2. refresh broker positions and executable quotes for open tickets;
3. evaluate each open ticket through the existing FastExit evidence and the
   canonical TradeController;
4. request and confirm any authorized close;
5. finalize confirmed closes through the canonical close finalizer;
6. write a fresh runtime heartbeat and checkpoint-latency telemetry; and
7. return control to the unfinished global scan.

The checkpoint is due according to monotonic elapsed time. It does not impose a
minimum trade age or alter an entry decision.

### 2. Checkpoint Placement

Checkpoint calls will be inserted at cooperative boundaries:

- before and after each symbol scan;
- between mechanism groups;
- between horizon batches where the current APIs permit it;
- before and after global ranking;
- before each frozen-candidate execution revalidation; and
- after every broker-confirmed close.

If a deeply nested candidate function cannot expose a callback safely, the
first implementation will checkpoint at the narrowest existing boundary and
record the measured maximum gap. Further callback insertion is justified only
by evidence that the required bound is still missed.

### 3. Canonical Confirmed-Close Finalizer

Extract the shared post-close workflow into one runner helper. Both the normal
management pass and cooperative checkpoint must call it only after the broker
confirms the ticket is absent.

The finalizer will perform idempotently:

- TradeController ticket release;
- turnover close recording with broker-confirmed net PnL when available;
- `firehose_close` and basket lifecycle journaling;
- ticket metadata and confirmed basket cleanup;
- reentry/portfolio slot release;
- broker-confirmed outcome-memory update;
- counterfactual replay when sufficient evidence exists; and
- immediate checkpoint/scan continuation signaling.

An acknowledged but unconfirmed close must retain local ownership and must not
release the slot.

### 4. Heartbeat Truth

Heartbeat output will distinguish:

- `RUNNING_SCAN`
- `RUNNING_MANAGEMENT_CHECKPOINT`
- `WAITING_BROKER_CONFIRMATION`
- `TECHNICAL_EXECUTION_BLOCK`
- `OPERATOR_STOPPED`

New telemetry:

- `LAST_RUNTIME_CHECKPOINT_AT`
- `RUNTIME_CHECKPOINT_GAP_MS`
- `RUNTIME_CHECKPOINT_GAP_P95_MS`
- `OPEN_TICKET_RECHECKS`
- `CONFIRMED_CLOSES_FINALIZED`
- `CLOSE_TO_RESCAN_MS`
- `SCAN_SYMBOL_INDEX`
- `SCAN_SYMBOL_COUNT`
- `SCAN_CYCLE_AGE_MS`

A heartbeat must not claim fresh trade-management coverage when the last
checkpoint exceeds the configured operational target.

### 5. Scan Throughput

Optimize only measured redundant work. Per scan/symbol, cache immutable inputs
such as broker specification, bars, point-in-time feature snapshots, and shared
mechanism context. BUY and SELL, every configured mechanism, and every horizon
must still enter the complete global candidate pool.

Caching must be keyed by symbol, quote/bar identity, mechanism inputs, and
horizon where relevant. It must never reuse future information or stale
execution prices. Frozen candidates still receive fresh broker revalidation
before order submission.

### 6. Outcome Quality

The daily lifecycle report remains observation-only. It will be used to rank
separate research hypotheses for reducing:

- never-green entries;
- fast losers;
- winner-to-loser giveback;
- excessive hold time; and
- negative after-cost expectancy.

No runtime gate is changed solely because a report metric is poor. Any strategy
change requires chronological costed replay and focused validation.

## Data Flow

```text
global scan chunk
  -> cooperative checkpoint due?
     -> refresh open-ticket executable quotes
     -> FastExit evidence
     -> TradeController decision
     -> HOLD/LOCK or broker close request
     -> broker confirms close
     -> canonical close finalizer
     -> slot released + learning persisted
  -> resume unfinished global scan
  -> global rank complete candidate universe
  -> frozen candidate revalidation
  -> governed MT5 DEMO order path
```

## Error Handling

- Missing or invalid liquidation quote: no close mutation; record explicit
  evidence failure and retry at the next checkpoint.
- Predictor unavailable: it cannot authorize continuation; existing
  unsupported-profit harvest behavior remains.
- Broker close acknowledged but position remains: retain ticket state and retry
  confirmation without duplicate close ownership.
- Finalizer partial failure: persist a pending idempotent cleanup record and
  retry; never fabricate broker PnL.
- Checkpoint exception: journal the component and continue only when broker and
  account state remain verifiable.
- Market/broker technical impossibility may block execution safely; model
  confidence alone must not stop the Firehose.

## Testing

Focused TDD must prove:

1. a deliberately slow multi-symbol scan invokes management checkpoints before
   the full universe completes;
2. a net-green ticket with unavailable continuation evidence is harvested
   during that scan;
3. a genuine fast loser can abort during that scan;
4. spread/commission friction alone does not close a new position;
5. an unconfirmed broker close does not release controller, basket, or portfolio
   state;
6. a confirmed close executes the same finalizer from normal and checkpoint
   paths;
7. confirmed close triggers immediate rescan continuation;
8. heartbeat freshness and scan-progress telemetry update during long scans;
9. BUY and SELL variants, mechanisms, and horizons still reach global ranking;
10. no new confidence/95-percent entry gate exists;
11. `allow_live=false` and DEMO verification remain enforced; and
12. exactly one broker execution owner remains.

After focused tests, run the full pytest suite once, then perform a controlled
single-runner restart and inspect fresh heartbeat, journal, fill, close, cleanup,
learning, and rescan evidence. Do not force a trade for verification.

## Completion Criteria

- Open-ticket management is not delayed by completion of the full global scan.
- Every broker-confirmed close uses the canonical finalizer.
- Heartbeat accurately reports scan progress and management-checkpoint age.
- A confirmed close releases its slot and resumes candidate search without an
  avoidable full-cycle wait.
- Entry generation remains complete and no new entry blocker is introduced.
- Focused and full tests pass.
- One governed MT5 DEMO runner is active with `allow_live=false`.

Profitability improvement is measured from subsequent broker-confirmed DEMO
outcomes; it is not declared from code completion alone.
