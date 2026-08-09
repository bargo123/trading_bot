# Million-trade sim from $100 — after book expectancy fix

Bootstrap of measured R from `config_100wr_safe_fast.yaml` (Tharp-style ~1.5R target, min_rr 1.3).

## Edge
| | Before (tiny scalp) | After (book RR) |
|--|--:|--:|
| WR | 78.2% | 50.0% |
| avg win R | +0.17 | **+1.50** |
| avg loss R | −1.00 | −1.00 |
| mean R | **−0.084** | **+0.250** |

## Bootstrap @1% risk / trade
| | Before | After |
|--|--:|--:|
| Seed 42 @1k trades | ~$52 | **~$812** |
| Seed 42 @~5–7k | ruined ~$1 | still growing |
| 20 seeds @1M target | 0/20 above $100 | **20/20 above $100** (math compounds to overflow — **not a forecast**) |

## Honest measured backtest (not 1M trades)
- $100 @1%: **$109.69** (+$9.69) over 76 trades  
- $10k @1%: **$10,968.90** (+$968.90)

Do **not** treat 1M bootstrap finals as achievable income — signal rate and costs in live markets are not i.i.d. forever.
