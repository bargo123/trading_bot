# $100 → thousands — Thomas growth algorithm

## What the books actually say (Thomas 10XROI)
People who “make thousands from a small account” in that book use:
1. Wins near **10R** (not tiny scalps)
2. **Compound 50% of each win** into the next trade
3. After a loss → reset to **1%**
4. Prefer a **separate speculative account**

Wired as: `thomas_growth` MM + `thomas_10r` / `book_optimal` signals → `config_100_to_thousands.yaml`

## Measured from $100 (this search)
| Metric | Value |
|--|--|
| Best peak | $112.04 |
| Best final | $97.55 |
| Best setup | `thomas10r_BTC-USD_15m_rr10_p0` |
| Configs hitting $1k peak | 0 |
| Best survivor final | $0.00 |

## Book streak math (IF you string 10R wins)
Starting $100 at 1% then compounding 50% of each 10R win: **$100 → hundreds → thousands in a few wins** — that is the ebook table. On real bars, those streak assumptions rarely hold.

## Run
```bash
python scripts/run_backtest.py --config config_100_to_thousands.yaml
```

CSV: `reports/growth_100_search.csv`
