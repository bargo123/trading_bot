# Strategy Bake-off

Symbol: `EURUSD=X` · Timeframe: `1h` · Bars: `16539`

Same data, same risk engine, same costs. No look-ahead.

**Winner (composite score, ≥10 trades): `aegis_range_hw` — Aegis Range HW (BB+RSI)**

- Win rate: **96.55%**
- Profit factor: **2.882**
- Max DD: **0.56%**
- Net PnL: **105.04**
- Trades: **29**
- Book basis: Optimized mean reversion / TA oscillators

## Ranked results

| Rank | ID | Name | Trades | WR% | PF | MaxDD% | Exp R | Net PnL | Score |
| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | `aegis_range_hw` | Aegis Range HW (BB+RSI) | 29 | 96.55 | 2.882 | 0.56 | 0.159 | 105.04 | 1153.87 |
| 2 | `rsi_pure` | RSI Pure MR | 193 | 72.54 | 0.552 | 12.05 | -0.042 | -1205.03 | 59.27 |
| 3 | `bb_mr` | Bollinger Fade | 142 | 72.54 | 0.397 | 12.47 | -0.072 | -1247.28 | 55.18 |
| 4 | `stoch_mr` | Stochastic MR | 95 | 66.32 | 0.322 | 12.29 | -0.151 | -1132.93 | 47.42 |
| 5 | `ema_cross` | EMA 50/200 Cross | 61 | 37.70 | 0.587 | 6.07 | -0.082 | -484.71 | 36.89 |
| 6 | `macd_cross` | MACD Cross | 157 | 33.76 | 0.723 | 12.33 | -0.015 | -1030.69 | 23.48 |
| 7 | `donch20` | Donchian 20 Breakout | 106 | 35.85 | 0.585 | 12.07 | -0.104 | -1102.44 | 22.89 |
| 8 | `elder_impulse` | Elder Impulse Proxy | 130 | 33.08 | 0.665 | 12.41 | -0.044 | -1038.34 | 21.34 |
| 9 | `atr_breakout` | ATR Channel Breakout | 79 | 34.18 | 0.434 | 12.07 | -0.202 | -1197.27 | 17.71 |
| 10 | `bb_squeeze` | BB Squeeze Breakout | 80 | 30.00 | 0.461 | 12.05 | -0.187 | -1205.00 | 14.18 |
| 11 | `donch55` | Donchian 55 Trend | 66 | 22.73 | 0.344 | 12.20 | -0.261 | -1129.96 | 3.91 |

## Notes

- High win rate ≠ best system if PF/expectancy are weak.
- Trend systems often have lower WR but larger winners.
- Promote winner into live/paper only after you accept its trade-off profile.

CSV: `/Users/zaid.barghouthi/trading-llm/bot/reports/bakeoff_results.csv`
