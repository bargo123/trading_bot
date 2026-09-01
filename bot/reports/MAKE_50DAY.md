# $50/day — measured way

## Do this
1. Fund account to **$3,174.07**
2. Run `book_optimal` at **5%** risk:

```bash
cd ~/trading-llm/bot && source .venv/bin/activate
python scripts/run_backtest.py --config config_make_50day.yaml
python scripts/run_paper.py --config config_make_50day.yaml
```

## Measured on sample
| | |
|--|--|
| Market | `BTC-USD` `15m` |
| Equity | **$3,174.07** |
| Risk | 5% |
| Trades | 33 |
| WR | 54.5% |
| **$/day** | **$50.50** |
| Net | $2,254.10 |
| Max DD | 20.2% |

## $100
Not enough by itself. Deposit until **$3,174.07**, then this config is the measured $50/day path.
