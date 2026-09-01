# MT5 demo hw_range — costed measurement

Not promoted. **Not a 100% WR claim.** Spread from live bid/ask at measurement time (Harris half-spread / Aldridge “gain must cover the spread”).

## Setup
- Account `900907` SupremeFX-Server demo, equity $100, `allow_live: false`
- Symbol: `EURUSD.gc` H1, **0.01 lots** (1000 units), `firehose_every_bar: false`
- Window: 2026-05-20 12:00 UTC → 2026-08-12 21:00 UTC (84.38 days, 1450 bars)
- Live quote at measure: bid 1.15200 / ask 1.15226 (2.6 pips)
- Cost model: 2.257 bps one-way spread + 0.4 bps slippage + $0 commission (unknown until a filled deal)
- Round-trip spread at 0.01 lots: **$0.26** (vs IB ~$4 on 20,000 units)

## Results

| Metric | Value |
| --- | --- |
| Trades | **1** |
| Trades/day | 0.012 |
| WR | 100.00% on n=1 |
| Wilson 95% CI | **20.7% – 100%** |
| Net E[R] | +0.000375 |
| PF | inf (no losing trade in sample) |
| Max DD | 0.00% |
| Start → end equity | $100.00 → $100.0023 |
| Halt | none |
| paper_promoted | **false** |
| trade_expert | **false** (orders still 10026) |

Yahoo `hw_range` used ~0.8 bps spread and produced many more cost_ok signals. Live SupremeFX ~2.26 bps one-way filters almost all of those. That is the book result, not a bug: Aldridge — tick-scale targets die when the move is comparable to the spread; Narang — do not trade unless alpha clears costs.

A single closed winner is not an edge. Do not treat 100% WR here as evidence.

OHLC next-open fill with a constant spread snapshot is not a tick path. Commission remains 0 until the server allows a fill.
