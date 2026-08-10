# Aegis book-to-code and project-health audit

Audit date: 2026-08-09  
Status: source/code audit, corrective implementation, exhaustive benchmark, and two new-strategy measurements complete.

## 1. Audit scope and source integrity

- Read all 36 Markdown files in `docs/trading/books/` at actionable-rule depth: entries, exits, filters, sizing, costs, execution, validation, and data requirements.
- Inspected all 38 originals in `books/`: 35 PDFs, one EPUB, and two small Markdown samples.
- The Steve Nison *Japanese Candlestick Charting Techniques* PDF (330 pages) and John Murphy *Technical Analysis of the Financial Markets* PDF (585 pages) are image-only. All 915 pages were rendered and OCR-scanned; 874 contained substantive text or chart material. Representative chart and text pages were visually checked.
- The two Jared Tendler Markdown extracts are duplicate copies and contain NUL/text-extraction artifacts.
- `market-structure.md` and `sample-author.md` are short synthetic samples, not full books.
- Four books discussed by `NEW_BOOKS_KAUFMAN_VOLMAN_JOHNSON_CHAN.md` are not present as full files: Bob Volman *Forex Price Action Scalping*, Perry Kaufman, Barry Johnson *Algorithmic Trading & DMA*, and Ernie Chan *Algorithmic Trading* (2013). The available full Chan book is *Quantitative Trading* (2008). Claims for the absent books can only be attributed to the repository digest and must not be described as full-book findings.
- Post-audit source: reviewed Roman Smirnov's 37-page *How to earn 1 million dollars with $100 in your pocket or win-win trading in the Forex market* PDF from Downloads, including every trading-parameter screenshot. Its detailed assessment is in `bot/reports/SMIRNOV_WIN_WIN_AUDIT.md`; the copyrighted source was not copied into the repository.
- Post-audit sources: fully read Marcel Robbinson's 61-page *High Win Rate Day Trading Setups* PDF and the image-only 66-page *Scalping is Fun — Book 2: Practical Examples* by Heikin Ashi Trader. Every page of the latter was rendered and OCR-read, and all actionable charts were visually checked. Their assessment is in `bot/reports/ROBBINSON_HEIKIN_ASHI_AUDIT.md`; neither copyrighted source nor its extraction was copied into the repository.
- No book text or OCR output was copied into the repository. The matrix below contains only short, original paraphrases of actionable ideas.

Priority key: **P0** blocks trustworthy measurement; **P1** is directly relevant to a cost-aware basket scalp; **P2** is useful after the primary path is sound; **P3** is process/context or not testable on the current OHLC feed.

Quality key: **good** means the coded rule materially matches the source and is testable; **partial** means a defensible proxy; **rough** means the name overstates fidelity; **absent** means no executable equivalent.

## 2. Book-to-code gap matrix

### Evidence, validation, execution, and portfolio construction

| Book / author | Actionable rule taught | Current Aegis mapping | Implementation quality | Missing test or defect | Priority |
| --- | --- | --- | --- | --- | --- |
| Kevin Davey — *Building Winning Algorithmic Trading Systems* | Freeze rules, use genuinely unseen data, walk-forward testing, enough trades, costs, Monte Carlo, and reject most candidates. | Parameter-search scripts, neighbor lookbacks, backtest summary. | Rough | Neighbor lookbacks overlap; no frozen holdout, walk-forward runner, Monte Carlo, parameter-stability surface, or selection-bias accounting. | P0 |
| David Aronson — *Evidence-Based Technical Analysis* | Objective rules, explicit null benchmark, data-mining controls, bootstrap/permutation inference, and no look-ahead. | Mechanical signal functions and next-bar entries. | Rough | No benchmark distribution, White Reality Check/equivalent, false-discovery control, confidence intervals, or leakage audit. Thousands of searched 100% configurations make this essential. | P0 |
| Ernie Chan — *Quantitative Trading* (2008) | Screen for real, stable statistical edges; include costs; test parameter and regime stability; control nonstationarity and portfolio risk. | `chan_bb_scalp`, `run_bakeoff.py`, fixed cost inputs. | Rough | `chan_bb_scalp` is a single-series Bollinger fade, not a tested stationary spread or portfolio. No half-life, cointegration, capacity, or rolling stability tests. | P0/P1 |
| Robert Carver — *Systematic Trading* | Combine normalized forecasts, volatility-target positions, diversify, buffer turnover, and slow down when costs dominate. | ATR stops and several trend/range signals. | Rough | No forecast scaling/capping, instrument risk normalization, diversification multiplier, turnover buffer, or shared portfolio volatility target. | P1 |
| Andreas Clenow — *Following the Trend* | Diversified breakout trend following, ATR/volatility sizing, portfolio-level exposure, accept frequent small losses, model impact. | Donchian 20/55 signals, ATR stops/trails. | Partial | Position sizing is per symbol and price-unit based; no shared capital, contract/pip conversion, portfolio volatility, correlation cap, or impact model. | P1 |
| Larry Harris — *Trading and Exchanges* | Spread, adverse selection, queue priority, market impact, order choice, and liquidity determine whether a scalp survives. | Fixed `spread_bps` and `slippage_bps`; next-open fill. | Rough | No bid/ask series, variable spread, commissions, queue, partial fill, impact, rejected order, or latency model. Tick/L2 claims require MT5/broker data. | P0/P1 |
| Van Tharp — *Trade Your Way to Financial Freedom* | Judge expectancy in R, opportunity count, position sizing, drawdown and ruin over a large sample; all-in sizing is ruin-prone. | `RiskEngine`, `HighRiskController`, expectancy/PF/DD fields. | Partial | Reported R excludes costs; no ruin/Monte Carlo distribution, SQN-style uncertainty, margin model, or minimum trade-count gate. | P0 |
| Sample risk basics | Fixed-fraction risk, always use stops, apply mean reversion only in ranges. | Risk percent, mandatory stops, ADX range gate. | Partial | The source is only a synthetic sample; it is not independent evidence. | P3 |
| Sample market structure | Liquidity/slippage matter; psychology and author disagreement require testing. | Fixed costs and notes. | Rough | Not a full source and no microstructure model. | P3 |

