# 1000 trades · book_optimal · $100 · high risk

## Real backtest (not 1000 trades — sample too short)
| | Strict | Looser filters |
|--|--|--|
| Trades | 14 | 48 |
| WR | 57.1% | 47.9% |
| PnL on $100 @80% risk | $-102.09 | $-100.00 |

Yahoo 15m history only yields dozens of signals, not 1000.

## 1000-trade Monte Carlo
Bootstrap the **real trade R multiples** from book_optimal (48 trades), replay **1000 trades × 2000 random paths**, start **$100**.

### @ 80% risk / trade
| | |
|--|--|
| **Ruined (equity <$1)** | **100.0%** of paths |
| Median final | $0.70 |
| Mean final | $0.59 |
| 5th percentile | $0.30 |
| 95th percentile | $0.80 |
| Paths still > $100 | 0.0% |

### @ 5% risk / trade (same 1000 trades)
| | |
|--|--|
| Ruined | 0.0% |
| Median final | $274569.78 |
| Mean final | $1850546.85 |

### @ 100% risk / trade
| | |
|--|--|
| Ruined | 100.0% |
| Median final | $0.00 |

## Verdict
At high risk on $100, **most 1000-trade paths ruin** even using book_optimal’s measured R distribution. A short lucky streak can spike equity; then one/few losses wipe it.
