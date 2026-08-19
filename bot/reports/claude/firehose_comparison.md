# OLD firehose vs INTELLIGENT firehose

All figures are computed from the committed demo journals by
`bot/scripts/claude_firehose_comparison.py`. Win rate is reported but is
never the verdict: the reference failure had a 91.91% win rate and still lost
money. A lower trade count is likewise not counted as an improvement.

## Reference failure (the target to beat)

| metric | value |
| --- | --- |
| trades | 1175 |
| win rate | 91.91% |
| gross profit | $26.33 |
| gross loss | $-37.09 |
| net | $-10.71 |
| profit factor | 0.710 |

A 91.91% win rate with PF 0.71 means the average loss erased roughly 30
average wins. Raising the win rate cannot fix that; only payoff structure can.

## Journals found

| journal | bytes | fire | scale | hold | reduce | exit | skip |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `bot/reports/mt5_demo_eurusd_hw_range_journal.jsonl` | 16,300 | 0 | 0 | 0 | 0 | 0 | 0 |
| `bot/reports/mt5_demo_firehose_hw_journal.jsonl` | 44,868,095 | 1224 | 391 | 0 | 6 | 853 | 9974 |
| `bot/reports/mt5_demo_m1_scalp_journal.jsonl` | 67,930 | 0 | 0 | 0 | 0 | 0 | 0 |
| `bot/reports/mt5_live_algo_test.jsonl` | 1,496 | 0 | 0 | 0 | 0 | 0 | 0 |
| `bot/reports/research/shadow_decisions.jsonl` | 45,191,591 | 0 | 0 | 0 | 0 | 0 | 0 |

## `bot/reports/mt5_demo_firehose_hw_journal.jsonl`

_No per-trade economics fields in this journal: it predates the EV gate._

### All closed P/L

| metric | value |
| --- | --- |
| trades (closed P/L observations) | 3672 |
| wins / losses | 1565 / 1942 |
| win rate | 42.62% |
| **expectancy / trade** | **-0.0437** |
| **profit factor** | **0.253** |
| avg win | 0.0347 |
| avg loss | -0.1106 |
| payoff ratio | 0.314 |
| breakeven WR required | 76.11% |
| wins erased by avg loss | 3.19 |
| wins erased by tail loss | 19.01 |
| tail loss | 0.6600 |
| net P/L | -160.46 |
| cosmetic win rate? | False |

### Intelligent-brain exits only

| metric | value |
| --- | --- |
| trades (closed P/L observations) | 771 |
| wins / losses | 182 / 571 |
| win rate | 23.61% |
| **expectancy / trade** | **-0.0636** |
| **profit factor** | **0.236** |
| avg win | 0.0834 |
| avg loss | -0.1125 |
| payoff ratio | 0.742 |
| breakeven WR required | 57.42% |
| wins erased by avg loss | 1.35 |
| wins erased by tail loss | 7.91 |
| tail loss | 0.6600 |
| net P/L | -49.04 |
| cosmetic win rate? | False |

### CORE / other closes

| metric | value |
| --- | --- |
| trades (closed P/L observations) | 2901 |
| wins / losses | 1383 / 1371 |
| win rate | 47.67% |
| **expectancy / trade** | **-0.0384** |
| **profit factor** | **0.260** |
| avg win | 0.0283 |
| avg loss | -0.1098 |
| payoff ratio | 0.258 |
| breakeven WR required | 79.51% |
| wins erased by avg loss | 3.88 |
| wins erased by tail loss | 22.96 |
| tail loss | 0.6500 |
| net P/L | -111.42 |
| cosmetic win rate? | False |

Top skip/hold reasons:

```
{
  "no_validated_strategy_model": 6611,
  "redundant_information": 3019,
  "hold_at_target_exposure": 343,
  "currency_factor:USD:long": 1
}
```

## `bot/reports/mt5_demo_m1_scalp_journal.jsonl`

_No per-trade economics fields in this journal: it predates the EV gate._

### All closed P/L

| metric | value |
| --- | --- |
| trades (closed P/L observations) | 106 |
| wins / losses | 38 / 49 |
| win rate | 35.85% |
| **expectancy / trade** | **-0.0345** |
| **profit factor** | **0.181** |
| avg win | 0.0213 |
| avg loss | -0.0912 |
| payoff ratio | 0.234 |
| breakeven WR required | 81.06% |
| wins erased by avg loss | 4.28 |
| wins erased by tail loss | 31.43 |
| tail loss | 0.6700 |
| net P/L | -3.66 |
| cosmetic win rate? | True |

### CORE / other closes

| metric | value |
| --- | --- |
| trades (closed P/L observations) | 106 |
| wins / losses | 38 / 49 |
| win rate | 35.85% |
| **expectancy / trade** | **-0.0345** |
| **profit factor** | **0.181** |
| avg win | 0.0213 |
| avg loss | -0.0912 |
| payoff ratio | 0.234 |
| breakeven WR required | 81.06% |
| wins erased by avg loss | 4.28 |
| wins erased by tail loss | 31.43 |
| tail loss | 0.6700 |
| net P/L | -3.66 |
| cosmetic win rate? | True |

