# Ensemble ACCEPT-ALL

**Both walk-forward halves PASS** on EURUSD 1h.

## Rules
- Ensemble votes ≥ **2**
- Members: `book_optimal`, `breakout_adx`, `trend_pullback`, `hw_range`
- Session **08–16 UTC**, ADX min **15**, min RR **1.5**

## Measured ($10k, 1% risk, ~400d)
| Window | Trades | WR | PnL | PF |
|--|--:|--:|--:|--:|
| First half | 10 | 50.0% | $141.92 | 1.35 |
| Second half | 5 | 80.0% | $446.70 | 53.26 |
| Full | 15 | 60.0% | $594.96 | 2.43 |

DD full: 2.4%

## Config
`config_ensemble_accept_all.yaml`

```bash
python scripts/run_backtest.py --config config_ensemble_accept_all.yaml
```
