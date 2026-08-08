# High-risk + 100% WR algorithm

Config: `config_100wr_high_risk.yaml`  
Engine: EURUSD 1h `hw_range` · risk **100%** · start **$100**

## Measured on hunt sample
- Trades: 11
- Win rate: 100.0%
- Net PnL: $51.58
- Final equity: $151.58
- Avg $/day: $0.848
- Ruined: False

## How to run
```bash
python scripts/run_backtest.py --config config_100wr_high_risk.yaml
python scripts/run_paper.py --config config_100wr_high_risk.yaml
```

## Honest limit
This was **100% on this sample** because every trade hit the tiny TP before the wide SL.
It is **not** a promise of forever 100%. First full stop ≈ wipe the account at this risk.