### Intraday, FX, and strategy rules

| Book / author | Actionable rule taught | Current Aegis mapping | Implementation quality | Missing test or defect | Priority |
| --- | --- | --- | --- | --- | --- |
| Andrew Aziz — *How to Day Trade for a Living* | Trade liquid names with relative volume; use ORB, VWAP, ABCD/flags; stop first; seek favorable R:R and manage partial exits. | `aziz_orb`, `aziz_vwap`, session OR/VWAP features. | Rough | Yahoo FX volume is zero/fabricated, so “VWAP” becomes an unweighted typical-price average. No scanner, RVOL, premarket levels, Level 2, partial exits, or stock universe. | P1/P3 |
| Peter Steidlmayer — *Steidlmayer on Markets* | Build TPO value/POC, initial balance, day type, initiating versus responsive activity, and single-print structure. | `steidl_ib_break`, `steidl_ib_fade`, IB fields and prior-value proxy. | Rough | “Value area” is prior-day range midpoint ±34%, not TPO/volume profile. No POC, TPO brackets, single prints, excess, or complete day-type logic. True test needs tick/time-at-price data. | P1/P3 |
| Gabriele Fabris — *The Price in Time* | Freeze the 07:00–08:00 GMT no-trading-zone, trade valid dual breakouts, filter range/session conditions, flatten at session end. | `add_fabris_ntz_features`, `sig_fabris_ntz`, flatten hook, small synthetic tests. | Good/partial | Validate daylight-saving/broker-time handling, exact instrument rules, same-bar ambiguity, and non-overlapping OOS windows. | P1 |
| Ed Ponsi — *Forex Patterns & Probabilities* | Separate trend/range regimes, use multi-timeframe trend, triangles/flags/squeeze, round-number behavior, and price targets large enough to cover spread. | `trend_pullback`, squeeze/breakout signals, session and cost gate. | Partial | `_htf_trend` is same-timeframe EMA state, not higher-timeframe data. Triangle/flag/round-number/boomerang rules are absent. | P1/P2 |
| Agustin Silvani — *Beat the Forex Dealer* | Respect dealer/session behavior, pivots and big figures, liquidity shifts, stop hunting, and weekend/event exposure. | UTC session filter. | Rough | No pivots/big figures, rollover spread spike, weekend flatten, event calendar, or executable bid/ask behavior. | P1/P3 |
| Laurentiu Damir — *Trade the Price Action* | Daily/4h directional context, lower-timeframe pullback, Fibonacci zones, candle confirmation, predefined R:R. | EMA “HTF” proxy, trend pullback, ATR R:R. | Rough | No actual resampled higher timeframe, Fibonacci zone, or exact confirmation sequence. | P1/P2 |
| Jim Brown — *Profitable Forex Trading Using High and Low Risk Strategies* | Indicator systems plus small fixed risk; the book also presents aggressive recovery/DCA methods with severe tail risk. | BB/RSI/MACD/EMA features and capped recovery/DCA modes. | Partial for safe rules; intentionally caged for dangerous rules | QMP/QQE rules are not exact. Recovery/DCA must remain a stress-test comparator, never the primary edge. | P2 |
| Roman Smirnov — *How to earn 1 million dollars with $100...* | XAUUSD previous-day/Friday high-low pending-order straddles, followed by opaque recovery/additional orders and basket profit/loss closure; a separate table assumes 25% monthly returns plus deposits. | Related Donchian/ORB/Fabris breakouts and capped DCA/recovery negative controls. | Partial for the breakout concept; intentionally absent for the no-stop grid | The compiled EA logic is undisclosed, screenshots show no per-trade SL and allow a 90% basket loss, and the return table is not evidence. Only a hard-stop OCO breakout can be tested honestly with MT5 ticks. | P3 / reject unsafe mode |
| Marcel Robbinson — *High Win Rate Day Trading Setups* | Combine regime filters with BB/RSI/Williams fades or HalfTrend/UT/KDJ trend signals and a 200-period trend filter. | BB, RSI, ADX, stochastic, ATR, slow EMA and multiple range/trend signals. | Partial | Seven recipes have no backtest, costs, sizing, complete stops, or fixed timeframe. Most depend on versioned TradingView community scripts whose formulas are not supplied; several written entry/exit rules contain contradictions. Exact replication is not auditable. | P2 |
| Heikin Ashi Trader — *Scalping is Fun, Book 2* | Fade exhaustion after shrinking Heikin-Ashi bars/doji at objective levels; confirm a color change, use tight structural and time stops, and switch to trend pullbacks after a dominant impulse. | Generic doji/range/trend/failed-break logic and `max_hold_bars`; no Heikin-Ashi transform. | Partial concept; exact setup absent | Heikin-Ashi prices are synthetic, chart/level selection is discretionary, and the only result is four uncosted trades at variable size. Build signal-only HA features but execute on MT5 bid/ask; test previous-day/round levels and non-performance exits on frozen OOS. | P1 MT5 |
| Nial Fuller — pyramiding extract | Add only to winners, move the unified stop, and keep total campaign risk controlled. | `pyramid.py` and backtest add logic. | Partial | Full original source is unclear; aggregate risk is not recomputed after every add, gaps/costs are not bounded, and each leg is not charged separately. | P1 |
| LR Thomas — *The 10XROI Trading System* | Higher-timeframe trend plus lower-timeframe pullback, small initial risk, asymmetric winners, reset sizing after a loss. | `thomas_10r` and Thomas compounding modes. | Rough | No true daily/hourly join, structural push/pull state, or realistic probability estimate for 10R targets. Aggressive compounding is unsafe without OOS edge. | P2 |
| James Windsor — *Holy Grail Forex Trading System* | Exact mechanical Forex rules and escalating risk claims. | Windsor sizing mode and historical experiments. | Rough | The strategy itself is not faithfully isolated; prior measured regime performance includes large drawdown. Loss escalation compounds model error and should be a negative-control test. | P2 |
| “Ultimate Forex Trading System” / Afshari | Pattern, volume-price, correlation, sentiment and confluence claims. | Generic `book_optimal` confluence only. | Rough/absent | The source's multiplied “probabilities” are not statistically valid. Exact pattern/correlation/sentiment inputs and independent validation are absent. | P2/P3 |
| Noble DraKoln — *Winning the Trading Game* | Treat trading as a complete framework: regime, liquidity, ATR risk, stops, time exits, and disciplined review. | ATR stops, session filters, `max_hold_bars`, journal. | Partial | No liquidity-state model, actual higher timeframe, or portfolio risk review. | P1/P2 |
| Alexander Elder — *The New Trading for a Living* | Triple Screen, Impulse System, Force Index, SafeZone stops, and strict 2%/6% risk limits. | `elder_impulse` proxy, EMA/MACD, risk fields. | Partial | No higher-timeframe screen, Force Index with meaningful FX volume, SafeZone stop, or enforced monthly 6% rule. | P2 |

