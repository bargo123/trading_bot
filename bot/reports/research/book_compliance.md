# Book-compliance matrix

| book | implemented | gap | claim |
| --- | --- | --- | --- |
| Coulling VPA | tick-volume effort proxy | not centralized volume | must not call true VPA |
| Brooks Ranges | 5m location/failed-break proxy | not the full 3-book method | must not call faithful Brooks |
| Damir 2016 | H4/M15 retest proxy | not M1-only | must not call full Damir |
| Jansen ML | none | no trained PIT model | jansen_score is a heuristic |
| Harris | spread-vs-take constraint + event blackout gate | no L2/queue | harris_jump is local heuristic |
| Steidlmayer | TPO time-at-price proxy | not pit IB | must not call Market Profile pit |
| Chan 2013 | chan_bb_fade research entry + chan_bb_scalp demo algo | 2013 PDF not extracted; costs kill naive MR | research_proxy not faithful Chan basket |
| Prado AFML | purged_holdout + meta-label + triple-barrier + CPCV proxy | no full AFML library or LOB features | research_proxy not Jansen ML |
| Frost/Prechter Elliott | objective swing-leg counter | subjective wave counts rejected by Aronson | research_proxy not Elliott Wave Principle |
| Johnson DMA | spread-vs-ATR gate only | no exchange DMA/co-lo | research_proxy; DMA unavailable on retail MT5 |
| Gann 1976 | bar-count cycle + slope/ATR proxy | no PDF extract; not hand-drawn angles | research_proxy |
| Zuckerman Medallion | six_book_stack vote ensemble + overfit gates | narrative not a strategy book | research_proxy; no Medallion replication |
| Nison / du Plessis | PnF/Renko/Kagi/TLB engines | research_proxy | not a trading system |
| kaufman | none | Perry Kaufman Trading Systems and Methods — no full extract on disk | unavailable extract |
| volman | none | Bob Volman Forex Price Action Scalping — digest only | unavailable extract |
