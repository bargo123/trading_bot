# Aegis MT5 book audit — 12 FX / session / MM sources (Aug 2026)

Full cleaned text under `@docs/trading/books/`. Every file below was read to EOF (chunked). **Do not invent 100% WR.** Reject Smirnov-style no-stop recovery and Windsor loss-escalation as **live** money management.

Cross-check mappings: `fabris_ntz`, `aziz_orb` / `aziz_vwap`, `pyramid.py`, `high_risk.py` (Brown / Windsor / Thomas **caged**), `thomas_10r`, `hw_range`.

Status key: **Implemented** / **Partial** / **Absent**. Quality is how faithfully Aegis matches the book (not backtest luck).

Priority: **P0** keep/ship on MT5 · **P1** next signal/gate · **P2** research/optional · **P3** reject or lab-only.

---

## Coverage table

| # | File | READ_COMPLETE | Author / title | Lines |
|---|------|---------------|----------------|-------|
| 1 | `beat-the-forex-dealer-an-insider-s-look-into-trading-today-s-foreign-exchange-ma.md` | YES | Agustin Silvani — *Beat the Forex Dealer* (Wiley 2008) | 2953 |
| 2 | `forex-strategy-the-price-in-time---libgen-li.md` | YES | Gabriele Fabris — *The Price in Time* (2023) | 781 |
| 3 | `forex-patterns-probabilities-trading-strategies-for-trending-range-bound-markets.md` | YES | Ed Ponsi — *Forex Patterns & Probabilities* (Wiley 2007) | 3394 |
| 4 | `trade-the-price-action---forex-trading-system-2012---libgen-li.md` | YES | Laurentiu Damir — *Trade the Price Action* (2012) | 140 |
| 5 | `profitable-forex-trading-using-high-and-low-risk-strategies-2024---annas-arch-37.md` | YES | Jim Brown — *Profitable Forex Trading Using High & Low Risk Strategies* (2024) | 1064 |
| 6 | `pyramiding-full-text-extracted.md` | YES | Nial Fuller — *Pyramiding* (2012 article) | 68 |
| 7 | `the-10xroi-trading-system----thomas-lr-thomas-lr----2014----109595d6293932cffaa6.md` | YES | LR Thomas — *The 10XROI Trading System* (©2013 / file 2014) | 390 |
| 8 | `the-holy-grail-forex-trading-system-foreign-exchange-day-trading-was-this-the-ul.md` | YES | James Windsor — *The Holy Grail Forex Trading System* (2013) | 1640 |
| 9 | `the-ultimate-forex-trading-system-unbeatable-strategy-to----unknown----2021----6.md` | YES | Mostafa Afshari — *The Ultimate Forex Trading System* (©2016 / file 2021) | 374 |
| 10 | `winning-the-trading-game-why-95-of-traders-lose-and-what-you-must-do-to-2008-wil.md` | YES | Noble DraKoln — *Winning the Trading Game* (Wiley 2008) | 4566 |
| 11 | `how-to-day-trade-for-a-living-a-beginner-s-guide-to-trading-tools-and-tactics-mo.md` | YES | Andrew Aziz — *How to Day Trade for a Living* (2015/2020) | 2188 |
| 12 | `steidlmayer-on-markets-trading-with-market-profile-2003-john-wiley-sons---libgen.md` | YES | J. Peter Steidlmayer / Steven B. Hawkins — *Steidlmayer on Markets* (Wiley 2003) | 2314 |

---

## 1. Silvani — *Beat the Forex Dealer*

**Thesis:** Retail FX is structurally stacked (spread, leverage marketing, dealer stop-runs). Survive by trading only when odds shift; professional MM; no holy-grail systems. Explicit: long-run retail failure is the base rate; FXCM-era comment that few day traders stay profitable.

**Actionable rules (exact numbers):**
- Risk **≤1–2%** equity per position.
- Retail leverage **≤10×** (pros often **2–5×**). Ten times leverage on $1000 ⇒ ~1000 points to wipeout.
- Scale multiple minis in a **10–15 pip** band (not one huge clip).
- **4h rolling pivot:** classic `(H+L+C)/3` on last 4h bar; long only above, short only below. Do **not** trade the pivot break itself — use as a **filter**.
- Session clocks: prefer London–NY overlap; avoid thin hours (~**3–7pm NY**).
- **Big Figure:** fade first test of a round / Fib / trendline if it fails in **≤15 min**; if it does not work immediately, exit (real-money demand, not dealer). Author claims **>70%** historical success on this setup — treat as dealer folklore, not a WR guarantee.
- **Friday→Sunday extension:** after a volatile data Friday, enter prevailing direction in the **3–5pm NY** window; expect **+20–30 pips** Sunday Sydney bump; limited downside in thin Sunday open.
- News: first **15 min** often stop-run both sides then return; fade first spike after dust settles; use **15m** charts.
- Dynamic stops (not tiny fixed at rounds/news).

**Discretionary vs mechanical:** Mostly discretionary dealer-tactics + filters. Pivot formula is mechanical; Big Figure / Friday extension need judgment.

