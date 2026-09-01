# HALE Basket — measured coarse-screen results

Symbols: `EURUSD=X, GBPUSD=X, AUDUSD=X, NZDUSD=X` · one shared starting equity: **$100**

**Verdict: REJECTED for paper promotion; the existing paper bot remains stopped. No primary frozen holdout achieved 100% WR after costs.**

HALE tests the added Heikin-Ashi book's strongest auditable rule: a contracted same-color impulse at an objective level, followed by the first opposite completed HA bar. HA prices generate signals only; all entries use the next real OHLC open.
The search evaluated 528 development/validation configurations. **0 of 4 family/timeframe selections passed the minimum-sample plus positive development/validation E[R] and PF gates.** The primary below is therefore diagnostic, not qualified.

## Development, validation, and frozen holdout selections

### Fade · M5

- Development: n=2 · 0.0/day · WR=100.0% (95% CI 34.2–100.0%) · net E[R]=+0.265 · PF=inf · DD=0.0% · $100→$100.93 · $+0.02/calendar day · halt=none · ambiguous=0
- Validation: n=0 · 0.0/day · WR=0.0% (95% CI 0.0–0.0%) · net E[R]=+0.000 · PF=0.00 · DD=0.0% · $100→$100.00 · $+0.00/calendar day · halt=none · ambiguous=0
- Frozen holdout: n=0 · 0.0/day · WR=0.0% (95% CI 0.0–0.0%) · net E[R]=+0.000 · PF=0.00 · DD=0.0% · $100→$100.00 · $+0.00/calendar day · halt=none · ambiguous=0

### Pullback · M5

- Development: n=65 · 1.3/day · WR=44.6% (95% CI 33.2–56.7%) · net E[R]=-0.480 · PF=0.24 · DD=30.8% · $100→$69.17 · $-0.62/calendar day · halt=max_drawdown 30.83% · ambiguous=0
- Validation: n=25 · 1.6/day · WR=52.0% (95% CI 33.5–70.0%) · net E[R]=-0.278 · PF=0.40 · DD=9.1% · $100→$91.52 · $-0.54/calendar day · halt=none · ambiguous=0
- Frozen holdout: n=34 · 2.2/day · WR=55.9% (95% CI 39.5–71.1%) · net E[R]=-0.259 · PF=0.41 · DD=12.5% · $100→$88.86 · $-0.71/calendar day · halt=none · ambiguous=0

### Fade · M1

- Development: n=0 · 0.0/day · WR=0.0% (95% CI 0.0–0.0%) · net E[R]=+0.000 · PF=0.00 · DD=0.0% · $100→$100.00 · $+0.00/calendar day · halt=none · ambiguous=0
- Validation: n=0 · 0.0/day · WR=0.0% (95% CI 0.0–0.0%) · net E[R]=+0.000 · PF=0.00 · DD=0.0% · $100→$100.00 · $+0.00/calendar day · halt=none · ambiguous=0
- Frozen holdout: n=0 · 0.0/day · WR=0.0% (95% CI 0.0–0.0%) · net E[R]=+0.000 · PF=0.00 · DD=0.0% · $100→$100.00 · $+0.00/calendar day · halt=none · ambiguous=0

### Pullback · M1

- Development: n=1 · 0.2/day · WR=0.0% (95% CI 0.0–79.3%) · net E[R]=-0.807 · PF=0.00 · DD=1.0% · $100→$99.04 · $-0.15/calendar day · halt=none · ambiguous=0
- Validation: n=0 · 0.0/day · WR=0.0% (95% CI 0.0–0.0%) · net E[R]=+0.000 · PF=0.00 · DD=0.0% · $100→$100.00 · $+0.00/calendar day · halt=none · ambiguous=0
- Frozen holdout: n=0 · 0.0/day · WR=0.0% (95% CI 0.0–0.0%) · net E[R]=+0.000 · PF=0.00 · DD=0.0% · $100→$100.00 · $+0.00/calendar day · halt=none · ambiguous=0

## Primary selected configuration

Family: **pullback** · timeframe: **5m** · selected without holdout metrics.
Development/validation selection gate: **FAIL**.

```yaml
max_hold_bars: 6
cafb_htf_adx_min: 25
hale_round_grid: 0.005
hale_impulse_bars: 3
hale_impulse_atr: 1.0
hale_contraction_ratio: 0.6
hale_level_atr: 0.5
hale_stop_buffer_atr: 0.25
hale_target_r: 0.8
hale_pullback_bars: 1
hale_pullback_near_atr: 1.0
```

## Mandatory primary holdout numbers

