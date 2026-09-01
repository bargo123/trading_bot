# Watcher Strategy Evidence Pipeline

## Status

Approved architecture for implementation planning. This document covers the
gap between the book-derived strategy library and the Watcher’s per-candidate
evidence view. It does not authorize broker execution, change Firehose entry
or exit policy, or promote any model.

## Problem and evidence

The current Watcher displays roughly 2,424 strategy rows, but the rows are not
2,424 independently executable strategies. The source library contains
duplicated passages, generic advice, and proposed hypotheses whose confirmation
fields are empty. The Firehose journal currently records candidate-level
rejections and sparse prediction metadata, not the point-in-time chart context
needed to evaluate a book rule. Broker outcome rows contain net PnL facts but
are not linked to strategy IDs, so the Watcher cannot compute strategy-level
win/loss results.

The current applicability evaluator checks fields such as side, regime, and
timeframe, then derives BUY/SELL from a side rule. It does not execute the
actual entry predicate described by the source. Therefore a non-empty
applicability result would not yet be a measured strategy signal.

The system already has suitable raw material: point-in-time quote,
microstructure, short-return, volatility, and M1/M5/M15 features in the
research shadow data, plus executable BID/ASK outcome labels. The design below
connects those facts without fabricating probabilities.

## Goals

1. Give every canonical strategy record an honest evidence state and a visible
   result or an explicit reason why no result exists.
2. Preserve source title, passage hash, page when available, and extraction
   provenance through every derived record.
3. Evaluate only deterministic, fully specified predicates as exact strategies.
4. Keep family-level context useful, but label it as proxy evidence rather than
   exact strategy performance.
5. Replay exact strategies chronologically with executable entry and exit
   prices, costs, and the same lifecycle policy used by the governed runner.
6. Link candidate decisions and broker-confirmed closed trades to the exact
   strategy IDs that were evaluated.
7. Keep Watcher, Book Brain, Factory, Council, and probes read-only.
8. Bound storage growth by normalizing strategy definitions, evaluations, and
   outcomes instead of repeating the full library for every candidate.

## Non-goals

- No automatic promotion to an execution-authorized model.
- No manual symbol authorization, probability fabrication, or 95% entry gate.
- No new broker execution owner and no call to `mt5.order_send()` outside the
  governed Firehose runner.
- No deletion of historical broker facts or raw source files.
- No claim that a book’s marketing win rate is validated by the repository.
- No conversion of generic M1 analogue evidence into horizon-specific captured
  win probability.

## Architecture

The pipeline has five read-only stages:

1. **Source registry** stores one canonical record per deduplicated source
   passage and links duplicate hypotheses to that record.
2. **Rule compiler** classifies and compiles only fully specified rules into a
   deterministic evaluator.
3. **Context capture** attaches a compact point-in-time market snapshot to each
   Firehose candidate evaluation.
4. **Replay/evidence** joins compiled rules to chronological quote/tick data
   and executable lifecycle outcomes.
5. **Watcher projection** serves normalized definitions, evaluations, evidence,
   and outcome summaries to the local dashboard.

The data flow is:

```text
book passage
  -> canonical strategy record
  -> exact/proxy/untestable classification
  -> deterministic rule (exact only)
  -> point-in-time context match
  -> executable replay and costs
  -> strategy evidence summary
  -> Watcher detail view
```

## Canonical strategy registry

Each canonical record has a stable `strategy_id` derived from a normalized
source identity and passage hash. Required fields are:

- `strategy_id`, `source_id`, `source_title`, `author`, `edition`
- `source_path`, `source_sha256`, `page_start`, `page_end`
- `source_text_hash`, `extraction_method`, `extracted_at`
- `canonical_title`, `mechanism_family`, `side_rule`, `timeframe`
- `entry_rule`, `exit_rule`, `stop_rule`, `target_rule`, `risk_rule`
- `required_features`, `allowed_symbols`, `allowed_sessions`
- `status`, `compile_errors`, `duplicate_strategy_ids`

The registry deduplicates exact or near-identical passages without discarding
their source links. Duplicate library rows point to the canonical record and
are not independently counted as strategies.

## Truthful status model

Every record has exactly one primary status:

- `CODED_EXACT`: entry, exit, invalidation, and required inputs are explicit
  enough to run without interpretation.
- `FAMILY_PROXY`: the passage supports a mechanism or context, but not an exact
  executable rule. It may contribute context evidence only.
- `UNTESTABLE_SOURCE`: the passage is advice, a claim, an incomplete setup, or
  otherwise lacks enough information for a defensible evaluator.
- `COMPILE_ERROR`: the passage appears intended as a rule but could not be
  compiled; the error is retained for correction.

`CODED_EXACT` is not the same as profitable, validated, or execution-authorized.
It means only that the rule is measurable. A record can additionally carry
`evidence_status` values such as `NO_SAMPLES`, `INSUFFICIENT_SAMPLES`,
`NEGATIVE_OOS`, `POSITIVE_TEST_UNSEALED`, or `MEASURED_NOT_PROMOTED`.

## Point-in-time context event

Every evaluated candidate stores a compact immutable context event rather than
copying the full strategy library. The event includes:

- event timestamp and source data timestamp
- `symbol`, `side`, `mechanism`, `horizon_s`, `session`, and `regime`
- executable `bid`, `ask`, spread, quote age, and tick flags when available
- short returns and tick velocity/direction persistence
- volatility and compression/expansion summaries
- M1, M5, and M15 summaries with their source timestamps
- structure/breakout/rejection state when explicitly available
- candidate and strategy IDs evaluated at that instant
- feature schema version and deterministic snapshot hash

