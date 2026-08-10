# Corrected re-measurement — tuned 1h 100%-WR configuration

The original selected parameters were not re-tuned. This rerun uses cost-adjusted R, end-of-test liquidation, and historical-time risk checks.

## Window results

| Window | Exact UTC sample | Trades | Trades/day | WR (95% Wilson CI) | Net E[R] | PF | Max DD | $100 end | Profit/day | Halt |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 45d_all_in | 2026-06-23 21:00:00+00:00 → 2026-08-07 21:00:00+00:00 | 17 | 0.38 | 100.0% (81.6–100.0%) | +0.058 | inf | -0.0% | $261.54 | $+3.59 | none |
| 60d_all_in | 2026-06-08 21:00:00+00:00 → 2026-08-07 21:00:00+00:00 | 23 | 0.38 | 100.0% (85.7–100.0%) | +0.060 | inf | -0.0% | $381.11 | $+4.69 | none |
| 75d_all_in | 2026-05-24 23:00:00+00:00 → 2026-08-07 21:00:00+00:00 | 28 | 0.37 | 100.0% (87.9–100.0%) | +0.059 | inf | -0.0% | $497.57 | $+5.31 | none |
| 90d_all_in | 2026-05-10 23:00:00+00:00 → 2026-08-07 21:00:00+00:00 | 29 | 0.33 | 100.0% (88.3–100.0%) | +0.060 | inf | -0.0% | $533.75 | $+4.88 | none |

## Same 60-day signals — sizing comparison

| Risk/trade | Trades | WR | Net E[R] | PF | Max DD | $100 end | Profit/day | Halt |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1% | 23 | 100.0% | +0.060 | inf | -0.0% | $101.39 | $+0.02 | none |
| 2% | 23 | 100.0% | +0.060 | inf | -0.0% | $102.80 | $+0.05 | none |
| 5% | 23 | 100.0% | +0.060 | inf | -0.0% | $107.13 | $+0.12 | none |
| 10% | 23 | 100.0% | +0.060 | inf | -0.0% | $114.74 | $+0.25 | none |
| 20% | 23 | 100.0% | +0.060 | inf | -0.0% | $131.55 | $+0.53 | none |
| 100% | 23 | 100.0% | +0.060 | inf | -0.0% | $381.11 | $+4.69 | none |

## Same 60-day signals — cost stress at 100% risk

| Cost | Trades | WR | Net E[R] | PF | Max DD | $100 end | Profit/day | Halt |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1.0x | 23 | 100.0% | +0.060 | inf | -0.0% | $381.11 | $+4.69 | none |
| 1.5x | 1 | 100.0% | +0.069 | inf | -0.0% | $106.93 | $+0.12 | none |
| 2.0x | 0 | 0.0% | +0.000 | 0.00 | 0.0% | $100.00 | $+0.00 | none |

## Limits

- This remains a previously selected parameter set on a rolling Yahoo sample, not a new frozen OOS discovery.
- The single-symbol engine does not enforce broker lot size, leverage or margin, so the all-in row is not an executable $100 recommendation.
- A perfect observed sample has a wide true-win-rate confidence interval and does not imply the next trade must win.

