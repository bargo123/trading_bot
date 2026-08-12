# Corrected re-measurement — tuned 1h 100%-WR configuration

The original selected parameters were not re-tuned. This rerun uses cost-adjusted R, end-of-test liquidation, and historical-time risk checks.

## Window results

| Window | Exact UTC sample | Trades | Trades/day | WR (95% Wilson CI) | Net E[R] | PF | Max DD | $100 end | Profit/day | Halt |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 45d_all_in | 2026-06-23 21:00:00+00:00 → 2026-08-07 21:00:00+00:00 | 15 | 0.33 | 100.0% (79.6–100.0%) | +0.059 | inf | 0.0% | $234.58 | $+2.99 | none |
| 60d_all_in | 2026-06-08 21:00:00+00:00 → 2026-08-07 21:00:00+00:00 | 20 | 0.33 | 100.0% (83.9–100.0%) | +0.060 | inf | 0.0% | $320.73 | $+3.68 | none |
| 75d_all_in | 2026-05-24 23:00:00+00:00 → 2026-08-07 21:00:00+00:00 | 24 | 0.32 | 100.0% (86.2–100.0%) | +0.059 | inf | 0.0% | $398.02 | $+3.98 | none |
| 90d_all_in | 2026-05-10 23:00:00+00:00 → 2026-08-07 21:00:00+00:00 | 25 | 0.28 | 100.0% (86.7–100.0%) | +0.060 | inf | 0.0% | $426.96 | $+3.68 | none |

## Same 60-day signals — sizing comparison

| Risk/trade | Trades | WR | Net E[R] | PF | Max DD | $100 end | Profit/day | Halt |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1% | 20 | 100.0% | +0.060 | inf | 0.0% | $101.21 | $+0.02 | none |
| 2% | 20 | 100.0% | +0.060 | inf | 0.0% | $102.43 | $+0.04 | none |
| 5% | 20 | 100.0% | +0.060 | inf | 0.0% | $106.18 | $+0.10 | none |
| 10% | 20 | 100.0% | +0.060 | inf | 0.0% | $112.73 | $+0.21 | none |
| 20% | 20 | 100.0% | +0.060 | inf | 0.0% | $126.99 | $+0.45 | none |
| 100% | 20 | 100.0% | +0.060 | inf | 0.0% | $320.73 | $+3.68 | none |

## Same 60-day signals — cost stress at 100% risk