### Technical analysis and discretionary structure

| Book / author | Actionable rule taught | Current Aegis mapping | Implementation quality | Missing test or defect | Priority |
| --- | --- | --- | --- | --- | --- |
| Jack Schwager — *Getting Started in Technical Analysis* | Trend/pullback/breakout rules, N-day patterns, stops, testing discipline, and costs. | Donchian, EMA, RSI, squeeze, ATR stops. | Partial | Named indicators are generic proxies, not exact rule studies; no N-day catalog, robustness surface, or OOS comparison. | P2 |
| Adam Grimes — *The Art and Science of Technical Analysis* | Market-structure failure tests, pullbacks, complex corrections/ABCD, disciplined trade management, and simulation of ruin. | Generic pullback/breakout signals. | Rough | No swing-state engine, failed-break/reclaim pattern, complex correction, trade-management study, or Monte Carlo. The failed-break rule is a useful P1 candidate. | P1 |
| Edwards, Magee & Bassetti — *Technical Analysis of Stock Trends* | Confirm breakouts and classical patterns with trend/volume context; define measured objectives and protective stops. | EMA/Donchian/ATR proxies. | Rough | No objective head-and-shoulders/triangle/rectangle/double-top catalog, confirmation rules, or reliable FX volume. | P2 |
| Thomas Bulkowski — *Encyclopedia of Chart Patterns* | Precisely define, measure, rank, and retest pattern variants, failures, pullbacks and busted patterns with costs. | No dedicated implementation. | Absent | Daily-stock pattern statistics cannot be imported as intraday-FX probabilities. Each formalized pattern needs new M1/M5 tests and multiple-testing controls. | P2 |
| Steve Nison — *Beyond Candlesticks* | Use Japanese patterns only with trend/support context; test three-line break, Renko/Kagi and disciplined stops/targets. | No named Nison strategy. | Absent | Requires objective encodings and separate tests; Renko/Kagi need a sampling design that avoids look-ahead. | P2 |
| Steve Nison — *Japanese Candlestick Charting Techniques* | Candles are subjective guideposts, not guarantees; define trend first, combine reversal patterns with support/resistance and confirmation. | OHLC exists; no candle catalog. | Absent | Encode exact patterns without hindsight, then test filtered versus unfiltered. Standalone candle shape is not evidence of edge. | P2 |
| Jeremy du Plessis — *Point and Figure* | Define box/reversal construction, breakouts, counts, stops, and validate parameters across regimes. | None. | Absent | P&F transformation and count rules need their own stateful engine and walk-forward test. Not the first choice for M1 frequency. | P2 |
| John Murphy — *Technical Analysis of the Financial Markets* | Trend/support/channel/pattern/volume/oscillator/cycle framework; money management decides size; robust systems should use few parameters and cross-market tests. | Broad indicator feature set and simple bake-off. | Partial | No channel/fan/gap/pattern/cycle breadth, no robust cross-market portfolio test. The book's older “add costs later” workflow is weaker than Davey/Aronson and should not control validation. | P1/P2 |
| John Murphy — *Trading with Intermarket Analysis* | Cross-asset relationships are regime-dependent and should be monitored through changing correlations. | None. | Absent | No synchronized rates, dollar, commodity, equity, and volatility feeds; no rolling correlation/regime features. | P3 |

