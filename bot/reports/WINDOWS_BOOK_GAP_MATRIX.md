# Aegis Windows takeover — book→code gap matrix

Date: 2026-08-12. Claims below are tied to book extracts + existing measured reports. **No 100% WR promise.**

## 1. Confirmation checklist

### Phase 0 — library present
| Path | Status |
| --- | --- |
| `docs/WINDOWS_FULL_CONTEXT.md` | present, read |
| `docs/WINDOWS_CONTINUE_HERE.md` | present, read |
| `docs/trading/INDEX.md` | present, read |
| `docs/trading/BOOKS.md` | present, read |
| `docs/trading/BOOKS_FULL.md` | present, read (catalog of 36 older extracts) |
| `docs/trading/books/` | present — **39 readable `.md` files** |
| `docs/trading/NEW_BOOKS_AZIZ_STEIDLMAYER.md` | present, read |
| `docs/trading/NEW_BOOKS_FULLER_FABRIS_BROWN_SILVANI.md` | present, read |
| `docs/trading/NEW_BOOKS_PONSI_DAMIR_DRAKOLN_THOMAS_AFSHARI_WINDSOR.md` | present, read |
| `docs/trading/NEW_BOOKS_KAUFMAN_VOLMAN_JOHNSON_CHAN.md` | present, read |
| `docs/trading/NEW_BOOKS_HFT_CARTEA_ALDRIDGE_ORESTE_NARANG_VANDERPOST.md` | present, read |
| `docs/trading/extra_hft_pdfs/` | optional; present |
| Cartea / Aldridge / Oreste / Narang / Van Der Post extracts | all five present |

`BOOKS_FULL.md` also lists two Jared Tendler extracts. They are **not readable in this workspace** (NUL/binary duplicates; glob finds 0 Tendler files). Status: `READ_BLOCKED_NUL`. Digest-level Tendler notes remain in `AEGIS_BOOK_CODE_AUDIT.md`.

### Phase 1 — project state
Read: `docs/IB_PAPER_SETUP.md`, `bot/README.md`, `bot/DESIGN.md`, `AEGIS_BOOK_CODE_AUDIT.md`, `TUNE_5H_FINAL.md`, `MGC_FIREHOSE.md`, `CAFB_BASKET.md`, `PULSE_BASKET.md`, `HALE_BASKET.md`, `TUNED_100WR_CORRECTED.md`, `IB_PAPER_STACK_AUDIT.md`, `SMIRNOV_WIN_WIN_AUDIT.md`, `ROBBINSON_HEIKIN_ASHI_AUDIT.md`, `VOLMAN_CHAN_BASKET.md`, plus engines/`session_algos`/`strategy`/`backtest`/`risk`/`paper_control`/runner scripts.

Hard facts (unchanged without new measurements):
- Mac IB EURUSD every-bar firehose lost to ~$2 commissions.
- MGC delayed replay: 13 trades, 53.85% WR, E[R] −0.10, −$11.96, `paper_promoted=false`.
- CAFB / Pulse / HALE failed honest holdouts after costs.
- Yahoo gold `hw_range` $100→~$45k is a tune-sample trophy, not live IB/MT5 proof.
- MetaTrader5 Python works on this Windows box; MT5 is the UI.

### Phase 2 — digests
All five `NEW_BOOKS_*.md` files plus `INDEX.md` / `BOOKS.md` / `BOOKS_FULL.md` read end-to-end.

---

## 2. Every file in `docs/trading/books/` — READ status

