# EXPLORATION FIREHOSE MASTER SPECIFICATION

> AUTHORITATIVE SPECIFICATION — saved verbatim per completion protocol.
> Ledger: bot/reports/research/master_spec_status.json
> Handoff: bot/reports/research/IMPLEMENTATION_HANDOFF.md
> Verifier: bot/scripts/verify_master_spec.py

IMPORTANT COMPLETION PROTOCOL:

This entire prompt is the AUTHORITATIVE SPECIFICATION.

Before modifying code:

1. Save this entire specification verbatim to:
   docs/aegis/EXPLORATION_FIREHOSE_MASTER_SPEC.md

2. Parse EVERY actionable requirement from it into:
   bot/reports/research/master_spec_status.json

3. Give every requirement a stable ID:
   EF-001, EF-002, EF-003, ...

4. Each requirement must have:
   - requirement
   - status
   - implementation_files
   - tests
   - evidence
   - commit_sha

5. Allowed statuses:
   NOT_STARTED
   IN_PROGRESS
   IMPLEMENTED_UNVERIFIED
   VERIFIED
   BLOCKED
   NOT_APPLICABLE

6. A requirement may be VERIFIED only when:
   - code exists
   - appropriate test exists
   - test passes
   - runtime evidence exists when runtime verification is required

7. NEVER silently skip a requirement.

8. Continue autonomously from highest-priority unfinished requirement until:
   - every requirement is VERIFIED, or
   - only genuine external BLOCKED requirements remain.

9. Create and continuously maintain:
   bot/reports/research/IMPLEMENTATION_HANDOFF.md

10. Before saying DONE, perform a SECOND independent audit:
    reread the original MASTER_SPEC line by line,
    compare it against master_spec_status.json,
    git diff,
    tests,
    and runtime evidence.

11. Create:
    bot/scripts/verify_master_spec.py

    It must return non-zero if any merge-blocking requirement is not VERIFIED.

12. You are NOT allowed to report READY TO MERGE unless:
    verify_master_spec.py passes,
    the full test suite passes,
    required MT5 DEMO runtime checks pass,
    allow_live=false,
    and exactly one runner is verified.

Do not stop at "mostly complete", "architecture complete", or "core requirements complete".

THE LEDGER DEFINES COMPLETION.

Now execute the complete specification below.

ADD THESE REQUIREMENTS TO THE CURRENT EXPLORATION-FIREHOSE REPAIR.
DO NOT DROP OR REPLACE ANY OF THE PREVIOUS MERGE-BLOCKER REQUIREMENTS.

============================================================
A. FULL BOOK-CORPUS OPERATIONALIZATION
============================================================

The current "book-backed" implementation is insufficient.

Current runtime largely:
- generates setup from existing market structure
- gets side from existing CORE/firehose logic
- retrieves a book family
- attaches the book family as provenance/reason

That is NOT equivalent to actually operationalizing the knowledge contained
in the trading-book corpus.

I want the ENTIRE available trading-book corpus processed offline into a
structured research knowledge base.

DO NOT put the entire 5M+ word corpus in an LLM context.

Build deterministic/restart-safe ingestion.

Recursively process every source under:
docs/trading/books/

Maintain corpus statuses:
INDEXED
PARTIALLY_INDEXED
FAILED
UNSUPPORTED
PLACEHOLDER
OCR_DEGRADED

Never silently skip a book.

Original extracted passages remain AUTHORITATIVE.
AI summaries are acceleration/indexing aids only.

============================================================
STRUCTURED BOOK KNOWLEDGE
============================================================

Extract useful trading knowledge into structured records such as:

bot/knowledge/concepts.jsonl
bot/knowledge/strategy_hypotheses.jsonl
bot/knowledge/entry_patterns.jsonl
bot/knowledge/exit_patterns.jsonl
bot/knowledge/regime_rules.jsonl
bot/knowledge/risk_rules.jsonl
bot/knowledge/execution_rules.jsonl
bot/knowledge/validation_rules.jsonl
bot/knowledge/source_index.json
bot/knowledge/corpus_manifest.json

