# Strategy assumption audit

This classifies controls; it does not alter the frozen CORE runner or YAML.

| control | value | class | why | replacement / retention | evidence |
| --- | --- | --- | --- | --- | --- |
| allow_live | False | safety_invariant | Prevents silent real-money activation. | retain deterministic gate | engine paper-mutation guard |
| completed_bar_only | True | safety_invariant | Future bars invalidate research and execution evidence. | retain deterministic gate | dataset/assert_no_lookahead and structure tests |
| broker_volume_min_step | symbol-specific | broker_market_constraint | Orders outside broker contract limits are invalid. | read contract snapshot per symbol | MT5 symbol capability |
| firehose_tp_sl_pips | 1/30 | temporary_research_assumption | Frozen CORE benchmark; not a validated challenger payoff. | thesis invalidation and costed candidate payoff | current_best: no champion |
| firehose_max_per_symbol | 3 | arbitrary_legacy_rule | Order count is not independent evidence or aggregate risk. | target_thesis_exposure with correlated-risk budget |  |
| max_positions | 40 | temporary_research_assumption | Demo capacity cap; does not express thesis or correlation exposure. | gross-risk safety cap plus thesis exposure policy |  |
| intel_mega_min_votes | 3 | arbitrary_legacy_rule | Raw proxy count is not a calibrated probability. | source-independent calibrated evidence |  |
| intel_min_er | 0.15 | temporary_research_assumption | Threshold has no attached calibration record. | regime-conditional holdout calibration |  |
| htf_ema_on_m1 | slow EMA proxy | arbitrary_legacy_rule | A slow M1 indicator is not a completed H4/D1 bar. | MarketState genuine M1→D1 resampling |  |
| max_spread_pips | 0.3 | temporary_research_assumption | Cost protection is needed, but fixed value needs symbol/regime evidence. | cost relative to predicted payoff and observed execution distribution |  |
| risk_halt_on_invalid_broker_state | True | safety_invariant | Invalid/stale execution state must not be traded through. | retain deterministic gate | OMS/execution circuit |
