# Firehose Basket Evidence Design

## Scope

Add a research-first basket mechanism for the Firehose runtime. The work does
not remove, disable, replace, or absorb Research Factory, AI Council, Book
Brain, historical replay, ML, failed-hypothesis memory, or champion governance.
Runtime executes only an explicit policy artifact that research validates.

The existing repository safety contract remains binding: no YAML modification,
no live enablement, and no order placement or MT5 runner start by this work.

## Evidence Packets

Every material basket, harvesting, extension, floor, scratch, or re-entry
hypothesis is created by a full indexed-corpus query. The packet persists
hypothesis ID/origin, all source IDs and verbatim supporting passages,
contradictory passages, source locations, evidence labels, the local data
observation, and a falsification rule. A query with no direct coverage records
`BOOK_COVERAGE: INSUFFICIENT` and may create only a
`NOVEL_SYNTHESIZED_HYPOTHESIS`, which requires a stronger empirical gate.

No runtime code invents book support or trains models. Existing BookIndex and
research knowledge APIs own retrieval and provenance.

## Basket Identity And Risk

Introduce exact, persistent basket metadata: basket ID, ticket ID, hypothesis,
family, symbol, side, trigger ID, clip sequence, entry geometry, initial risk,
cost evidence, regime, and session. Ticket metadata remains the source of
truth; restart recovery cannot infer ownership from symbol/side alone.

A basket has a broker-native total risk budget. Every additional clip requires
the same-side fresh trigger, positive continuation evidence, normal spread,
positive remaining EV, and no adverse selection. It cannot exceed the basket
budget or clip cap and cannot add to a losing basket or form an opposite-side
self-hedge.

## Policy Validation And Runtime

The research layer evaluates structural, quick-harvest, extension, profit-floor,
remaining-EV, scratch, and combined policies chronologically with point-in-time
features, costs, walk-forward, and sealed OOS. It compares expectancy, PF,
payoff, tails, drawdown, capture, and turnover; it does not select by win rate.

Absent a complete validated artifact, basket clip addition and harvest remain
unavailable and legacy safe behavior continues. A validated runtime artifact
defines normalized R/cost/momentum parameters only, never fixed USD exits.

## Runtime Observations

The runner emits exact ticket/basket traces and append-only outcome records:
MFE, MAE, peak net profit, realized net, capture ratio, age, clips, decision
reasons, EV, costs, regime, session, and turnover. These observations are
available to Research Factory/Council later but do not promote any candidate.

## Verification

Tests cover multi-source evidence and contradiction provenance, insufficient
coverage, novel labeling, basket risk/clip/continuation/no-loss-add/no-hedge,
restart ownership, confirmed close lifecycle, stale/fresh re-entry, point-in-
All DEMO safety values remain unchanged. No profitability claim is made without
valid OOS and forward DEMO evidence.