Each useful concept should preserve where available:

book
author
file hash
chapter
section
source location
source passage reference/hash
concept type
strategy family
market mechanism
required regime
required timeframe
required data
entry hypothesis
confirmation hypothesis
invalidation hypothesis
exit hypothesis
profit-management hypothesis
risk principle
execution principle
known limitation
falsification condition

Do not force every passage into a trading strategy.

Distinguish:

DESCRIPTIVE KNOWLEDGE
STRATEGY HYPOTHESIS
ENTRY PRINCIPLE
EXIT PRINCIPLE
RISK PRINCIPLE
EXECUTION PRINCIPLE
VALIDATION PRINCIPLE

============================================================
CONFLICTING AUTHORS
============================================================

Do NOT merge conflicting ideas into majority votes.

Example:
author A:
breakout continuation

author B:
failed-breakout fade

These become TWO different falsifiable hypotheses.

BOOK CONSENSUS DOES NOT AUTHORISE A TRADE.

Books propose.
Data validates.

============================================================
BOOK-BACKED STRATEGY GENERATION
============================================================

Aegis must be able to retrieve relevant hypotheses for CURRENT state.

Example current state:
symbol = EURUSD
session = London
H1 trend = up
M15 structure = pullback
M5 momentum = returning
volatility = expanding

Retrieve relevant original-source knowledge relating to:
trend continuation
pullback entry
momentum confirmation
volatility
stop placement
profit management
exit management

Then construct DISTINCT hypotheses.

Do not merely label the existing CORE signal as "book-derived".

A book-derived experiment must have actual logic derived from the structured
source concept.

Persist:

hypothesis_id
source hashes
strategy_family
symbol
side
entry logic
invalidation
exit logic
profit management
regime
timeframes
required data
reasoning mechanism
falsification test

============================================================
RETRIEVAL
============================================================

Use the whole indexed corpus for retrieval.

Do NOT reread every book on every bar.

Compile/cache offline.

At runtime/research time retrieve only relevant records.

Cache retrieval by:
state hash
source hashes
corpus version

If the corpus changes, invalidate affected caches.

============================================================
B. INTELLIGENT PROFIT MANAGEMENT
============================================================

The current screenshot demonstrates why this is necessary.

At one point the account had:
Balance ~95.78
Equity ~98.13
Floating P/L +2.35
Margin ~62.37
Free margin ~35.76
Margin level ~157%

with multiple profitable 0.01 positions:
EURUSD SELL winners
GBPUSD SELL winners

and one small EURUSD BUY loser.

The system must NOT simply let strong floating winners deteriorate indefinitely.

BUT:

DO NOT create a dumb:
"if pnl > X then always close"

rule.

That risks returning to the old pattern:
many tiny wins
+
larger losses
=
negative expectancy.

============================================================
C. SEPARATE ENTRY EDGE FROM REMAINING-TRADE EV
============================================================

For every open thesis continually estimate:

ENTRY_EV_AT_OPEN
CURRENT_REMAINING_EV
MFE
MAE
current P/L
peak P/L
giveback from MFE
time held
distance to target
distance to invalidation
spread required to exit
state/regime change
momentum deterioration
portfolio/margin pressure

A position should remain open only while the expected value of CONTINUING to
hold justifies the additional giveback risk.

A winner should not remain open merely because the original entry was valid.

============================================================
D. MFE-BASED PROFIT PROTECTION
============================================================

Implement an Intelligent Firehose profit-protection framework.

Do NOT hardcode one arbitrary threshold globally.

Research candidate policies such as:

1. STRUCTURAL TARGET
close at the validated thesis target.

2. MFE GIVEBACK
after sufficiently meaningful MFE,
allow only a validated fraction/amount of profit to be given back.

