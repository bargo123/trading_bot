 V# Watcher book review and implementation record

This is a human-authored research record for the read-only Watcher. It is not
an extraction pipeline and it does not authorize, alter, or submit trades.
The Watcher perspectives are deliberately conservative: unavailable inputs
remain `MISSING_DATA` or `NOT_APPLICABLE`, and qualitative ideas are not
converted into fabricated win probabilities.

Registry provenance is resolved from the downloaded book filename when a PDF
page header is not a reliable title; page excerpts are never presented as the
book name.

The local library contains 54 Markdown book records, including duplicate and
auxiliary copies. The catalog below contains 77 reviewed title/alias records;
statuses distinguish material that was reviewed, scanned, or kept contextual.
Text-enabled titles were read at multiple locations where feasible. Image-only
and incomplete material is recorded as a limitation rather than treated as
evidence.

| Title | Status | Knowledge incorporated into Watcher |
|---|---|---|
| Algorithmic Trading and Quantitative Strategies — Velu, Hardy, Nehren | PARTIALLY_REVIEWED | market mechanics, cost-aware testing, Alexander percentage filters, SMA/EWA ratio rules, BWMA/Bollinger bands, moving-average oscillator crosses, RSI 70/30 reversal, causal kernel smoothing and bandwidth-selection caveats, factor-adjusted fair-value residuals, sign/magnitude return decomposition, measured price/volatility/volume omnibus rule, characteristic-time normalization, timestamped event-duration intensity, intraday profile shocks, volume-conditioned return regimes, normalized distance-based pairs, fine-versus-slow sampling and negative-lag-one microstructure-noise diagnostic, and square-root impact-plus-spread cost hurdles |
| Technical Analysis of the Financial Markets — Murphy | PARTIALLY_REVIEWED_SCANNED | chart/indicator and volume/open-interest continuation concepts implemented as read-only observations; local PDF is image-only |
| Technical Analysis of Stock Trends — Edwards & Magee | PARTIALLY_REVIEWED | confirmed head-and-shoulders, triangle, gap, support/resistance role-flip, trend-channel, one-day reversal, selling-climax, trendline-penetration, right-angled broadening, decisive close/penetration and volume confirmation, climactic-volume profit protection, defensive exit versus reversal, key-reversal-day, spike, and runaway-day rules implemented as causal/observed research perspectives |
| The Microstructure of Financial Markets — de Jong, Rindi | REVIEWED | quoted/effective/realized spread decomposition, duration-weighted quoted spread, Roll transaction-price spread diagnostic, information asymmetry, order choice, execution friction; the new decompositions are observed-data, non-directional diagnostics |
| The Art and Science of Technical Analysis — Grimes | REVIEWED | continuation/termination/level hold/failure, regimes, structural stops, failed breaks |
| Statistical Arbitrage — Pole | PARTIALLY_REVIEWED | mean-reversion hypothesis discipline, popcorn-process reversion to the local mean, volatility-qualified causal turning-point events, event-history pair selection, staged spread entries, conditional 75%-reversion and multi-step probability rules, calibrated spread margins, evolutionary-operation calibration monitoring, spread/risk context, forecast-error monitoring/intervention, and Cuscore-style change-point protection |
| Inside the Black Box — Narang | PARTIALLY_REVIEWED | model-process separation, conditional, linear, and recent-performance rotation alpha blending, horizon definition, cost/liquidity hurdles, forecast-bucket monotonicity, delayed-entry time decay, run-frequency cost/noise tradeoff replay, parameter-plateau robustness, portfolio value-add comparison, risk monitoring, validation discipline, regime-change warnings, exogenous-shock abstention, and contagion/common-investor exposure monitoring |
| Quantitative Momentum — Gray, Vogel | PARTIALLY_REVIEWED | momentum persistence, look-back reversal/continuation, path quality/FIP, lottery-risk avoidance, seasonal timing, 52-week-high and absolute-strength alternatives, earnings-momentum alternatives, portfolio concentration/rebalance-cost trade-off, time-series trend overlay, volatility-stop study, and long-horizon evidence caveat |
| Building Winning Algorithmic Trading Systems — Davey | REVIEWED | curve-fit warning, robustness, Monte Carlo and out-of-sample discipline, plus the Appendix A three-close baseline, Appendix B Euro Night limit-bracket, and Appendix C Euro Day reversal-limit systems |
| Reading Price Charts Bar by Bar — Al Brooks | REVIEWED | trend pullbacks, High/Low 1-4 counts, wedges, failed failures, spike/channel and flag tests, range location |
| The New Trading for a Living — Elder | REVIEWED | higher-timeframe confirmation, volume breakout confirmation, SafeZone stops outside measured market noise, and risk control |
| Evidence-Based Technical Analysis — Aronson | REVIEWED | falsifiable objective rules, causal signal timing, position-bias detrending, practical-versus-statistical significance, and family-wise Reality Check/permutation evidence |
| Quantitative Trading — Ernie Chan | REVIEWED | regime switching, mean reversion versus momentum, execution, costs, strategy-family-specific exits, and bid/ask/last quote-data sufficiency for after-cost high-frequency study |
| High-Frequency Trading — Aldridge | REVIEWED | current data, quote state, spread, adverse selection, event and operational risk; bid/ask-bounce contamination, inter-quote duration activity context, trade-direction provenance diagnostics, anonymous quote-matching infeasibility, persistence and after-cost requirements, and source-grounded pairs, triangular, UIP, index-composition, volatility-curve, basis, futures/ETF, dual-class, and risk-arbitrage perspectives |
| Markets in Profile — Dalton et al. | REVIEWED | auction context, timeframe alignment, open-drive/rejection, volume-at-price, day-structure classification, failed range-extension fade, and single-print retest |
| Market Microstructure: Confronting Many Viewpoints — Abergel, Bouchaud, Foucault | REVIEWED | limit/market choice, winner's curse, execution risk and competing microstructure views |
| Algorithmic Trading — Winning Strategies and Their Rationale — Chan | PARTIALLY_REVIEWED | linear/Kalman/cross-sectional mean reversion, time-series/Alexander momentum, volatility-scaled opening gaps, post-event drift, stop cascades, signed order flow, bid/ask imbalance, pro-rata ratio trading, ticking/quote matching, leveraged-fund close rebalancing, capped half-Kelly sizing, and distinct ADF/Hurst/variance-ratio/half-life/CADF/Johansen diagnostics implemented as read-only perspectives; full book remains partial |
| A Complete Guide to Volume Price Analysis — Coulling | REVIEWED | effort/result, trend-level effort confirmation, long-legged-doji and narrow-spread warnings, stopping/topping-out volume, and clear-water breakout/retest validation; implemented as causal completed-quote-bar volume/activity proxies, with real-volume-only claims kept fail-closed |
| Algorithmic Trading and DMA — Barry Johnson | PARTIALLY_REVIEWED_SCANNED | Chapters on order types, transaction costs, adaptive/price-inline tactics, liquidity seeking, and order difficulty reviewed; five Watcher perspectives added; remaining material is still partial |
| Forex Price Action Scalping — Bob Volman | REVIEWED | micro pressure, 20EMA pullbacks, DD/FB/SB/BB/RB/IRB/ARB break logic, retest, technical tipping-point exits, pullback-quality distinctions, path-room and unfavorable-condition filters; implemented as causal completed-quote-bar proxies |
| Encyclopedia of Chart Patterns — Bulkowski | REVIEWED | double bottoms/tops, flags, high-tight flags, gaps, broadening formations, right-angled formations, broadening wedges, BARRs, cup variants, head-and-shoulders variants, horns, islands, measured moves, ascending triangles, falling wedges, and diamonds with source confirmation, measured targets, structural stops, and explicit sample-size/regime caveats; implemented as causal observed-bar perspectives |
| Day Trading and Swing Trading the Currency Market — Kathy Lien | REVIEWED | pair/session characteristics, double-zero fades, London stop-hunt/reversal, fader and filtered false-breakout rules, narrow-channel breakouts, perfect-order trends, 20/100 momentum, proactive/reactive/combined news context, seven-day extension turns, two-day-low protective stops, and one-R scale-out/trailing management |
| Machine Trading — Ernest P. Chan | REVIEWED | ranking/factor robustness, volatility and event strategies, data integrity, and bulk-volume-classification order-flow entry/exit rules using executable quote context |
| Mind Over Markets — Dalton et al. | REVIEWED | auction structure, volume profile, multiple timeframe context, day-structure classification, failed range-extension fade, and single-print retest |
| Japanese Candlestick Charting Techniques — Steve Nison | PARTIALLY_REVIEWED_SCANNED | candlestick concepts retained; local PDF text is not extractable |
| Trades, Quotes and Prices — Bouchaud et al. | REVIEWED | bid/ask executable prices, order-flow persistence, queue imbalance and tails |
| Empirical Market Microstructure — Hasbrouck | REVIEWED | quote/trade conditioning, spread variation, order choice and uncertainty |
| Mastering the Trade — John F. Carter | PARTIALLY_REVIEWED | opening-gap fade (pp. 172–173), pivot pullback (pp. 192–193), tick extremes/flow and explicit noise bands (pp. 215–230), price/tick divergence, ATR/13–21 mean extension (pp. 234–236), 3:52 play (pp. 332–334), pivot-plus-Scalper-Alert multisetup confirmation, and other setup context implemented as read-only causal perspectives; full-book coverage remains partial |
| High Probability Trading — Marcel Link | PARTIALLY_REVIEWED | 10-period and buffered trendline breakouts, 30-minute opening-range breakout, reversal-day, double-top/bottom, exhaustion reversal, key-number reversal, top-down timeframe confirmation, ADX regime, stochastic-wave/cross/failure and extreme-retest context, RSI-50-line/extreme-exit/pattern-break, MACD-line relationship, retracement-entry, news-reaction fade, ATR-based stop feasibility, cancel-if-close stop discipline, and risk/entry timing rules implemented as causal Watcher perspectives |
| Advances in Financial Machine Learning — Lopez de Prado | PARTIALLY_REVIEWED | leakage prevention, sample uniqueness, sequential bootstrap, purged/CPCV validation, PSR/DSR, strategy-failure risk, CUSUM event sampling, entropy context, tick/volume/dollar bars, tick/volume/dollar imbalance bars, tick/volume/dollar runs bars, and robust research requirements |
| Market Microstructure Theory — Maureen O'Hara | PARTIALLY_REVIEWED_SCANNED | inventory/information microstructure noted; local PDF is image-only |
| An Introduction to High-Frequency Finance — Dacorogna et al. | PARTIALLY_REVIEWED_SCANNED | high-frequency data/volatility concepts noted; local PDF is image-only |
| Python for Finance — Yves Hilpisch | PARTIALLY_REVIEWED | reproducible data and quantitative implementation context |
| Active Portfolio Management — Grinold, Kahn | PARTIALLY_REVIEWED | signal breadth, forecast quality, Fundamental-Law skill/breadth capacity, volatility-scaled alpha, marginal turnover-cost frontier, and portfolio-impact context |
| Systematic Trading — Robert Carver | REVIEWED | simple rules, forecast scaling/caps, regime/tail risk, OOS, position inertia, and cost-based trading-speed limits |
| The Economics of Financial Markets — Roy Bailey | PARTIALLY_REVIEWED | market-efficiency and incentive context; no directional claim treated as proof |
| Machine Learning for Algorithmic Trading — Stefan Jansen | PARTIALLY_REVIEWED | feature/label separation and validation/calibration context |
| Quantitative Finance For Dummies — Steve Bell | PARTIALLY_REVIEWED | basic return, risk and probability definitions used for terminology |
| Trading Price Action Trading Ranges — Al Brooks | PARTIALLY_REVIEWED_SCANNED | breakout-mode strength, barbwire uncertainty, failed-break reversal, measured-move projection, shrinking-stairs momentum decay, micro-measuring gaps, always-in mode, trader's-equation probability/reward/risk/cost math, two-reasons entry discipline with steep-countertrend exception, timeframe-drift review, range/auction context, and middle-of-range avoidance; represented as causal quote-bar research proxies |
| Forex Patterns & Probabilities — Ed Ponsi | PARTIALLY_REVIEWED | multiple-timeframe trend pullbacks, Fibonacci trend re-entries, price-action-at-level filtering, intraday round-trip geometry, level bounces, liquid-session breakouts, pennants, round-number reactions, proper-order EMA pullbacks, squeeze breakouts, and low-liquidity boomerang fades implemented as causal or explicitly observed research perspectives |
| Brian Anderson — The 1 Hour Trade | PARTIALLY_REVIEWED | high-volume runner and conditional bracket perspectives mapped as read-only research; source-specific volume and bracket inputs remain required |
| Steve Nison — Beyond Candlesticks | PARTIALLY_REVIEWED_SCANNED | three-line break, extra-line confirmation, black-shoe/white-suit/neck, Renko, Kagi yang/yin, double-window, tweezers, three-Buddha, disparity, candlestick reversal/continuation, three-window exhaustion, gapping-doji confirmation, window, and session perspectives mapped; full source review remains partial |
| The Price in Time — Gabriele Fabris | REVIEWED | full local text reviewed; objective European opening-price boundary, Asian/Frankfurt/London/New York session windows, abnormal-day exclusions, 07:00–08:00 GMT NTZ range, 10–30 pip width, London breakout, range-cycle, range-projection, three TP management models, and pending-order lifecycle perspectives implemented causally |
| The 10XROI Trading System — L.R. Thomas | REVIEWED | full local text reviewed; push-pull momentum variants, separated 3/10-period moving-average momentum, confirmed breakout families, pullback-to-level, delayed break-even protection, hourly confirmation, structural stop, session, fixed-R geometry, and high-R parabolic/weekly-level warning implemented causally |
| Following the Trend — Andreas Clenow | PARTIALLY_REVIEWED | dual-EMA trend filter, confirmed breakout, ATR/risk-factor sizing, volatility-scaled bull-market dip, term-structure carry, and long/short symmetry implemented; full book remains partial |
| Beat the Forex Dealer — Agustin Silvani | PARTIALLY_REVIEWED_SCANNED | observed retail crowding is a contrarian context only; no broker claim is accepted as a signal |
| Developing High-Frequency Trading Systems | PARTIALLY_REVIEWED_SCANNED | market-data, order-book, latency, impact, and execution concepts mapped to existing research perspectives |
| Elliott Wave Principle — Frost & Prechter | PARTIALLY_REVIEWED_SCANNED | wave context remains explicitly supplied; impulse rules, wave-3 extension, leading/ending diagonal structure, corrective structure, and wave-2/wave-4 alternation are checked without fabricating counts from sparse ticks; full source review remains partial |
| Getting Started in Technical Analysis — Jack Schwager | PARTIALLY_REVIEWED_SCANNED | trend, chart, level, candle, oscillator-alert/price-confirmation, stronger restrictive reversal-day, trend-adjusted oscillator, minor-reaction re-entry, long-MA reaction, island-validation, held-record continuation, narrow-consolidation location bias, significant-news non-follow-through reversal, equity-warning, and validation perspectives mapped; full book remains partial |
| Hands-On Machine Learning for Algorithmic Trading — Stefan Jansen | PARTIALLY_REVIEWED_SCANNED | labels, purged validation, meta-labeling, model evidence, and bet-sizing perspectives mapped |
| How to Day Trade for a Living — Andrew Aziz | PARTIALLY_REVIEWED_SCANNED | opening range, VWAP, momentum, volume, trade management, risk context, premarket gapper, relative-volume/market-sector independence, reversal-context filters, and the source ORB entry/VWAP invalidation mapped |
| How to Make Profits in Commodities — W.D. Gann | PARTIALLY_REVIEWED_SCANNED | higher/lower top-and-bottom progression, 50% half-way-point interaction, repeated double/triple levels, secondary lower-top/higher-bottom reactions, reverse-signal day, cycle, and level concepts mapped as read-only rules; full source review remains partial and no deterministic Gann prediction is claimed |
| Market Structure — Sample Author | PARTIALLY_REVIEWED | structure, levels, range, and break quality mapped |
| Modelling Asset Prices for Algorithmic and High-Frequency Trading — Cartea & Jaimungal | PARTIALLY_REVIEWED_SCANNED | Hawkes/order-flow, market-making, volatility, and impact concepts mapped |
| Price Action Breakdown — Laurentiu Damir | PARTIALLY_REVIEWED_SCANNED | value-area rejection sequence, trend-aware value/excess location, narrow-rotation trend-health warning, plus trend/level/candle/pattern context mapped; full book remains partial |
| Profitable Forex Trading Using High and Low Risk Strategies — Jim Brown | PARTIALLY_REVIEWED_SCANNED | QMP next-candle trigger/structural stop, MA stack, Bollinger confirmation, MACD zero filter, QQE midline/extreme filter, divergence, trend, and risk ideas mapped as research hypotheses; full book remains partial |
| Pyramiding | REVIEWED | full local article reviewed; profit-funded same-thesis adds, strong-trend restriction, and non-increasing risk envelope mapped to read-only pyramiding perspectives |
| Quantum Finance | CONTEXT_ONLY | conceptual quantitative context; no objective watcher signal supplied |
| Quantum Trading — Fabio Oreste | CONTEXT_ONLY | conceptual forecasting context; no objective watcher signal supplied |
| Reminiscences of a Stock Operator — Edwin Lefevre | PARTIALLY_REVIEWED_SCANNED | trend, timing, pyramiding, sizing, and discipline context mapped |
| Risk Basics | PARTIALLY_REVIEWED | risk, sizing, geometry, and tail-control context mapped |
| Steidlmayer on Markets | PARTIALLY_REVIEWED_SCANNED | market-profile, auction, initial-balance, day-structure, failed range-extension, single-print retest, and range context mapped; full source review remains partial |
| Stock Market Wizards — Jack Schwager | PARTIALLY_REVIEWED_SCANNED | process, trend, momentum, risk, and management context mapped |
| Stock Trading & Investing Using Volume Price Analysis — Anna Coulling | PARTIALLY_REVIEWED_SCANNED | VPA concepts mapped to explicit volume-provenance perspectives |
| The Definitive Guide to Point and Figure — Jeremy du Plessis | PARTIALLY_REVIEWED_SCANNED | double/triple-top and bottom signals, pole reversals, opposing poles, 45-degree trendline maintenance/breaks, trend-aligned signals, early fulcrum entries, levels, catapult, activated vertical/horizontal-count targets, shakeout filtering, trap reversals, semi-catapults, and fulcrums mapped |
| The Disciplined Trader — Mark Douglas | CONTEXT_ONLY | behavioral/process context; no market signal is invented |
| The Holy Grail Forex Trading System | PARTIALLY_REVIEWED_SCANNED | time-anchored bracket and explicit trend-regime failure warning mapped; claims remain unvalidated research context and no “holy grail” promotion is possible |
| The Man Who Solved the Market — Gregory Zuckerman | PARTIALLY_REVIEWED_SCANNED | systematic, statistical-arbitrage, market-making, and validation context mapped |
| The Mental Game of Trading — Jared Tendler | CONTEXT_ONLY | behavioral/process context only |
| The New Market Wizards — Jack Schwager | PARTIALLY_REVIEWED_SCANNED | trader process, trend, momentum, risk, and validation context mapped |
| The Ultimate Forex Trading System | PARTIALLY_REVIEWED_SCANNED | EMA(9)/EMA(15) reversal, right-shoulder head-and-shoulders, repeated support/resistance tests, VPA extremes, higher-timeframe confirmation, and low-confidence M/W context mapped to causal read-only perspectives; full source review remains partial and win-rate claims remain unverified |
| Trade the Price Action — Laurentiu Damir | REVIEWED | full local text reviewed; 4H/200EMA context, confirmed swing changes, Fibonacci pullback confluence, named reversal candles, and source geometry mapped to causal read-only perspectives |
| Trade Your Way to Financial Freedom — Van Tharp | PARTIALLY_REVIEWED_SCANNED | narrow-range and failed-test setups; MAE winner-band, net expectancy/R, liquidity and volatility selection; position sizing and management context mapped |
| Trading and Exchanges — Larry Harris | PARTIALLY_REVIEWED_SCANNED | microstructure, adverse selection, order choice, impact, and execution context mapped |
| Trading in the Zone — Mark Douglas | CONTEXT_ONLY | behavioral/process context only |
| Trading with Intermarket Analysis — John Murphy | PARTIALLY_REVIEWED_SCANNED | intermarket, correlation, relative-strength, and trend context mapped |
| Winning the Trading Game — Noble DraKoln | CONTEXT_ONLY | process and risk context only; no win-rate claim is accepted |

