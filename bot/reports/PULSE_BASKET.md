# EMA/ATR Pulse Basket — measured results

Symbols: `EURUSD=X, GBPUSD=X, AUDUSD=X, NZDUSD=X` · one shared starting equity: **$100**

**Verdict: No EMA/ATR pulse candidate achieved 100% WR on frozen holdout after costs.**

## Selected development, validation, and frozen holdout

### M5

- Development: n=52 · 1.1/day · WR=59.6% (95% CI 46.1–71.8%) · net E[R]=-0.056 · PF=0.29 · DD=5.6% · $100→$94.69 · $-0.11/calendar day · halt=none · ambiguous=0
- Validation: n=29 · 1.8/day · WR=72.4% (95% CI 54.3–85.3%) · net E[R]=-0.038 · PF=0.44 · DD=2.2% · $100→$98.03 · $-0.12/calendar day · halt=none · ambiguous=0
- Frozen holdout: n=9 · 0.6/day · WR=66.7% (95% CI 35.4–87.9%) · net E[R]=-0.086 · PF=0.22 · DD=1.6% · $100→$98.63 · $-0.09/calendar day · halt=none · ambiguous=0

### M1

- Development: n=55 · 8.9/day · WR=43.6% (95% CI 31.4–56.7%) · net E[R]=-0.083 · PF=0.40 · DD=5.5% · $100→$94.67 · $-0.86/calendar day · halt=none · ambiguous=0
- Validation: n=30 · 21.8/day · WR=36.7% (95% CI 21.9–54.5%) · net E[R]=-0.084 · PF=0.33 · DD=2.9% · $100→$97.48 · $-1.83/calendar day · halt=none · ambiguous=0
- Frozen holdout: n=27 · 19.6/day · WR=29.6% (95% CI 15.9–48.5%) · net E[R]=-0.125 · PF=0.17 · DD=3.8% · $100→$96.30 · $-2.69/calendar day · halt=none · ambiguous=0

## Selected parameters

```yaml
m5:
  cafb_htf_adx_min: 12
  pulse_regime_mode: range
  pulse_z_atr: 0.75
  pulse_rsi_edge: 45
  pulse_trend_near_atr: 0.75
  pulse_trend_rsi: 55
  pulse_sl_atr: 10.0
  pulse_tp_atr: 1.0
  pulse_sl_pips: null
  pulse_tp_pips: null
  pulse_pip_size: 0.0001
m1:
  cafb_htf_adx_min: 20
  pulse_regime_mode: range
  pulse_z_atr: 0.25
  pulse_rsi_edge: 40
  pulse_trend_near_atr: 0.75
  pulse_trend_rsi: 55
  pulse_sl_atr: null
  pulse_tp_atr: null
  pulse_sl_pips: 10.0
  pulse_tp_pips: 3.0
  pulse_pip_size: 0.0001
```

## Holdout cost and risk stress

| TF | Test | Trades | Trades/day | WR | Net E[R] | PF | Max DD | $100 end | Profit/day | Halt |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 5m | holdout_cost_1.0x | 96 | 6.1 | 62.5% | -0.091 | 0.21 | 12.2% | $87.84 | $-0.77 | none |
| 5m | holdout_cost_1.5x | 9 | 0.6 | 66.7% | -0.086 | 0.22 | 1.6% | $98.63 | $-0.09 | none |
| 5m | holdout_cost_2.0x | 0 | 0.0 | 0.0% | +0.000 | 0.00 | -0.0% | $100.00 | $+0.00 | none |
| 5m | holdout_risk_1 | 0 | 0.0 | 0.0% | +0.000 | 0.00 | -0.0% | $100.00 | $+0.00 | none |
| 5m | holdout_risk_2 | 9 | 0.6 | 66.7% | -0.086 | 0.22 | 1.6% | $98.63 | $-0.09 | none |
| 5m | holdout_risk_5 | 28 | 1.8 | 67.9% | -0.043 | 0.45 | 4.6% | $95.98 | $-0.25 | none |
| 5m | holdout_risk_10 | 30 | 1.9 | 66.7% | -0.035 | 0.45 | 8.9% | $92.03 | $-0.51 | none |
| 5m | holdout_risk_20 | 28 | 1.8 | 67.9% | -0.034 | 0.43 | 10.9% | $90.05 | $-0.63 | none |
| 1m | holdout_cost_1.0x | 69 | 50.1 | 31.9% | -0.133 | 0.23 | 9.8% | $90.66 | $-6.79 | none |
| 1m | holdout_cost_1.5x | 27 | 19.6 | 29.6% | -0.125 | 0.17 | 3.8% | $96.30 | $-2.69 | none |
| 1m | holdout_cost_2.0x | 13 | 9.4 | 23.1% | -0.178 | 0.08 | 2.3% | $97.68 | $-1.68 | none |
| 1m | holdout_risk_1 | 0 | 0.0 | 0.0% | +0.000 | 0.00 | -0.0% | $100.00 | $+0.00 | none |
| 1m | holdout_risk_2 | 27 | 19.6 | 29.6% | -0.125 | 0.17 | 3.8% | $96.30 | $-2.69 | none |
| 1m | holdout_risk_5 | 21 | 15.3 | 23.8% | -0.157 | 0.10 | 12.8% | $87.48 | $-9.09 | none |
| 1m | holdout_risk_10 | 21 | 15.3 | 23.8% | -0.157 | 0.10 | 12.8% | $87.38 | $-9.17 | none |
| 1m | holdout_risk_20 | 21 | 15.3 | 23.8% | -0.157 | 0.10 | 12.8% | $87.38 | $-9.17 | none |

## Audit interpretation

- Selection used development and validation only. Each selected configuration opened its holdout once.
- Costs are charged round trip; raw signals are not trades; SL/TP collisions are stop-first and counted.
- Minimum units, unit step, leverage, shared heat, currency exposure and simultaneous-position limits are enforced.
- Profit/day is historical P&L divided by calendar span, not a promised income rate.
- Compare the failed-break and complete legacy benchmark in `reports/CAFB_BASKET.md`.

Full grid: `/Users/zaid.barghouthi/trading-llm/bot/reports/pulse_search_results.csv`
