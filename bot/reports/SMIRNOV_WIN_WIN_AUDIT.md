# Roman Smirnov *Win-Win Forex* - Aegis audit

Audit date: 2026-08-09  
Source reviewed: complete 37-page PDF in Downloads, cross-checked against the matching FB2 text and the trading-parameter screenshots.  
Decision: **do not add the proprietary EA or its no-stop recovery sizing to Aegis.** The only independently testable signal ingredient is a conventional previous-session range breakout, which Aegis already represents through related breakout strategies.

## What the book actually specifies

| Mode | Entry framework | Position/exit framework visible in the book | Audit interpretation |
| --- | --- | --- | --- |
| Daily semi-automatic | On XAUUSD, around 20:00 Moscow time, draw a buy level at the current daily high and a sell level at the current daily low. The EA converts the lines into pending orders. | Screenshot inputs include `TP=150`, `NextOrderLevel=1`, `Razv_Work=true`, `Razv_TP=150`, `Razv_SetLevel=10`, `Lots=0.01`, `AddLots=0.01`, and `StopMaxLots=100`. | A daily-range breakout straddle plus undisclosed additional/reversal-order logic. `StopMaxLots` is a lot cap, not a price stop. |
| Weekly semi-automatic | After Friday closes, place the two levels at Friday's high and low and leave the EA active for the following week. | Screenshot inputs include `TP=500`, `NextOrderLevel=5`, `Razv_TP=500`, `Razv_SetLevel=10`, and initial/additional lots of `0.01`. | A Friday-range breakout with the same opaque recovery engine. |
| Weekly+ | Start another instance on the same XAUUSD account each successive week, using four terminals. | The screenshots use separate IDs and increase lots/additional lots from 0.01 through 0.04. There is no disclosed stop-loss rule. | Four overlapping, highly correlated gold campaigns. This increases exposure; it is not diversification. |
| Automatic | Attach the compiled `soft_demo_Avtomat` EA to XAUUSD M1 and allow DLL/external-expert imports. | The internal signal that replaces the manually drawn levels is not disclosed. | Not reproducible from the book. It is a black-box executable, not a strategy specification. |
| Automatic+ | Start four automatic XAUUSD instances on successive weeks and increase `Lots`/`AddLots`. | Examples escalate to 2.5/3.0, 4.0/4.5, and 6.0/6.0 lots. A separate close EA uses `PercentProfit` of 100% or 500% and `PercentLoss=90`. | No-stop, path-dependent basket recovery with permission to lose 90% of the account before closing. The screenshots visibly show `S/L=0.00`. |

`Razv` appears to denote reversal/recovery behavior, but the book does not define its order-state machine. The exact behavior of `SuperFeature`, order spacing, cancellation, reversal, additional entries, gaps, and simultaneous triggers is absent. The compiled EA/source code is not present in Downloads.

## Why the displayed win rate is not a disclosed edge

- Individual trades have no visible stop loss. Losses can remain floating while small winners are closed, which can make closed-trade win rate look excellent without improving account expectancy.
- The account-level close permits a 90% loss. A 90% drawdown requires a 900% gain merely to recover.
- Four weekly instances trade the same XAUUSD account and directionally correlated price path. Their risk stacks rather than diversifies.
- The book reports screenshots/examples, not a complete trade ledger, broker statement, sample window, costs, spread, slippage, profit factor, expectancy, or maximum floating drawdown.
- The text itself says the trading modes need at least a $1,000 account or a $150 cent account. That does not validate the title's $100 premise.
- Enabling DLL and external-expert imports for an unverified downloaded binary creates a computer/account-security risk. It should not be run on the trading machine without source review and isolation.

## The million-dollar table

The table assumes 25% profit every month plus a new $100 deposit every month for 36 months. Its arithmetic follows approximately:

`B[n+1] = 1.25 * B[n] + 100`

Starting at $100, that recurrence reaches about $1.54 million after 36 months. This is an arithmetic scenario, not measured trading evidence. It assumes:

- 25% every month without a losing month;
- reinvestment without withdrawals, margin limits, or capacity limits;
- $3,600 of additional deposits on top of the initial $100;
- no spread, commission, slippage, tax, outage, or adverse execution.

Twenty-five percent monthly compounds to roughly 1,355% per year. In the first month it is only $25, about $0.83 per calendar day before costs; it does not demonstrate the requested $50 per day from $100.

## Book-to-code mapping

| Book rule | Existing Aegis coverage | Quality / action |
| --- | --- | --- |
| Previous-day or Friday high/low breakout | Donchian, Aziz ORB, Fabris NTZ and breakout catalog rules | The broad concept is already covered. A precise previous-session comparator could be tested, but it is not a novel edge. |
| Pending buy/sell straddle | Aegis currently models directional next-open signals, not broker-native stop orders | Requires bid/ask tick replay, OCO semantics, gaps, stop levels and margin. OHLC cannot reproduce both-trigger sequencing faithfully. |
| Repeated/additional recovery orders | `HighRiskController` contains capped recovery/DCA negative controls | Aegis correctly forbids the book's true no-stop grid. Do not weaken this protection. |
| Basket profit/loss close | Portfolio drawdown/daily-loss halts exist; profit-lock behavior is available as a future execution feature | A profit close changes realization timing, not the underlying expectancy. The book's 90% loss threshold is unacceptable. |
| VPS/MT4 setup | Covered operationally by the Windows deployment plan | Operational advice only; no trading edge. |
| Fixed 25% monthly compounding table | No strategy mapping | A financial projection is not an entry, exit, or validated return process. |

## What can be tested honestly

A transparent **previous-session OCO breakout comparator** may be useful as a negative/control experiment:

1. Freeze the completed D1 or weekly high/low.
2. Place broker-valid stop entries outside both boundaries after adding actual spread and a volatility buffer.
3. Cancel the opposite side after one fill; allow at most one campaign per session.
4. Use a finite structural stop, time exit, and 1%-2% account risk. Never reproduce the no-stop recovery grid.
5. Test XAUUSD with MT5 bid/ask ticks, broker lot steps, margin, gaps, commissions, swaps, and chronological shared equity.
6. Require positive net E[R], PF above 1, acceptable drawdown, and stability on a frozen holdout at stressed costs before considering it.

The proprietary recovery EA cannot be faithfully tested from M1/M5/1h OHLC. Its outcome depends on intrabar trigger order, real bid/ask spread, gaps, exact add/reversal rules, and margin liquidation. Without source code or a complete mechanical specification, coding an imitation and attributing its result to the book would be false precision.

## Final contribution to Aegis

This book does **not** improve the primary Aegis strategy or support a 100% win-rate claim. It reinforces two controls already present in the project:

1. Report open/floating equity and maximum drawdown, not just closed winners.
2. Reject any high-win-rate method whose losses are deferred through no-stop grids, recovery orders, or extreme basket-loss thresholds.

No trading code or live configuration was added from this source.