**Tick/L2 vs OHLC:** Book’s edge is **dealer flow / EBS / client stops**. Transferable without L2: session clocks, 4h pivot, cost, news wait, Big Figure time-box. Does **not** transfer: latency arb, knowing client stops, dealing-desk phone flow, invisible broker stops.

**Hype:** Casino-broker framing is useful; **>70%** Big Figure and “easy pips” dealer setups are not measured Aegis stats. No 100% WR claim as a system.

**MT5-portable:** High for **gates** (session, cost, leverage, pivot filter). Low for true dealer microstructure. MT5 demo has broker-native quotes — still not interbank L2.

**Aegis mapping:**
| Piece | Status | Quality |
|-------|--------|---------|
| Session / cost / ≤1–2% risk | **Implemented** (`in_session`, `cost_ok`, `risk_percent`, `config_mt5_demo_eurusd.yaml`) | High |
| 4h rolling pivot bias | **Absent** as dedicated filter | — |
| Big Figure ≤15 min fade | **Absent** | — |
| Friday–Sunday extension | **Absent** | — |
| Thin-hour blackout 15–19 NY | **Partial** (generic session window, not Silvani hours) | Low |
| Dealer L2 / stop-run hunting | **Absent** (correct) | — |

**P0:** Keep cost + session + ≤2% as live default. **P2:** 4h pivot filter. **P3:** latency arb / stop-hunting.

---

## 2. Fabris — *The Price in Time*

**Thesis:** Edge = **Price + Time** only. Fixed GMT session structure → mechanical dual breakout of the London open range. No discretionary patterns. Explicit: **no infallible method**.

**Actionable rules:**
- **NTZ:** GMT **07:00–08:00** (Frankfurt→London) high/low. Trade only if width **W ∈ [10, 30] pips**. Skip if **W < 10** (both sides fill on noise) or **W > 30** (Larry Williams: large range → next range small).
- Skip: Asia already trending; holidays; NFP/FED/ECB; wars; NY/London closed.
- Indicator default: Asia box max **40 pips** (configurable).
- **~08:00 GMT:** BuyStop = NTZ_H **+1 pip**; SellStop = NTZ_L **−1 pip**. Place 2–3 minutes before London.
- SL = opposite NTZ **±1 pip**.
- TP = project W: TP1…TP4 (prefer **half-pip early** so price does not wick the level and reverse).
- **≤2 trades/day/pair**; never same direction twice; opposite side only after a stop; flatten **~17:00 GMT** (London close). If both pending unfilled into late turquoise box, cancel.
- **Models:** (1) trail SL to prior TP; (2) half at TP1, leave SL, then SL→TP1 at TP2, rest to TP3 for ~1:2; (3) BE at TP1, fixed TP2 (~1:2). Pick per pair via backtest. Aegis default spirit = Model 3 (`ntz_tp_mult: 2`).
- Second pending: cancel if first already at target; keep if first stopped before TP1 (Variant A); keep into peach / early turquoise if TP1/TP2 hit then reverse (B/C).
- Risk **0.5–2%** total across **≤3 pairs** (author often **2%** book-wide). Lot ≈ `$ risk / pips / 10`.
- Capital: only **15–20%** of savings in the trading account; withdraw **40%** quarterly or **60%** monthly of net profits.
- Timeframe does not matter for NTZ H/L (objective prices); H1 or lower is practical.

**Discretionary vs mechanical:** **Mechanical** (author’s point vs H&S). Skip-days (Asia trend, news) have some judgment.

**Tick/L2 vs OHLC:** Pure OHLC + clock. MT5-native.

**Hype:** “Constant gains” / “complete safety from backtests” — still no holy grail; author says so in the close.

**MT5-portable:** **Highest in this batch.** GMT vs broker server (often GMT+2/3) must be mapped (`ntz_start_utc` / `GMT` on Fabris’s own MT4 indicator).

**Aegis mapping:**
| Piece | Status | Quality |
|-------|--------|---------|
| NTZ 07–08 GMT, width, dual break, opposite SL, flatten 17:00 | **Implemented** (`fabris_ntz`, `add_fabris_ntz_features`) | High (width often ATR-scaled; book is **10–30 pips** — set `ntz_min_abs` / `ntz_max_abs` on EURUSD) |
| BuyStop +1 / SellStop −1 pending | **Partial** (close-cross after ready, not pending ±1) | Medium |
| Models 1–2 (trail / half) | **Partial** (Model 3 TP2 default) | Medium |
| Asia skip | **Partial** (`ntz_asia_ok`, default 3% of price — book is ~40 pip box) | Medium |
| ≤2 trades/day, never same dir twice | **Partial** / config | Medium |

**P0:** `fabris_ntz` on MT5 with pip-band + GMT map. **P1:** pending ±1, flatten, 2-trade cap.

---

## 3. Ponsi — *Forex Patterns & Probabilities*

**Thesis:** Match technique to regime (trend vs range). Multi-timeframe + risk first. Anti–holy-grail; anti–10-pip scalping; pros obsess over **losses**, not win count.