### Risk, psychology, and trader case studies

| Book / author | Actionable rule taught | Current Aegis mapping | Implementation quality | Missing test or defect | Priority |
| --- | --- | --- | --- | --- | --- |
| Mark Douglas — *The Disciplined Trader* | Execute a predefined plan, accept risk before entry, and separate process from individual outcome. | Config-driven rules and journal. | Partial | No plan-compliance, skipped-signal, manual-intervention, or rule-violation metrics. | P3 |
| Mark Douglas — *Trading in the Zone* | Think in distributions; evaluate a fixed sample rather than demanding certainty from each trade. | Batch backtests. | Partial | No frozen 20/100-trade experiment protocol, confidence interval, or live-vs-model drift monitor. | P2/P3 |
| Jared Tendler — *The Mental Game of Trading* | Record A/B/C performance, recognize recurring error patterns, and use a mental hand-history process. | Basic trade journal. | Rough | Duplicate/corrupt extracts need library cleanup; no A/B/C process fields or behavioral review workflow. | P3 |
| Edwin Lefèvre — *Reminiscences of a Stock Operator* | Let price confirm the premise, probe before scaling, add to winners rather than losers, respect liquidity/execution, and ring-fence capital. | Winner-only pyramid and high-risk “protected” bookkeeping. | Partial | No probe-size state, liquidity-aware fills, or actual capital separation. Correct market view can still lose through execution, which the simulator barely models. | P1/P3 |
| Jack Schwager — *Stock Market Wizards* | Edges differ, but risk limits, catalysts/context, time stops, specialization, and process consistency recur. | Stops, time exit, heterogeneous signals. | Partial | Many interviewed edges depend on fundamentals, discretionary research, options, or short infrastructure not present in OHLC. Treat as process evidence, not rules to fake-code. | P3 |
| Jack Schwager — *The New Market Wizards* | Protect capital, size small relative to uncertainty, cut losses, and match method to temperament/market structure. | Risk engines and stops. | Partial | Exact interviewed edges are often undisclosed or nonportable; use the common risk constraints, not invented entries. | P3 |

### Digest-only books not available in full

