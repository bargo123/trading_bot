# Research entry families on replayed MT5 bars

Challengers to the live every-bar EMA trigger, with ATR stops and R-multiple targets. `always-take E` is the family's own expectancy after costs on an untouched time holdout; `filtered E` adds the market-state filter. A family with fewer than 5 sampled losses cannot be judged.

| entry | RR | clips | kept | losses seen | always-take E | filtered E | WR | note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| structure_breakout | 2.0 | 284 | 23 | 13 | -0.03857654241102271 | -0.008199332780274229 | 0.43478260869565216 | judged |
| failed_break | 2.0 | 342 | 22 | 11 | -0.03451242196604659 | 0.008911090433292546 | 0.5 | judged |
| level_retest | 2.0 | 317 | 1 | 0 | -0.026093652309128666 | 0.20963305442024682 | 1.0 | tail not sampled |
| pullback_retest | 2.0 | 363 | 21 | 14 | -0.023804326456483744 | -0.01355279817145299 | 0.3333333333333333 | judged |
