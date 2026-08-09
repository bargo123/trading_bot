# 100WR Safe Fast — measured 100% WR window

Config: `config_100wr_safe_fast.yaml`  
Signal = classic `config_100wr` (wide SL / tiny TP) + forever_safe pocket.

## Measured on the hunt window (~45d EURUSD 1h)
| Metric | Value |
|--------|-------|
| Trades | **11** |
| Win rate | **100%** (11/11 TP) |
| From $100 | **$104.17** (+$4.17) |
| Expectancy R | 0.114 |

## Honesty (not “always forever”)
Same params on **~400d**: WR drops to **~91%**, profit factor **&lt;1**, net **loss**.  
100% WR here is a **short measured sample**, not a guarantee every future trade wins.

```bash
python scripts/run_backtest.py --config config_100wr_safe_fast.yaml
```