| Cost | Trades | WR | Net E[R] | PF | Max DD | $100 end | Profit/day | Halt |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1.0x | 20 | 100.0% | +0.060 | inf | 0.0% | $320.73 | $+3.68 | none |
| 1.5x | 1 | 100.0% | +0.069 | inf | 0.0% | $106.93 | $+0.12 | none |
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
      "trades": 15,
      "trades_per_day": 0.3333333333333333,
      "win_rate": 100.0,
      "ci_low": 79.6110733695652,
      "ci_high": 100.0,
      "expectancy_r": 0.05856786013177931,
      "profit_factor": Infinity,
      "max_drawdown_pct": 0.0,
      "start_equity": 100.0,
      "end_equity": 234.57675043298687,
      "net_pnl": 134.57675043298687,
      "profit_per_day": 2.990594454066375,
      "halt_reason": "none",
      "ambiguous": 0
    },
    {
      "label": "60d_all_in",
      "start_utc": "2026-06-08 21:00:00+00:00",
      "end_utc": "2026-08-07 21:00:00+00:00",
      "trades": 20,
      "trades_per_day": 0.3333333333333333,
      "win_rate": 100.0,
      "ci_low": 83.88698745050667,
      "ci_high": 100.0,
      "expectancy_r": 0.06010653345331317,
      "profit_factor": Infinity,
      "max_drawdown_pct": 0.0,
      "start_equity": 100.0,
      "end_equity": 320.72941888563247,
      "net_pnl": 220.72941888563244,
      "profit_per_day": 3.678823648093874,
      "halt_reason": "none",
      "ambiguous": 0
    },
    {
      "label": "75d_all_in",
      "start_utc": "2026-05-24 23:00:00+00:00",
      "end_utc": "2026-08-07 21:00:00+00:00",
      "trades": 24,
      "trades_per_day": 0.3203559510567297,
      "win_rate": 100.0,
      "ci_low": 86.20194241710247,
      "ci_high": 100.0,
      "expectancy_r": 0.05935791914089549,
      "profit_factor": Infinity,
      "max_drawdown_pct": 0.0,
      "start_equity": 100.0,
      "end_equity": 398.01597193655255,
      "net_pnl": 298.01597193655255,
      "profit_per_day": 3.9779662549929147,
      "halt_reason": "none",
      "ambiguous": 0
    },
    {
      "label": "90d_all_in",
      "start_utc": "2026-05-10 23:00:00+00:00",
      "end_utc": "2026-08-07 21:00:00+00:00",
      "trades": 25,
      "trades_per_day": 0.2811621368322399,
      "win_rate": 100.0,
      "ci_low": 86.68035060468213,
      "ci_high": 100.0,
      "expectancy_r": 0.05989213585555455,
      "profit_factor": Infinity,
      "max_drawdown_pct": 0.0,
      "start_equity": 100.0,
      "end_equity": 426.9570414382918,
      "net_pnl": 326.95704143829187,
      "profit_per_day": 3.677117616925494,
      "halt_reason": "none",
      "ambiguous": 0
    }
  ],
  "risk": [
    {
      "label": "risk_1",
      "start_utc": "2026-06-08 21:00:00+00:00",
      "end_utc": "2026-08-07 21:00:00+00:00",
      "trades": 20,
      "trades_per_day": 0.3333333333333333,
      "win_rate": 100.0,
      "ci_low": 83.88698745050667,
      "ci_high": 100.0,
      "expectancy_r": 0.06010653345331317,
      "profit_factor": Infinity,
      "max_drawdown_pct": 0.0,
      "start_equity": 100.0,
      "end_equity": 101.20899746271853,
      "net_pnl": 1.2089974627185254,
      "profit_per_day": 0.020149957711975423,
      "halt_reason": "none",
      "ambiguous": 0
    },
    {
      "label": "risk_2",
      "start_utc": "2026-06-08 21:00:00+00:00",
      "end_utc": "2026-08-07 21:00:00+00:00",
      "trades": 20,
      "trades_per_day": 0.3333333333333333,
      "win_rate": 100.0,
      "ci_low": 83.88698745050667,
      "ci_high": 100.0,
      "expectancy_r": 0.06010653345331317,
      "profit_factor": Infinity,
      "max_drawdown_pct": 0.0,
      "start_equity": 100.0,
      "end_equity": 102.43182732866939,
      "net_pnl": 2.4318273286693866,
      "profit_per_day": 0.04053045547782311,
      "halt_reason": "none",
      "ambiguous": 0
    },
    {
      "label": "risk_5",
      "start_utc": "2026-06-08 21:00:00+00:00",
      "end_utc": "2026-08-07 21:00:00+00:00",
      "trades": 20,
      "trades_per_day": 0.3333333333333333,
      "win_rate": 100.0,
      "ci_low": 83.88698745050667,
      "ci_high": 100.0,
      "expectancy_r": 0.06010653345331317,
      "profit_factor": Infinity,
      "max_drawdown_pct": 0.0,
      "start_equity": 100.0,
      "end_equity": 106.18481247784987,
      "net_pnl": 6.184812477849897,
      "profit_per_day": 0.10308020796416496,
      "halt_reason": "none",
      "ambiguous": 0
    },
    {
      "label": "risk_10",
      "start_utc": "2026-06-08 21:00:00+00:00",
      "end_utc": "2026-08-07 21:00:00+00:00",
      "trades": 20,
      "trades_per_day": 0.3333333333333333,
      "win_rate": 100.0,
      "ci_low": 83.88698745050667,
      "ci_high": 100.0,
      "expectancy_r": 0.06010653345331317,
      "profit_factor": Infinity,
      "max_drawdown_pct": 0.0,
      "start_equity": 100.0,
      "end_equity": 112.73067742634571,
      "net_pnl": 12.730677426345743,
      "profit_per_day": 0.21217795710576237,
      "halt_reason": "none",
      "ambiguous": 0
    },
    {
      "label": "risk_20",
      "start_utc": "2026-06-08 21:00:00+00:00",
      "end_utc": "2026-08-07 21:00:00+00:00",
      "trades": 20,
      "trades_per_day": 0.3333333333333333,
      "win_rate": 100.0,
      "ci_low": 83.88698745050667,
      "ci_high": 100.0,
      "expectancy_r": 0.06010653345331317,
      "profit_factor": Infinity,
      "max_drawdown_pct": 0.0,
      "start_equity": 100.0,
      "end_equity": 126.98594825301059,
      "net_pnl": 26.9859482530106,
      "profit_per_day": 0.44976580421684337,
      "halt_reason": "none",
      "ambiguous": 0
    },
    {
      "label": "risk_100",
      "start_utc": "2026-06-08 21:00:00+00:00",
      "end_utc": "2026-08-07 21:00:00+00:00",
      "trades": 20,
      "trades_per_day": 0.3333333333333333,
      "win_rate": 100.0,
      "ci_low": 83.88698745050667,
      "ci_high": 100.0,
      "expectancy_r": 0.06010653345331317,
      "profit_factor": Infinity,
      "max_drawdown_pct": 0.0,
      "start_equity": 100.0,
      "end_equity": 320.72941888563247,
      "net_pnl": 220.72941888563244,
      "profit_per_day": 3.678823648093874,
      "halt_reason": "none",
      "ambiguous": 0
    }
  ],
  "cost": [
    {
      "label": "cost_1.0x",
      "start_utc": "2026-06-08 21:00:00+00:00",
      "end_utc": "2026-08-07 21:00:00+00:00",
      "trades": 20,
      "trades_per_day": 0.3333333333333333,
      "win_rate": 100.0,
      "ci_low": 83.88698745050667,
      "ci_high": 100.0,
      "expectancy_r": 0.06010653345331317,
      "profit_factor": Infinity,
      "max_drawdown_pct": 0.0,
      "start_equity": 100.0,
      "end_equity": 320.72941888563247,
      "net_pnl": 220.72941888563244,
      "profit_per_day": 3.678823648093874,
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
      "expectancy_r": 0.06929454372847092,
      "profit_factor": Infinity,
      "max_drawdown_pct": 0.0,
      "start_equity": 100.0,
      "end_equity": 106.92945437284709,
      "net_pnl": 6.929454372847092,
      "profit_per_day": 0.1154909062141182,
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