- Sample: `2026-07-23 02:50:00+00:00` to `2026-08-07 21:25:00+00:00` (15.77 calendar days).
- Closed trades: **34**; trades/day: **2.16**.
- WR: **55.88%** (Wilson 95% CI **39.45–71.12%**).
- Net E[R]: **-0.2586**; PF: **0.41**.
- Max DD: **12.53%**; equity: **$100.00 → $88.86**.
- Net P&L/day: **$-0.71** per historical calendar day; halt: **none**; ambiguous exits: **0**.
- Primary costs: 0.6 bps spread + 0.3 bps slippage per side, no fixed commission; stop/target collisions are stop-first.

## Cost and aggressive-sizing stress

| Test | Trades | Trades/day | WR | Net E[R] | PF | Max DD | $100 end | Profit/day | Halt |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| holdout_cost_1.0x | 90 | 5.71 | 51.1% | -0.465 | 0.36 | 24.4% | $77.44 | $-1.43 | none |
| holdout_cost_1.5x | 34 | 2.16 | 55.9% | -0.259 | 0.41 | 12.5% | $88.86 | $-0.71 | none |
| holdout_cost_2.0x | 6 | 0.38 | 33.3% | -0.574 | 0.18 | 6.9% | $93.93 | $-0.38 | none |
| holdout_risk_1 | 35 | 2.22 | 51.4% | -0.346 | 0.34 | 9.8% | $90.57 | $-0.60 | none |
| holdout_risk_2 | 34 | 2.16 | 55.9% | -0.259 | 0.41 | 12.5% | $88.86 | $-0.71 | none |
| holdout_risk_5 | 33 | 2.09 | 54.5% | -0.283 | 0.41 | 12.5% | $88.90 | $-0.70 | none |
| holdout_risk_10 | 33 | 2.09 | 54.5% | -0.283 | 0.41 | 12.5% | $88.90 | $-0.70 | none |
| holdout_risk_20 | 33 | 2.09 | 54.5% | -0.283 | 0.41 | 12.5% | $88.90 | $-0.70 | none |
| holdout_ib_4usd_gate | 0 | 0.00 | 0.0% | +0.000 | 0.00 | 0.0% | $100.00 | $+0.00 | none |
| holdout_ib_4usd_forced | 7 | 0.44 | 0.0% | -14.099 | 0.00 | 32.4% | $67.60 | $-2.05 | max_drawdown 32.40% |

## Promotion gates

- `holdout_trades_at_least_100`: **FAIL**
- `holdout_expectancy_positive`: **FAIL**
- `holdout_pf_above_1`: **FAIL**
- `holdout_survived`: **PASS**
- `positive_pnl_concentration_at_most_60pct`: **PASS**
- `two_x_cost_survived_with_edge`: **FAIL**
- `max_positive_pnl_concentration`: **46.8%**
- `promoted`: **FAIL**

## Data windows

- 5m `EURUSD=X`: 16776 bars, `2026-05-18 23:00:00+00:00` to `2026-08-07 21:25:00+00:00`, actual interval `5m`.
- 5m `GBPUSD=X`: 16776 bars, `2026-05-18 23:00:00+00:00` to `2026-08-07 21:25:00+00:00`, actual interval `5m`.
- 5m `AUDUSD=X`: 16777 bars, `2026-05-18 23:00:00+00:00` to `2026-08-07 21:25:00+00:00`, actual interval `5m`.
- 5m `NZDUSD=X`: 16776 bars, `2026-05-18 23:00:00+00:00` to `2026-08-07 21:25:00+00:00`, actual interval `5m`.
- 1m `EURUSD=X`: 9889 bars, `2026-07-29 23:00:00+00:00` to `2026-08-07 21:29:00+00:00`, actual interval `1m`.
- 1m `GBPUSD=X`: 9892 bars, `2026-07-29 23:00:00+00:00` to `2026-08-07 21:29:00+00:00`, actual interval `1m`.
- 1m `AUDUSD=X`: 4942 bars, `2026-07-29 23:01:00+00:00` to `2026-08-07 21:29:00+00:00`, actual interval `1m`.
- 1m `NZDUSD=X`: 4941 bars, `2026-07-29 23:01:00+00:00` to `2026-08-07 21:29:00+00:00`, actual interval `1m`.

## Limits and decision

- Yahoo OHLC cannot validate tick ordering, live spread at the level, or sub-minute bid/ask fills. This is a conservative coarse screen, not an MT5 scalp proof.
- The IB-like `$4` rows expose the fixed fee that earlier bps-only basket tests omitted. The `gate` row declines uneconomic trades; the `forced` row shows the result if that guard is bypassed.
- Aggressive risk changes the equity path but not the underlying E[R]. No sizing row authorizes live trading.
- Profit/day is historical P&L divided by calendar span, not a promised daily income.
- Full development/validation grid: `/Users/zaid.barghouthi/trading-llm/bot/reports/hale_search_results.csv`.