| File | Status |
| --- | --- |
| `modelling-asset-prices-for-algorithmic-and-high-frequency-trading-cartea-jaimungal.md` | READ_COMPLETE |
| `high-frequency-trading-a-practical-guide-aldridge.md` | READ_COMPLETE |
| `inside-the-black-box-narang.md` | READ_COMPLETE |
| `quantum-trading-using-principles-of-modern-physics-oreste.md` | READ_COMPLETE |
| `quantum-finance-van-der-post.md` | READ_COMPLETE |
| `beat-the-forex-dealer-an-insider-s-look-into-trading-today-s-foreign-exchange-ma.md` | READ_COMPLETE |
| `forex-strategy-the-price-in-time---libgen-li.md` | READ_COMPLETE |
| `forex-patterns-probabilities-trading-strategies-for-trending-range-bound-markets.md` | READ_COMPLETE |
| `trade-the-price-action---forex-trading-system-2012---libgen-li.md` | READ_COMPLETE |
| `profitable-forex-trading-using-high-and-low-risk-strategies-2024---annas-arch-37.md` | READ_COMPLETE |
| `pyramiding-full-text-extracted.md` | READ_COMPLETE |
| `the-10xroi-trading-system----thomas-lr-thomas-lr----2014----109595d6293932cffaa6.md` | READ_COMPLETE |
| `the-holy-grail-forex-trading-system-foreign-exchange-day-trading-was-this-the-ul.md` | READ_COMPLETE |
| `the-ultimate-forex-trading-system-unbeatable-strategy-to----unknown----2021----6.md` | READ_COMPLETE |
| `how-to-day-trade-for-a-living-a-beginner-s-guide-to-trading-tools-and-tactics-mo.md` | READ_COMPLETE |
| `winning-the-trading-game-why-95-of-traders-lose-and-what-you-must-do-to-2008-wil.md` | READ_COMPLETE |
| `building-winning-algorithmic-trading-systems-website-a-trader-s-journey-from-dat.md` | READ_COMPLETE |
| `evidence-based-technical-analysis-applying-the-scientific-method-and-statistical.md` | READ_COMPLETE |
| `quantitative-trading-how-to-build-your-own-algorithmic-trading-business-2008-wil.md` | READ_COMPLETE |
| `systematic-trading-a-unique-new-method-for-designing-trading-and-investing-syste.md` | READ_COMPLETE |
| `following-the-trend-diversified-managed-futures-trading-wiley-trading-2023-wiley.md` | READ_COMPLETE |
| `the-new-trading-for-a-living-psychology-discipline-trading-tools-and-systems-ris.md` | READ_COMPLETE |
| `trade-your-way-to-financial-freedom-2006-mcgraw-hill-companies---libgen-li.md` | READ_COMPLETE |
| `trading-and-exchanges-market-microstructure-for-practitioners---full---2002-oxfo.md` | READ_COMPLETE |
| `the-art-and-science-of-technical-analysis-market-structure-price-action-and-trad.md` | READ_COMPLETE |
| `steidlmayer-on-markets-trading-with-market-profile-2003-john-wiley-sons---libgen.md` | READ_COMPLETE |
| `technical-analysis-of-stock-trends-eleventh-edition-2018-crc-press---libgen-li.md` | READ_COMPLETE |
| `encyclopedia-of-chart-patterns-2005-john-wiley-sons-inc---libgen-li.md` | READ_COMPLETE |
| `beyond-candlesticks-new-japanese-charting-techniques-revealed-wiley-finance-1994.md` | READ_COMPLETE |
| `the-definitive-guide-to-point-and-figure-2005---libgen-li.md` | READ_COMPLETE |
| `trading-with-intermarket-analysis-a-visual-approach-to-beating-the-financial-mar.md` | READ_COMPLETE |
| `getting-started-in-technical-analysis-1999-wiley---libgen-li.md` | READ_COMPLETE |
| `the-disciplined-trader-developing-winning-attitudes-1990-prentice-hall-press---l.md` | READ_COMPLETE |
| `trading-in-the-zone-2021-wiley-trading---libgen-li.md` | READ_COMPLETE |
| `reminiscences-of-a-stock-operator-2012-john-wiley-sons---libgen-li.md` | READ_COMPLETE |
| `stock-market-wizards-interviews-with-america-s-top-stock-traders-2001-harperbusi.md` | READ_COMPLETE |
| `the-new-market-wizards-conversations-with-america-s-top-traders.md` | READ_COMPLETE |
| `market-structure.md` | READ_COMPLETE (synthetic sample, not a book) |
| `sample-author.md` | READ_COMPLETE (synthetic sample, not a book) |
| Tendler extracts listed in `BOOKS_FULL.md` | READ_BLOCKED_NUL |

