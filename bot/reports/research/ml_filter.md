# Research linear PnL filter

Not Jansen ML. Not a 100% win-rate claim. Shadow only.

- hypothesis: Grid of ridge/win filters on signal-bar market state from replayed bars, threshold fit on train, ranked by holdout E not WR, has E>0 and PF>1
- label: research_proxy (not_jansen_ml=True)
- clips: 342 train=226 holdout=103 taken=23
- holdout E=0.01150398207024589 PF=1.252418610423276 WR=56.5% net=0.2645915876156555
- observed losses in the kept set: 10 (worst 0.15949021993396736) - a high WR here means the loss tail was barely sampled
- always-take holdout E=-0.03451242196604659 PF=0.5657785979463091
- time split: train_max=2026-06-15T11:12:00+00:00 holdout_min=2026-06-15T12:51:00+00:00
- cycle decision: rejected (bootstrap 5th-percentile expectancy is not > 0)
- rank_metric: holdout_expectancy n_searches=32 best={'ridge': 0.01, 'target': 'pnl', 'drop_neg_symbols': False, 'skip_asia': False, 'threshold': 0.020639297201, 'n_taken': 23, 'expectancy': 0.01150398207024589, 'profit_factor': 1.252418610423276, 'win_rate': 0.5652173913043478, 'net_pnl': 0.2645915876156555}
- data_source: mt5_bars features=['adx', 'brooks_barbwire', 'brooks_in_range', 'close_ema_pips', 'dow_utc', 'ema_side_streak', 'harris_jump', 'hour_utc', 'impulse_green', 'impulse_red', 'jansen_score', 'kaufman_er', 'm5_up', 'ret3_pips', 'rsi', 'side_buy', 'volman_doji']
- placed_orders=False mt5_touched=False promoted_live_yaml=False