Directly implemented perspectives are individually authored in
`bot/aegis/research/watcher_algorithms/` and registered by
`bot/aegis/research/watcher_algorithms/__init__.py`. The current module set is
616 individually authored modules. The registry is authoritative; the compact
catalog below is supplemented by the source-specific additions described in
this record:

`trend_continuation`, `trend_pullback`, `range_edge_fade`, `failed_breakout`,
`breakout_continuation`, `volume_effort_result`, `pyramiding`, `adverse_selection`, `time_stop`,
`intermarket_analysis`, `noise_filter`, `tail_risk`, `event_arbitrage`,
`spread_scalping`, `latency_arbitrage`, `rebate_capture`,
`market_impact_symmetry`,
`al_brooks_high_low_count`, `al_brooks_wedge`, `al_brooks_failed_failure`,
`al_brooks_spike_channel`, `al_brooks_double_flag`, `al_brooks_range_location`,
`davey_three_bar_baseline`, `davey_euro_night_strategy`, `davey_euro_day_strategy`,
`lien_high_probability_turn`, `lien_two_day_low_stop`, `lien_two_stage_profit_management`,
`volman_double_doji_break`, `volman_first_break`, `volman_second_break`,
`volman_block_break`, `volman_range_break`, `volman_inside_range_break`,
`volman_advanced_range_break`, `volman_tipping_point_exit`,
`volman_unfavorable_path_filter`, `volman_pullback_quality`,
`vpa_long_legged_doji`, `vpa_narrow_spread_high_volume`, `vpa_stopping_volume`,
`vpa_topping_out_volume`, `vpa_breakout_volume_validation`,
`edwards_magee_head_shoulders`, `edwards_magee_triangle_breakout`,
`edwards_magee_gap_classification`, `edwards_magee_support_resistance_flip`,
`edwards_magee_channel_deterioration`, `edwards_magee_one_day_reversal`,
`edwards_magee_selling_climax`, `edwards_magee_trendline_penetration`,
`edwards_magee_broadening_breakout`, `edwards_magee_key_reversal_day`,
`edwards_magee_spike_reversal`, `edwards_magee_runaway_day`,
`edwards_magee_dow_confirmation`, `edwards_magee_basing_points_stop`,
`ponsi_level_bounce`, `ponsi_intraday_breakout`, `ponsi_pennant_continuation`,
`ponsi_round_number_bounce`, `ponsi_boomerang_fade`,
`anderson_high_volume_runner`, `anderson_conditional_bracket`, `nison_three_line_break`, `nison_renko_trend`,
`nison_kagi_yang_yin`, `nison_disparity_reversal`, `nison_hammer_hanging_man`,
`nison_shooting_star`, `nison_doji_confirmation`, `nison_two_line_reversal`,
`nison_three_line_star`, `nison_spring_upthrust`, `nison_last_engulfing`,
`nison_window_context`, `nison_record_sessions`, `nison_harami`, `nison_harami_cross`,
`nison_two_black_gapping`, `nison_three_windows`, `nison_gapping_doji`,
`nison_extra_line_break_confirmation`, `nison_three_line_neck`,
`nison_kagi_double_window`, `nison_kagi_tweezers`, `nison_kagi_three_buddha`,
`aldridge_order_flow_autocorrelation`, `aldridge_trade_aggressiveness`,
`aldridge_bid_ask_bounce_filter`, `aldridge_quote_duration`,
`aldridge_trade_direction_uncertainty`, `johnson_implementation_shortfall`,
`johnson_adaptive_shortfall`, `johnson_price_inline`, `johnson_liquidity_seeking`,
`johnson_order_difficulty`, `elliott_impulse_rules`, `elliott_wave_three_extension`,
`elliott_diagonal_rules`, `elliott_corrective_structure`, `elliott_alternation`,
`price_in_time_ntz_projection`, `price_in_time_range_cycle`,
`price_in_time_pending_order`, `price_in_time_ntz_breakout`, `price_in_time_trade_management_models`,
`thomas_push_pull_10xroi`, `clenow_dual_ema_breakout`, `clenow_regime_filter`,
`clenow_atr_impact_sizing`, `clenow_currency_exposure`, `clenow_countertrend_pullback`,
`clenow_term_structure_carry`,
`silvani_retail_contrarian`, `silvani_rolling_pivot_filter`, `silvani_friday_stop_run`, `aziz_abcd_pattern`,
`aziz_bull_flag_momentum`, `aziz_red_to_green`, `aziz_bhod`,
`aziz_bottom_reversal`, `aziz_top_reversal`, `aziz_moving_average_trend`,
`aziz_vwap_control`, `aziz_stock_in_play_scanner`,
`grail_time_anchor_breakout`,
`chan_linear_mean_reversion`, `chan_kalman_mean_reversion`,
`chan_cross_sectional_mean_reversion`, `chan_time_series_momentum`,
`chan_alexander_filter`, `chan_ratio_trade`, `chan_ticking_quote_matching`,
`chan_adf_mean_reversion`, `chan_hurst_stationarity`,
`chan_variance_ratio_stationarity`, `chan_mean_reversion_half_life`,
`chan_cadf_cointegration`, `chan_johansen_cointegration`,
`ultimate_price_rejection`, `ultimate_correlation_lag`,
`ultimate_abandoned_baby_ema5`, `ultimate_triangle_pattern`,
`ultimate_cascade_exhaustion`, `ultimate_sandwich_pattern`,
`ultimate_fractal_pattern`, `ultimate_local_extrema_timing`,
`ultimate_sentiment_change`, `ultimate_high_performance_confluence`,
`ultimate_news_sr_reaction`,
`pf_double_top_bottom`, `pf_triple_top_bottom`, `pf_three_box_catapult`,
`pf_pole_reversal`, `pf_trendline_signal_confirmation`, `pf_opposing_poles`,
`pf_45_degree_trendline`, `pf_early_fulcrum_entry`, `pf_trend_aligned_signal`,
`pf_vertical_count_target`,
`pf_horizontal_count_target`, `pf_shakeout_filter`, `pf_trap_reversal`,
`pf_one_box_semicatapult`, `pf_one_box_fulcrum`, `damir_fib_confluence_reversal`,
`damir_confirmed_trend_change`, `damir_value_rejection_sequence`,
`damir_value_location_guideline`, `damir_value_health_warning`, `grail_bracket_lifecycle`,
`gann_reverse_signal_day`, `gann_higher_tops_bottoms`, `gann_halfway_point`,
`gann_repeated_level_reversal`, `gann_secondary_reaction`,
`gann_fourth_level_reversal`,
`brooks_breakout_pullback_test`, `elder_triple_screen`,
`elder_impulse_censorship`, `elder_force_index_pullback`,
`bulkowski_double_bottom`, `bulkowski_double_top`,
`bulkowski_flag_breakout`, `bulkowski_ascending_triangle`,
`bulkowski_falling_wedge`,
`bulkowski_broadening_bottom`, `bulkowski_broadening_top`,
`bulkowski_right_angled_ascending`, `bulkowski_right_angled_descending`,
`bulkowski_ascending_broadening_wedge`, `bulkowski_descending_broadening_wedge`,
`bulkowski_barr_bottom`, `bulkowski_barr_top`, `bulkowski_cup_with_handle`,
`bulkowski_inverted_cup_with_handle`, `bulkowski_diamond_bottom`,
`bulkowski_diamond_top`,
`bulkowski_high_tight_flag`, `bulkowski_gap`, `bulkowski_head_shoulders_bottom`,
`bulkowski_complex_head_shoulders_bottom`, `bulkowski_head_shoulders_top`,
`bulkowski_complex_head_shoulders_top`, `bulkowski_horn_bottom`, `bulkowski_horn_top`,
`bulkowski_island_reversal`, `bulkowski_long_island`, `bulkowski_measured_move_down`,
`bulkowski_measured_move_up`,
`bulkowski_pennant`, `bulkowski_pipe_bottom`, `bulkowski_pipe_top`,
`bulkowski_rectangle_bottom`, `bulkowski_rectangle_top`,
`bulkowski_rounding_bottom`, `bulkowski_rounding_top`,
`bulkowski_ascending_scallop`, `bulkowski_ascending_inverted_scallop`,
`bulkowski_descending_scallop`, `bulkowski_descending_inverted_scallop`,
`bulkowski_descending_triangle`, `bulkowski_symmetrical_triangle`,
`bulkowski_rising_wedge`, `bulkowski_triple_bottom`, `bulkowski_triple_top`,
`bulkowski_three_falling_peaks`, `bulkowski_three_rising_valleys`,
`bulkowski_dead_cat_bounce`, `bulkowski_inverted_dead_cat_bounce`,
`bulkowski_earnings_surprise_good`, `bulkowski_earnings_surprise_bad`,
`bulkowski_fda_drug_approval`, `bulkowski_earnings_flag`,
`bulkowski_same_store_sales_good`, `bulkowski_same_store_sales_bad`,
`bulkowski_stock_downgrade`, `bulkowski_stock_upgrade`,
`carter_scalper_alert`, `carter_tick_extreme_fade`, `carter_tick_flow_follow`,
`carter_anchor_squeeze`,
`carter_brick_reversal`, `carter_holp_lohp`, `carter_end_of_day_fade`,
`carter_ema_propulsion`, `carter_opening_gap_fade`, `carter_pivot_play`,
`carter_atr_mean_reversion`, `carter_352_play`,
`schwager_bull_bear_trap`, `schwager_false_trend_breakout`,
`schwager_filled_gap_failure`, `schwager_spike_extreme_failure`,
`schwager_wide_range_day_failure`, `schwager_counter_flag_failure`,
`schwager_restrictive_reversal_day`,
`schwager_minor_reaction_reentry`, `schwager_long_ma_reaction`,
`schwager_oscillator_price_confirmation`, `schwager_trend_adjusted_oscillator`,
`schwager_island_reversal_validation`, `schwager_equity_deterioration_warning`,
`brown_qmp_filter_trigger`, `brown_macd_zero_filter`, `brown_qqe_filter`,
`brown_multi_ma_alignment`, `brown_trendline_break_reentry`,
`brown_divergence_type_filter`, `brown_bollinger_trade_management`,
`grimes_pullback_quality`, `grimes_three_push_exhaustion`,
`developing_hft_flow_exhaustion`, `cartea_regime_rebate_safety`,
`cartea_inventory_skew`, `cartea_state_intensity`,
`cartea_quote_freshness_guard`,
`aldridge_pair_dislocation`, `dalton_trend_day_integrity`,
`dalton_auction_point_retest`, `dalton_day_structure`,
`dalton_failed_range_extension`, `dalton_single_print_retest`,
`process_discipline_control`,
`pole_spread_reversion`, `pole_forecast_monitoring`, `pole_cuscore_change_point`,
`pole_75_percent_reversion`, `pole_multi_step_reversion`, `velu_omnibus_rule`,
`velu_fair_value_residual`, `velu_sign_magnitude_decomposition`, `velu_alexander_filter`,
`velu_sma_rule`, `velu_ewa_rule`, `velu_bwma_bollinger_rule`,
`velu_moving_average_oscillator`, `velu_rsi_reversal`, `velu_kernel_pattern`,
`narang_linear_alpha_blend`,
`narang_alpha_rotation`, `narang_run_frequency_tradeoff`, `chan_hft_quote_data_requirements`,
`chan_bulk_volume_order_flow`,
`narang_forecast_bucket_monotonicity`, `narang_time_decay`,
`narang_parameter_robustness`, `narang_portfolio_value_add`,
`narang_risk_monitoring`,
`gray_vogel_path_momentum`, `gray_vogel_rebalance_tradeoff`,
`gray_vogel_lookback_regime`,
`gray_vogel_lottery_avoidance`, `gray_vogel_seasonality_timing`,
`gray_vogel_52_week_high`, `gray_vogel_absolute_strength`,
`gray_vogel_momentum_stop_loss`, `gray_vogel_time_series_overlay`,
`gray_vogel_fundamental_momentum`,
`lien_intraday_range_reversal`, `lien_medium_term_breakout`,
`lien_double_zero_fade`, `lien_wait_for_real_deal`, `lien_fader`,
`lien_filter_false_breakout`, `lien_channel_breakout`, `lien_perfect_order`,
`lien_short_term_momentum_20_100`, `lien_proactive_news`,
`lien_reactive_news`, `lien_combined_news`,
`link_ten_period_breakout`, `link_trendline_buffer_breakout`,
`link_opening_range_breakout_30m`, `link_reversal_day`,
`link_double_top_bottom_reversal`, `link_pain_reversal`,
`link_key_number_reversal`,
`link_multi_timeframe_confirmation`, `link_news_reaction_fade`,
`link_stochastic_wave_entry`, `link_stochastic_cross_entry`, `link_stochastic_extreme_retest`,
`link_rsi_fifty_line_entry`, `link_rsi_extreme_exit`, `link_rsi_pattern_break`,
`link_macd_signal_line_entry`,
`link_adx_regime_switch`,
`link_stochastic_failed_move`,
`link_trend_retracement_entry`, `link_atr_risk_feasibility`,
`link_stop_discipline`,
`momentum`,
`market_profile`, `mean_reversion`, `trend_structure`, `breakout_quality`, `pullback_retest`,
`price_action_candles`, `momentum_exhaustion`, `volume_price`, `volume_open_interest`,
`murphy_percentage_retracement`, `murphy_speed_resistance_lines`,
`volatility_regime`, `microstructure`, `mean_reversion_vs_momentum`,
`higher_timeframe_alignment`, `session_liquidity`, `risk_reward_geometry`,
`validation_integrity`, `market_profile_auction`, `statistical_arbitrage`,
`oscillator_signal`, `scalping_execution`, `support_resistance`,
`chart_patterns`, `moving_average_context`, `channel_analysis`,
`range_edge_rejection`, `volatility_breakout`, `divergence`, `opening_range`,
`news_event_risk`, `liquidity_sweep`, `correlation_context`, `trade_management`,
`bollinger_bands`, `macd_signal`, `atr_regime`, `fibonacci_retracement`,
`pivot_levels`, `rsi_reversal`, `stochastic_reversal`, `donchian_breakout`,
`adx_trend_strength`, `keltner_channel`, `ichimoku_context`, `cci_reversal`,
`williams_reversal`, `vwap_context`, `obv_volume`, `rate_of_change`,
`parabolic_sar`, `elliott_wave`, `harmonic_patterns`, `gann_levels`,
`cointegration_pairs`, `kalman_filter`, `seasonality_context`,
`order_book_imbalance`, `volume_profile_context`, `fundamental_macro`,
`sentiment_positioning`, `time_series_forecasting`, `machine_learning_signal`,
`portfolio_allocation`, `bollinger_pair_mean_reversion`,
`ten_period_sd_breakout`, `triple_screen`, `volume_spread_analysis`,
`candlestick_patterns`, `initial_balance_profile`, `cross_sectional_momentum`,
`meta_labeling`, `force_index`, `elder_impulse`, `market_making_inventory`,
`forecast_combination`, `triple_barrier_label`, `purged_walk_forward`,
`realized_volatility`, `fractional_differentiation`, `risk_parity_allocation`,
`vwap_execution`, `twap_execution`, `participation_execution`,
`ewmac_trend_following`, `carry_rule`, `ab_system`, `wyckoff_spring_upthrust`,
`ttm_squeeze`, `al_brooks_second_entry`, `kangaroo_tail`, `relative_strength`,
`point_and_figure`, `cycle_analysis`, `factor_momentum`, `fundamental_law`,
`market_impact`, `garch_volatility`, `hawkes_order_flow`, `turtle_breakout`,
`volatility_targeting`, `position_sizing`,
`random_forest_signal`, `bayesian_pairs`, `pca_eigenportfolio`, `bet_sizing`,
`feature_importance_stability`, and `stochastic_volatility`.