| Book / author | Digest-level idea | Current Aegis mapping | Implementation quality | Required next evidence | Priority |
| --- | --- | --- | --- | --- | --- |
| Bob Volman — *Forex Price Action Scalping* | 20 EMA plus compact price-action setups such as DD/FB/SB/BB/RB, very tight spread sensitivity, roughly scalp-sized targets. | `volman_scalp`: two-doji/two-bar box break around EMA20. | Rough | Obtain the actual book or an authorized rule specification; test trigger-level tick/M1 sequencing and real bid/ask. Do not call the current proxy a faithful Volman implementation. | P1 |
| Perry Kaufman | Adaptive/noise-aware trading and efficiency concepts per digest. | None. | Absent | Obtain the exact title/source, encode efficiency/adaptive-speed rules, and test against fixed-speed controls. | P2 |
| Barry Johnson — DMA | Market microstructure, order-book execution, latency, queue and impact per digest. | Fixed spread/slippage only. | Absent | Requires broker tick/L2/order-event data and an execution simulator or Windows MT5 demo telemetry; OHLC cannot validate DMA/HFT behavior. | P0/P3 |
| Ernie Chan — *Algorithmic Trading* (2013) | Mean-reverting spreads/baskets, stationarity/half-life and conservative Kelly concepts per digest. | Misnamed single-symbol `chan_bb_scalp`. | Rough | Obtain the full source or define rules independently; build synchronized multi-symbol spread tests, rolling hedge ratio, stationarity and shared-capital sizing. | P1 |

## 3. Project health check

This section records the defects found at audit time. Remediation completed during this work is summarized in section 9.

### P0 — results can be wrong or materially misleading

1. **Historical daily-loss state uses the wall clock.** `run_backtest()` updates risk with the bar time at `bot/aegis/backtest.py:65`, but `RiskEngine.allow()` immediately calls `update(equity)` without that time at `bot/aegis/risk.py:47-50`. A historical day can therefore be replaced by today's UTC date before the daily-loss calculation.
2. **Reported expectancy R is gross, not cost-adjusted.** P&L subtracts round-trip spread/slippage at `bot/aegis/backtest.py:145-150`, but `r` uses raw price move divided by stop distance. Ranking and reporting can show positive E[R] while net P&L is negative.
3. **An open final position disappears.** The loop ends with no forced liquidation or mark-to-market at `bot/aegis/backtest.py:251-257`; neither trade count nor final equity reflects the open risk.
4. **Intraday data can silently become daily data.** `fetch_ohlcv()` falls back from an empty intraday request to `1d` at `bot/aegis/data.py:41-50` but returns no actual-timeframe metadata or validation. A nominal M1/M5 test may therefore run on daily bars.
5. **The reported “basket” is not a portfolio.** `measure_firehose.py` runs eight independent $100 single-symbol backtests, adds trade counts, and divides by the maximum calendar span. It does not share equity, enforce simultaneous-position limits, net USD exposure, or compute basket PF/DD/equity.
6. **Paper and backtest accounting disagree.** `PaperBroker.close()` at `bot/aegis/paper.py:36-41` subtracts no spread/slippage. The paper loop can repeatedly process the same closed bar and re-enter it because there is no last-processed timestamp or signal de-duplication.
7. **Feature preparation is not idempotent.** The recent column-drop safeguard in `features.py` omits profile fields such as `prior_va_hi/lo`; a second `prepare()` creates merge suffixes and later raises `KeyError: 'prior_va_hi'`. Some scripts prepare once and backtest again, so this must be deterministic.
8. **No executable FX sizing model exists.** Units are generic `risk_money / price_distance`. There is no contract size, account/base/quote conversion, pip value, leverage, margin requirement, minimum lot, lot step, margin call, or broker stop-distance rule. A $100 result may request an impossible order.

### P1 — material realism or strategy-fidelity defects

1. Costs are constant basis points only. There is no commission, session-dependent spread, rollover/event spike, market impact, latency, partial fill, gap slippage, or stochastic cost stress. `add_spread_proxy()` creates a `spread` column that the backtester never reads.
2. Entries occur at the next bar open, but an entry cannot stop or target within that entry bar. This is a large sequencing assumption for M1 scalps.
3. If SL and TP are both inside a later OHLC bar, the engine always selects SL first. That conservative rule is defensible, but the number of ambiguous bars and best/worst bounds are not reported.
4. Pyramiding adds the original full units at each layer. It charges one final round-trip cost on averaged entry rather than per leg, and the claim that aggregate risk remains `<=1R` is not recomputed under gaps/costs.
5. The ensemble says it selects the “strictest” stop, but a long takes the minimum stop and a short the maximum (`session_algos.py:605-616`), which are the farthest/loosest stops.
6. Ensemble members suppress every exception (`session_algos.py:587-590`), hiding data and strategy defects.
7. `_htf_trend()` is same-timeframe EMA state (`session_algos.py:408-417`), despite multi-timeframe claims in the docstrings.
8. Aziz VWAP substitutes volume `1.0` for zero FX volume (`profile_features.py:97-109`), so it is not volume-weighted market information.
9. Steidlmayer value is a price-range proxy (`profile_features.py:163-187`), not Market Profile/TPO value.
10. Firehose's required-column check executes `pass` rather than rejecting incomplete rows (`session_algos.py:711-715`).
11. High-risk “protected principal” is an accounting floor inside one equity value, not money held in a separate account. Costs/gaps can cross it.
12. `max_daily_loss_percent: 100`, `max_total_drawdown_percent: 100`, 100% risk, and nearly-zero equity floors make the tuned/all-in configs effectively unprotected.

