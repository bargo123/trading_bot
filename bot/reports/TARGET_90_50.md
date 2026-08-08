# Target: 90% win rate + $50/day from $100

## Tried
864 configs (hw_range / rsi_cross, many SL/TP/risk/trade-count combos) on BTC-USD 5m with costs.

## Best honest results
| Goal | Result |
|---|---|
| 90% WR | **Not reached.** Best **89.6%** (`hw_range`, SL 8 ATR / TP 0.6 ATR, 1 trade) |
| $50/day from $100 | **0% of days** hit +$50 in any tested config |
| Best day seen (high-WR profiles) | about **$0.26–$3.40** (only when risk was jacked up, and average day still lost) |
| Mean daily PnL @ ~90% WR | about **−$0.50** |

Installed closest-to-90% profile in `config_100_2h.yaml` (**~89.6% WR**).

## Why $50/day from $100 is blocked by math
$50/day on $100 = **+50% per day**.

Even assuming **90% WR** and a favorable small-TP setup (risk 5%, SL5/TP0.8):
- Expected value ≈ **$0.22 per trade**
- You would need **~227 winning-quality trades per day** after spreads to average +$50

That does not exist on this data without look-ahead / fake fills. Raising risk makes one loss wipe most of the $100; it still does not produce stable $50 days.

## What is possible on $100 (honest)
- High win rate (~87–90%) with **tiny** daily dollar moves
- Or higher dollar swings with **much lower** win rate and high wipe risk
- Not both 90% WR **and** +$50/day on a $100 account

To target ~$50/day with sane risk (~1%/day), you typically need on the order of **~$5,000+** equity — and even then only if a real edge exists.