The added modules distinguish measured inputs from unavailable inputs. The
dedicated momentum perspective requires directional follow-through, the market
profile perspective requires explicit real-volume profile provenance, the
mean-reversion perspective requires a range regime plus measured displacement,
and the noise and tail-risk perspectives require explicit classifications with
observed provenance. The event-arbitrage perspective requires a released,
timestamped event, a measured surprise, and positive chronological net OOS
response; spread scalping requires two-sided quote, inventory, adverse-selection,
closeability, and cost evidence; latency arbitrage requires synchronized
multi-venue data that MT5 does not provide; rebate capture requires a venue fee
schedule plus forecast/fill economics; and market-impact symmetry is only a
buy/sell impact diagnostic. The intermarket perspective additionally requires two independent,
timestamped cross-asset observations with non-proxy provenance; it does not
infer relationships from a symbol name or substitute a generic correlation.
The Al Brooks perspectives require explicit point-in-time structure fields:
High/Low 1-4 count plus prior strength/trendline break, three-push wedge plus
reversal confirmation, failure-of-failure confirmation, a tested
spike-and-channel state, a held second test for double flags, and observed
range location. A count, pattern name, or synthetic/proxy label alone does not
produce a directional view; middle-of-range location remains a warning.
These perspectives remain read-only and fail closed when those inputs are absent. Quote
history can support rate-of-change, quote-mid SAR, prior-observation breakout
channels, EWMA/three-screen context, realized-volatility context, squeeze,
Force Index, Elder Impulse, VSA/tail/Wyckoff proxies, initial balance, as-of
cross-sectional momentum, point-and-figure geometry, activated vertical-count
targets, reversal-specific horizontal-count targets, and shakeout filtering, completed-bar second
entry context, a causal quote-autocorrelation cycle-phase proxy, and a causal
linear-drift forecast with historical walk-forward error; descriptive
same-weekday/hour seasonality; and a causal log-quote fractional-difference
feature; plus a causal local-level Kalman residual proxy. Elliott, harmonic,
Gann, validated seasonality, pair-validated Kalman, level-2 depth, real
volume-profile, macro, sentiment, and validated-model perspectives require
explicitly supplied, timestamped evidence. Tick-price or tick-activity
proxies remain warnings/`WAIT`, not equivalent real-data signals. Quote
GARCH-style recursion, log-variance, and Hawkes-style direction intensities
are likewise descriptive proxies and are never treated as validated models.