A missing feature remains missing. The pipeline never fills a feature from a
future quote, a later bar, or an inferred default that could change the rule’s
meaning.

## Deterministic evaluator

The compiler converts only an allow-listed rule grammar into predicates over a
context event. The grammar supports explicit comparisons, ranges, crossings,
ordered conditions, and named mechanism primitives whose definitions are
versioned and tested. It rejects prose that requires discretionary chart
interpretation, unspecified parameters, or hidden future information.

An evaluator returns one of:

- `MATCH`
- `NO_MATCH`
- `MISSING_INPUT`
- `INVALID_INPUT`
- `EVALUATION_ERROR`

The reason includes the first failed predicate and all missing/invalid field
names. A `MATCH` is a candidate signal, not a trade authorization. Execution
and risk remain outside the Watcher.

## Replay and evidence

For each exact strategy match, replay starts at the candidate timestamp and
uses only quotes at or after entry. BUY uses ASK entry and BID liquidation;
SELL uses BID entry and ASK liquidation. The replay records:

- `p_captured_win`, `net_pnl`, `mfe`, `mae`
- time to first net green, `never_green`, and `green_then_loser`
- time to peak, selected horizon, spread, commission, and measurable slippage
- exit action/reason under the governed lifecycle policy
- tail-loss observations and missing-data reasons

The primary probability is the proportion of replayed samples with positive
broker-executable net PnL under that exact strategy, symbol, side, and horizon.
Generic structural or M1 analogue results are stored separately as
`FAMILY_PROXY` evidence and cannot populate `P_CAPTURED_WIN_<horizon>`.

Reports include sample count, wins, losses, net expectancy, profit factor when
defined, quantiles of loss, calibration ECE when probabilities exist, and
chronological test/OOS/holdout partitions. Weak or missing evidence is shown as
such; it is never converted to a favorable default.

## Live decision and broker outcome attribution

The Firehose decision snapshot carries the exact set of strategy IDs evaluated,
which predicates matched, and the evidence version used. If the runner opens a
DEMO position, the execution owner carries the frozen matched strategy IDs in
its existing order metadata or journal correlation fields.

On broker-confirmed close, the learning path appends one immutable outcome fact
containing the broker net PnL and the frozen pre-entry context. It joins that
fact to strategy IDs only from the recorded pre-entry decision; it never
reconstructs strategy membership from post-entry information. If correlation
is absent or incomplete, the outcome is stored as `UNATTRIBUTED`, not guessed.

Post-close counterfactuals are learning-only records. They may replay the
opposite side, alternative horizon, or abstention using the same pre-entry
context and subsequent quotes, but they cannot alter the original trade label.

## Normalized storage and retention

The Watcher store is normalized into four logical datasets:

1. `strategy_registry`: one row per canonical source passage.
2. `strategy_aliases`: duplicate library IDs and source references.
3. `strategy_evaluations`: one row per strategy/context evaluation with reason.
4. `strategy_outcomes`: immutable replay or broker-confirmed outcome facts.

Dashboard queries join these datasets by stable IDs and time partitions. Raw
event files remain append-only and can be compacted or archived by the existing
retention process. Compaction must preserve hashes, offsets, counts, and source
links so summaries remain auditable.

Backfill can classify and deduplicate historical source rows immediately. Exact
strategy performance is backfilled only where the historical data contains all
required point-in-time inputs and executable prices. Older broker outcomes with
no strategy correlation remain unattributed. No missing state is synthesized.

## Dashboard contract

The Watcher detail view shows, for every strategy:

- source and page provenance
- primary status and compile/evaluation reason
- exact measured evidence: wins, losses, sample size, net expectancy, and
  confidence/uncertainty
- family-proxy evidence in a visibly separate section
- untestable-source explanation when no exact result is possible
- recent matched contexts and broker-confirmed outcomes

The UI must never show a blank percentage as if it were zero, and must never
label proxy or synthetic evidence as exact captured-win probability. A missing
percentage is replaced by a truthful state such as `NO_SAMPLES`,
`MISSING_INPUT`, or `UNTESTABLE_SOURCE`.

## Safety boundaries

All registry, evaluator, replay, and dashboard processes are read-only with
respect to MT5 positions. Only `bot/scripts/run_broker_paper.py` may submit
governed MT5 DEMO orders. The design does not change `engine: mt5`,
`mode: mt5_demo`, `allow_live: false`, `paper_trading_enabled: true`, or the
existing risk, quote, spread, economics, portfolio, OMS, and exit gates.

## Testing and acceptance criteria

Focused tests must prove:

1. duplicate passages resolve to one canonical strategy record with preserved
   aliases and source provenance;
2. exact, proxy, untestable, compile-error, missing-input, and invalid-input
   statuses remain distinct;
3. BUY and SELL executable price orientation is correct and costs are applied
   once;
4. horizon is part of evidence identity, so 3s and 10s can differ;
5. future quotes cannot affect a pre-entry match or label;
6. every candidate evaluation carries the same immutable context hash;
7. broker-confirmed outcomes link only to frozen pre-entry strategy IDs;
8. missing correlation yields `UNATTRIBUTED`, never an invented assignment;
9. the dashboard exposes exact evidence separately from proxy/untestable
   records and loads normalized data without expanding every row into the full
   library;
10. Watcher/Factory/Council/Book Brain code paths contain no broker order
    submission capability.

Success means every visible strategy row has a truthful classification and an
explicit evidence state, exact strategies have reproducible after-cost replay
results where data supports them, and no unsupported strategy receives a
fabricated win/loss percentage or execution authority.