**Actionable rules:**
- **Proper order (up):** 10 > 20 > 50 > 200 SMA/EMA. Down = reverse. Spaghetti = range-only methods.
- **ADX > 35 and rising** = strong trend.
- **MTF:** HTF bias only; LTF Fib pullback **38.2 / 50 / 61.8**; stop beyond extreme; scale at **1R → BE**; soften S/R targets by **~10% of the range** (example: 10% of 150 pips = **15 pips**).
- **FX-Ed (daily only):** proper order + price on correct side of **10-EMA ≥10 bars**; enter on 10-EMA touch (no need to wait for close); trail **0.5 × ATR(14) daily** under/over the EMA; **no forced TP**; never lower a long stop; don’t stack correlated pairs.
- **Squeeze:** flat **20-EMA** + ATR↓ + BB width↓ → triangle; break either way; stop **inside** the triangle; Fib/S/R exits; longer squeeze → stronger break.
- **Flags/pennants:** entry = pole extreme **±10%** of pole; stop = **25%** of pole from entry; TP1 = 1R; TP2 = measured pole.
- **Round Trip:** fade **first** touch of xx00 on **5–15m** after **≥20 pips** from 20MA; stop **15 + spread**; spread cap **5**; 1R→BE. Stale figures skipped.
- **Boomerang:** **EURUSD only**, just after **17:00 ET** (rollover); sell **+15** / buy **−15** from open; stop **15**; target = open (**1:1**); cancel unfilled side; needs **~30 pips** one-way to stop (15+15). Confirm broker rollover time.
- **Carry:** long high-yield / short low-yield when differential **widening** (months). Example math uses 4.0%→4.25% etc. — not a day-trade.
- Aspirational compounding (e.g. **7%/month → 125%/year**) is illustration, not a guarantee. Prefer large R over scalping (spread tax).

**Discretionary vs mechanical:** Mix. FX-Ed / flag % / Round Trip / Boomerang are codeable; Fib confluence is discretionary.

**Tick/L2 vs OHLC:** OHLC + ATR. Carry needs swap, not L2.

**Hype:** Anti-hype book. Ignore “7% every month” compounding table as a live target.

**MT5-portable:** Strong. Boomerang needs correct **17:00 ET** vs MT5 server. Round Trip pip recipe must become ATR on gold/BTC.

**Aegis mapping:**
| Piece | Status | Quality |
|-------|--------|---------|
| Squeeze (BB width vs MA) | **Partial** (`sig_bb_squeeze_breakout`, `sig_inside_bar_break`) | Medium (not 20-EMA+ATR+triangle) |
| Trend pullback / book_optimal Fib spirit | **Partial** (`trend_pullback`, `book_optimal`) | Low–medium (EMA+RSI, not 38.2/50/61.8) |
| FX-Ed daily 10EMA + 0.5 ATR trail | **Absent** (`ponsi_fxed` still listed as unwired in older digest) | — |
| Flag 10%/25% | **Absent** | — |
| Round Trip / Boomerang | **Absent** | — |
| `hw_range` | **Implemented** but **not Ponsi** (BB+RSI range scalp; Ponsi warns tiny scalps lose to spread) | Different thesis |

**P1:** `ponsi_fxed` daily. **P2:** squeeze+triangle, flag %, Boomerang as session module. **P3:** 10-pip scalp culture.

---

## 4. Damir — *Trade the Price Action*

**Thesis:** H4 price action + Fib + candles; daily **200 EMA** confirmation only. Few trades/month. Patience. No other indicators.

**Actionable rules:**
- TF: **H4 zoomed out**; broker charts should use **NY close** (or prep on a NY-close demo).
- Trend = confirmed **HH/HL** or **LH/LL** of **same amplitude** (ignore nested small waves). Change only after last HL/LH **breach + correction + impulsive confirmation** of new HH/LL. Spike through without confirmation ≠ trend change.
- Daily: uptrend only if price **above 200 EMA**; downtrend **below**.
- Pullback Fib **50 → 61.8 → 78.2** (**skip 38.2** — “not a complete correction”). Confluence with S/R / trendline strongest.
- Enter only after **completed** reversal candle at the Fib: hammer, engulfing, morning/evening star, piercing/dark cloud, equal-size two-candle extreme, three-candle middle-high.
- SL = pattern extreme; conservative TP = **correction origin**; require **reward > risk** or skip; trail only **confirmed** pivots (not unconfirmed wiggles).
- Optional aggressive TP: trendline from correction start to prior HH/LL, extended.
- Worked examples (illustrative, not stats): 30R/100+R, 75/265, 90/440, 110/420, 130/365, 150/1400 pips.

**Discretionary vs mechanical:** Discretionary labeling of swings/candles; rules are strict once labeled.

**Tick/L2 vs OHLC:** OHLC candles. NY-close daily 200 EMA matters on MT5.

**Hype:** Back-matter “200 pips/week,” “1000 pips/month,” “50 pips a day” — **sibling-book marketing**, not in the system chapter.

**MT5-portable:** Yes if candle patterns are strictly OHLC-defined and H4+D1 200 EMA exist.