Completed quote-bar history also supplies conservative High/Low count, double
flag, wedge/failure, spike/channel, range-location, and named candlestick
labels when the required sequence is visible. These labels carry
`completed_quote_bar_proxy` provenance and remain Watcher research evidence;
they are not exchange-volume or live execution signals.

The new book-specific perspectives keep source rules separate: Ponsi
distinguishes liquid-session continuation from low-liquidity fades; Fabris'
Price-in-Time rule uses only a completed Frankfurt/London range; Thomas'
push-pull rule requires daily momentum plus a separately confirmed hourly
entry; Clenow's model requires a daily dual-EMA filter and confirmed breakout;
and Silvani's positioning view requires observed retail crowding. Missing
daily, positioning, or exchange-volume inputs remain missing rather than being
filled with short-tick proxies.

The Carter perspectives keep the source's market-specific rules separate:
consecutive-close Scalper Alerts, observed breadth-$TICK fades, anchor-chart
squeeze alignment, third-brick reversal breaks, HOLP/LOHP extreme reversals,
the exact 3:52 end-of-day fade, and the 8/21 EMA propulsion pullback. The
breadth and end-of-day studies remain not applicable without their observed
equity-index inputs; no FX proxy is substituted.

The Ultimate Forex source-specific perspectives now also keep the EMA(9)/EMA(15)
reversal, overlapping right-shoulder setup, repeated support/resistance tests,
volume-price extremes, higher-timeframe confirmation, solid-wall break, early
fractal, local-extreme timing, recent sentiment-evolution, and multi-signal
confluence studies separate. Its high-win-rate language is retained as source
context, not as a Watcher probability or authorization.

