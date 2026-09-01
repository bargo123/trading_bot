# $50/day from $100 — full check result

## What was checked
- Books (Aziz, DraKoln, Ponsi, Silvani, Fabris, Brown, Elder/Tharp digests): small account cannot fund large daily income; ≤1–2% risk; undercapitalized salary targets = ruin.
- Extreme backtests from **$100**: 100% WR, book_optimal, fabris, breakout, pyramiding, risk 50–100%.

## Measured from $100
| Setup | Avg $/day | Best single day | End equity |
|--|--|--|--|
| 100%WR EURUSD @ 100% risk | **+$0.85** | +$8.61 | $151 (still up) |
| book_optimal BTC @ 100% risk | **−$4.43** | +$752* | **−$98 (ruined)** |
| breakout+pyramid @ 50–100% | **−$2+** | — | **$0 / ruined** |

\*One lucky day printed >$50 but the same run wiped the account. That is not a daily method.

## Hits for sustained $50/day from $100
**Zero.** No config averaged ≥ $50/day starting at $100.

## The way that does hit $50/day (measured)
Fund to **~$3,174**, then:

```bash
python scripts/run_backtest.py --config config_make_50day.yaml
python scripts/run_paper.py --config config_make_50day.yaml
```

Measured: **~$50.50/day**, BTC 15m `book_optimal`, 5% risk, ~20% max DD on sample.

### Deposit bridge from $100 → $3,174
- $50/week → ~62 weeks
- $100/week → ~31 weeks
- $200/week → ~16 weeks
- $500/week → ~7 weeks

There is no book-backed or backtest-backed path to **$50/day from $100 alone** without ruin-level betting that fails on average.
