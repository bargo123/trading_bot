# 2-hour profit-probability optimization

## What the books said (and we enforced)
| Idea | Source | What we did |
|---|---|---|
| Costs kill HF scalps | Chan *Quantitative Trading* | Cost gate + max **1 trade / 2h** |
| Model spread/slippage | Harris | `spread_bps` + `slippage_bps` |
| High WR via asymmetric R | Tharp | Wide SL (5 ATR), small TP (0.8 ATR) |
| Fixed fractional risk | Elder / Tharp | 5% risk on $100 |
| Test many systems | Davey / Aronson | 720+ then 244 focused configs |
| Regime / reclaim entries | Grimes / oscillators | RSI cross reclaim (not raw dump) |

## Results vs old aggressive scalper
| Metric | Old (26%) | New |
|---|---|---|
| P(profit \| trade in 2h) | ~26% | **~72.5%** |
| P(profit overall in 2h) | ~26% (almost always traded) | **~40%** |
| Trades per active session | ~2.8 | **1** |
| Mean active PnL | −$17 | **~−$0.50** (still slightly negative) |

## Installed profile (`config_100_2h.yaml`)
- Algo: **`rsi_cross`** on BTC-USD 5m
- Risk 5% · SL 5 ATR · TP 0.8 ATR · RSI 35/65 · max 1 trade
- Highest **overall** chance a 2h play ends green (~40%), with ~72.5% when a setup appears

### Alternate “sniper” (rare but highest conditional WR)
- `hw_range` SL3/TP0.6 → **~78.5%** when traded, but only ~24% of sessions get a trade (overall ~19%)

## Honest limit
High win rate ≠ positive expectancy. This profile wins often for small $, loses rarely for larger $ — mean PnL can still be flat/slightly negative after costs. Raising P(profit) further without look-ahead usually means trading less (more flats), not printing free money.

```bash
python scripts/optimize_2h_profit.py      # broad search
python scripts/optimize_2h_highwr.py     # high-WR pass
python scripts/run_paper.py --config config_100_2h.yaml
```
