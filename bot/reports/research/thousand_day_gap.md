# $1,000/day gap snapshot

Label: `research_proxy`. This is a read-only calculation from recorded MT5 deals, not a forecast or promotion.

- source: `C:\Users\Raqam\trading_bot\bot\optimizer\metrics\trades.jsonl`
- ticket-deduped deals: 1647
- active UTC days: 4 (2026-08-12 to 2026-08-17)
- recorded net PnL: $-46.94
- mean PnL per active day: $-11.74
- target: $1,000.00/day
- recorded quantity: 0.01 lots
- required quantity if linear: not applicable
- size conclusion: unsupported: observed daily expectancy is non-positive, so size-up cannot close the gap
- capital: unavailable from deal history alone: broker margin, leverage, contract specs, and risk limits are required; no estimate is invented
- cost scope: Uses recorded deal PnL as provided. Commission/swap fields are not available in this snapshot, so this is not proof that every execution cost is captured.

No candidate is promoted. If observed expectancy is non-positive, increasing size cannot turn it positive.