**Aegis mapping:**
| Piece | Status | Quality |
|-------|--------|---------|
| H4 Fib 50/61.8/78.2 + D1 EMA200 + R>R | **Absent** as dedicated algo | — |
| Generic HTF EMA side | **Partial** (`_htf_trend`, `book_optimal`) | Low |

**P1:** `damir_h4_fib` if candle rules are coded without discretion. **P3:** pips-per-week marketing.

---

## 5. Brown — *High & Low Risk Strategies*

**Thesis:** Indicator framework on **higher TFs** (Daily preferred) + four risk modes. Realistic **~2–6%/month**; management > entry; no holy grail. Broker stats: **~75%** losers; **~65%** pick direction but fail on management. Skilled WR **30–70%** can still profit. **ATR(10)** as vol context (EURUSD daily ~**75 pips** in late 2023).

**Actionable rules — signals (closed bar → next open):**
- MAs: **50 EMA, 100 EMA, 240 LWMA** stack = trend; pullback to 50; optional trail halfway 50–100.
- BB **20/2** (and **80/3** mean-revert to mid). Prefer prior touch of outer band; optional: signal close still on “correct” side of mid.
- **QMP Filter** = QQE + MACD Platinum sync dots. Settings: MACD **12/26/9 zero-lag**; QQE **1,8,3** or **10,14,2**. Dots only on **closed** bar (no repaint). Alternate colors only.
- MACD Platinum: generally buy below 0, sell above 0 (~**95%** of his trades).
- QQE: 50 mid; optional **35 / 65** OB/OS.
- Personal labels: **Q12** (1+8+3), **Q26** (10+14+2), BB80, OB/OS.
- Bonus: QQE **1,8,3** trendline break from 65→35 or 35→65.
- Traditional SL: **0.5–2%**; ATR **×1.5** example (80 ATR → 120 pip SL, 2×ATR TP). Industry standard **0.5–2%**.
- Closed-bar manage only (Daily = once per 24h). Partial → overall BE math (half off +30, SL −30 on rest = flat).

**Four risk modes:**
| Mode | Stops | Size | Live? |
|------|-------|------|-------|
| Traditional | Yes | Fixed % | **Default** |
| Loss recovery | Yes **or** no | Fib **1,3,5,8,13…** after losses; recover then leave base | **Cage only** |
| Hedging | Often no | Lock loss, release with larger bias | **Reject live** |
| DCA | No | Same-dir grid → BE | **Highest ruin — reject live** |

His own busy template: Q12/Q26/OBOS at **constant** 0.02 lots **no SL** + hedge; BB80 and hidden-div use **1,3,5,8**. That is **Smirnov-style no-stop recovery** in spirit — **not live MM**.

**Discretionary vs mechanical:** Indicators are mechanical; which filter + hedge/DCA is discretionary.

**Tick/L2 vs OHLC:** OHLC. QMP/QQE are closed-source JAGfx — reimplement from MACD/RSI-like formulas, do not assume identical dots.

**Hype:** Anti-Instagram; 20%/month → $56M table is explicitly **not going to happen**. Prop-firm 2%/month average is anecdote.

**MT5-portable:** Traditional path yes. Hedge/DCA need hedging accounts (not US FIFO/netting).

**Aegis mapping:**
| Piece | Status | Quality |
|-------|--------|---------|
| Traditional ≤2% + ATR SL | **Implemented** (`high_risk_mode: traditional`, `hw_range` ATR SL) | High |
| `brown_recovery` Fib 1,3,5,8 | **Implemented** in `high_risk.py` **with stops + cage** (max 3 steps, ≤5%, 4-loss halt, 50% floor) | Medium (book allows no-stop; Aegis requires SL) |
| `brown_dca_size` | **Implemented** as **next-trade size-up with SL**, not a no-stop grid | Low vs book (intentionally safer) |
| QMP/QQE/Q12/Q26 | **Absent** | — |
| Hedge / no-stop DCA | **Absent** as live (correct) | — |

**P0:** Traditional + cage. **P2:** closed-bar QMP-like filter if formulas are open. **P3:** no-stop hedge/DCA as live MM.

---

## 6. Fuller — *Pyramiding*

**Thesis:** Scale into **winners** so total risk never exceeds predefined **1R**. Only in strong trends / strong intra-day moves. Never add in range/chop.

**Actionable rules:**
- **Stupid:** add without trailing → more risk. **Never.**
- **Smart:** predetermined add levels + trail all stops so aggregate risk **≤ 1R**.
- Decide **before entry** whether this trade may pyramid.
- Worked EURUSD short: entry **1.2550**, SL **1.2650**, 1R=**$200** (20k / 2 mini); adds at **+100** and **+200 pips**; after 2nd add net risk **≈ 0R**, potential **~1:6** to **1.2250**. Prefer full-position **1:2 / 1:3** **or** pyramid in — **do not scale out** as policy.
- Conditions “don’t happen extremely often” (May 2012 majors cited).

**Discretionary vs mechanical:** Add distances can be mechanical; “strong trend” is discretionary (Aegis uses ADX gate).

