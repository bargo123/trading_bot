# Aziz + Steidlmayer wiring test

Symbol: `BTC-USD` · TF: `15m` · Bars: `4167` · Start equity: `$10,000`

| Algo | Trades | WR% | PF | MaxDD% | Exp R | Net PnL | Final |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `steidl_ib_fade` | 2 | 0.0 | 0.000 | 2.42 | -1.000 | -241.81 | 9758.19 |
| `breakout_adx` | 125 | 54.4 | 0.933 | 9.63 | 0.088 | -411.64 | 9588.36 |
| `steidl_ib_break` | 30 | 33.3 | 0.795 | 10.12 | 0.000 | -469.36 | 9530.64 |
| `aziz_orb` | 87 | 42.5 | 0.914 | 16.19 | 0.276 | -522.38 | 9477.62 |
| `hw_range` | 28 | 32.1 | 0.591 | 9.07 | -0.143 | -901.68 | 9098.32 |
| `aziz_vwap` | 112 | 33.9 | 0.813 | 15.21 | 0.018 | -1468.95 | 8531.05 |

## Wired from books
- **Aziz ORB** — opening-range break, VWAP-related stop, min 2:1 R:R
- **Aziz VWAP** — reclaim/reject VWAP, min 2:1 R:R
- **Steidlmayer IB break** — go-with Initial Balance break (initiating filter)
- **Steidlmayer IB fade** — fade first extension on narrow IB

CSV: `/Users/zaid.barghouthi/trading-llm/bot/reports/aziz_steidl_test.csv`