The Holy Grail case-study perspective also records its central failure lesson:
the time-anchored trend system is not fit for an observed range/reversal regime.
The source's loss-based stake escalation is deliberately not implemented because
the Watcher contract forbids martingale or loss-chasing behavior.

The Schwager perspectives keep failed-signal variants separate: confirmed
bull/bear traps, repeated-close false trend-line breaks, close-based filled
gaps, spike-extreme penetration, wide-range-day failure, and counter-direction
flag/pennant breaks. Aziz's bottom/top reversals, moving-average trend, VWAP
control, and equity-only Stock-in-Play scanner likewise require their own
observed fields; the scanner is explicitly `NOT_APPLICABLE` to FX.

The Grimes perspectives keep structural pullback quality separate from
exhaustion warnings: a trend-aligned continuation pullback requires a causal
impulse, controlled retracement, quieter pullback, no observed momentum
divergence, and continuation confirmation; three roughly symmetric pushes
with a trendline break warn of exhaustion but never create a countertrend
entry signal. Missing structural observations remain `MISSING_DATA`.

The HFT source perspectives keep three additional ideas explicit: large
directional order flow is distinct from flow exhaustion, Cartea/Jaimungal's
rebate case requires observed regime persistence, zero-revision probability,
revision volatility, and positive net edge, and inventory skew points back
toward the target inventory (normally zero). They remain research-only and
require causal provenance; they do not turn MT5 quote/tick proxies into level-2
or venue-rebate evidence.

