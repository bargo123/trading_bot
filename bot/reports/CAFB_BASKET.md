# Cost-Aware Failed-Break Basket — measured results

Symbols: `EURUSD=X, GBPUSD=X, AUDUSD=X, NZDUSD=X` · one shared starting equity: **$100**

**Verdict: No tuned CAFB candidate achieved 100% WR on its frozen holdout after costs.**

## Frozen holdouts

- M5: n=7 · 0.4/day · WR=28.6% (95% CI 8.2–64.1%) · net E[R]=-1.105 · PF=0.15 · DD=6.4% · $100→$94.50 · $-0.35/calendar day · halt=none · ambiguous=0
- M1: n=12 · 8.7/day · WR=41.7% (95% CI 19.3–68.0%) · net E[R]=-0.629 · PF=0.37 · DD=4.1% · $100→$96.92 · $-2.24/calendar day · halt=none · ambiguous=0

The M1 Yahoo sample is intrinsically short; its holdout cannot establish long-run reliability even if it is perfect.

## Selected parameters

```yaml
m5:
  cafb_exclude_hours_utc: &id001
  - 21
  - 22
  cafb_context_minutes: 15
  cafb_htf_fast: 8
  cafb_htf_slow: 21
  cafb_htf_adx_period: 14
  cafb_htf_adx_min: 12
  cafb_box_bars: 5
  cafb_box_min_atr: 0.1
  cafb_box_max_atr: 1.5
  cafb_allow_range: false
  cafb_target_mode: opposite
  cafb_stop_buffer_atr: 0.15
  cafb_min_rr: 0.1
m1:
  cafb_exclude_hours_utc: *id001
  cafb_context_minutes: 5
  cafb_htf_fast: 8
  cafb_htf_slow: 21
  cafb_htf_adx_period: 14
  cafb_htf_adx_min: 20
  cafb_box_bars: 8
  cafb_box_min_atr: 0.1
  cafb_box_max_atr: 4.0
  cafb_allow_range: true
  cafb_target_mode: extension
  cafb_stop_buffer_atr: 0.15
  cafb_min_rr: 0.1
```

## Cost and sizing stress

| TF | Test | Trades | Trades/day | WR | Net E[R] | PF | Max DD | $100 end | Profit/day | Halt |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 5m | holdout_cost_1.0x | 19 | 1.2 | 42.1% | -0.737 | 0.19 | 9.2% | $91.56 | $-0.54 | none |
| 5m | holdout_cost_1.5x | 7 | 0.4 | 28.6% | -1.105 | 0.15 | 6.4% | $94.50 | $-0.35 | none |
| 5m | holdout_cost_2.0x | 1 | 0.1 | 0.0% | -1.428 | 0.00 | 1.8% | $98.16 | $-0.12 | none |
| 5m | holdout_risk_1 | 7 | 0.4 | 28.6% | -1.105 | 0.14 | 5.2% | $95.51 | $-0.28 | none |
| 5m | holdout_risk_2 | 7 | 0.4 | 28.6% | -1.105 | 0.15 | 6.4% | $94.50 | $-0.35 | none |
| 5m | holdout_risk_5 | 7 | 0.4 | 28.6% | -1.105 | 0.15 | 6.4% | $94.50 | $-0.35 | none |
| 5m | holdout_risk_10 | 7 | 0.4 | 28.6% | -1.105 | 0.15 | 6.4% | $94.50 | $-0.35 | none |
| 5m | holdout_risk_20 | 7 | 0.4 | 28.6% | -1.105 | 0.15 | 6.4% | $94.50 | $-0.35 | none |
| 1m | holdout_cost_1.0x | 31 | 22.5 | 32.3% | -0.887 | 0.28 | 7.9% | $92.90 | $-5.16 | none |
| 1m | holdout_cost_1.5x | 12 | 8.7 | 41.7% | -0.629 | 0.37 | 4.1% | $96.92 | $-2.24 | none |
| 1m | holdout_cost_2.0x | 0 | 0.0 | 0.0% | +0.000 | 0.00 | 0.0% | $100.00 | $+0.00 | none |
| 1m | holdout_risk_1 | 12 | 8.7 | 41.7% | -0.629 | 0.37 | 4.1% | $96.92 | $-2.24 | none |
| 1m | holdout_risk_2 | 12 | 8.7 | 41.7% | -0.629 | 0.37 | 4.1% | $96.92 | $-2.24 | none |
| 1m | holdout_risk_5 | 12 | 8.7 | 41.7% | -0.629 | 0.37 | 4.1% | $96.92 | $-2.24 | none |
| 1m | holdout_risk_10 | 12 | 8.7 | 41.7% | -0.629 | 0.37 | 4.1% | $96.92 | $-2.24 | none |
| 1m | holdout_risk_20 | 12 | 8.7 | 41.7% | -0.629 | 0.37 | 4.1% | $96.92 | $-2.24 | none |

## Existing-algorithm benchmark — validation ranking

All distinct registered functions, the two generic engines, and all 11 catalog strategies were attempted with the same shared-capital and 1.5x-cost assumptions.

