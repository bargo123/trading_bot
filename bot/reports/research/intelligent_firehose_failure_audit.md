# Intelligent Firehose Failure Audit
_generated 2026-08-20T22:29:15.940220+00:00 | HEAD 13fe5090f8c7945238272aafbb8e87c64a466ff7_

## Runtime snapshot

- heartbeat: `{"pid": 14808, "status": "running", "brain": "intelligent_firehose", "equity": 95.66, "open": 2, "fire": null, "scale": null, "reduce": null, "exit": null, "skip": null, "quote_stale": 9710, "validated_states": 2, "gate_validated_states": true, "champion": null}`
- risk_state: `{"halted": false, "permanent_halt": false, "peak_equity": 101.91, "day_start_equity": 99.59, "reason": ""}`
- validated states artifact: `{"schema": "validated_states.v2", "built_at": "2026-08-20T22:26:22.064001+00:00", "n_survive": 2, "states": [{"regime": "range", "structure": "none", "session": "asia", "side": "sell", "n_validate": 237, "n_losses_validate": 85, "expectancy_validate": 3.149367088607608, "profit_factor_validate": 2.7796852646637746, "win_rate_validate": 0.6413502109704642, "bootstrap_p05_validate": 2.10296284903301`
- champion artifact: `{"id": "CORE_STRATEGY_V1", "decision": null, "expectancy": null, "profit_factor": null, "updated_utc": "2026-08-14T17:39:57.555318+00:00"}`
- intelligent champion present: `False`
- ml_pipeline strategy_selection: `{"n_shortlisted": 10, "n_validated": 10, "n_survive": 2, "cost_pips_assumed": 0.3}`

## Decision distribution

- window: 2026-08-13 01:46:00+00:00 -> 2026-08-20 22:28:02+00:00
- FIRE 1704 | SCALE 0 | REDUCE 16 | EXIT 831 | BRAIN_SKIP 31718 (skip rate 0.9256)

### brain skip reasons

| reason | count |
|---|---|
| no_validated_strategy_model | 23805 |
| state_not_in_validated_set | 4255 |
| redundant_information | 3087 |
| hold_at_target_exposure | 343 |
| edge_gone:no_validated_strategy_model | 88 |
| trade_economics:payoff_below_floor | 87 |
| sizing:minimum_lot_exceeds_clip_budget | 50 |
| trade_economics:expected_net_value_not_positive | 2 |
| currency_factor:USD:long | 1 |

## Execution

- orders ok 3380 / rejected 3021; oms_reject total 470
- top order reject reasons: `{"firehose_bar_up": 1494, "firehose_bar_dn": 1150, "positive_state_ev_on_validated_strategy": 239, "new_evidence_increase_exposure": 138}`
- top oms rejects: `{"stops": 470}`
- halts: `{"daily_loss 3.54%": 883, "no_money_backoff": 310, "max_drawdown 12.01%": 260, "max_drawdown 39.11%": 80, "daily_loss 4.07%": 43}`
- flatten reasons: `{"quick_win": 1383, "never_green": 1288, "gave_back": 229}`

## Quotes

- stale events 12463 (median age 10.1419s, p95 71011.6306s)
- future-quote events 7069 (median skew 10798.318121s, max 10800.049101s)

## Spread skips by symbol (top)

- CADJPY: 33060 skips, median spread at skip 0.007
- AUDSGD: 32925 skips, median spread at skip 7e-05
- GBPJPY: 32552 skips, median spread at skip 0.008
- CADCHF: 32537 skips, median spread at skip 9e-05
- EURNZD: 32444 skips, median spread at skip 9e-05
- GBPAUD: 31965 skips, median spread at skip 8e-05
- GBPNZD: 31612 skips, median spread at skip 9e-05
- GBPCAD: 30224 skips, median spread at skip 6e-05
- NZDJPY: 27930 skips, median spread at skip 0.005
- AUDCAD: 27588 skips, median spread at skip 5e-05
- AUDJPY: 16062 skips, median spread at skip 0.005
- EURAUD: 14540 skips, median spread at skip 5e-05
- GBPCHF: 14228 skips, median spread at skip 5e-05
- EURCAD: 12633 skips, median spread at skip 5e-05
- AUDNZD: 11552 skips, median spread at skip 4e-05

## Fires by symbol|side (top)

- EURUSD|buy: 202
- USDCHF|buy: 165
- USDCAD|buy: 152
- GBPUSD|buy: 138
- USDJPY|buy: 117
- EURUSD|sell: 114
- AUDUSD|sell: 106
- AUDUSD|buy: 103
- NZDUSD|sell: 92
- NZDUSD|buy: 88
- USDCHF|sell: 81
- GBPUSD|sell: 79
- EURJPY|buy: 71
- USDCAD|sell: 69
- USDJPY|sell: 59