**Tick/L2 vs OHLC:** OHLC.

**Hype:** “Trade with the market’s money” is valid **only** with unified trail. Not a WR claim.

**MT5-portable:** Yes (modify SL on all tickets / net position).

**Aegis mapping:**
| Piece | Status | Quality |
|-------|--------|---------|
| Add to winners, unified SL, ≤1R | **Implemented** (`pyramid.py`, `should_pyramid`, `fuller_pyramid`) | High |
| +100/+200 pip example | **Partial** (adds at **+N·R**, ADX min, max 2 adds) | Medium |
| “Never scale out” | **Partial** (bot still has TP/partials elsewhere) | — |

**P0:** Keep pyramid **winners-only** behind `pyramid_enabled`. Do not confuse with Thomas 10R hold.

---

## 7. Thomas — *The 10XROI Trading System*

**Thesis:** Small clear stop + fixed **~10×** reward → can win with low WR. D1 context → H1 entry. Explicitly: **no holy grail**. FXCM-era: winners had **larger wins than losses**.

**Actionable rules:**
- **Push-pull:** 1–2 strong push candles; pull toward prior close/open (within ~**9 pips** OK if S/R explains shortfall); enter near pullback extreme on **H1** with clear S/R invalidation.
- Context: parabolic, breakouts, flags, S/R, candles hugging **SMA(3)** without piercing **SMA(10)**. Weak momentum = candles pierce slow MA → skip.
- Prefer shorts (faster). London or NY session for H1 entry. Alerts night before **22:00–00:00 GMT** / **17:00–19:00 US**.
- Frequency **~1–4 setups/month** if job-trading.
- Stop **~15–40 pips** typical (**~25 avg** in $500 example); include spread. TP = **10R**; if stop **~40** on a small-range pair (EURUSD), use **8R**. Measure move from **close**, not wick.
- BE only **after first H1 pullback resumes** (not immediately). Around **8R** he may trail / exit on weekly S/R + parabolic.
- Risk **1–2%** (beginners **1%**). Hypothetical: 50% WR + 10R → +134% / 20 trades at 1%; compounding **50% of win** on next trade is **fantasy tables** (3829% / 42975%). Author says test **25% / 10% / 5%** of prior win; **two accounts** (conservative vs speculative).
- “Lose **70%** still profit” **if** winners are full 10R and costs ignored.
- Gold example: **650 points** risk, 10R, “24,000 points” fall — anecdote.

**Discretionary vs mechanical:** Pattern + context is visual/discretionary; 10R + delayed BE is mechanical.

**Tick/L2 vs OHLC:** OHLC D1/H1. Designed for **MT4/MT5**.

**Hype:** Compounding thousands of % and “lose 70% still rich” assume every winner hits full 10R. **Reject as live MM.** Keep 1–2% + 10R research.

**MT5-portable:** Yes. `thomas_10r` currently uses EMA pullback + ATR stop, **not** push-pull candle geometry.

**Aegis mapping:**
| Piece | Status | Quality |
|-------|--------|---------|
| ~10R target + trend pullback | **Implemented** (`sig_thomas_10r`, `thomas_rr` default 10) | Medium (missing push-pull / SMA3-10 hug / delayed BE) |
| `thomas_compound` / `thomas_growth` | **Implemented** in `high_risk.py` **caged** | Low vs book tables (intentional) |
| Separate from Fuller pyramid | **Correct** (hold for 10R, don’t add) | High |

**P1:** Real push-pull D1→H1 detector. **P3:** uncapped compound / 100% WR.

---

## 8. Windsor — *The Holy Grail Forex Trading System*

**Thesis:** Cautionary autobiography. Mechanical GBPUSD “Grail” + reckless MM turned **£10k → ~£100k+** then crashed (**~48–50%+ DD**, later **~60%** from Nov highs). Million target missed. Overconfidence + insufficient regime coverage.

**Exact Grail (Appendix 1):**
1. At **08:00 UK**, GBPUSD price P.
2. BuyStop **P+40** / SellStop **P−40**.
3. SL **80**, TP **240**, trail **60**.
4. OCO: one fill cancels the other.
5. Flat by **18:00 UK**.

**Tweaks they actually used:** BE-ish at **+1 pip** (stop to −77); hide orders until within **10 pips**; shorts flatten **15:59 UK**; TP **280**; SL **75**; longs flatten **18:59**.

**Fatal MM (reject live):**
- Start **£10/pip** on £10k (~1 standard lot); ratchet **£/pip** to next £k high; **never cut size on DD**.
- From Jan 2006: **+£1/pip per losing day**, −£1 on winning day in DD, floor = last high’s base. Later **±£2**. Dec 2006: **£118/pip** on **~£54k** remaining → **>20:1** leverage.
- Withdraw “safe” **25%** then trade main account as if cash still there (**double leverage**) + income account same system.
- Celebrating **50–65% DD** as “OK because MM is clever.”

**Live lesson:** Worked in trending cable; died in doji/range months (20-day range **<70** then recovered **>100**). Author: test data did not cover all regimes. Similar spirit to Fabris (price+time) but **fixed 2005 params**.

