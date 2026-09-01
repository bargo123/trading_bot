# Phase 0 baseline — 2026-08-15

Measured from the live MetaQuotes demo. Not a profit claim. Not a 100% WR claim.

## Frozen live process

- Config: `bot/config_mt5_demo_firehose_hw.yaml` (`allow_live: false`)
- Heartbeat pid 10336, equity $57.41, open 4
- Held: USDCAD sell, EURUSD buy, EURJPY buy, EURCAD buy
- `risk_state.json`: peak $94.28, `permanent_halt: true`, `max_drawdown 39.11%`
- `firehose_every_bar: false`, `position_sizing_mode: risk`, `max_positions: 8`
- This research package must not edit that YAML, restart the runner, flatten, or import into `run_broker_paper.py`

## Journal (`bot/reports/mt5_demo_firehose_hw_journal.jsonl`)

| Event | Count |
|---|---|
| spread_skip | 20756 |
| order | 3402 (861 ok, 2541 fail) |
| 10019 No money | 2252 |
| flatten | 1723 (616 ok, 1107 fail) |
| open_skip | 1333 |
| halt | 1186 |
| margin_skip | 973 |
| quote_stale | 784 |
| intel_skip | 100 |
| oms_reject | 59 |

Other order rejects: 158 min-lot 0.1, 102 market closed, 26 invalid stops.

Successful flatten clips: n=616, WR 37.3%, avg win +$0.056, avg loss −$0.088, E −$0.0135, PF 0.61.

## Deduped MT5 deals (`bot/optimizer/metrics/trades.jsonl`)

n=989, WR 42.1%, avg win +$0.054, avg loss −$0.153, E −$0.043, PF 0.34, net −$42.60.

Worst names by net: GBPUSD, EURUSD, NZDUSD, USDCAD.

Account path about $94.46 → $57.41 (open float remaining).

## Old optimizer

42 experiments: 9 accept, 32 reject, 1 dry-run. Mostly synthetic OHLCV and digest snippets. Several accepts had negative OOS expectancy. Not a verified champion.

## Honest labels

- Implemented: MT5 connect/quote/bars/orders, completed-bar path, OMS, risk halt, sizing, execution circuit, intel skip.
- Research proxies: Coulling tick-volume VPA, Brooks overlap, Damir HH/HL loc, Nison candles, Jansen z-score blend, Harris ATR jump, Elder impulse on M1, `htf_ema` on the same M1 series.
- Unavailable: L2/queue/partial-fill state, news/calendar, COT/OI, genuine Jansen ML, pit Market Profile, faithful author systems, Kaufman/Volman/Johnson extracts.

There is no verified positive-expectancy research champion on real MT5 data.
