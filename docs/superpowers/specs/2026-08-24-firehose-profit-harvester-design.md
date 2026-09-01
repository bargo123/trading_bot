# Firehose Profit Harvester Design

## Scope And Safety

This change affects only the DEMO Firehose runtime's exit, ticket lifecycle,
and runtime telemetry. It does not remove, disable, replace, or move the
Research Factory, AI Council, Book Brain, historical replay, ML training, or
champion/challenger governance. The runtime consumes approved behavior and
may emit additional observations for research; it does not train or promote.

DEMO constraints remain unchanged:

- `engine=mt5`
- `mode=mt5_demo`
- `allow_live=false`
- `paper_trading_enabled=true`
- `exploration_max_risk_per_trade_usd=0.15`

Existing entry-quality, stale-quote, spread, economics, self-hedge, and risk
gates remain mandatory and unchanged. No policy uses a fixed USD take-profit
constant.

## Current Root Cause

The production call path is `run_broker_paper.py` -> `evaluate_fast_exit()` ->
`FastExitStateMachine.evaluate()`.

The current state machine takes profit only at the structural target or after
the armed MFE giveback limit. It emits `LOCK` rather than a close after MFE
arming. The runner currently provides `remaining_ev=None` with
`remaining_ev_status="UNKNOWN"`, so the EV branch cannot close a profitable
position. Consequently a position with material profit and modest/no giveback
legitimately returns `HOLD`, which explains the observed 0.70/0.80 USD symptom.

No threshold will be selected from that symptom alone.

## Evidence Pipeline

A read-only analyzer will load legitimate DEMO journals, MFE/MAE ledgers, deal
reconciliation data, and replay outputs. It will reject incomplete records
rather than infer missing quotes, costs, or peaks.

For realized positions it will report buckets at 0.30, 0.50, 0.70, 0.80, and
1.00 USD plus normalized R-based buckets when broker-native cost/stop evidence
exists. Each bucket reports count, subsequent peak improvement, giveback,
realized net PnL, MFE, time to threshold/peak/close, post-threshold hold time,
and costs. Aggregate reports include profit capture ratio, loss-erasure ratios,
hold-time percentiles, round trips per hour, slot utilization, and net/gross
profit per hour.

Historical replay compares the original structural policy, quick harvest,
quick harvest with short momentum extension, MFE floor, remaining-EV exit, and
a combined policy. Policy selection is OOS and cost-aware. It requires complete
evidence and compares expectancy, profit factor, payoff, tails, drawdown,
turnover, and capture ratio; it never selects on win rate alone.

## Runtime Policy

`ProfitHarvester` is a ticket-scoped decision layer called by FastExit after
liquidation-side pricing and broker-native cost conversion. It receives exact
ticket metadata, current net PnL/R, MFE/MAE, age, side-specific 5/15/30 second
returns, momentum acceleration, spread-normality evidence, and remaining EV.

It can return only explained actions:

- `QUICK_TAKE`: meaningful net/R profit with stalled/weakening momentum,
  inadequate remaining EV, or evidence-supported short-horizon completion.
- `PROFIT_LOCK`: arm or advance a dynamic MFE-derived profit floor.
- `MOMENTUM_HOLD`: allow a strictly bounded micro extension only when all
  required favorable momentum, normal spread, positive EV, and no-giveback
  evidence is present.
- `SCRATCH`: early no-progress/adverse-selection failure within the evidence
  supported micro horizon.
- `ABORT`: regime, EV, or invalidation failure.

The dynamic profit floor is expressed in net R and MFE capture, not USD. Once
armed, a floor breach exits immediately; it cannot degrade into a normal large
loss. Missing required microstructure, cost, or ticket evidence fails closed to
the existing safety-preserving state and is reported as unavailable.

## Ticket Lifecycle And Re-entry

Successful close confirmation releases ticket metadata, MFE/MAE state, and the
Firehose slot. A re-entry guard fingerprints the prior trigger/quote state and
rejects an identical stale signal. It permits a new, independently valid thesis
with refreshed quote evidence without adding a winner cooldown.

## Observability And Research Interface

Every evaluation emits an explainable `FIREHOSE EXIT TRACE` with ticket,
liquidation BID/ASK, net PnL/pips/R, MFE, giveback, floor, momentum windows,
remaining EV, structural target distance, decision, and reason. Runtime journal
events expose observed `profit_capture_ratio`, `time_to_quick_take`, MFE
giveback, early-scratch reason, round trips per hour, winner extension seconds,
loss-erasure ratios, and cost per round trip. These are observational only;
Research Factory decides whether to research them and Council remains separate.

## Testing And Verification

Deterministic tests cover stalled profit quick-take, strong bounded extension,
floor breach, negative EV abort, no-progress scratch, liquidation BID/ASK,
cost inclusion, exact ticket metadata, slot release, stale re-entry rejection,
fresh re-entry, and unchanged risk/entry gates. Tests also cover absent evidence
fail-closed behavior and analysis refusal to fabricate missing history.

Before completion, run Firehose focused tests, full pytest, Research Factory
tests, Council tests/imports, safety-config checks, and the existing verifier.
The repository rule prohibiting order placement remains binding, so no MT5
DEMO order runner will be started by this implementation.