**Discretionary vs mechanical:** **100% mechanical** entries. MM was the discretionary/reckless part.

**Tick/L2 vs OHLC:** Time + price. Tick data used in their tests; live is stop orders.

**Hype:** Title + “almost no chance of losing month” + 20%/month / 35% DD backtest. Diary later admits curve-fit and arrogance.

**MT5-portable:** Breakout template is codeable. **Never** ship loss-escalation.

**Aegis mapping:**
| Piece | Status | Quality |
|-------|--------|---------|
| `windsor_escalate` | **Implemented** **caged** (reset after max steps unless `allow_unsafe_high_risk`) | High as a **reject-path** |
| 08:00 ±40 / SL80 / TP240 / trail60 / 18:00 | **Absent** as `windsor_grail` signal | — |
| Regime kill-switch | **Partial** (ADX/session on other algos, not this template) | — |

**P2:** Research-only London breakout with **% risk**, not £/pip ratchet. **P3:** loss-escalation, double-leverage withdrawals, 50% DD OK.

---

## 9. Afshari — *The Ultimate Forex… 92% Winning Trades*

**Thesis (sold):** Multi-signal confluence → “92%.” **Reality:** Discretionary checklist soup. Ch.6 admits no holy-grail indicator — contradicts the title.

**Actionable fragments:**
- Lots: “**3–5% of balance** in a single trade is safe” — **reject** vs Silvani/DraKoln/Brown 0.5–2%.
- Leverage cheerleading if “system is reliable.”
- Consolidation **15–25 pips** for hours; local max/min **10–25 pips**.
- Session table (Sydney 21:00 GMT … NY close 21:00) but he also says trade whenever confluence exists.
- Patterns: triangle “**0.8+** probable”; H&S “**>80%**” if right shoulder overlaps left **>80%**; sandwich 4–8 bars.
- Correlation: |ρ| **0.75–0.85** on **1H / 300 periods**; trade **lagging** pair; abort if no setup in **3 hours**.
- Abandoned Baby + **EMA(5)** on D/W: dwarf bilateral pin; close-to-EMA distance **≥ previous bar range**; SL local ext; TP nearest S/R. Claims **>95%** — **do not use**.
- Sentiment: use **Δ%** over recent hours (e.g. 3%), not absolute Oanda %.
- News stats (his research): **50%** no real reaction; **25%** impulse then obeys TA; **25%** impulse **against** TA; bad spike **15–50 pips**; at tight S/R spike **≤10–15**. SL **10–15** beyond HH/LL, **max 30–35** from entry; R:R **≥2**; TP 2/3 of the way to S/R. Skip news if novice / **$100–$200** account.
- Pair SL tables: AUD/NZD/EURGBP **15–20**; EURUSD/JPY/CHF/CAD **20–25**; GBPUSD **25–30**; EUR/AUD, GBP/AUD, GBPJPY **30–35**. Skip if SL would be **>35**.
- Open risk **≤3%** ( **5%** if “perfect” / “optimal trading”).
- **Probability theater:** 1 signal ~70% → 2→82% → 3→92% via bogus `(0.3/0.7)³`. **Do not use for sizing.** Demo **2–3 months** then “70% WR” to go live — unsourced.

**Discretionary vs mechanical:** Discretionary. Correlation lag + R:R gate are the only crisp bits.

**Tick/L2 vs OHLC:** OHLC + broker sentiment/volume (not true L2).

**Hype:** Title **92%**, “95% probable correlation,” “99% double correlation,” “unbeatable.” **Reject.**

**MT5-portable:** Process only (SL+TP first, R:R≥2, MTF, journal).

**Aegis mapping:**
| Piece | Status | Quality |
|-------|--------|---------|
| min_rr / cost / session | **Implemented** (generic) | Process only |
| 92% confluence math | **Absent** (correct) | — |
| Correlation-lag engine | **Absent** | — |

**P3:** 92%/95%/99% WR, confidence→size-up, 3–5% “safe” lots.

---

## 10. DraKoln — *Winning the Trading Game*

**Thesis:** ~**90–95%** fail because they bring stock buy-hold/DCA into leveraged FX/futures. Pillars = **money management + TA + risk management**. No holy grail. Unsourced 95% = industry folklore (treat as warning, not a measured stat).

**Actionable rules:**
- CTA-style: **max ~2%** loss (size of holdings); **never risk 1 to make <2**.
- **≤⅓ account in one market.**
- **25%** equity drop → halt and reevaluate; **50%** → full halt / shut program.
- First trades: small size (book: first **10 trades 1–2 contracts** in futures context).
- FX “gear” ~**3×** cash vs margin; futures **20–50×**; retail FX up to **400:1** turns 2–3% moves into account-killing swings — so **don’t DCA** into leveraged losers (opposite of stocks).
- Market filter: ATR volatility, liquidity/OI, affordable margins.
- Liverpool TA: (1) **50DMA** direction — wait **3 successive days** after cross + candle; **no trade if sideways** on the 50; (2) RSI using **market’s own extremes**, not fixed 30/70; (3) horizontal S/R (+ Fib, BB).
- Micro: S/R break sustained **48–72h**; ATR stop often **1.5×** (**0.5–2×** by vol); price vs **9EMA / 20 / 50 ≥2 days**; candles confirm.
- If thesis fails in **2–3 days** → exit.
- CTA survey anecdote: **6/10** losers, **2** scratch, **2** pay for all — **~40%** accuracy can still work. **Do not** read as 100% WR.
- Options-as-hard-stop / “never risk more than premium” — **not** a no-SL FX grid.

