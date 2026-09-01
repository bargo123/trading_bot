# Intelligence shadow cycle

Label: `research_proxy`. No orders placed; no live YAML promotion.

```text
THESIS: GBPUSD_SELL_FAILED_BREAK_REVERSAL_20260817T171642Z
DECISION: REDUCE_OR_WAIT (research-only; no order placed)
SETUP: failed break reversal
REGIME: trend
EVIDENCE: none
CONTRADICTING_EVIDENCE: book:a-complete-guide-to-volume-price-analysis-coulling.md: not used as support: required data unavailable (broker_tick_volume_proxy, mt5_l2, volume_unspecified); book:advances-in-financial-machine-learning-prado-2018.md: not used as support: required data unavailable (futures_oi, mt5_l2, volume_unspecified); book:algorithmic-trading-and-dma-johnson-2010.md: not used as support: required data unavailable (futures_oi, mt5_l2, volume_unspecified); book:algorithmic-trading-winning-strategies-chan-2013.md: not used as support: required data unavailable (futures_oi, mt5_l2, volume_unspecified); book:beat-the-forex-dealer-an-insider-s-look-into-trading-today-s-foreign-exchange-ma.md: not used as support: required data unavailable (mt5_l2, volume_unspecified); book:beyond-candlesticks-new-japanese-charting-techniques-revealed-wiley-finance-1994.md: not used as support: required data unavailable (volume_unspecified); book:building-winning-algorithmic-trading-systems-website-a-trader-s-journey-from-dat.md: not used as support: required data unavailable (volume_unspecified); book:elliott-wave-principle-frost-prechter-2005.md: not used as support: required data unavailable (volume_unspecified)
BOOK_PROVENANCE: 8 hashed source(s)
ESTIMATED_EDGE: -0.030447154471544714
UNCERTAINTY: symbol_only_outcomes_not_market_state_matched; n=246; lower95=-0.06832734723707236
CURRENT_THESIS_RISK_USD: 0.0000
TARGET_THESIS_RISK_USD: 0.0000
INVALIDATION: completed-bar close above failed resistance
EXPECTED_DURATION: M15-H1
```

## Market state

- observed_at: 2026-08-17 20:16:00+00:00
- regime: trend
- htf_ready: True
- session: newyork
- volatility: compressing

## Exposure

- action: reduce_or_wait
- reason: symbol_only_outcomes_not_market_state_matched
- target risk USD: 0.0

## Outcome learning

- thesis clusters: 1
- registry row recorded: True

## State-matched challenger validation

- Selected on purged training data: `none`
- Sealed decision: `rejected`
- Reason: no candidate has enough state-matched training outcomes
- Searches corrected for: 1
- Point-in-time state matches: 0
- Sealed trades: 0
- Sealed expectancy (R): None
- Sealed profit factor: None
- Train/hold boundary: None < None
- Promotion: live YAML and CORE remain unchanged unless every governed gate passes.