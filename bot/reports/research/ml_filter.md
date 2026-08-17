# Research linear PnL filter

Not Jansen ML. Not a 100% win-rate claim. Shadow only.

- hypothesis: Prado meta-label ridge on signal-bar state: fit win/loss on train, rank by holdout E not WR, purged split by default
- label: research_proxy (not_jansen_ml=True)
- clips: 222 train=140 holdout=67 taken=0
- holdout E=0.0 PF=0.0 WR=0.0% net=0.0
- observed losses in the kept set: 0 (worst 0.0) - a high WR here means the loss tail was barely sampled
- always-take holdout E=-0.12534886677501308 PF=0.3763800632145937
- time split: train_max=2026-06-15T16:16:00+00:00 holdout_min=2026-06-15T18:06:00+00:00
- cycle decision: rejected (holdout expectancy must be strictly positive)
- rank_metric: holdout_expectancy n_searches=16 best={'ridge': 0.01, 'target': 'win', 'drop_neg_symbols': False, 'skip_asia': False, 'threshold': 0.532622829721, 'n_taken': 0, 'expectancy': 0.0, 'profit_factor': 0.0, 'win_rate': None, 'net_pnl': 0.0}
- data_source: mt5_bars features=['adx', 'atr_expand', 'bb_pct_b', 'brooks_barbwire', 'brooks_in_range', 'close_ema_pips', 'dow_utc', 'elliott_leg', 'elliott_phase', 'elliott_up_leg', 'ema_side_streak', 'gann_angle_z', 'gann_cycle_hit', 'harris_jump', 'hour_utc', 'impulse_green', 'impulse_red', 'jansen_score', 'johnson_spread_ok', 'kaufman_er', 'm5_up', 'prado_fdiff', 'range_loc', 'ret3_pips', 'rsi', 'side_buy', 'volman_doji']
- placed_orders=False mt5_touched=False promoted_live_yaml=False
