# Payoff sweep on replayed MT5 bars

Filtered expectancy is after costs on an untouched time holdout. A row with fewer than 5 sampled losses cannot be judged, however good it looks: a 100% win rate over one trade is not a result.

Restored from `s3` (60 days, 6 symbols). The `--stack` run had overwritten this file; that overwrite is now blocked.

| TP pips | SL pips | clips | kept | losses seen | filtered E | always-take E | WR | note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1.0 | 30.0 | 4113 | 247 | 8 | -0.0032288741279775683 | -0.004855893032472543 | 0.9676113360323887 | judged |
| 4.0 | 8.0 | 304 | 29 | 9 | -0.005877533667242735 | -0.015670815518292025 | 0.6896551724137931 | judged |
| 8.0 | 8.0 | 59 | - | - | - | - | - | too few clips |
| 12.0 | 6.0 | 56 | - | - | - | - | - | too few clips |
