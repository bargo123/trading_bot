# Prev example check — big day then account ruined

Replay of `reports/FROM_100_TO_50DAY.md`: **book_optimal BTC 15m from $100 @ 100% risk**.

## Verdict

- **Prev unsafe 100% risk:** best day **$751.99**, final **$-98.03**, ruined = **True**
- Same pattern at 80%: best day **$542.68**, ruined = **True**
- **All solved modes:** not ruined on this sample (cage blocks the wipe path).

## Results

| Mode | Trades | WR% | Best day $ | PnL | Final | DD% | Ruined | Halt |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| `PREV_unsafe_100pct` | 3 | 66.7 | 751.99 | -198.03 | -98.03 | 111.5 | True | max_drawdown 111.51% |
| `PREV_unsafe_80pct` | 14 | 57.1 | 542.68 | -102.09 | -2.09 | 100.3 | True | max_drawdown 100.31% |
| `solved_traditional` | 33 | 54.5 | 7.82 | 26.1 | 126.1 | 8.1 | False |  |
| `solved_brown_recovery` | 33 | 54.5 | 7.37 | 42.21 | 142.21 | 11.8 | False |  |
| `solved_windsor_escalate` | 33 | 54.5 | 4.5 | 26.86 | 126.86 | 7.6 | False |  |
| `solved_thomas_compound` | 33 | 54.5 | 3.87 | 12.62 | 112.62 | 4.1 | False |  |
| `solved_fuller_pyramid` | 5 | 20.0 | 1.62 | -3.36 | 96.64 | 4.9 | False | max_consecutive_losses (4) |
| `solved_brown_dca_size` | 33 | 54.5 | 7.37 | 42.21 | 142.21 | 11.8 | False |  |

## Meaning
Yes — the previous example is real: one huge day, then the account is ruined under uncaged high risk.
The solved high-risk cage stops that ruin on this sample; it does **not** deliver $50/day from $100.
