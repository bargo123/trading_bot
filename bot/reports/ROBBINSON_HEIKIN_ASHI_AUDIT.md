# Robbinson and Heikin-Ashi additional-book audit

Audit date: 2026-08-10  
Status: both books fully read and mapped to Aegis; no strategy promoted without a backtest.

## Source coverage

- Marcel Robbinson, *High Win Rate Day Trading Setups*: all 61 pages read from the text-bearing PDF (6,016 extracted words). The indicator and strategy pages, including the examples for all seven combinations, were also visually checked.
- Heikin Ashi Trader, *Scalping is Fun — Book 2: Practical Examples*: the 66-page PDF is image-only. Every page was rendered and OCR-read (9,058 words), and the setup, trade-management, results, support/resistance, round-number, and trend-day charts were visually checked.
- Neither PDF, its extracted text, nor its OCR was copied into this repository. This report contains only original paraphrase and audit conclusions.

## Book-to-code gap matrix

| Source | Actionable rule | Current Aegis mapping | Quality | Missing test / defect | Priority |
| --- | --- | --- | --- | --- | --- |
| Robbinson | Match the signal family to the regime: Bollinger/RSI/Williams-style fades when ADX or a consolidation filter says range; HalfTrend/UT/KDJ-style entries with a 200-period trend filter in directional markets. | `features.py` supplies BB, RSI, ADX, stochastic, ATR and a configurable 200-period slow EMA. `sig_hw_range`, `sig_rsi_cross`, `sig_breakout_adx`, `sig_trend_pullback`, and `sig_chan_bb_scalp` cover most of the economic idea. | Partial, and stronger than a literal port because Aegis includes stops, costs and next-bar execution. | The book depends on versioned TradingView community indicators without providing formulas or source. Exact HalfTrend, UT Bot, KDJ-J, KAMA, HMA/MFI, pivot bands, Reversal Finder and the consolidation filter are absent. A literal historical replication could repaint or differ by script version. | P2; do not promote from the book alone |
| Heikin Ashi Trader | After a strong run, look for shrinking Heikin-Ashi bodies/doji at an objective level, then enter after a completed opposite-color candle; exit on renewed color reversal, a technical target, a hard stop, or early non-performance. Avoid countertrend entries after a dominant impulse and favor pullbacks in the higher-timeframe direction on trend days. | Aegis has real OHLC, ATR, a generic doji proxy, `max_hold_bars`, range/trend signals, and rough prior-value/session structure. CAFB already covers failed-break/reclaim logic. | Conceptually partial; the actual Heikin-Ashi transform, previous-day extremes, round-number distance and early non-performance exit are absent. | Heikin-Ashi prices are synthetic and cannot be used as executable fills. Signal columns must be separate from real bid/ask execution. The author's chart choice and level selection are discretionary, and Yahoo M1 FX can contain degenerate bars. Tick/M1 broker data is required for a credible scalp test. | P1 MT5 research candidate |

## What the books actually add

### Robbinson

The seven strategy recipes are:

1. Bollinger Bands + UT Bot + 200-period trend filter.
2. HalfTrend breakout + consolidation/trend filter + 200-period trend filter.
3. MFI(21) crossing an SMA(18) + HMA(65) + 200-period trend filter.
4. Bollinger reversal + Reversal Finder while the consolidation filter is below 50.
5. Pivot bands(20) + Williams %R + ADX below 25.
6. RSI(5) + Bollinger Bands + ADX below 25.
7. UT Bot (key value 3, ATR period 30) + KDJ + 200-period trend filter.

The reusable idea is regime-conditioned confluence, which Aegis already has in simpler, auditable form. The source supplies no sample window, trade count, win rate, expectancy, profit factor, drawdown, spread, slippage, commission, position sizing, or complete stop specification. It therefore contributes hypotheses, not measured evidence.

There are also rule-quality warnings: one KDJ short-exit instruction repeats the bearish crossover; an Angle Attack Follow Line short rule says “buy”; Williams %R overbought/oversold labels and exits are inconsistent; and indicator numbering is duplicated. Those errors make an automatic literal port unsafe.

MFI is not a sound priority on the current Yahoo FX feed because volume is zero or a synthetic proxy. It should only be tested after MT5 tick volume or another defensible volume series is available. Standard KAMA can be implemented independently as a later adaptive-filter control, but the book does not specify enough to reproduce its pictured TradingView script exactly.

### Heikin Ashi Trader

The mechanical core that can be formalized is:

- Construct Heikin-Ashi signal bars only from completed real OHLC bars.
- Require a measurable impulse, several same-color bars, then body contraction or a doji near a predefined level such as the previous-day high/low or a round number.
- Confirm with the first completed opposite-color Heikin-Ashi bar and enter on the next executable real bid/ask price.
- Place a structural hard stop beyond the real-price extreme. Never widen it.
- Exit at the first opposite color change, a predefined real-price target, or a short bar-count non-performance limit.
- Disable countertrend fading after an objectively dominant impulse; test a separate trend-pullback branch rather than mixing the statistics.

The book's only numerical trading sequence is one discretionary EUR/USD morning: four trades, three wins and one loss (75% observed win rate), +26 gross pips, and EUR782 gross. It changes size from one standard lot to five lots, does not state the account equity, and omits spread, commission and slippage. This is an anecdote, not a backtest. The author also says that direction cannot be known with 100% certainty and describes trading as a probability game.

Risk and money management are explicitly deferred to Book 3, so Book 2 cannot justify aggressive sizing. Its 5-lot example would be impossible or ruinous for a $100 retail account under normal broker margin constraints.

## Candidate test, not a promoted strategy

The strongest incremental hypothesis from these two sources is **Heikin-Ashi Level Exhaustion (HALE)**, not a stack of opaque TradingView indicators:

1. Signal timeframe: MT5 M1, with genuine M5 and H1 context resampled without look-ahead.
2. Level: previous-day high/low, session high/low, or an instrument-specific round-number grid fixed before the trigger.
3. Impulse gate: at least three same-color Heikin-Ashi bars and total real-price displacement above a tunable ATR multiple.
4. Exhaustion gate: the completed signal bar's real body and Heikin-Ashi body contract relative to the impulse median; a doji/wick rule is tested separately.
5. Trigger: first completed opposite-color Heikin-Ashi bar, followed by next-tick real bid/ask entry. No fill at the synthetic Heikin-Ashi close.
6. Exit: real structural stop plus spread buffer, fixed-R/level target, and a 3–7 bar non-performance exit. Same-tick and same-bar ambiguity must be reported.
7. Regime branch: countertrend only in an objectively non-trending state; trend-day continuation/pullback is a separate candidate with separate statistics.
8. Validation: one shared $100 basket, realistic lot/margin constraints, 1.0x/1.5x/2.0x costs, non-overlapping development/validation/frozen holdout, at least 100 closed OOS trades, positive net E[R], PF above 1, and no pair concentration before any sizing increase.

Current Yahoo OHLC is adequate for feature/unit tests and a conservative coarse screen. It cannot validate the sub-minute entries, real spread at the level, event volatility, or synthetic-bar execution assumptions in this setup. The decision is therefore to queue HALE for the Windows MT5 tick path, not claim that either book has produced a new edge.

## Decision

- No Robbinson strategy is promoted: its main ideas are already represented, while its proprietary/community inputs and missing statistics reduce auditability.
- HALE is the highest-value new experiment from these books because it adds an explicit exhaustion state, objective location, trend-day veto, and short non-performance exit to existing Aegis structure.
- There is no new evidence for 100% future win rate or for safe aggressive sizing from $100.