**Discretionary vs mechanical:** Process book; Liverpool checklist is semi-discretionary.

**Tick/L2 vs OHLC:** OHLC + ATR. Options hedges are not MT5 spot.

**Hype:** 95% title. Anti-holy-grail otherwise.

**MT5-portable:** Risk halts, ATR stops, regime gate, journal — yes. Options overlay — no.

**Aegis mapping:**
| Piece | Status | Quality |
|-------|--------|---------|
| ≤2% traditional, equity floor 50%, consec-loss halt | **Implemented** (`solved_policy_config`, `HighRiskController`) | High |
| 25% monthly-style halt | **Partial** (`max_daily_loss_percent` / DD caps, not DraKoln’s 25% reevaluate) | Medium |
| 50DMA + 3-day wait | **Absent** | — |
| ATR 1.5× stops | **Partial** (configurable `atr_sl_mult`) | Medium |
| Anti-DCA in leverage | **Aligned** (Brown DCA caged / unsafe flag) | High |

**P0:** Keep 2% + floors. **P2:** 50DMA regime gate. **P3:** options-as-only-stop, stock DCA in FX.

---

## 11. Aziz — *How to Day Trade for a Living*

**Thesis:** Day trading is a profession. Edge = few mastered setups + **≤2%** risk + discipline. Trade catalyst-driven **Stocks in Play**, not hope. He states **~30% of trades lose** and he stays profitable via R:R — **not** 100% WR.

**Actionable rules:**
- Max **2%** account risk/trade (often **1%**). Min **2:1** R:R. Stop at a **real technical** level (not a fake tight stop to force 2:1).
- US PDT **$25,000** floor (4 day-trades / 5 days). Start **100 shares**.
- Session: **9:30–11:30 ET** focus; new traders skip first **5 minutes** (9:30–9:35); he later uses **1-minute ORB**.
- Gappers: **>2%** premarket + news catalyst. Low-float **<$10** → Bull Flag; **$10–$100** → VWAP/S&R; avoid expensive mega-caps for retail size.
- **ORB:** opening range (1m or 5m) **must be < daily ATR**; break → next S/R or 5m new low/high exit. VWAP-side invalidation in examples.
- **VWAP:** most important intraday indicator; stop related to VWAP reclaim/reject (MOH example: short below VWAP, stop above VWAP, **1:3**).
- PlayBook: ABCD (stop < C; half at D → BE; rest on 5m new low), Bull Flag, Bottom/Top Reversal, MA trend, VWAP, Horizontal S/R, Red↔Green, ORB. Shared: technical stops, **no average-down**, partials → BE → trail.
- AAL anecdote: no-stop mindless trade **$25k** loss vs **$1k** planned — anti-hero lesson.
- Amaranth / Hunter: averaging down with “bigger account” still blew up — **reject no-stop recovery**.

**Discretionary vs mechanical:** Named setups + hard risk math; stock selection is discretionary (float, Level 2, chatroom).

**Tick/L2 vs OHLC:** Book uses **Level 2**, hotkeys, float, tape. FX MT5: **OHLC + VWAP/ORB proxies only**.

**Hype:** Anti-get-rich. Tiny accounts cannot fund big daily income.

**MT5-portable:** Risk algebra, ORB/VWAP/S&R/flag, session gates — yes. Drop equity L2, PDT, chatroom alpha. FX “open” ≠ NYSE 9:30; map to **London OR** or session VWAP.

**Aegis mapping:**
| Piece | Status | Quality |
|-------|--------|---------|
| `aziz_orb` VWAP-side stop, min 2:1 | **Implemented** | Medium (FX session OR, not 9:30 NYSE; no float/L2) |
| `aziz_vwap` reclaim/reject ≥2:1 | **Implemented** | Medium |
| ABCD / bull flag / red-green | **Absent** | — |
| No average-down | **Aligned** (Fuller pyramid is winners-only) | High |

**P0:** Keep `aziz_orb` / `aziz_vwap` as FX-adapted, not US-equity clones. **P2:** ABCD on FX H1 if strictly OHLC.

---

## 12. Steidlmayer / Hawkins — *Steidlmayer on Markets*

**Thesis:** Markets are auctions. **Price + Time = Value**. Market Profile shows acceptance (horizontal) vs rejection (vertical). Diagnose *present* conditions — do not predict like classic TA. No holy grail; capital safety first.

