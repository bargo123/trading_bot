# Intelligent Firehose Failure Audit
_generated 2026-08-28T10:02:26.417363+00:00 | HEAD b757254e1ab75d52d6c2a7fbabca934ff7038790_

## Runtime snapshot

- heartbeat: `{"pid": 19112, "status": "running", "brain": "intelligent_firehose", "equity": 43.07, "open": 2, "fire": null, "scale": null, "reduce": null, "exit": null, "skip": null, "quote_stale": 0, "validated_states": 0, "gate_validated_states": true, "champion": null}`
- risk_state: `{"halted": false, "permanent_halt": false, "peak_equity": 94.78, "day_start_equity": 53.12, "reason": ""}`
- validated states artifact: `{"schema": "validated_states.v2", "built_at": "2026-08-28T09:48:59.545223+00:00", "n_survive": 0, "states": [], "path_exists": true}`
- champion artifact: `{"id": "CORE_STRATEGY_V1", "decision": null, "expectancy": null, "profit_factor": null, "updated_utc": "2026-08-14T17:39:57.555318+00:00"}`
- intelligent champion present: `False`
- ml_pipeline strategy_selection: `{"n_shortlisted": 166, "n_validated": 200, "n_survive": 25, "cost_pips_assumed": null}`

## Decision distribution

- window: 2026-08-21 00:04:02+00:00 -> 2026-08-28 10:01:00+00:00
- FIRE 56226 | SCALE 0 | REDUCE 0 | EXIT 0 | BRAIN_SKIP 136244 (skip rate 0.7079)

### brain skip reasons

| reason | count |
|---|---|
| short_horizon_not_calibrated | 75290 |
| state_not_in_validated_set | 33258 |
| spread_above_measured_session_limit | 16203 |
| short_horizon_abstain | 8469 |
| short_horizon_probability_below_threshold | 2992 |
| no_validated_strategy_model | 31 |
| short_horizon_negative_expected_value | 1 |

## Execution

- orders ok 758 / rejected 19; oms_reject total 146
- top order reject reasons: `{"10016 Invalid stops": 19}`
- top oms rejects: `{"stops": 146}`
- halts: `{"daily_loss 11.33%": 188, "max_drawdown 25.05%": 70, "daily_loss 10.07%": 36, "daily_loss 10.11%": 28}`
- flatten reasons: `{}`

## Quotes

- stale events 981105 (median age 78271.977559s, p95 163397.6489s)
- future-quote events 29199 (median skew 14133.51259s, max 14134.869926s)

## Spread skips by symbol (top)

- GBPJPY: 20868 skips, median spread at skip 0.008
- GBPAUD: 20530 skips, median spread at skip 8e-05
- EURNZD: 20381 skips, median spread at skip 9e-05
- CADJPY: 20349 skips, median spread at skip 0.007
- GBPNZD: 20163 skips, median spread at skip 9e-05
- GBPCAD: 19416 skips, median spread at skip 6e-05
- AUDSGD: 19052 skips, median spread at skip 7e-05
- CADCHF: 18849 skips, median spread at skip 9e-05
- AUDCAD: 17812 skips, median spread at skip 5e-05
- NZDJPY: 16772 skips, median spread at skip 0.005
- AUDJPY: 8819 skips, median spread at skip 0.005
- EURAUD: 8148 skips, median spread at skip 5e-05
- GBPCHF: 7763 skips, median spread at skip 5e-05
- EURCAD: 6884 skips, median spread at skip 5e-05
- EURJPY: 5991 skips, median spread at skip 0.004

## Fires by symbol|side (top)

- GBPUSD|buy: 3081
- EURUSD|buy: 2873
- NZDUSD|buy: 2680
- AUDUSD|buy: 2672
- EURGBP|buy: 2593
- USDJPY|sell: 2547
- USDCHF|buy: 2327
- EURCHF|sell: 2109
- USDCAD|buy: 2087
- EURUSD|sell: 2033
- EURCHF|buy: 2004
- USDJPY|buy: 1975
- EURGBP|sell: 1942
- USDCAD|sell: 1643
- USDCHF|sell: 1616

## Realized outcomes (MT5 deals)

- closed trades 3462; overall `{"n": 3462, "wins": 1929, "losses": 1533, "win_rate": 0.5572, "gross_profit": 136.77, "gross_loss": 216.23, "profit_factor": 0.6325, "expectancy": -0.02295, "net": -79.46, "avg_win": 0.0709, "avg_loss": -0.1411, "tail_loss_5pct": -0.56}`

### by symbol