## Realized outcomes (MT5 deals)

- closed trades 2404; overall `{"n": 2404, "wins": 1644, "losses": 760, "win_rate": 0.6839, "gross_profit": 81.13, "gross_loss": 108.03, "profit_factor": 0.751, "expectancy": -0.01119, "net": -26.9, "avg_win": 0.0493, "avg_loss": -0.1421, "tail_loss_5pct": -0.49}`

### by symbol

| symbol | n | WR | PF | expectancy | net |
|---|---|---|---|---|---|
| AUDCAD | 6 | 0.1667 | 0.0897 | -0.11833 | -0.71 |
| AUDCHF | 10 | 0.5 | 0.1579 | -0.064 | -0.64 |
| AUDJPY | 7 | 0.4286 | 0.75 | -0.02 | -0.14 |
| AUDNZD | 3 | 1.0 | None | 0.01667 | 0.05 |
| AUDUSD | 307 | 0.684 | 0.8139 | -0.00691 | -2.12 |
| CADJPY | 1 | 1.0 | None | 0.02 | 0.02 |
| EURAUD | 18 | 0.7222 | 0.4839 | -0.01778 | -0.32 |
| EURCAD | 27 | 0.963 | 0.9492 | -0.00111 | -0.03 |
| EURCHF | 42 | 0.8333 | 0.4664 | -0.02833 | -1.19 |
| EURGBP | 65 | 0.8 | 0.4134 | -0.02292 | -1.49 |
| EURJPY | 107 | 0.4673 | 0.3987 | -0.04243 | -4.54 |
| EURUSD | 335 | 0.6955 | 0.6058 | -0.01818 | -6.09 |
| GBPAUD | 1 | 1.0 | None | 0.01 | 0.01 |
| GBPCAD | 2 | 0.5 | 0.1207 | -0.255 | -0.51 |
| GBPCHF | 26 | 0.8462 | 0.4706 | -0.03115 | -0.81 |
| GBPJPY | 1 | 0.0 | 0.0 | -0.45 | -0.45 |
| GBPNZD | 5 | 0.6 | 0.3333 | -0.032 | -0.16 |
| GBPUSD | 315 | 0.7524 | 1.0325 | 0.0013 | 0.41 |
| NZDUSD | 290 | 0.6655 | 0.6507 | -0.01383 | -4.01 |
| USDCAD | 336 | 0.6815 | 1.1002 | 0.00357 | 1.2 |
| USDCHF | 321 | 0.7321 | 0.9171 | -0.00417 | -1.34 |
| USDJPY | 179 | 0.5084 | 0.6167 | -0.02257 | -4.04 |

### by side

- buy: `{"n": 1170, "wins": 870, "losses": 300, "win_rate": 0.7436, "gross_profit": 32.73, "gross_loss": 45.96, "profit_factor": 0.7121, "expectancy": -0.01131, "net": -13.23, "avg_win": 0.0376, "avg_loss": -0.1532, "tail_loss_5pct": -0.54}`
- sell: `{"n": 1234, "wins": 774, "losses": 460, "win_rate": 0.6272, "gross_profit": 48.4, "gross_loss": 62.07, "profit_factor": 0.7798, "expectancy": -0.01108, "net": -13.67, "avg_win": 0.0625, "avg_loss": -0.1349, "tail_loss_5pct": -0.4}`

### by close reason

- manual: `{"n": 1891, "wins": 1210, "losses": 681, "win_rate": 0.6399, "gross_profit": 40.88, "gross_loss": 72.11, "profit_factor": 0.5669, "expectancy": -0.01652, "net": -31.23, "avg_win": 0.0338, "avg_loss": -0.1059, "tail_loss_5pct": -0.33}`
- sl: `{"n": 70, "wins": 0, "losses": 70, "win_rate": 0.0, "gross_profit": 0, "gross_loss": 35.21, "profit_factor": 0.0, "expectancy": -0.503, "net": -35.21, "avg_win": null, "avg_loss": -0.503, "tail_loss_5pct": -0.99}`
- tp: `{"n": 432, "wins": 426, "losses": 6, "win_rate": 0.9861, "gross_profit": 39.09, "gross_loss": 0.0, "profit_factor": null, "expectancy": 0.09049, "net": 39.09, "avg_win": 0.0918, "avg_loss": -0.0, "tail_loss_5pct": 0.0}`
- unknown: `{"n": 11, "wins": 8, "losses": 3, "win_rate": 0.7273, "gross_profit": 1.16, "gross_loss": 0.71, "profit_factor": 1.6338, "expectancy": 0.04091, "net": 0.45, "avg_win": 0.145, "avg_loss": -0.2367, "tail_loss_5pct": -0.26}`