Aldridge's pair-dislocation perspective requires a validated stationary spread,
an observed z-score at its specified entry threshold, and the corresponding
rich/cheap leg direction. Dalton/Steidlmayer's day-structure perspectives
require an observed trend day with a close near its extreme and limited
countertrend rotation, or an auction point that holds on retest without a
significant violation. These rules remain descriptive and research-only.

Pole's calibrated spread rule now remains separate from the broader
statistical-arbitrage perspective: it requires a validated stationary pair,
point-in-time correlation and calibration window, an extreme z-score, and a
reversion target inside the entry band. Gray and Vogel's momentum perspective
also records the formation-period return, top/bottom decile, skipped recent
period, and their information-discreteness path measure; a discontinuous path
waits instead of being treated as equivalent to smooth momentum.

Lien's two explicit market-condition checklists are represented separately:
the intraday range rule requires daily range confirmation, hourly range-edge
context, an RSI/stochastic reversal, and supporting level behavior; the
medium-term breakout rule requires short volatility below long volatility,
pivot confirmation, and aligned moving-average and breakout directions.

Validation, provenance, calibration, and confirmation labels are interpreted
with token-aware fail-closed checks. Labels such as `not_validated`,
`unverified`, `uncalibrated`, and `unconfirmed` cannot pass because they happen
to contain a positive word as a substring. Missing positive validation is also
kept at `WAIT`/`MISSING_DATA` for validation-dependent perspectives.