| symbol | n | WR | PF | expectancy | net |
|---|---|---|---|---|---|
| AUDCAD | 31 | 0.129 | 0.0492 | -0.13097 | -4.06 |
| AUDCHF | 29 | 0.4138 | 0.3978 | -0.11276 | -3.27 |
| AUDJPY | 69 | 0.1739 | 0.2601 | -0.05812 | -4.01 |
| AUDNZD | 79 | 0.1772 | 0.4772 | -0.04937 | -3.9 |
| AUDSGD | 4 | 0.0 | 0.0 | -0.0925 | -0.37 |
| AUDUSD | 358 | 0.6425 | 0.7441 | -0.0112 | -4.01 |
| CADCHF | 1 | 0.0 | 0.0 | -0.41 | -0.41 |
| CADJPY | 15 | 0.1333 | 0.0894 | -0.07467 | -1.12 |
| EURAUD | 97 | 0.2784 | 0.402 | -0.05 | -4.85 |
| EURCAD | 53 | 0.6415 | 0.7506 | -0.02094 | -1.11 |
| EURCHF | 71 | 0.6338 | 0.4198 | -0.06423 | -4.56 |
| EURGBP | 90 | 0.7 | 0.9619 | -0.00211 | -0.19 |
| EURJPY | 178 | 0.3652 | 0.4546 | -0.03815 | -6.79 |
| EURNZD | 58 | 0.1724 | 0.0929 | -0.07741 | -4.49 |
| EURUSD | 390 | 0.6692 | 0.5835 | -0.028 | -10.92 |
| GBPAUD | 38 | 0.0526 | 0.0224 | -0.09184 | -3.49 |
| GBPCAD | 20 | 0.15 | 0.0365 | -0.145 | -2.9 |
| GBPCHF | 47 | 0.5745 | 0.3288 | -0.07426 | -3.49 |
| GBPJPY | 22 | 0.0455 | 0.0045 | -0.09955 | -2.19 |
| GBPNZD | 44 | 0.2045 | 0.1299 | -0.07614 | -3.35 |
| GBPUSD | 398 | 0.6985 | 0.9401 | -0.00334 | -1.33 |
| NZDUSD | 335 | 0.6149 | 0.5204 | -0.02316 | -7.76 |
| USDCAD | 396 | 0.6439 | 1.2131 | 0.0078 | 3.09 |
| USDCHF | 385 | 0.6883 | 1.1271 | 0.00701 | 2.7 |
| USDJPY | 254 | 0.4094 | 0.5544 | -0.0263 | -6.68 |

### by side

- buy: `{"n": 1684, "wins": 1002, "losses": 682, "win_rate": 0.595, "gross_profit": 56.06, "gross_loss": 97.86, "profit_factor": 0.5729, "expectancy": -0.02482, "net": -41.8, "avg_win": 0.0559, "avg_loss": -0.1435, "tail_loss_5pct": -0.58}`
- sell: `{"n": 1778, "wins": 927, "losses": 851, "win_rate": 0.5214, "gross_profit": 80.71, "gross_loss": 118.37, "profit_factor": 0.6818, "expectancy": -0.02118, "net": -37.66, "avg_win": 0.0871, "avg_loss": -0.1391, "tail_loss_5pct": -0.49}`

### by close reason

- manual: `{"n": 2486, "wins": 1407, "losses": 1079, "win_rate": 0.566, "gross_profit": 63.25, "gross_loss": 95.58, "profit_factor": 0.6617, "expectancy": -0.013, "net": -32.33, "avg_win": 0.045, "avg_loss": -0.0886, "tail_loss_5pct": -0.28}`
- sl: `{"n": 431, "wins": 11, "losses": 420, "win_rate": 0.0255, "gross_profit": 0.63, "gross_loss": 111.89, "profit_factor": 0.0056, "expectancy": -0.25814, "net": -111.26, "avg_win": 0.0573, "avg_loss": -0.2664, "tail_loss_5pct": -0.85}`
- tp: `{"n": 479, "wins": 473, "losses": 6, "win_rate": 0.9875, "gross_profit": 62.08, "gross_loss": 0.0, "profit_factor": null, "expectancy": 0.1296, "net": 62.08, "avg_win": 0.1312, "avg_loss": -0.0, "tail_loss_5pct": 0.0}`
- unknown: `{"n": 66, "wins": 38, "losses": 28, "win_rate": 0.5758, "gross_profit": 10.81, "gross_loss": 8.76, "profit_factor": 1.234, "expectancy": 0.03106, "net": 2.05, "avg_win": 0.2845, "avg_loss": -0.3129, "tail_loss_5pct": -0.79}`