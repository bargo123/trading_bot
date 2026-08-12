# HALE Basket Research Design

## Objective

Test the strongest unimplemented rule set found in the added Heikin-Ashi material: objective-level exhaustion after a real-price impulse. The experiment seeks the highest measured trade frequency that retains positive net expectancy after realistic costs. It may report a 100% observed sample if one occurs, but it must never describe that sample as a guaranteed future win rate.

Paper trading remains stopped while the candidate is researched. A candidate is not promoted to IB paper merely because it trades often or has a high in-sample win rate.

## Approaches considered

1. **HALE countertrend fade — selected primary.** Require a completed same-color Heikin-Ashi impulse, contraction/exhaustion at a level known before the trigger, then the first completed opposite-color bar. This is the most faithful test of the new book rule and adds information not already represented by CAFB/Pulse.
2. **Heikin-Ashi trend pullback — comparator only.** Enter with the higher-timeframe direction after a short opposite-color pullback and resumption. Its results remain separate so trend and fade statistics cannot mask each other.
3. **Opaque indicator-stack recreation — rejected.** Robbinson's proprietary/community inputs do not have complete, auditable formulas or defensible execution assumptions. Recreating labels from screenshots would fake precision.

## Data and split protocol

- Coarse research uses the existing immutable Yahoo snapshots under `bot/data/cafb_snapshots/`: four USD-quoted pairs, M5 for approximately 59 requested days and M1 for seven requested days.
- Every symbol is sorted by UTC time. The first 60% of its bars are development, the next 20% validation, and the final 20% frozen holdout.
- Parameter selection uses development and validation only. One selected configuration per timeframe opens holdout once.
- The snapshots and their period are already known from earlier strategy research, so “frozen” means unobserved by the HALE grid, not globally pristine market data.
- Yahoo M1/M5 OHLC cannot validate sub-minute spread changes, tick ordering, queue priority, or the exact next-tick bid/ask fill. Any passing result remains a coarse screen for the Windows MT5 tick path.

## HALE feature contract

`bot/aegis/hale.py` owns features and signals.

- Heikin-Ashi close is `(open + high + low + close) / 4`.
- The first Heikin-Ashi open is `(open + close) / 2`; every later value is `(prior HA open + prior HA close) / 2`.
- HA high/low are the maximum/minimum of real high/low, HA open, and HA close.
- HA values are signal-only. Entries and exits always use real OHLC through `run_basket_backtest`, with entry at the next real bar open.
- Previous-day high/low are daily aggregates shifted by one complete UTC day.
- Session high/low use only prior bars from the same UTC day via expanding high/low shifted one bar.
- The round-number level is the nearest configured grid increment to the completed trigger bar's real close. The grid increment is fixed by configuration.
- Higher-timeframe regime comes from closed, one-bucket-lagged resampling using the existing CAFB helper.

## Signal contract

### HALE fade

For a short, the bars before the trigger must contain at least `hale_impulse_bars` bullish HA colors. For a long they must contain the same number of bearish HA colors. Their real close displacement must exceed `hale_impulse_atr * ATR`.

The last impulse bar must show exhaustion: its HA body is at most `hale_contraction_ratio` times the median HA body of the earlier impulse bars. Its real high/low must touch or approach at least one pre-defined level within `hale_level_atr * ATR`. The trigger is the first opposite HA color. Countertrend fades are allowed only when the lagged higher-timeframe regime is `range`.

The structural stop sits beyond the real extreme of the impulse plus `hale_stop_buffer_atr * ATR`. The target is a fixed `hale_target_r` multiple of the signal risk. The basket engine enters next-bar real open while preserving signal stop/target distances. A `max_hold_bars` time exit closes non-performing positions.

### Trend pullback comparator

The lagged higher-timeframe regime must be directional. A short run of opposite-color HA bars must pull price toward EMA20 without breaking the configured ATR distance, followed by a completed HA color resumption with the regime. Stops use the pullback real extreme plus buffer and targets use a fixed R multiple. Results are selected and reported independently from the fade.

## Cost and portfolio model

- Variable round-trip costs remain explicit: two one-way charges of spread, slippage, and commission bps.
- `run_basket_backtest` gains `commission_round_trip_usd`, subtracted once from every closed trade. This makes the live IB assumption of about $4 round trip testable instead of silently ignoring it.
- Cost gates estimate the candidate's expected dollar gross reward at the leverage-capped size and reject trades that cannot exceed the configured cost buffer.
- The primary research scenario uses a shared $100 account, 2% risk per trade, two simultaneous positions, 4% basket heat, 30:1 gross leverage, 1,000-unit minimum and step, and 1.5x variable costs (0.6 bps spread plus 0.3 bps slippage per side).
- Stress tests cover 1.0x, 1.5x, and 2.0x variable costs; 1%, 2%, 5%, 10%, and 20% nominal risk; and the IB-like fixed $4 round trip.
- Aggressive sizing is reported only as stress behavior. It cannot turn negative E[R] into an edge and is not promoted when drawdown or ruin worsens.

## Selection and promotion rules

The selector first requires positive E[R] and PF above 1 on both development and validation. Among passing candidates it rewards the smaller of development/validation E[R] and PF, then trade frequency and win rate, while penalizing drawdown. Candidates below minimum trade counts cannot win the search. If none pass, the best diagnostic candidate is still opened on holdout and reported as rejected.

Promotion requires all of the following on frozen holdout at 1.5x variable costs:

- at least 100 closed trades;
- positive net E[R];
- PF greater than 1;
- positive ending equity with no bankruptcy or risk halt;
- no single symbol responsible for more than 60% of total positive P&L;
- survival at 2.0x variable costs.

An observed 100% win rate must still meet the trade-count and cost gates, include a Wilson confidence interval, and be labeled as a finite historical observation rather than an always-win claim.

## Outputs

- `bot/aegis/hale.py`: HA features and two separate signal functions.
- `bot/tests/test_hale_unit.py`: hand-derived HA, no-lookahead level, next-real-open signal, and branch tests.
- `bot/tests/test_basket_backtest.py`: fixed-dollar commission accounting test.
- `bot/scripts/tune_hale_basket.py`: deterministic development/validation search, one-time holdout, stress runs, and report generation.
- `bot/config_hale_basket.yaml`: auditable base settings.
- `bot/config_hale_basket.tuned.yaml`: selected coarse-screen settings.
- `bot/reports/hale_search_results.csv`: full development/validation grid.
- `bot/reports/HALE_BASKET.md`: trades, trades/day, WR and interval, E[R], PF, maximum drawdown, start/end equity, halt reason, sample window, costs, per-symbol results, and promotion decision.

## Failure handling

No-data and insufficient-bar cases return no signal rather than inventing defaults. Zero ATR, invalid stop distance, target below the cost gate, minimum-size violations, leverage violations, or portfolio heat violations are skipped and counted by the existing basket engine. Same-bar stop/target collisions remain stop-first and are reported as ambiguous. If the experiment fails promotion, paper trading stays stopped and the report says why.
