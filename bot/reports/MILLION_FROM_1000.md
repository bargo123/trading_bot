# $1000 @ 100% → $1.26M — stress test

## Data checked
- EURUSD 1h: **17,243 bars** (~2 years)
- Walk-forward 45d windows: **48** with ≥5 trades
- Perfect 100% windows: **16 / 48 (33.3%)**
- Window WR: median **88.9%** · mean **88.5%** · min **57.1%**

## Full-history 100WR params
- Trades: 157 · WR: 89.2% · final@$1k 1% risk: $884.23

## $1000 @ 100% risk
- On original ~45d hunt window: trades=11 WR=100.0% final=**$1515.79**
- On full ~2y history: trades=13 WR=92.3% final=**$-196.72** ruined=True

## Config
`config_1000_to_million.yaml`

## Verdict
The **$1.26M** figure needs unbroken 100% WR for ~66 compounds at 100% risk.
Walk-forward shows 100% is **not** always true. Full history at 100% risk does **not** print a million.
