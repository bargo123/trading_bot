# Research entry families on replayed MT5 bars

Challengers to the live every-bar EMA trigger, with ATR stops and R-multiple targets. `always-take E` is the family's own expectancy after costs on an untouched time holdout; `filtered E` adds the market-state filter. A family with fewer than 5 sampled losses cannot be judged.

| entry | RR | clips | kept | losses seen | always-take E | filtered E | WR | note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| structure_breakout | 2.0 | 284 | 37 | 22 | -0.03857654241102271 | -0.01771341620598236 | 0.40540540540540543 | judged |
| failed_break | 2.0 | 342 | 23 | 10 | -0.03451242196604659 | 0.01150398207024589 | 0.5652173913043478 | judged |
| level_retest | 2.0 | 317 | 21 | 12 | -0.026093652309128666 | -0.017082828002503332 | 0.42857142857142855 | judged |
| chan_bb_fade | 2.0 | 311 | 24 | 14 | -0.0440678899671536 | -0.02895681119857575 | 0.4166666666666667 | judged |
| chan_momentum | - | 0 | - | - | - | - | - | too few clips |
| elliott_leg3 | 2.0 | 278 | 26 | 14 | -0.04732434614563115 | 0.0005938956370098783 | 0.46153846153846156 | judged |
| gann_turn | 2.0 | 261 | 35 | 19 | -0.05752511980685825 | 0.0001691763308573379 | 0.45714285714285713 | judged |
| six_book_stack | 2.0 | 295 | 0 | 0 | -0.08118886291422897 | 0.0 | 0.0 | tail not sampled |
| pullback_retest | 2.0 | 363 | 52 | 35 | -0.023804326456483744 | -0.02428133453829933 | 0.3269230769230769 | judged |
