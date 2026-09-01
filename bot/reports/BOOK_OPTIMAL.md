# Book-optimal algorithm — measured search (NOT a promise)

Synthesized from all library books: session gates (Silvani/Fabris), HTF trend
(Ponsi/Damir/DraKoln), NTZ/ORB/squeeze/pullback triggers, VWAP side (Aziz),
min R:R (Damir/Afshari/Thomas), cost filter (Silvani/Harris), 1% risk.

TF: `15m` · Start equity: `$10,000` · Costs included · No look-ahead

## Did we find 100% win rate?
**No.** Across all baselines + parameter grid, **zero** configs hit **100% WR with ≥5 trades**.

## Best by net PnL (trades ≥ 5)

| Symbol | Tag | Trades | WR% | PF | Exp R | Net PnL | MaxDD% |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `BTC-USD` | `search:book_optimal` | 33 | 54.5 | 1.820 | 0.551 | 1262.35 | 4.06 |
| `BTC-USD` | `search:book_optimal` | 33 | 54.5 | 1.820 | 0.551 | 1262.35 | 4.06 |
| `BTC-USD` | `search:book_optimal` | 33 | 54.5 | 1.706 | 0.530 | 1150.21 | 4.93 |
| `BTC-USD` | `search:book_optimal` | 33 | 54.5 | 1.706 | 0.530 | 1150.21 | 4.93 |
| `BTC-USD` | `search:book_optimal` | 33 | 54.5 | 1.675 | 0.530 | 1113.87 | 5.15 |
| `BTC-USD` | `search:book_optimal` | 33 | 54.5 | 1.675 | 0.530 | 1113.87 | 5.15 |
| `BTC-USD` | `search:book_optimal` | 34 | 52.9 | 1.659 | 0.505 | 1113.45 | 4.06 |
| `BTC-USD` | `search:book_optimal` | 34 | 52.9 | 1.659 | 0.505 | 1113.45 | 4.06 |
| `BTC-USD` | `search:book_optimal` | 31 | 61.3 | 1.898 | 0.528 | 1069.76 | 3.55 |
| `BTC-USD` | `search:book_optimal` | 31 | 61.3 | 1.898 | 0.528 | 1069.76 | 3.55 |

## Best by win rate (trades ≥ 5)

| Symbol | Tag | Trades | WR% | Net PnL | Exp R |
| --- | --- | ---: | ---: | ---: | ---: |
| `BTC-USD` | `search:book_optimal` | 6 | 66.7 | 298.20 | 0.682 |
| `BTC-USD` | `search:book_optimal` | 6 | 66.7 | 298.20 | 0.682 |
| `BTC-USD` | `search:book_optimal` | 6 | 66.7 | 298.20 | 0.682 |
| `BTC-USD` | `search:book_optimal` | 6 | 66.7 | 298.20 | 0.682 |
| `BTC-USD` | `search:book_optimal` | 6 | 66.7 | 298.20 | 0.682 |
| `BTC-USD` | `search:book_optimal` | 6 | 66.7 | 298.20 | 0.682 |
| `BTC-USD` | `search:book_optimal` | 6 | 66.7 | 298.20 | 0.682 |
| `BTC-USD` | `search:book_optimal` | 6 | 66.7 | 298.20 | 0.682 |
| `BTC-USD` | `search:book_optimal` | 6 | 66.7 | 298.20 | 0.682 |
| `BTC-USD` | `search:book_optimal` | 6 | 66.7 | 298.20 | 0.682 |

## Verdict
- Books (Ponsi, DraKoln, Windsor, Afshari’s own Ch.6, Elder/Tharp) reject guaranteed 100%.
- This search **tried** the confluence engine + tight R:R high-WR attempts.
- Use the **best PnL** config if positive; never size as if WR=100%.

CSV: `/Users/zaid.barghouthi/trading-llm/bot/reports/book_optimal_search.csv`

Run: `python scripts/run_backtest.py --config config_book_optimal.yaml`