Digest-only (no full extract in `books/`): Volman, Kaufman, Johnson DMA, Chan 2013. Claims for those stay digest-level.

---

## 3. BOOK→CODE GAP MATRIX (every book)

Quality: **good** = coded rule matches source and is testable; **partial** = defensible proxy; **rough** = name overstates fidelity; **absent**; **reject** = do not implement as live edge.

### A. HFT / quant (latest five)

| Book | Thesis / actionable | Aegis | Quality | MT5-portable? | Priority |
| --- | --- | --- | --- | --- | --- |
| **Aldridge** *HFT* | Bid-ask is the cost of instant round-trip; tick moves can be ≤ spread; EURUSD spread widens in Tokyo / crises (extract pp. ~bid-ask chapter). | `spread_bps` + new `symbol_spec` / `round_trip_spread_usd` / `copy_ticks`. Firehose still forbidden. | Partial (snapshot spread, not full diurnal model) | Yes: measure broker spread before any scalp | **P0** |
| **Narang** *Inside the Black Box* | Do not trade unless alpha clears costs; successful quants estimate costs eat **20–50% of returns**; alpha + risk + cost models. | Cost fields in backtest; no live-vs-model drift monitor; no capacity model. | Partial / process | Yes as process, not as entries | **P0** |
| **Cartea & Jaimungal** | HMM regimes; post limit orders to earn spread; rebate trading; tick durations. | Absent (no inventory MM, no HMM quotes). | Absent | Needs tick/L2 + maker rebates. **Not** retail `EURUSD.gc` market orders. | P2 / defer |
| **Oreste** *Quantum Trading* | Gann + “quantum price lines” (QPLs) as discretionary forecast. | Absent | **reject as edge** | Metaphor / unverifiable | reject |
| **Van Der Post** *Quantum Finance* | QC-for-finance popularization; text itself calls hardware nascent. | Absent | **reject as edge** | No QC on this demo | reject |

### B. FX / systems

| Book | Actionable | Aegis | Quality | Notes |
| --- | --- | --- | --- | --- |
| **Fabris** NTZ | GMT 07–08 band 10–30 pips; pending ±1 pip; flatten ~17:00; ≤2 trades/day | `sig_fabris_ntz` | Partial | Close-cross proxy, not pending ±1; broker clock TBD |
| **Aziz** | ≤2% risk, ≥2:1, ORB/VWAP; ~30% losers OK | `aziz_orb`, `aziz_vwap` | Rough | FX volume ≠ stock RVOL; no L2 |
| **Fuller** pyramid | Add winners only; aggregate ≤1R | `pyramid.py` | Partial | Risk not recomputed after every add |
| **Ponsi** | Regime match; anti-10-pip scalp; MTF / squeeze / flags | squeeze/trend proxies | Partial | `_htf_trend` is same-TF EMA |
| **Damir** | H4 PA + Fib; few trades/month | EMA proxy | Rough | No true HTF join |
| **Brown** | Indicator systems + **unsafe** recovery/DCA | features + caged high-risk | Partial / **reject live recovery** | Keep cage |
| **Silvani** | Dealer/session, pivots, stop-runs | UTC session only | Rough | No pivots/rollover flatten |
| **Thomas 10XROI** | D1 trend + H1 pullback, asymmetric R | `thomas_10r` | Rough | Not true D1→H1 |
| **Windsor** holy grail | Stake ratchet / escalating risk | Windsor mode experiments | **reject live** | Loss escalation compounds model error |
| **Afshari** “Ultimate” | Multiplied confluence “probabilities” | `book_optimal` | Rough / **reject math** | 92% confluence is not statistics |
| **DraKoln** | Framework, ATR, time stops | ATR + `max_hold_bars` | Partial | Process, not a named edge |

### C. Process / risk

