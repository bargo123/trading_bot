# 5-hour tune — final

Finished after **65,445** trials · **2,516** configs with 100% WR · 0 fetch/bt errors.

## Winner

| Field | Value |
|--------|--------|
| Symbol | `GC=F` (gold) |
| Timeframe | 1h |
| Algo | `hw_range` |
| Lookback | 60d |
| Trades | 19 |
| Win rate | **100%** |
| Net E[R] | 0.381 |
| $100 → | **$45,830** |
| Avg $/day | **~$762** |
| Max day | ~$21,558 |
| Days ≥ $100 PnL | 9 |

**Params:** `atr_sl_mult=1.2885`, `atr_tp_mult=0.5695`, RSI 31/69, `adx_range_max=35`, all-in risk.

Config: `bot/config_tune_5h_best.yaml`  
Live log: `bot/reports/TUNE_5H_LIVE.md` · hits: `bot/reports/tune_5h_hits.json`

## Notes

- Selected on a rolling Yahoo gold sample with all-in sizing; neighbor WR was part of the score but this is still a search winner, not a frozen OOS discovery.
- FX and other book algos found many 100% WR hits; none beat this gold equity in the campaign.