**Actionable rules:**
- **TPO** = 30-minute letter. **Initial Balance (IB)** = **first hour** (first two 30m periods). Stocks example: **9:30–10:30 ET**.
- **Value area ≈ 68%** (first SD of the bell curve / volume). POC = widest TPO / volume node.
- **Initiating** vs **responsive** vs prior day’s value area: trade **with** initiative away from value if volume confirms; fade failed extensions (responsive).
- **Day types (from IB):**
  - Nontrend: little extension beyond IB; small range.
  - Normal: long-term ~**10–20%** of activity; extension ~**50%** of IB.
  - Normal variation: ~**20–40%**; expansion ~**2× IB**.
  - Trend: ~**40–60%**; small IB; close within **~10%** of extreme; directional half-hours; single prints; **often exit by close** (next day often not a good “go-with”).
  - Neutral: both-side extensions, close mid; **symmetric** ticks above/below IB. Running-profile neutral: skewed, close near extreme → possible trend change.
- Extremes / tails: **≥2 TPOs** of single prints, **not** last period, **not** a single tick.
- Four steps of activity + “internal time clock” (wide-TPO count thresholds — proprietary Capital Flow numbers; do not cargo-cult 11/22/40 without re-estimation).
- Size by opportunity quality; trend days go-with.

**Discretionary vs mechanical:** Day-type classification can be mechanical from IB width vs day range; trade management is structural.

**Tick/L2 vs OHLC:** Profile is **time-sliced OHLC** (30m TPOs), not L2. True CBOT LDB/OFI not on retail FX. Volume on FX is tick volume.

**Hype:** None of the 100% WR kind. Conceptual / professional.

**MT5-portable:** Session Profile / IB / day-type from M30. FX session choice (London vs NY) must be explicit. `steidl_ib_*` already approximates.

**Aegis mapping:**
| Piece | Status | Quality |
|-------|--------|---------|
| `steidl_ib_break` go-with, skip wide IB, prefer initiating vs prior VA | **Implemented** | Medium (no TPO letters, no 5 day-types, TP ≈ 1× IB) |
| `steidl_ib_fade` narrow IB | **Implemented** | Medium (heuristic, not full neutral-day) |
| Full TPO / VA 68% / tails | **Partial** (profile features exist; not full Matrix) | Low–medium |

**P1:** Day-type state machine (nontrend skip, trend go-with, fade only narrow/neutral). **P3:** pretending tick-volume Profile is pit LDB.

---

## Combined Aegis / MT5 policy

**Keep / ship (P0):**
- `fabris_ntz` with GMT + pip band **[10, 30]** on EURUSD (or ATR-calibrated elsewhere).
- `hw_range` as **measured** range engine — **not** a book 100% WR; tiny ATR TPs still lose after costs (Ponsi/Tharp).
- `aziz_orb` / `aziz_vwap` as FX session proxies, **≥2:1**, no average-down.
- Fuller `pyramid.py` winners-only, aggregate **≤1R**.
- `high_risk.py` **cage**: traditional ≤2%, max 3 Fib/escalate steps, ≤5% cap, 4-loss halt, 50% floor, **stops required**. `allow_unsafe_high_risk` lab only.

**Next (P1):**
- True Thomas **push-pull** D1→H1 (not just EMA+RSI `thomas_10r`).
- Ponsi **FX-Ed** daily 10-EMA + **0.5 ATR** trail.
- Damir H4 Fib **50/61.8/78.2** + D1 200 EMA + R>R + OHLC candles.
- Steidlmayer **day-type** gate on IB.
- Silvani **4h pivot** as a filter, not a signal.

**Research (P2):**
- Ponsi squeeze/flag/Boomerang; Windsor **08:00±40** as a **test subject** with % risk; Aziz ABCD; Brown QMP if formulas are reconstructed.

**Reject live (P3):**
- **Windsor** stake ratchet / double-leverage “income” account.
- **Brown/Smirnov-style** no-stop recovery, hedge-lock, DCA grids (even if Brown’s traditional path is fine).
- **Afshari** 92% confluence math and 3–5% “safe” lots.
- **Thomas** compounding fantasy / “lose 70% still print thousands of %.”
- Any **100% WR** claim. Aziz himself: ~30% losers. DraKoln CTA: ~40% accuracy. Brown: 30–70% WR. Fabris: no infallible method. Windsor: Grail was **not** 100% winning.

**Disagreements (make configurable, don’t pick a religion):**
- Damir skips Fib **38.2**; Ponsi uses it. Config: `fib_levels`.
- Fuller: don’t scale out; Thomas/Aziz: partials then runner. Config: `scale_out` vs `pyramid_enabled` (mutually exclusive on one ticket).
- Brown higher-TF indicators vs Fabris/Windsor time-box vs Aziz US-equity ORB. Separate `signal_mode`s; ensemble only with `ensemble_min_votes` and costs.

**MT5 demo note:** `config_mt5_demo_eurusd.yaml` is **EURUSD `hw_range`**, small size — not Fabris NTZ and not a 100% WR engine. Porting Fabris/Aziz/Thomas to MT5 is a **clock + cost + halt** problem, not a new holy grail.