```json
{
  "windows": [
    {
      "label": "45d_all_in",
      "start_utc": "2026-06-23 21:00:00+00:00",
      "end_utc": "2026-08-07 21:00:00+00:00",
      "trades": 17,
      "trades_per_day": 0.37777777777777777,
      "win_rate": 100.0,
      "ci_low": 81.56763396284354,
      "ci_high": 100.0,
      "expectancy_r": 0.05825533491514652,
      "profit_factor": Infinity,
      "max_drawdown_pct": -0.0,
      "start_equity": 100.0,
      "end_equity": 261.5382388954368,
      "net_pnl": 161.5382388954368,
      "profit_per_day": 3.5897386421208175,
      "halt_reason": "none",
      "ambiguous": 0
    },
    {
      "label": "60d_all_in",
      "start_utc": "2026-06-08 21:00:00+00:00",
      "end_utc": "2026-08-07 21:00:00+00:00",
      "trades": 23,
      "trades_per_day": 0.38333333333333336,
      "win_rate": 100.0,
      "ci_low": 85.68788745827374,
      "ci_high": 100.0,
      "expectancy_r": 0.05998741647651311,
      "profit_factor": Infinity,
      "max_drawdown_pct": -0.0,
      "start_equity": 100.0,
      "end_equity": 381.1073009274289,
      "net_pnl": 281.10730092742887,
      "profit_per_day": 4.685121682123815,
      "halt_reason": "none",
      "ambiguous": 0
    },
    {
      "label": "75d_all_in",
      "start_utc": "2026-05-24 23:00:00+00:00",
      "end_utc": "2026-08-07 21:00:00+00:00",
      "trades": 28,
      "trades_per_day": 0.3737486095661846,
      "win_rate": 100.0,
      "ci_low": 87.93527963418923,
      "ci_high": 100.0,
      "expectancy_r": 0.0590801750284954,
      "profit_factor": Infinity,
      "max_drawdown_pct": -0.0,
      "start_equity": 100.0,
      "end_equity": 497.57166864431144,
      "net_pnl": 397.5716686443113,
      "profit_per_day": 5.3068520842399725,
      "halt_reason": "none",
      "ambiguous": 0
    },
    {
      "label": "90d_all_in",
      "start_utc": "2026-05-10 23:00:00+00:00",
      "end_utc": "2026-08-07 21:00:00+00:00",
      "trades": 29,
      "trades_per_day": 0.3261480787253983,
      "win_rate": 100.0,
      "ci_low": 88.30264055344442,
      "ci_high": 100.0,
      "expectancy_r": 0.05955028406224977,
      "profit_factor": Infinity,
      "max_drawdown_pct": -0.0,
      "start_equity": 100.0,
      "end_equity": 533.7517650717654,
      "net_pnl": 433.75176507176536,
      "profit_per_day": 4.878182924893331,
      "halt_reason": "none",
      "ambiguous": 0
    }
  ],
  "risk": [
    {
      "label": "risk_1",
      "start_utc": "2026-06-08 21:00:00+00:00",
      "end_utc": "2026-08-07 21:00:00+00:00",
      "trades": 23,
      "trades_per_day": 0.38333333333333336,
      "win_rate": 100.0,
      "ci_low": 85.68788745827374,
      "ci_high": 100.0,
      "expectancy_r": 0.059987416476513095,
      "profit_factor": Infinity,
      "max_drawdown_pct": -0.0,
      "start_equity": 100.0,
      "end_equity": 101.38883027206569,
      "net_pnl": 1.3888302720657077,
      "profit_per_day": 0.023147171201095128,
      "halt_reason": "none",
      "ambiguous": 0
    },
    {
      "label": "risk_2",
      "start_utc": "2026-06-08 21:00:00+00:00",
      "end_utc": "2026-08-07 21:00:00+00:00",
      "trades": 23,
      "trades_per_day": 0.38333333333333336,
      "win_rate": 100.0,
      "ci_low": 85.68788745827374,
      "ci_high": 100.0,
      "expectancy_r": 0.059987416476513095,
      "profit_factor": Infinity,
      "max_drawdown_pct": -0.0,
      "start_equity": 100.0,
      "end_equity": 102.79605307814091,
      "net_pnl": 2.796053078140949,
      "profit_per_day": 0.04660088463568248,
      "halt_reason": "none",
      "ambiguous": 0
    },
    {
      "label": "risk_5",
      "start_utc": "2026-06-08 21:00:00+00:00",
      "end_utc": "2026-08-07 21:00:00+00:00",
      "trades": 23,
      "trades_per_day": 0.38333333333333336,
      "win_rate": 100.0,
      "ci_low": 85.68788745827374,
      "ci_high": 100.0,
      "expectancy_r": 0.05998741647651311,
      "profit_factor": Infinity,
      "max_drawdown_pct": -0.0,
      "start_equity": 100.0,
      "end_equity": 107.13040842719482,
      "net_pnl": 7.130408427194823,
      "profit_per_day": 0.11884014045324705,
      "halt_reason": "none",
      "ambiguous": 0
    },
    {
      "label": "risk_10",
      "start_utc": "2026-06-08 21:00:00+00:00",
      "end_utc": "2026-08-07 21:00:00+00:00",
      "trades": 23,
      "trades_per_day": 0.38333333333333336,
      "win_rate": 100.0,
      "ci_low": 85.68788745827374,
      "ci_high": 100.0,
      "expectancy_r": 0.059987416476513095,
      "profit_factor": Infinity,
      "max_drawdown_pct": -0.0,
      "start_equity": 100.0,
      "end_equity": 114.74437106828188,
      "net_pnl": 14.744371068281882,
      "profit_per_day": 0.24573951780469805,
      "halt_reason": "none",
      "ambiguous": 0
    },
    {
      "label": "risk_20",
      "start_utc": "2026-06-08 21:00:00+00:00",
      "end_utc": "2026-08-07 21:00:00+00:00",
      "trades": 23,
      "trades_per_day": 0.38333333333333336,
      "win_rate": 100.0,
      "ci_low": 85.68788745827374,
      "ci_high": 100.0,
      "expectancy_r": 0.05998741647651311,
      "profit_factor": Infinity,
      "max_drawdown_pct": -0.0,
      "start_equity": 100.0,
      "end_equity": 131.5493561933709,
      "net_pnl": 31.54935619337093,
      "profit_per_day": 0.5258226032228488,
      "halt_reason": "none",
      "ambiguous": 0
    },
    {
      "label": "risk_100",
      "start_utc": "2026-06-08 21:00:00+00:00",
      "end_utc": "2026-08-07 21:00:00+00:00",
      "trades": 23,
      "trades_per_day": 0.38333333333333336,
      "win_rate": 100.0,
      "ci_low": 85.68788745827374,
      "ci_high": 100.0,
      "expectancy_r": 0.05998741647651311,
      "profit_factor": Infinity,
      "max_drawdown_pct": -0.0,
      "start_equity": 100.0,
      "end_equity": 381.1073009274289,
      "net_pnl": 281.10730092742887,
      "profit_per_day": 4.685121682123815,
      "halt_reason": "none",
      "ambiguous": 0
    }
  ],
  "cost": [
    {
      "label": "cost_1.0x",
      "start_utc": "2026-06-08 21:00:00+00:00",
      "end_utc": "2026-08-07 21:00:00+00:00",
      "trades": 23,
      "trades_per_day": 0.38333333333333336,
      "win_rate": 100.0,
      "ci_low": 85.68788745827374,
      "ci_high": 100.0,
      "expectancy_r": 0.05998741647651311,
      "profit_factor": Infinity,
      "max_drawdown_pct": -0.0,
      "start_equity": 100.0,
      "end_equity": 381.1073009274289,
      "net_pnl": 281.10730092742887,
      "profit_per_day": 4.685121682123815,
      "halt_reason": "none",
      "ambiguous": 0
    },
    {
      "label": "cost_1.5x",
      "start_utc": "2026-06-08 21:00:00+00:00",
      "end_utc": "2026-08-07 21:00:00+00:00",
      "trades": 1,
      "trades_per_day": 0.016666666666666666,
      "win_rate": 100.0,
      "ci_low": 20.654329147389294,
      "ci_high": 100.0,
      "expectancy_r": 0.0692945437285139,
      "profit_factor": Infinity,
      "max_drawdown_pct": -0.0,
      "start_equity": 100.0,
      "end_equity": 106.9294543728514,
      "net_pnl": 6.9294543728513895,
      "profit_per_day": 0.11549090621418982,
      "halt_reason": "none",
      "ambiguous": 0
    },
    {
      "label": "cost_2.0x",
      "start_utc": "2026-06-08 21:00:00+00:00",
      "end_utc": "2026-08-07 21:00:00+00:00",
      "trades": 0,
      "trades_per_day": 0.0,
      "win_rate": 0,
      "ci_low": 0.0,
      "ci_high": 0.0,
      "expectancy_r": 0,
      "profit_factor": 0,
      "max_drawdown_pct": 0,
      "start_equity": 100.0,
      "end_equity": 100.0,
      "net_pnl": 0,
      "profit_per_day": 0.0,
      "halt_reason": "none",
      "ambiguous": 0
    }
  ]
}
```
