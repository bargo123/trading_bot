# Cost-Aware Failed-Break Basket — measured results

Symbols: `EURUSD=X, GBPUSD=X, AUDUSD=X, NZDUSD=X` · one shared starting equity: **$100**

**Verdict: No tuned CAFB candidate achieved 100% WR on its frozen holdout after costs.**

## Frozen holdouts

- M5: n=11 · 0.7/day · WR=54.5% (95% CI 28.0–78.7%) · net E[R]=-0.328 · PF=0.56 · DD=5.3% · $100→$97.03 · $-0.19/calendar day · halt=none · ambiguous=0
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
  cafb_allow_range: true
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
| 5m | holdout_cost_1.0x | 31 | 2.0 | 54.8% | -0.439 | 0.45 | 8.7% | $92.26 | $-0.49 | none |
| 5m | holdout_cost_1.5x | 11 | 0.7 | 54.5% | -0.328 | 0.56 | 5.3% | $97.03 | $-0.19 | none |
| 5m | holdout_cost_2.0x | 3 | 0.2 | 66.7% | +0.443 | 1.06 | 1.8% | $100.11 | $+0.01 | none |
| 5m | holdout_risk_1 | 11 | 0.7 | 54.5% | -0.328 | 0.63 | 4.1% | $98.09 | $-0.12 | none |
| 5m | holdout_risk_2 | 11 | 0.7 | 54.5% | -0.328 | 0.56 | 5.3% | $97.03 | $-0.19 | none |
| 5m | holdout_risk_5 | 11 | 0.7 | 54.5% | -0.328 | 0.56 | 5.3% | $97.03 | $-0.19 | none |
| 5m | holdout_risk_10 | 11 | 0.7 | 54.5% | -0.328 | 0.56 | 5.3% | $97.03 | $-0.19 | none |
| 5m | holdout_risk_20 | 11 | 0.7 | 54.5% | -0.328 | 0.56 | 5.3% | $97.03 | $-0.19 | none |
| 1m | holdout_cost_1.0x | 31 | 22.5 | 32.3% | -0.844 | 0.28 | 7.7% | $93.07 | $-5.04 | none |
| 1m | holdout_cost_1.5x | 12 | 8.7 | 41.7% | -0.629 | 0.37 | 4.1% | $96.92 | $-2.24 | none |
| 1m | holdout_cost_2.0x | 0 | 0.0 | 0.0% | +0.000 | 0.00 | -0.0% | $100.00 | $+0.00 | none |
| 1m | holdout_risk_1 | 12 | 8.7 | 41.7% | -0.629 | 0.37 | 4.1% | $96.92 | $-2.24 | none |
| 1m | holdout_risk_2 | 12 | 8.7 | 41.7% | -0.629 | 0.37 | 4.1% | $96.92 | $-2.24 | none |
| 1m | holdout_risk_5 | 12 | 8.7 | 41.7% | -0.629 | 0.37 | 4.1% | $96.92 | $-2.24 | none |
| 1m | holdout_risk_10 | 12 | 8.7 | 41.7% | -0.629 | 0.37 | 4.1% | $96.92 | $-2.24 | none |
| 1m | holdout_risk_20 | 12 | 8.7 | 41.7% | -0.629 | 0.37 | 4.1% | $96.92 | $-2.24 | none |

## Existing-algorithm benchmark — validation ranking

All distinct registered functions, the two generic engines, and all 11 catalog strategies were attempted with the same shared-capital and 1.5x-cost assumptions.

| Strategy | Trades | Trades/day | WR | Net E[R] | PF | DD | $100 end |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `thomas_10r` | 8 | 0.5 | 75.0% | +0.395 | 3.51 | 1.8% | $105.28 |
| `hw_range` | 3 | 0.2 | 100.0% | +0.166 | inf | -0.0% | $100.76 |
| `trend_pullback` | 2 | 0.1 | 100.0% | +0.156 | inf | -0.0% | $100.42 |
| `steidl_ib_fade` | 0 | 0.0 | 0.0% | +0.000 | 0.00 | -0.0% | $100.00 |
| `generic_regime` | 119 | 7.5 | 43.7% | -0.060 | 0.83 | 18.6% | $90.65 |
| `catalog:macd_cross` | 133 | 8.4 | 42.1% | -0.110 | 0.74 | 20.0% | $80.33 |
| `catalog:donch55` | 124 | 7.9 | 36.3% | -0.138 | 0.62 | 26.4% | $73.77 |
| `squeeze_bo` | 13 | 0.8 | 61.5% | -0.160 | 0.31 | 3.7% | $96.49 |
| `rsi_cross` | 29 | 1.8 | 62.1% | -0.169 | 0.34 | 8.6% | $92.56 |
| `ensemble` | 38 | 2.4 | 28.9% | -0.177 | 0.53 | 12.3% | $89.27 |
| `catalog:aegis_range_hw` | 16 | 1.0 | 31.2% | -0.180 | 0.07 | 4.4% | $95.59 |
| `fabris_ntz` | 32 | 2.0 | 34.4% | -0.187 | 0.48 | 11.0% | $90.66 |
| `book_optimal` | 46 | 2.9 | 37.0% | -0.197 | 0.59 | 15.7% | $86.78 |
| `catalog:ema_cross` | 80 | 5.1 | 37.5% | -0.201 | 0.51 | 23.5% | $76.57 |
| `catalog:elder_impulse` | 110 | 7.0 | 33.6% | -0.207 | 0.58 | 30.6% | $69.62 |
| `breakout_adx` | 63 | 4.0 | 66.7% | -0.210 | 0.25 | 19.8% | $81.46 |
| `catalog:donch20` | 110 | 7.0 | 38.2% | -0.215 | 0.56 | 30.4% | $69.64 |
| `volman_scalp` | 23 | 1.5 | 43.5% | -0.216 | 0.39 | 7.7% | $94.36 |
| `aziz_orb` | 52 | 3.3 | 32.7% | -0.222 | 0.37 | 17.8% | $83.90 |
| `catalog:bb_squeeze` | 39 | 2.5 | 35.9% | -0.227 | 0.50 | 14.9% | $86.59 |
| `aziz_vwap` | 73 | 4.6 | 31.5% | -0.246 | 0.51 | 30.1% | $73.87 |
| `catalog:stoch_mr` | 98 | 6.2 | 42.9% | -0.248 | 0.10 | 30.4% | $69.59 |
| `scalper_2h` | 91 | 5.8 | 61.5% | -0.252 | 0.16 | 30.8% | $69.22 |
| `chan_bb_scalp` | 81 | 5.1 | 37.0% | -0.259 | 0.55 | 30.3% | $71.82 |
| `firehose` | 73 | 4.6 | 41.1% | -0.295 | 0.29 | 30.2% | $69.77 |
| `catalog:bb_mr` | 81 | 5.1 | 46.9% | -0.300 | 0.08 | 31.4% | $68.64 |
| `catalog:atr_breakout` | 68 | 4.3 | 26.5% | -0.340 | 0.32 | 30.0% | $70.03 |
| `catalog:rsi_pure` | 47 | 3.0 | 51.1% | -0.383 | 0.10 | 24.9% | $75.90 |
| `steidl_ib_break` | 18 | 1.1 | 33.3% | -0.408 | 0.43 | 12.0% | $90.60 |
| `hw_runner` | 10 | 0.6 | 50.0% | -0.455 | 0.18 | 7.8% | $92.66 |

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