The current canonical registry contains 12,614 source records: 342 exact
predicate records, 3,403 family-perspective records (including known-family
records whose exact parameters could not be compiled safely), 2,125
known-family context records, and 6,744 records without a known family or
enough usable specification. Context records are replayed through a named
family view for descriptive study only; they do not recover missing entry,
exit, or parameter rules and cannot authorize a trade. The final group remains
`SPECIFICATION_ONLY`; it is not silently converted into an executable rule.
The book replay reports descriptive applicability and historical outcomes for
the exact, mapped family-perspective, and mapped family-context groups.

The latest bounded Watcher-algorithm replay evaluated 1,000 chronological
rows through all 616 modules. The newly added de Jong diagnostics, Velu
distance-pair, Narang rotation/run-frequency, Chan quote-data/BVC, Davey
three-close baseline/Euro Night/Euro Day, and Lien extension-turn/two-day-stop/
two-stage-management and Link's stochastic cross/RSI extreme-exit/pattern-break
perspectives are covered by focused tests;
the refreshed replay artifact includes them. It produced no
fabricated signals: only perspectives with the required causal inputs
generated replay samples, while the remaining modules reported
`MISSING_DATA` or `WAIT`.

The Brooks range-specific inputs are now derived in the live Watcher feature
adapter from completed quote bars: shrinking breakout increments, the latest
three-bar micro-measuring-gap context, and directional always-in/spike context.
They retain the exact `completed_quote_bar_proxy` provenance (accepted only by
these proxy-aware perspectives; synthetic/unverified labels remain blocked)
and remain descriptive; they do not authorize execution.

