# EMA/ATR Pulse Basket — measured results

Symbols: `EURUSD=X, GBPUSD=X, AUDUSD=X, NZDUSD=X` · one shared starting equity: **$100**

**Verdict: No EMA/ATR pulse candidate achieved 100% WR on frozen holdout after costs.**

## Selected development, validation, and frozen holdout

### M5

- Development: n=50 · 1.0/day · WR=60.0% (95% CI 46.2–72.4%) · net E[R]=-0.056 · PF=0.28 · DD=5.4% · $100→$94.86 · $-0.10/calendar day · halt=none · ambiguous=0
- Validation: n=28 · 1.8/day · WR=75.0% (95% CI 56.6–87.3%) · net E[R]=-0.028 · PF=0.53 · DD=1.7% · $100→$98.59 · $-0.09/calendar day · halt=none · ambiguous=0
- Frozen holdout: n=8 · 0.5/day · WR=62.5% (95% CI 30.6–86.3%) · net E[R]=-0.101 · PF=0.18 · DD=1.6% · $100→$98.56 · $-0.09/calendar day · halt=none · ambiguous=0

### M1

- Development: n=53 · 8.6/day · WR=43.4% (95% CI 31.0–56.7%) · net E[R]=-0.085 · PF=0.40 · DD=5.4% · $100→$94.75 · $-0.85/calendar day · halt=none · ambiguous=0
- Validation: n=28 · 20.3/day · WR=35.7% (95% CI 20.7–54.2%) · net E[R]=-0.085 · PF=0.33 · DD=2.8% · $100→$97.62 · $-1.73/calendar day · halt=none · ambiguous=0
- Frozen holdout: n=26 · 18.9/day · WR=30.8% (95% CI 16.5–50.0%) · net E[R]=-0.120 · PF=0.18 · DD=3.6% · $100→$96.58 · $-2.49/calendar day · halt=none · ambiguous=0

## Selected parameters

```yaml
m5:
  cafb_htf_adx_min: 12
  pulse_regime_mode: range
  pulse_z_atr: 0.25
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
| 5m | holdout_cost_1.0x | 80 | 5.1 | 63.7% | -0.090 | 0.20 | 10.7% | $89.34 | $-0.68 | none |
| 5m | holdout_cost_1.5x | 8 | 0.5 | 62.5% | -0.101 | 0.18 | 1.6% | $98.56 | $-0.09 | none |
| 5m | holdout_cost_2.0x | 0 | 0.0 | 0.0% | +0.000 | 0.00 | 0.0% | $100.00 | $+0.00 | none |
| 5m | holdout_risk_1 | 0 | 0.0 | 0.0% | +0.000 | 0.00 | 0.0% | $100.00 | $+0.00 | none |
| 5m | holdout_risk_2 | 8 | 0.5 | 62.5% | -0.101 | 0.18 | 1.6% | $98.56 | $-0.09 | none |
| 5m | holdout_risk_5 | 27 | 1.7 | 63.0% | -0.054 | 0.38 | 5.2% | $95.16 | $-0.31 | none |
| 5m | holdout_risk_10 | 31 | 2.0 | 64.5% | -0.038 | 0.42 | 10.0% | $90.87 | $-0.58 | none |
| 5m | holdout_risk_20 | 30 | 1.9 | 66.7% | -0.034 | 0.44 | 11.4% | $89.52 | $-0.66 | none |
| 1m | holdout_cost_1.0x | 65 | 47.2 | 30.8% | -0.137 | 0.22 | 9.5% | $90.93 | $-6.59 | none |
| 1m | holdout_cost_1.5x | 26 | 18.9 | 30.8% | -0.120 | 0.18 | 3.6% | $96.58 | $-2.49 | none |
| 1m | holdout_cost_2.0x | 13 | 9.4 | 23.1% | -0.178 | 0.08 | 2.3% | $97.68 | $-1.68 | none |
| 1m | holdout_risk_1 | 0 | 0.0 | 0.0% | +0.000 | 0.00 | 0.0% | $100.00 | $+0.00 | none |
| 1m | holdout_risk_2 | 26 | 18.9 | 30.8% | -0.120 | 0.18 | 3.6% | $96.58 | $-2.49 | none |
| 1m | holdout_risk_5 | 20 | 14.5 | 25.0% | -0.151 | 0.10 | 12.0% | $88.31 | $-8.49 | none |
| 1m | holdout_risk_10 | 20 | 14.5 | 25.0% | -0.151 | 0.10 | 12.0% | $88.21 | $-8.57 | none |
| 1m | holdout_risk_20 | 20 | 14.5 | 25.0% | -0.151 | 0.10 | 12.0% | $88.21 | $-8.57 | none |

## Audit interpretation

- Selection used development and validation only. Each selected configuration opened its holdout once.
- Costs are charged round trip; raw signals are not trades; SL/TP collisions are stop-first and counted.
- Minimum units, unit step, leverage, shared heat, currency exposure and simultaneous-position limits are enforced.
- Profit/day is historical P&L divided by calendar span, not a promised income rate.
- Compare the failed-break and complete legacy benchmark in `reports/CAFB_BASKET.md`.

Full grid: `/Users/zaid.barghouthi/trading-llm/bot/reports/pulse_search_results.csv`
