# Ensemble optimal — all strategies combined

## Idea
Trade only when **multiple book engines agree** (votes).
Members: book_optimal, thomas_10r, breakout, pullback, hw_range, aziz_vwap, steidl IB, fabris NTZ.

## Best measured
```
{'sym': 'EURUSD=X', 'tf': '1h', 'votes': 2, 'mrr': 1.5, 'sess': '7-17', 'trades': 7, 'wr': 57.1, 'pf': 2.09, 'exp': 0.438, 'pnl': 223.07, 'final': 10223.07, 'dd': 1.2, 'score': 0.793}
```
Config: `config_ensemble_optimal.yaml`

## Walk-forward (half/half)
- First: trades=6 WR=66.7% PnL=$230.78 PF=2.17
- Second: trades=1 WR=0.0% PnL=$-7.54 PF=0.00
- Both halves acceptable: **False**

## Run
```bash
python scripts/run_backtest.py --config config_ensemble_optimal.yaml
```