| Book | Actionable | Aegis | Quality | Priority |
| --- | --- | --- | --- | --- |
| **Davey** | Frozen holdout, WFA, MC, enough trades, costs | search scripts only | Rough | **P0 still open** |
| **Aronson** | Permutation / search-size / no data-mined certainty | mechanical signals | Rough | **P0 still open** |
| **Chan 2008** | Costs, stability, capacity | `chan_bb_scalp` misnamed | Rough | P1 |
| **Carver** | Vol-target, forecast cap, turnover buffer | ATR stops | Rough | P1 |
| **Clenow** | Diversified breakout, ATR risk_factor | Donchian 20/55 | Partial | P1 (needs multi-symbol) |
| **Elder** | 2%/6% monthly, Triple Screen | `elder_impulse` proxy | Partial | P2 |
| **Tharp** | Expectancy in R, sizing, ruin | RiskEngine + net R (after cost fix) | Partial | P0/P1 |
| **Harris** | Half-spread = immediacy tax; impact; order choice | bps + now live MT5 spread USD | Partial | **P0** — firehose loss **is** Harris |

### D. Structure / PA

| Book | Aegis | Quality |
| --- | --- | --- |
| **Grimes** | generic pullback | Rough — failed-break is a later candidate |
| **Steidlmayer** | IB break/fade, range-mid “value” | Rough — not TPO/POC |
| **Edwards/Magee** | EMA/Donchian proxies | Rough |
| **Bulkowski** | none | Absent — **do not import daily-stock % as FX** |
| **Nison** (both) | none | Absent |
| **du Plessis P&F** | none | Absent |
| **Murphy** TA of FM | indicators | Partial |
| **Murphy** Intermarket | none | Absent (needs multi-asset) |
| **Schwager** Getting Started | generic TA | Partial |

### E. Psychology / narrative

| Book | Aegis | Quality |
| --- | --- | --- |
| **Douglas** ×2 | journal / batch tests | Partial — 20-trade sample protocol still missing |
| **Tendler** | journal | READ_BLOCKED_NUL |
| **Lefèvre** | winner-only pyramid | Partial — no probe size |
| **Schwager wizards** ×2 | stops / process | Partial — do not fake-code fund catalysts on EURUSD |

### F. Samples + digest-only

| Source | Status |
| --- | --- |
| `market-structure.md` / `sample-author.md` | Synthetic. Not evidence. |
| Volman (digest) | `volman_scalp` rough; hunt lost money at 20% risk |
| Kaufman / Johnson DMA | Absent full text; DMA not retail MT5 |
| Chan 2013 (digest) | Not the 2008 book; `chan_bb_scalp` is not pairs |

---

## 4. Ranked MT5 plan (Windows demo)

1. **Keep `allow_live: false`.** Demo only. MT5 terminal is the UI — no new web dashboard.
2. **Unblock orders or stop calling it “trading.”** Account `900907` previously had `trade_expert=False` → retcode **10026**. Algo Trading in the toolbar is necessary but not sufficient if the server forbids EAs.
3. **Measure live spread/commission** (`scripts/measure_mt5_costs.py`) — Harris half-spread, Aldridge “gain must cover spread,” Narang 20–50% cost haircut.
4. **Place/cancel 0.01 lot far limit** only after `trade_expert=True`. Then flatten.
5. **Measured path:** `hw_range` on broker H1, **0.01 lots**, costs in WR / E[R] / PF / DD. `firehose_every_bar: false`. Report `paper_promoted=false` until frozen holdout exists (Davey/Aronson still open).
6. Later: Fabris NTZ with broker clock; cost-gate any scalp so TP ≫ round-trip (Ponsi/Aldridge). IB firehose already failed that test.
7. Do **not** implement Cartea quotes, Oreste QPLs, Van Der Post QC, Smirnov grid, Windsor martingale, every-bar spray.

## 5. Explicit rejects

- Smirnov-style no-stop recovery / 90% basket-loss / black-box EA
- Every-bar commission spray (measured loss on IB)
- Quantum / Gann / QC as “edge”
- 100% WR as a promise (Yahoo gold trophy ≠ live MT5)
- Importing Bulkowski daily-stock stats as FX probabilities
- Afshari multiplied-confluence math
- Windsor stake-ratchet on a $100 demo
- Brown/Smirnov DCA as the primary system