3. BREAKEVEN / COST-PLUS LOCK
after enough favorable excursion,
optionally move protection to:
entry
+
spread
+
commission/slippage buffer
+
validated minimum locked profit

ONLY if evidence shows this improves expectancy.

4. TRAILING STRUCTURAL STOP
advance invalidation behind new market structure.

Never loosen a protective stop.

5. CURRENT-EV EXIT
if remaining expected value falls <= 0 after costs,
exit or reduce.

6. TIME DECAY
if the expected edge was short-lived and has failed to progress,
exit according to validated holding-time evidence.

7. REGIME CHANGE
if the market regime invalidates the underlying mechanism,
exit.

8. PORTFOLIO PRESSURE
when margin/currency concentration becomes excessive,
prefer reducing the lowest-current-EV exposure.

Do NOT blindly close the largest winner merely because it is profitable.

============================================================
E. PROFIT LOCK MUST BE PER TICKET / PER THESIS
============================================================

Current MFE/MAE tracking is too symbol-level for multiple independent theses.

Track per:
thesis_id
hypothesis_id
ticket

For every position store:

entry
current P/L
MFE
MAE
MFE timestamp
current locked profit
current SL
target
age
strategy family
experiment status

Multiple EURUSD positions must NOT share one fake common MFE.

============================================================
F. 0.01 LOT REALITY
============================================================

If broker volume_min is 0.01 and the ticket itself is 0.01:

partial closing may not be possible.

Therefore intelligently choose between:

FULL TICKET CLOSE
or
PROTECTIVE STOP ADJUSTMENT

Do not pretend partial-close behavior is available below broker minimum volume.

============================================================
G. EXPLORATION EXIT LEARNING
============================================================

Exploration trades should actively research exit policies.

Record for every exploration trade:

maximum favorable excursion
maximum adverse excursion
P/L at:
1m
3m
5m
10m
15m
30m
60m
where available

MFE before close
MAE before close
profit given back from MFE
exit reason
profit if closed at various candidate MFE/giveback policies
profit if held to structural target
profit if held to invalidation

Use counterfactual analysis carefully and point-in-time only.

Research:

which exit policy would have improved COSTED EXPECTANCY,
not which policy maximizes one historical trade.

============================================================
H. DO NOT LET WINNERS BECOME LOSERS WITHOUT EXPLANATION
============================================================

Create metrics:

winner_to_loser_count
winner_to_loser_usd_given_back
total_mfe_usd
realized_vs_mfe_capture_ratio
average_profit_capture_ratio
median_profit_capture_ratio
p25/p75 capture ratio

Define:

profit_capture_ratio =
realized_profit / maximum_favorable_excursion

for trades with meaningful positive MFE.

Report by:

strategy family
symbol
side
session
regime
exit method
exploration/champion stage

This lets us answer with evidence:

"Are we letting winners turn into losers?"

============================================================
I. SCREENSHOT REGRESSION SCENARIO
============================================================

Add a deterministic test scenario resembling:

EURUSD SELL +0.47
EURUSD SELL +0.24
EURUSD SELL +0.15
EURUSD BUY  -0.12
GBPUSD SELL +0.98
GBPUSD SELL +0.63

Do NOT assert that they must all close.

Instead verify:

- each ticket has independent thesis ownership;
- opposite EURUSD BUY/SELL exposure is intentional and independent;
- margin pressure is considered;
- MFE is tracked per ticket;
- existing winners receive a valid HOLD/LOCK/EXIT decision;
- no profitable ticket is ignored by profit management;
- the system explains why a winner remains open.

============================================================
J. SELF-HEDGING / CONFLICTING THESIS AUDIT
============================================================

The screenshot contains simultaneous EURUSD SELL and EURUSD BUY exposure.

This can be legitimate ONLY when backed by distinct independent hypotheses.

Before allowing opposing exposure on the same symbol:

prove:
different hypothesis IDs
different mechanisms/time horizons
independent invalidation logic
independent expected value
portfolio benefit after DOUBLE spread/cost

Otherwise block self-hedging.

Add metrics:

gross_long_exposure
gross_short_exposure
net_exposure
hedged_exposure
cost_of_internal_hedge

Do not consume margin to fight yourself without measured benefit.

============================================================
K. MARGIN PRESSURE
============================================================

Exploration is information gathering.

It should not consume most of a ~$100 DEMO account's margin.

Add exploration margin controls independent from max-position count.

Use broker-measured margin requirements.

Examples of controls to research/implement:

minimum free-margin reserve
minimum margin level
maximum exploration margin fraction

Do not choose thresholds solely to create more trades.

When margin pressure is elevated:

block new exploration entries first.

Then evaluate existing positions by remaining EV.

Do not automatically close a high-EV winner solely to make room for another
unvalidated experiment.

============================================================
L. BOOKS MUST ALSO INFORM EXITS
============================================================

Do not use the books only for entries.

Extract and test book knowledge relating to:

taking profits
letting winners run
trailing stops
structural exits
time stops
failed breakouts
momentum decay
MFE/MAE
risk/reward
volatility-dependent exits
scaling out
trend termination
mean-reversion completion

Each becomes an exit hypothesis.

DATA decides which exit policy works for each strategy/regime.

There should NOT necessarily be one universal exit system.

============================================================
M. NO SURVIVORSHIP / LOOKAHEAD
============================================================

Exit-policy research must remain point-in-time.

Never use information unavailable when the exit decision would have happened.

Use purged/time-aware OOS validation.

Keep sealed holdout governance.

Do not repeatedly optimize against the same holdout.

============================================================
N. PROFIT MANAGEMENT DOES NOT WEAKEN CHAMPION GATES
============================================================

A prettier equity curve is not proof.

Every exit challenger still needs:

costed expectancy > 0
PF > 1
adequate N
adequate losses
bootstrap lower bound > 0
payoff sanity
tail sanity
drawdown sanity
OOS stability
walk-forward stability
sealed holdout
demo canary

Do not promote an exit policy because it happened to bank this screenshot's
winners.

============================================================
O. HEARTBEAT / REPORTING
============================================================

Add:

open_floating_profit_usd
open_floating_loss_usd
open_mfe_usd
open_profit_given_back_usd

winner_to_loser_count
profit_capture_ratio

positions_with_profit_lock
positions_without_profit_lock

per ticket:

ticket
thesis
hypothesis
stage
pnl
mfe
mae
locked_profit
remaining_ev
exit_state

============================================================
P. CRITICAL CURRENT-CODE ISSUE
============================================================

Audit run_broker_paper.py.

Currently Intelligent Firehose explicitly bypasses:

quick_win closure
MFE giveback closure

because those branches use:

not intelligent_mode

Meanwhile max_hold_seconds is 0 and flatten_if_profit_usd is 0.

Do NOT simply remove "not intelligent_mode" and reuse the old CORE exit logic.

Build the proper intelligent per-thesis profit-management layer described above.

Exploration entries with target=None must NOT claim they have a
"quick-win exit" when Intelligent Firehose does not actually provide one.

Every exploration experiment must have an explicit executable exit plan.

============================================================
FINAL REQUIREMENT
============================================================

The Intelligent Firehose should answer for EVERY open profitable ticket:

WHY AM I STILL HOLDING THIS WINNER?

Example valid answers:
- remaining costed EV remains strongly positive
- target not reached and trailing invalidation protects X profit
- historical MFE analysis supports additional continuation
- only Y% of MFE has been given back
- regime and thesis remain intact

Examples of INVALID answers:
- because it has not hit the stop yet
- because intelligent mode disables quick-win
- because there is no target
- because we forgot to implement profit management

No winner should turn into a loser simply because the exit layer was absent.
