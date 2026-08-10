# Cost-Aware Failed-Break Basket design

Date: 2026-08-09

## Objective

Build and measure the strongest Aegis path toward frequent basket scalping from a shared $100 account. Search for a 100% historical win-rate candidate, but promote it only if it remains 100% on a frozen, non-overlapping holdout after costs. Otherwise report the strongest positive-expectancy tradeoff without implying a guaranteed edge.

## Measurement contract

Every result includes exact UTC sample bounds, requested and actual interval, symbols, closed trades, trades per calendar day, win rate, cost-adjusted expectancy in R, profit factor, maximum drawdown, start/end equity, costs, ambiguous-bar count, and halt reason.

All strategy comparisons use the same execution assumptions and one shared portfolio. Raw signals are never counted as trades.

## Correctness requirements

- Historical risk checks receive the current bar timestamp and never fall back to wall-clock time.
- Trade R includes all modeled round-trip costs.
- End-of-test positions are closed at the last available close and charged costs.
- Preparing an already enriched frame is idempotent.
- An unavailable intraday interval raises an error instead of silently returning daily bars.
- Same-bar SL/TP ambiguity is resolved conservatively and counted.
- Bankruptcy, leverage, margin, lot minimum, and lot step are explicit.

## Strategy

The Cost-Aware Failed-Break Basket (CAFB) uses:

1. A real resampled higher-timeframe context from the same timestamped OHLC stream.
2. A short rolling compression box around EMA20.
3. A failed break outside the prior box followed by a close back inside it.
4. A regime selector that permits either trend-aligned failed pullbacks or range reversion; the branches are reported separately.
5. A target toward the box midpoint or opposite edge, a stop beyond the failed-break extreme plus a volatility buffer, and a short time stop.
6. A cost gate requiring expected target distance to exceed modeled round-trip cost by a configurable multiple.
7. London/New York liquid-session filtering and rollover exclusion.

## Basket and sizing

- One shared $100 equity series across all symbols.
- Chronological event processing with at most one new entry per symbol/bar.
- Limits for total open positions, portfolio heat, gross leverage, and net exposure by currency.
- FX sizes respect contract size, minimum lot, lot step and margin. Unexecutable trades are skipped and counted.
- Signal selection is evaluated at small fixed risk. Only frozen signals are replayed with 1%, 2%, 5%, 10%, and 20% risk.
- Sizing above 20% is reported only as a ruin stress test.

## Validation

- Benchmark every distinct registered algorithm plus the generic engines and 11 catalog strategies.
- Use non-overlapping chronological development, validation, and holdout segments.
- Tune only on development; rank on validation; open holdout once for the finalists.
- Evaluate 1.0x, 1.5x, and 2.0x costs.
- Promotion requires at least 100 holdout basket trades, positive net E[R], PF > 1 at 1.5x costs, no bankruptcy or margin breach, and diversified profits.
- A 100% result is labeled as such only for the exact observed sample and accompanied by a binomial confidence interval.

## Deliverables

- Regression-tested accounting fixes.
- CAFB signal and shared basket backtester.
- Exhaustive benchmark/tuning script and focused YAML config.
- `bot/reports/CAFB_BASKET.md` with complete metrics and an explicit result: robust candidate, insufficient evidence, or no positive edge.
- Exact Windows MT5 tick/M1 integration steps for execution validation.

