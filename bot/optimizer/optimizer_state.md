# Optimizer state

- version: `1`
- updated_utc: `2026-08-18T18:00:57.314046+00:00`
- live_config: `C:\Users\Raqam\trading_bot\bot\config_mt5_demo_firehose_hw.yaml`
- accepted_yaml: `C:\Users\Raqam\trading_bot\bot\optimizer\accepted.yaml`
- best_metrics: `{"win_rate": 98.48484848484848, "profit_factor": 1.5072871162339176, "max_drawdown_pct": 0.4398222666666704, "expectancy_r": 0.0034145060606026977, "total_trades": 66, "net_pnl": 0.2246051632693089, "final_equity": 100.2246051632694, "halt_reason": "", "avg_win": 0.010267117529593577, "avg_loss": -0.4427574761542734, "max_consecutive_wins": 65, "max_consecutive_losses": 1, "sharpe": 0.5035677471844758, "sortino": null}`
- next_step: No untested hypotheses left.

## Weaknesses
- EURUSD hunt sample: ~95% WR with negative expectancy — left off live list (Tharp).
- MetaQuotes 0-spread quotes can vanish; Harris: do not scalp when spread >= take.
- High WR is not the accept gate; OOS expectancy_r must beat baseline.

## Tested
- exp_20260813_201013_drop_eurusd_hunt_e
- exp_20260813_203400_lock_small_wins_tharp
- exp_20260813_205736_jpy_cluster_two_clenow
- exp_20260813_212124_time_stop_30m_tharp
- exp_20260813_214859_nison_chart_read
- exp_20260813_221617_vpa_coulling_filter
- exp_20260813_224224_tighten_sl_to_25
- exp_20260813_230628_brooks_range_fade
- exp_20260813_233025_damir_structure_gate
- exp_20260813_235416_time_stop_5m_volman
- exp_20260814_075955_intel_ema_streak_12
- exp_20260814_082713_jansen_score_025
- exp_20260814_085432_intel_quality_min_50
- exp_20260814_153559_intel_impulse_against_elder
- exp_20260814_171001_intel_quality_min_40
- exp_20260814_173859_intel_wrong_extreme_90
- exp_20260814_181029_intel_weak_adx_edge
- exp_20260814_183939_intel_unready_volman
- exp_20260814_190422_intel_floor_chop_sell
- exp_20260817_082746_drop_eurusd_neg_e

## Rejected
- exp_20260813_194631_tighten_spread_mild
- exp_20260813_201013_drop_eurusd_hunt_e
- exp_20260813_203400_lock_small_wins_tharp
- exp_20260813_205736_jpy_cluster_two_clenow
- exp_20260813_212124_time_stop_30m_tharp
- exp_20260813_214859_nison_chart_read
- exp_20260813_221617_vpa_coulling_filter
- exp_20260813_224224_tighten_sl_to_25
- exp_20260813_230628_brooks_range_fade
- exp_20260813_233025_damir_structure_gate
- exp_20260813_235416_time_stop_5m_volman
- exp_20260814_075955_intel_ema_streak_12
- exp_20260814_082713_jansen_score_025
- exp_20260814_085432_intel_quality_min_50
- exp_20260814_153559_intel_impulse_against_elder
- exp_20260814_171001_intel_quality_min_40
- exp_20260814_173859_intel_wrong_extreme_90
- exp_20260814_183939_intel_unready_volman
- exp_20260814_190422_intel_floor_chop_sell
- exp_20260817_082746_drop_eurusd_neg_e

## Promising
- exp_20260813_011126_widen_tp_probe
- exp_20260813_022003_widen_tp_tharp
- exp_20260813_032746_tighten_sl_tharp
- exp_20260813_040143_book_filter_impulse
- exp_20260813_175929_widen_tp_to_4
- exp_20260813_180723_tighten_tp_to_2
- exp_20260813_182514_tighten_sl_to_20
- exp_20260813_184203_min_range_half_pip
- exp_20260814_181029_intel_weak_adx_edge

## Hypotheses
- If live WR is high and expectancy <= 0, widen TP or drop fat-spread symbols.
- If spread_skip floods the journal, tighten max_spread_pips (Harris).
- If stacked losers, cut max_positions.

## Regimes
- mt5_demo_firehose_hw