| Strategy | Trades | Trades/day | WR | Net E[R] | PF | DD | $100 end |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `trend_pullback` | 2 | 0.1 | 100.0% | +0.156 | inf | 0.0% | $100.42 |
| `hw_range` | 3 | 0.2 | 100.0% | +0.141 | inf | 0.0% | $100.58 |
| `steidl_ib_fade` | 0 | 0.0 | 0.0% | +0.000 | 0.00 | 0.0% | $100.00 |
| `pulse_scalp` | 0 | 0.0 | 0.0% | +0.000 | 0.00 | 0.0% | $100.00 |
| `squeeze_bo` | 14 | 0.9 | 64.3% | -0.109 | 0.48 | 2.0% | $98.20 |
| `rsi_cross` | 31 | 2.0 | 64.5% | -0.148 | 0.36 | 8.4% | $92.76 |
| `ensemble` | 44 | 2.8 | 31.8% | -0.159 | 0.65 | 10.2% | $92.21 |
| `catalog:donch55` | 154 | 9.8 | 39.0% | -0.193 | 0.56 | 30.0% | $69.99 |
| `generic_regime` | 157 | 10.0 | 38.9% | -0.194 | 0.60 | 28.9% | $71.11 |
| `hw_runner` | 12 | 0.8 | 66.7% | -0.208 | 0.32 | 6.1% | $94.65 |
| `catalog:aegis_range_hw` | 21 | 1.3 | 14.3% | -0.212 | 0.04 | 6.0% | $94.03 |
| `catalog:elder_impulse` | 128 | 8.1 | 37.5% | -0.212 | 0.52 | 30.1% | $69.93 |
| `thomas_10r` | 24 | 1.5 | 41.7% | -0.214 | 0.71 | 10.7% | $96.35 |
| `fabris_ntz` | 33 | 2.1 | 30.3% | -0.216 | 0.44 | 11.7% | $89.97 |
| `volman_scalp` | 23 | 1.5 | 43.5% | -0.216 | 0.39 | 7.7% | $94.36 |
| `chan_bb_scalp` | 105 | 6.7 | 41.0% | -0.223 | 0.54 | 30.3% | $71.53 |
| `catalog:macd_cross` | 133 | 8.4 | 36.8% | -0.223 | 0.50 | 30.3% | $69.73 |
| `breakout_adx` | 56 | 3.6 | 62.5% | -0.248 | 0.20 | 20.6% | $80.32 |
| `catalog:ema_cross` | 107 | 6.8 | 37.4% | -0.265 | 0.46 | 30.3% | $69.97 |
| `aziz_vwap` | 97 | 6.1 | 32.0% | -0.278 | 0.50 | 30.6% | $72.50 |
| `catalog:atr_breakout` | 97 | 6.1 | 30.9% | -0.286 | 0.39 | 30.1% | $69.87 |
| `firehose` | 105 | 6.7 | 43.8% | -0.287 | 0.29 | 30.5% | $69.48 |
| `book_optimal` | 92 | 5.8 | 37.0% | -0.333 | 0.55 | 26.7% | $75.70 |
| `catalog:stoch_mr` | 95 | 6.0 | 20.0% | -0.366 | 0.06 | 30.8% | $69.17 |
| `catalog:rsi_pure` | 61 | 3.9 | 37.7% | -0.377 | 0.09 | 28.0% | $72.49 |
| `catalog:bb_squeeze` | 94 | 6.0 | 28.7% | -0.385 | 0.49 | 30.2% | $70.13 |
| `aziz_orb` | 101 | 6.4 | 31.7% | -0.405 | 0.32 | 30.4% | $69.73 |
| `scalper_2h` | 89 | 5.6 | 36.0% | -0.416 | 0.09 | 30.6% | $69.37 |
| `catalog:bb_mr` | 85 | 5.4 | 28.2% | -0.436 | 0.05 | 31.1% | $68.85 |
| `steidl_ib_break` | 22 | 1.4 | 27.3% | -0.497 | 0.33 | 16.1% | $85.98 |
| `catalog:donch20` | 65 | 4.1 | 27.7% | -0.531 | 0.21 | 31.4% | $68.64 |

## Data windows

- 5m `EURUSD=X`: 16776 bars, 2026-05-18 23:00:00+00:00 to 2026-08-07 21:25:00+00:00, actual interval `5m`.
- 5m `GBPUSD=X`: 16776 bars, 2026-05-18 23:00:00+00:00 to 2026-08-07 21:25:00+00:00, actual interval `5m`.
- 5m `AUDUSD=X`: 16777 bars, 2026-05-18 23:00:00+00:00 to 2026-08-07 21:25:00+00:00, actual interval `5m`.
- 5m `NZDUSD=X`: 16776 bars, 2026-05-18 23:00:00+00:00 to 2026-08-07 21:25:00+00:00, actual interval `5m`.
- 1m `EURUSD=X`: 9889 bars, 2026-07-29 23:00:00+00:00 to 2026-08-07 21:29:00+00:00, actual interval `1m`.
- 1m `GBPUSD=X`: 9892 bars, 2026-07-29 23:00:00+00:00 to 2026-08-07 21:29:00+00:00, actual interval `1m`.
- 1m `AUDUSD=X`: 4942 bars, 2026-07-29 23:01:00+00:00 to 2026-08-07 21:29:00+00:00, actual interval `1m`.
- 1m `NZDUSD=X`: 4941 bars, 2026-07-29 23:01:00+00:00 to 2026-08-07 21:29:00+00:00, actual interval `1m`.

## Interpretation

- Profit/day is the historical net P&L divided by calendar span; it is not a promised daily payment.
- Trades include round-trip spread, slippage and commission assumptions. Raw signals are not counted.
- Same-bar SL/TP collisions are resolved stop-first and counted as ambiguous.
- The basket enforces shared equity, simultaneous-position, heat, currency-exposure, leverage, minimum-unit and unit-step constraints.
- Aggressive risk changes the loss path, not the strategy's underlying edge. A 100% short sample never licenses all-in live sizing.

Details: `/Users/zaid.barghouthi/trading-llm/bot/reports/cafb_benchmark_results.csv` and `/Users/zaid.barghouthi/trading-llm/bot/reports/cafb_search_results.csv`