### P2 — methodology, reporting, and maintenance gaps

1. The 100% search tested thousands of parameter sets on a short window. Adjacent 45/60/75/90-day lookbacks overlap, so they are not independent OOS samples. `5,553` perfect hits is evidence of a broad multiple-search problem, not evidence of certainty.
2. There is no data snapshot/version hash. Rerunning a Yahoo lookback later changes the exact window, so results are not reproducible.
3. Existing reports omit required fields. The firehose report lacks E[R], PF, max DD, exact start/end timestamps, start equity and halt reason; the tuned report lacks PF, DD, exact timestamps and trades/day.
4. `VIDEO_100_ATTEMPT.md` reports an actual all-in result of `$184.92` but separately prints idealized 0.1R compounding math ending at `$555.99`. The two are easy to confuse and the discrepancy is not reconciled.
5. `VOLMAN_CHAN_BASKET.md` and `config_volman_chan_basket.yaml` say Kaufman/Johnson PDFs are image scans. They are actually absent from `books/`.
6. The repository has test functions, but `pytest` is not installed in `bot/.venv`; `unittest discover` finds zero because the tests are plain functions. Running the two files directly passes, but there is no standard test command that collects them.
7. Configs and strategy names overstate fidelity (`chan_bb_scalp`, “HTF,” Market Profile, “all_books”). Reports should distinguish exact rule, OHLC proxy, and digest-only inspiration.

## 4. Current measured baselines — as recorded, before P0 fixes

These are historical observations, not forward claims. `E[R]` in current reports is gross of costs because of the defect above.

| Experiment | Sample window recorded | Trades | Trades/day | WR | E[R] | PF | Max DD | Start -> end equity | Halt | Audit interpretation |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| `config_tuned_100wr.yaml`, EURUSD 1h | Yahoo rolling 60d; exact timestamps omitted | 29 | ~0.48/calendar day | 100.0% | 0.150 gross | not recorded | not recorded | $100 -> $533.75 | none recorded | Best recorded perfect sample, but selected after thousands of trials, all-in risk, overlapping neighbors, and incomplete reporting. At 90d: 36 trades, 97.2% WR. |
| `config_video_firehose.yaml`, 8 FX pairs M1 | Yahoo rolling 7d request; reported spans 8.92–8.94 calendar days | 1,871 total across separate runs | ~209.4 aggregate | 56.7–66.5% by pair | not recorded | not recorded | not recorded | Eight separate $100 accounts ended about $0.96–$12.30 | not recorded | High frequency achieved, but every pair lost most of its equity. This is negative expectancy/ruin, not a valid basket equity curve. |
| Video 100% attempt, all-in | Exact timestamps/timeframe omitted in report | 18 | not recorded | 100.0% | not recorded | not recorded | not recorded | $100 -> $184.92 | none | Short, selected perfect window; report's separate `$555.99` ideal math is not the measured equity. |
| Volman/Chan proxy hunt | 5m, nominal 14d; exact timestamps omitted | best count not recorded | not recorded | best ~70% | not recorded | not recorded | not recorded | best ~$100 -> $35 at 20% risk | not recorded | 36 configurations with >=5 trades; zero 100% hits. Aggressive sizing amplified a losing cost/R:R profile. |

## 5. What the evidence rules out

- No available book teaches a defensible guarantee of 100% future wins.
- The current 29/29 sample does not establish a permanent edge: a neighboring longer lookback already contains a loss, the search tried thousands of configurations, and the window boundaries overlap.
- A target of `$1,000 profit per day from $100` is a 1,000% daily return target. No measured Aegis strategy supports it; the required leverage and path risk imply near-certain eventual ruin if attempted repeatedly.
- High win rate can be manufactured historically with a wide stop and tiny target. It transfers probability into rare, very large losses; it does not create free expectancy.
- OHLC can test signal logic and conservative fill bounds. It cannot establish queue priority, spread at the trigger, sub-bar path, adverse selection, DMA latency, or thousands of tick round-trips.

## 6. Primary design for approval

### Recommended: Cost-Aware Failed-Break Basket (CAFB)

Primary objective: **high-frequency basket scalping with non-ruin, positive net expectancy**, while still measuring win rate. This is stronger than optimizing directly for 100% because it forces the strategy to survive costs and an unseen sample.

The book synthesis is:

- Harris: reject a trade unless expected movement comfortably exceeds stressed execution cost.
- Volman digest + Grimes: enter only after compression/pullback and a failed break/reclaim, rather than every one-bar break.
- Murphy/Nison: define regime and structure before treating a bar pattern as a trigger.
- Carver/Clenow: normalize risk across instruments and treat the basket as one portfolio.
- Tharp/Davey/Aronson/Chan: optimize net expectancy with opportunity count, freeze OOS data, penalize multiple searches, and size only after the edge survives.

Proposed signal, testable on M1/M5 OHLC:

1. Use M5 context for an M1 trigger (or M15 context for M5): EMA slope/stack plus ADX and ATR-percentile state. This is a real resampled higher timeframe, not the current same-frame proxy.
2. During London/New York liquid hours, detect a short compression box near EMA20 followed by a one-side break that closes back through the broken boundary. Trade the reclaim toward the box midpoint/opposite boundary only when it agrees with the permitted regime. Also test a continuation branch separately; never blend its statistics silently.
3. Require target distance to exceed stressed round-trip cost by a configurable multiple. Exclude rollover and bars with an excessive high-low spread proxy; MT5 later replaces this with actual bid/ask.
4. Use a structural stop beyond the failed-break extreme plus a cost/volatility buffer, a predefined target, and a short time stop. Report OHLC bars where SL and TP are both possible.
5. Run one shared `$100` basket account. Limit concurrent positions, portfolio heat, per-currency directional exposure, leverage, and minimum executable lot. Risk variants are evaluated on frozen signals after the signal edge is selected.

Alternatives rejected as the primary:

- **Firehose continuation on every M1 break:** highest frequency, but the measured implementation destroyed nearly all equity on all eight pairs.
- **Wide-stop/tiny-target all-in mean reversion:** easiest way to obtain a short historical 100% sample, but low frequency, hidden left-tail risk, selection bias, and non-executable all-in sizing make it unsuitable for robust compounding.

### Required validation protocol

1. First fix P0 accounting and write regression tests.
2. Save immutable per-symbol data snapshots with requested and actual interval plus exact UTC timestamps.
3. Benchmark every executable strategy: the 17 distinct functions behind the 19 registered names, the generic range/trend strategy, `scalper_2h`, and all 11 catalog strategies. Aliases are reported once, not counted as new algorithms.
4. Use non-overlapping chronological development, validation, and frozen holdout segments. Do not select parameters on the holdout.
5. Report at 1.0x, 1.5x and 2.0x costs; conservative same-bar ordering; shared-capital portfolio results; Wilson interval for win rate; and bootstrap uncertainty for net mean R.
6. Minimum promotion gate: at least 100 closed basket trades, positive cost-adjusted E[R] and PF > 1 on frozen OOS at 1.5x costs, no bankruptcy/margin breach, and no single pair responsible for most profits. The 2.0x result may be negative but must be shown.
7. Only then compare 1%, 2%, 5%, 10% and 20% risk overlays. Any more aggressive mode is labeled a ruin stress test, not a recommended config.

The final report must include, for every promoted candidate: exact sample timestamps, requested/actual interval, symbols, trades, trades/day, WR plus confidence interval, net E[R], PF, max DD, start/end equity, cost assumptions, ambiguity count, and halt reason.

## 7. Short Windows MT5 tick path

If the OHLC candidate passes its gate, the Windows validation path is:

1. Install 64-bit MetaTrader 5 and a broker demo; enable algorithmic trading and select the exact symbols/account currency.
2. In 64-bit Windows Python, install `MetaTrader5`, Aegis dependencies, and run a connectivity script that records terminal/account/symbol metadata. The MT5 Python package is not expected to work on macOS ARM.
3. Pull UTC M1 bars and `copy_ticks_range` bid/ask ticks into immutable Parquet snapshots. Record broker, server timezone, digits, point, trade contract size, volume min/max/step, stops level, spread, and swap/commission schedule.
4. Add an `MT5DataProvider` that returns requested/actual interval metadata and a `MT5ExecutionModel` that uses bid for sell fills, ask for buy fills, real volume steps, margin checks, order rejection, and measured slippage.
5. Replay signals offline first with tick-path SL/TP ordering. Then run shadow mode, then minimum-lot demo paper mode. Compare expected versus actual fill, spread, rejection, latency, and missed-trade distributions.
6. Do not enable aggressive sizing unless the demo OOS sample still passes the same net-expectancy gate. Add terminal-side equity, daily-loss, portfolio-heat, stale-data, disconnect, and spread-spike kill switches.

## 8. Verification performed during the audit

