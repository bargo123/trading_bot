# Fabris NTZ + Fuller pyramiding wiring test

TF: `15m` · Start equity: `$10,000`

| Symbol | Algo | Trades | WR% | PF | MaxDD% | Exp R | Net PnL | Final | Adds |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `BTC-USD` | `breakout_adx` | 122 | 54.9 | 0.951 | 9.63 | 0.098 | -291.59 | 9708.41 | 0 |
| `BTC-USD` | `fabris_ntz` | 64 | 37.5 | 0.660 | 15.62 | -0.040 | -1282.27 | 8717.73 | 0 |
| `BTC-USD` | `fabris_ntz_pyramid` | 29 | 6.9 | 0.109 | 20.27 | -0.559 | -2027.36 | 7972.64 | 9 |
| `EURUSD=X` | `fabris_ntz` | 40 | 52.5 | 1.071 | 3.34 | 0.209 | 129.34 | 10129.34 | 0 |
| `EURUSD=X` | `fabris_ntz_pyramid` | 40 | 40.0 | 0.783 | 16.19 | -0.122 | -548.94 | 9451.06 | 17 |
| `EURUSD=X` | `breakout_adx` | 79 | 48.1 | 0.545 | 20.80 | -0.038 | -2080.27 | 7919.73 | 0 |

## Wired from books
- **Fabris NTZ** — GMT 07–08 high/low breakout, width filter, SL=opposite NTZ, TP=N×width, flatten 17:00, ≤2 trades/day
- **Fuller pyramid** — add at +1R/+2R only if ADX strong; trail unified SL to prior entry (risk ≤ 1R)

Note: sample results are costs-in, no look-ahead; Fabris was designed for FX session structure — BTC is a transfer test.

CSV: `/Users/zaid.barghouthi/trading-llm/bot/reports/fabris_fuller_test.csv`
