# Measured edge, and the gap to $100/day

Source: `analogue_index.json` — provenance **mt5_m1**, outcomes in **pips**, **9,569** records.

## Population-level result

| metric | value |
| --- | --- |
| trades | 9,569 |
| win rate | 47.08% |
| **expectancy** | **-0.5595 pips/trade** |
| **profit factor** | **0.850** |
| avg win / avg loss | 6.72 / -7.10 pips |
| payoff ratio | 0.946 |
| breakeven WR required | 51.38% |
| tail loss | 89.3 pips |
| cosmetic win rate? | False |

This is the honest baseline for the M15 structural-thesis family, measured on
real MT5 M1 history and **before spread costs**. It is not a positive-edge
strategy at the population level.

## Per-state breakdown

- States with at least 20 observations: **41**
- States with positive point expectancy: **14**
- States that pass the runtime's 95% lower-bound test: **2**

### Best states by expectancy

| regime | structure | session | side | n | WR | exp (pips) | PF | payoff | lower95 | runtime eligible |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| range | retest | newyork | sell | 39 | 59.0% | 2.71 | 1.91 | 1.33 | -0.82 | False |
| range | retest | newyork | buy | 72 | 61.1% | 1.92 | 1.89 | 1.16 | -0.34 | False |
| noise | none | london | buy | 37 | 62.2% | 1.70 | 1.98 | 1.21 | -0.40 | False |
| trend | retest | asia | sell | 50 | 48.0% | 1.39 | 2.31 | 2.40 | -0.05 | False |
| range | none | asia | sell | 759 | 54.0% | 1.39 | 1.59 | 1.34 | 0.80 | True |
| trend | none | asia | sell | 674 | 54.0% | 0.86 | 1.35 | 1.14 | 0.23 | True |
| noise | none | newyork | sell | 25 | 48.0% | 0.78 | 1.22 | 1.32 | -3.48 | False |
| range | retest | asia | sell | 61 | 50.8% | 0.60 | 1.43 | 1.38 | -0.49 | False |
| range | none | london | buy | 510 | 54.1% | 0.40 | 1.13 | 0.94 | -0.36 | False |
| noise | none | london | sell | 25 | 44.0% | 0.25 | 1.08 | 1.37 | -3.29 | False |
| range | none | newyork | sell | 576 | 48.4% | 0.14 | 1.03 | 1.09 | -1.05 | False |
| range | retest | london | buy | 81 | 54.3% | 0.10 | 1.06 | 0.89 | -0.92 | False |

## Gap to $100/day

| item | value |
| --- | --- |
| measured_expectancy_pips_per_trade | -0.5595 |
| measured_profit_factor | 0.8498 |
| measured_win_rate | 0.4708 |
| measured_payoff_ratio | 0.9464 |
| expectancy_usd_per_trade_at_0.01_lots | -0.0559 |
| runtime_eligible_states | 2 |
| required_capital_for_100_per_day | unavailable |

**Measured expectancy is not positive, so there is no capital level or lot size at which this strategy family yields $100/day. Leverage multiplies a negative number. The gap is an EDGE gap, not a capital gap.**