- `bot/tests/test_fabris_fuller_unit.py`: passed when run directly.
- `bot/tests/test_high_risk_unit.py`: passed when run directly.
- The two cases in `tests/test_extract.py`: invoked directly and passed.
- `python -m pytest`: unavailable because `pytest` is not installed in `bot/.venv`.
- `unittest discover`: zero tests collected because current tests are plain functions.
- `git diff --check`: passed for the existing working tree.
- Existing modified/untracked strategy, config, report, and CSV files were treated as user-owned and not overwritten.

## 9. Implementation and final measured outcome

### Corrections implemented

- Historical bar time now flows through `RiskEngine.allow()`; total-drawdown halts persist across day changes.
- Single-symbol and basket R multiples include spread, slippage, and optional commission.
- Open positions are liquidated and charged at EOF; same-bar ambiguity is counted; bankruptcy/negative-balance protection is explicit.
- Feature preparation is idempotent across indicator, profile, CAFB, and pulse columns.
- Intraday downloads no longer silently fall back to daily bars; requested/actual interval metadata is attached.
- Paper closes now charge the same cost inputs, reject duplicate closed bars, and pass bar time into risk checks.
- A chronological shared-equity basket engine now enforces position count, heat, currency exposure, leverage, minimum units, and unit step. Oversized requests are capped to available heat/leverage before being rejected.
- Added the Cost-Aware Failed-Break Basket and EMA/ATR Pulse Basket, synthetic no-look-ahead/cost tests, configs, tuning scripts, immutable Yahoo snapshots, and complete reports.

### Exhaustive benchmark result

The corrected shared-capital benchmark attempted every distinct registered function, the generic regime engine, `scalper_2h`, and all 11 catalog strategies on four USD-quoted FX pairs. The M5 data ran from 2026-05-18 23:00 UTC through 2026-08-07 21:25 UTC with non-overlapping 60/20/20 development, validation, and holdout segments.

- No existing strategy had positive net E[R] in all three segments.
- No existing strategy achieved 100% WR on holdout with at least one trade.
- The closest positive holdout was `thomas_10r`: 15 trades, 0.95/day, 46.7% WR, net E[R] +0.008, PF 1.03, max DD 7.1%, `$100 -> $100.33`. Its development segment was materially negative, so it is not promoted.
- Firehose holdout: 139 trades, 8.81/day, 52.5% WR, net E[R] -0.157, PF 0.49, max DD 30.5%, `$100 -> $69.77`, halted on max drawdown.

### New strategy results

- CAFB M5 frozen holdout: 11 trades, 0.7/day, 54.5% WR, net E[R] -0.328, PF 0.56, max DD 5.3%, `$100 -> $97.03`.
- CAFB M1 frozen holdout: 12 trades, 8.7/day, 41.7% WR, net E[R] -0.629, PF 0.37, max DD 4.1%, `$100 -> $96.92`.
- Pulse M5 frozen holdout: 9 trades, 0.6/day, 66.7% WR, net E[R] -0.086, PF 0.22, max DD 1.6%, `$100 -> $98.63`.
- Pulse M1 frozen holdout: 27 trades, 19.6/day, 29.6% WR, net E[R] -0.125, PF 0.17, max DD 3.8%, `$100 -> $96.30`.
- Across 288 CAFB and 432 Pulse parameter/timeframe configurations, neither new family produced a 100% frozen holdout or a candidate positive on both development and validation with adequate evidence.

### Corrected 1h selected-sample result

The original `config_tuned_100wr.yaml` parameters were re-measured without re-tuning on fresh 1h data:

- Exact 90-day sample: 2026-05-10 23:00 UTC to 2026-08-07 21:00 UTC.
- 29 trades, 0.33/day, 100% observed WR; 95% Wilson lower bound 88.3%.
- Net E[R] +0.060, PF infinite because no observed loss, max closed-equity DD 0%.
- At modeled 100% risk: `$100 -> $533.75`, historical arithmetic profit `$4.88/calendar day`.
- At 20% risk on the 60-day slice: `$100 -> $131.55`, `$0.53/calendar day`.
- At 1.5x costs the 60-day cost gate admitted only one trade; at 2x costs it admitted zero.

This is still the only observed 100% sample, but it is a previously selected rolling sample, not frozen OOS, is far below firehose frequency, is highly cost-sensitive, and the single-symbol engine does not prove its all-in units are broker-executable.

### Decision

No high-frequency strategy is promoted. Continuing to tune the same Yahoo windows until they display 100% would be data snooping. The strongest measured current action is to keep the corrected 1h profile as a low-frequency research control at small risk and move the firehose research to new Windows MT5 tick/bid-ask data. Aggressive sizing is not enabled because every adequately sampled high-frequency candidate has negative net expectancy.

Detailed results:

- `bot/reports/CAFB_BASKET.md`
- `bot/reports/PULSE_BASKET.md`
- `bot/reports/TUNED_100WR_CORRECTED.md`
