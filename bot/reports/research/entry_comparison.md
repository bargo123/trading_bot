# Entry comparison on replayed MT5 bars

All rows are after costs on an untouched time holdout, shadow research only. Nothing here
was promoted, and no orders were placed.

`always-take E` is the entry's own expectancy. `filtered E` is the best ridge filter found
by the search, ranked by holdout expectancy and never by win rate.

Updated 2026-08-16 after e2 (45d/26 symbols) and s3 payoff sweep. `chan_bb_fade`,
`chan_momentum`, `elliott_leg3`, and `gann_turn` were added after e2 and are **not**
in this table until an `--entries` round measures them.

| entry | window | symbols | clips | kept | losses seen | always-take E | filtered E | WR | judgeable |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| firehose 1/30 (live shape) | 60d | 6 | 4113 | 247 | 8 | -0.00486 | -0.00323 | 96.8% | yes |
| firehose 4/8 | 60d | 6 | 304 | 29 | 9 | -0.01567 | -0.00588 | 69.0% | yes |
| firehose 8/8 | 60d | 6 | 59 | - | - | - | - | - | no, too few clips |
| firehose 12/6 | 60d | 6 | 56 | - | - | - | - | - | no, too few clips |
| structure_breakout 2R | 45d | 26 | 284 | 23 | 13 | -0.03858 | -0.00820 | 43.5% | yes |
| failed_break 2R | 45d | 26 | 342 | 22 | 11 | -0.03451 | +0.00891 | 50.0% | yes, bootstrap rejected |
| level_retest 2R | 45d | 26 | 317 | 1 | 0 | -0.02609 | +0.20963 | 100% | no, tail not sampled |
| pullback_retest 2R | 45d | 26 | 363 | 21 | 14 | -0.02380 | -0.01355 | 33.3% | yes |
| six_book_stack (meta-label) | 45d | 26 | 222 | 0 | 0 | -0.12535 | 0.0 | n/a | no, filter kept 0 |

## Findings

1. **No promoter.** Gates require E>0, PF>1, sampled losses, and bootstrap 5th-pct E>0.
2. **`failed_break` is the only judged row with positive filtered E** (+$0.0089). It still
   failed bootstrap. Always-take E is negative for every family.
3. **High win rate tracked fragility, not quality.** 96.8% WR on 1/30 is negative E.
   100% WR on `level_retest` is one trade.
4. **The filter can shrink a loss; it has not flipped firehose to E>0.**