Gray/Vogel's portfolio-construction comparison is represented separately as
`gray_vogel_rebalance_tradeoff`. It requires observed portfolio size, universe,
holding/rebalance cadence, gross edge, and per-rebalance cost; it reports
concentration, overlap, and after-cost viability without creating a direction.

The latest chronological replay evaluated 1,000 rows and all 12,614 registry
records: 342 exact rules, 3,403 family perspectives, 2,125 family contexts,
and 6,744 records kept as specification-only. It used 26 evaluator groups and
reports
`no_lookahead=true`, `research_only=true`, and `execution_authority=false`.

The process-discipline perspective represents the psychology books as a
non-directional diagnostic: it requires pre-decision rules and risk, checks
compliance and explicit loss acceptance, and flags revenge or confirmation
bias. It does not create a market signal or an execution decision; those books
remain `CONTEXT_ONLY` for market prediction.

`watcher_book_perspectives.py` is now only the compatibility/catalog layer.
`BOOK_ALGORITHM_COVERAGE` explicitly cross-references every reviewed title to
the relevant human-authored modules. Each module reports its source books,
missing inputs, and research-only status; none has execution authority.

This record is intentionally honest about partial/scanned coverage. It is not
evidence that any book-derived idea is profitable; shadow outcomes and
broker-confirmed outcomes must establish that separately.
