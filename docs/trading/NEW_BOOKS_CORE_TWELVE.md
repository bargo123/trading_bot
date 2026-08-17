# Core twelve — Aegis digest (Aug 2026)

Processed from full cleaned extracts in `docs/trading/books/`. Chunked reads of every listed file: TOC, all chapters that contain numeric/actionable rules, plus pattern scans for leftover numbers. No invented 100% win rates. No backtest statistics that are not in the sources.

**Aegis already has:** `RiskEngine` (per-trade % + daily/total DD halt), Donchian 20/55 + ATR, BB+RSI range (`aegis_range_hw`), bakeoff catalog, cost-adjusted R in backtest (post-audit). **Still incomplete vs these books:** Davey walk-forward / incubation / frozen holdout; Aronson data-mining / permutation tests.

Priority: **P0** blocks honest promotion; **P1** next code; **P2** useful after P0/P1; **P3** process or needs data Aegis does not have.

---

## 1. Kevin J. Davey — *Building Winning Algorithmic Trading Systems* (2014)

- **Filename:** `building-winning-algorithmic-trading-systems-website-a-trader-s-journey-from-dat.md`
- **READ_COMPLETE:** YES (23 sections; process chapters 5–17 and live-monitoring 20–24 read in 10-page chunks; contest memoir used only for numbered caution, not as a system)
- **Author / title:** Kevin J. Davey — *Building Winning Algorithmic Trading Systems, + Website: A Trader’s Journey from Data Mining to Monte Carlo Simulation to Live Trading*
- **Thesis:** Mechanical systems can work, but naive full-history optimization is a lie. Develop on limited data, walk-forward, Monte Carlo, incubate 3–6 months on unseen live data, then size. Most candidates fail. Contest 100%+ years with 75% DD are not a living-account template.

**Actionable rules with numbers:**
- Treat any result that did not happen in *your* account as hypothetical.
- Four result types, in increasing honesty: historical backtest → out-of-sample (typically **10–20%** of data reserved) → walk-forward (stitched OOS windows) → real-time.
- Do not analyze optimized full-sample reports. Prefer walk-forward or live.
- Data: **5–10 years**; **30–100 trades per rule**. Four rules ⇒ **120–400** trades. Intraday: 10 years preferred, 5 years if electronic history is short.
- Limited testing: use **1–2 years** of random (not crisis-only) data; leave the rest untouched.
- Entry screen (no costs): **>50%** WR vs random; Davey finds **52–60%** achievable for some entries. Trend-following WR is often lower; then use average $ / trade.
- Optimization robustness: want **≥70%** of parameter iterations profitable on the limited set; **30–70%** is “maybe add one filter”; **<30%** is scrap (or reverse only after **double** costs).
- Monkey tests: **8,000** random runs; strategy should beat monkey on net profit and max DD in **~90%** of cases (~7,200/8,000). Match trade count, long/short mix, bars in trade.
- Walk-forward: in-sample enough for **~25–50 trades per input** (many cite **30**); out period **10–50%** of in period. Choose in/out *before* looking. Nested WFA: leave **~3 years** untouched if you must pick among in/out pairs.
- Fitness: net profit most used; return/account = net / (max DD + margin). Unanchored WFA preferred so old data does not dominate.
- Costs in optimizer always: example **$25** round-turn flips which parameter wins. Futures: **~$5**/RT commission; **1–2 ticks** slippage market/stop, **0** on true limits; mixed orders **1.5–2.0 ticks**.
- Preliminary gates: annual net **$5k–$10k+ per contract**; PF **>1.0** (hard to survive **<1.5**); average trade **≥$50**/contract after costs; Tharp expectancy **>0.1** ($0.10 per $1 risked).
- Monte Carlo: **2,500** equity-curve runs, one year, one contract. Risk of ruin **<10%** (0–1% better). Return/max DD **>2.0**.
- Incubation: **3–6 months**, check monthly, usually no real money. Avoid: fills at bar high/low, limit fills on touch only (**0–30%** real fill rate), Renko/Kase/P&F history bars, same-bar entry+exit.
- Diversification: different market / bar / session / entry / exit. Daily-return correlation **≪ 1.0** (check full history and **6–12 month** windows). Combined R of equity curve should rise (euro day+night example **0.937 / 0.9745 → 0.9817**). Combined ret/DD and P(profit in 1 year) should beat parts.
- Position sizing: start **1 contract**. Fixed fraction `N = floor(x * Equity / LargestLoss)`. Many say **x ≤ 0.02**; Davey picks **x** from MC subject to DD and ruin. Example euro: Vince optimal **x = 0.32** implied **67.4%** median max DD and **21%** ruin — rejected; he accepted **45%** DD / **10%** ruin ⇒ **x = 0.175**.
- Do not size a losing core into a winner. Aggressive size can turn a winner into a loser. Martingale: one sequence often +$1; repeated with limits → ruin.
- Live: skip adding to losers (contest coffee example). Systems die; do not put all eggs in one basket.
- FX: broker A data ≠ broker B; he uses **market orders only** and adds spread. Bid-only charts create phantom limit/stop fills on winners.

**Discretionary vs mechanical:** 100% mechanical is the book’s target. Discretionary pieces can be tested if they reduce to rules (MA, stops). Intuition itself is not walk-forwardable.

**Data needs:** Multi-year OHLC; consistent session (pit vs electronic); back-adjusted continuous futures **without** price ratios/% on adjusted prices; FX bid+ask or market-order assumption; commissions + slippage in the fitness.

**Hype:** World Cup **148% / 107% / 112%** and **75%** contest DD are *contest* goals, not living-account advice. “90–95% WR” scale-trading claims: he says WR is meaningless; scale trading often **10–20%** return with **≥20%** DD. **90%+** of vended systems are junk.

**MT5-portable:** High. WFA, MC, incubation, cost-in-optimizer, monkey tests, fixed-fraction size all map to Python/MT5. Euro day/night EasyLanguage in appendices is futures-session specific — port the *process*, not the 2005–2013 euro parameters.

**Aegis mapping quality:** **Rough / P0.** Bakeoff and cost-adjusted R exist; frozen holdout, walk-forward runner, incubation clock, monkey/MC promotion, and “burn the data once” still incomplete (same gap as `AEGIS_BOOK_CODE_AUDIT.md`).

**Priority:** **P0**

---

## 2. David Aronson — *Evidence-Based Technical Analysis* (2007/2011 Wiley)

- **Filename:** `evidence-based-technical-analysis-applying-the-scientific-method-and-statistical.md`
- **READ_COMPLETE:** YES for claims and case study (intro, Ch.1–2, 6–9). Statistical-method chapters (bootstrap algebra, 6,402-rule construction tables) read in chunks; every numeric result in Ch.9 captured. Not every philosophy anecdote.
- **Author / title:** David R. Aronson — *Evidence-Based Technical Analysis: Applying the Scientific Method and Statistical Inference to Trading Signals*
- **Thesis:** Subjective TA is untestable (empty claims). Objective TA can still fool you via luck and **data-mining bias**. Use rules that computers can backtest, then White’s Reality Check or Monte Carlo permutation. His S&P 500 mine of **6,402** binary rules found **none** significant at **0.05**.

**Actionable rules with numbers:**
- Restrict research to **objective** binary (or otherwise unambiguous) rules.
- Reject subjective methods that cannot be coded: hand trendlines, Elliott, Gann, Magic T’s as commonly practiced.
- Historical profit is **necessary but not sufficient**.
- Data-mining: the *best of N* rules has an upward-biased observed return. Traditional t-tests ignore the search.
- Case study: **6,402** long/short rules on S&P 500, **~25 years**, detrended data. Best rule **E-12-28-10-30**: **10.25%** annualized mean on detrended data. WRC p-value **0.8164**; MCP p-value **0.8194**. Null not rejected at **α = 0.05**. Sampling distribution of the *best of 6,402 worthless rules* centered near **~11%**, not 0%.
- Bootstrap / MCP: thousands of replications (example **1,999** WRC; MCP illustrated with **~5,000** permutations).
- Academic notes he cites (not his own 100% claims): expert chartists fail to distinguish real vs random charts; some commodity/FX trend evidence; H&S on stocks ≈ random; 52-week-high relative-strength effects in some equity studies.
- Ethical bar: recommendations need a **reasonable basis** = objective evidence.

**Discretionary vs mechanical:** Mechanical only for knowledge claims. Discretion is religion unless reformulated as a testable algorithm (he notes one objectified Elliott attempt).

**Data needs:** Long, clean, no look-ahead; detrending/benchmarking for position bias (appendix: detrending ≡ benchmark for position bias); full log of how many rules were searched.

**Hype:** Popular TA anecdotes and “this pattern always works” fail the discernible-difference test. **10.25%** best-of-mine is *not* an edge after multiple testing.

**MT5-portable:** The *inference layer* is portable (permutation of +1/−1 signals vs next returns). The 6,402 S&P indicator zoo is not an MT5 EURUSD playbook.

**Aegis mapping quality:** **Rough / P0.** Mechanical signals exist; no WRC/MCP, no false-discovery control, no “N rules searched” accounting. Thousands of 100% WR parameter hits in old hunts are exactly the bias this book names.

**Priority:** **P0**

---

## 3. Ernest P. Chan — *Quantitative Trading* (2008)

- **Filename:** `quantitative-trading-how-to-build-your-own-algorithmic-trading-business-2008-wil.md`
- **READ_COMPLETE:** YES (21 sections; Ch.2–7 and Kelly appendix read in chunks)
- **Author / title:** Ernest P. Chan — *Quantitative Trading: How to Build Your Own Algorithmic Trading Business*
- **Thesis:** An independent trader can run a simple, backtested, automated business. Edge = process (data hygiene, costs, Sharpe, drawdown tolerance, Kelly leverage), not a secret indicator. Examples are mostly **stock stat-arb**, not a retail FX firehose.

**Actionable rules with numbers:**
- Screen: Sharpe, drawdown depth/duration, costs, survivorship, snooping, whether it “flies under institutional radar.”
- Rule of thumb: stand-alone Sharpe **< 1** is not a main profit center; profitable **almost every month** often Sharpe **> 2**; **almost every day** often **> 3**.
- Example 5-minute BB: **2σ** entry, **1σ** exit, every 5 minutes → Sharpe **~3** without costs, **−3** after **1 bp** costs.
- Training/test threshold tweak example: **1σ** entry / **0.5σ** exit raised train Sharpe **2.9**, test **2.1** (still a snooping warning).
- Data: split/dividend adjusted; survivorship-bias free; beware H/L in strategies.
- Avoid look-ahead and data-snooping. Paper-trade before size.
- Reg T: overnight leverage **2×**, intraday **4×**. Prop can be much higher (example **$50k** equity / **$2M** intraday = **40×**) — he warns this is dangerous.
- Kelly (Gaussian, independent): **f = m / s²**. Example SPY: excess **7.231%**, σ **16.91%**, Sharpe **0.4275**, Kelly **f = 2.528**, levered compounded **13.14%** vs unlevered **g = 9.8%**. Prefer **half-Kelly** because of fat tails and estimation error.
- Geometric random walk ±**1%/minute**: you **lose ~0.5 bp/minute** (`g = m − s²/2`). Risk reduces compounded growth.
- If constrained to leverage **l**, scale all **f_i** by **l / Σ|f_i|**.
- Max compounded growth **g = r + S²/2** at Kelly leverage.
- HFT chapter: institutional; not the retail path.

**Discretionary vs mechanical:** Fully quantitative / automated. Psychology chapter is about sticking to the model, not chart art.

**Data needs:** Split/dividend-adjusted, survivorship-free stock history; futures/FX sources listed but expertise is stocks. MATLAB/Excel backtests with costs.

**Hype:** Jacket “challenge institutions from home” is bounded by costs, leverage caps, and non-Gaussian tails. He does **not** promise 200%/year.

**MT5-portable:** Kelly, Sharpe gates, cost stress, half-Kelly, paper-vs-live divergence — yes. Dollar-neutral stock pairs / cointegration — **no** on single-pair EURUSD MT5 without a second leg.

**Aegis mapping quality:** **Partial / P1.** Costs and bakeoff exist; `chan_bb_scalp` is a single-series fade, not 2008 stat-arb. No Kelly allocator, no half-Kelly, no rolling Sharpe/DD halt vs his formulas.

**Priority:** **P1** (P0 if we keep calling a BB fade “Chan”)

---

## 4. Robert Carver — *Systematic Trading* (2015)

- **Filename:** `systematic-trading-a-unique-new-method-for-designing-trading-and-investing-syste.md`
- **READ_COMPLETE:** YES (33 sections; Theory + Framework Ch.5–12 + Practice examples + vol-target tables read in chunks)
- **Author / title:** Robert Carver — *Systematic Trading: A unique new method for designing trading and investing systems*
- **Thesis:** Systematize **position and risk** even if forecasts stay discretionary. Modular framework: instruments → forecasts → combine → **volatility target** → size → portfolio. Overfitting and one-size-fits-all systems are the enemy.

**Actionable rules with numbers:**
- Three user types: asset allocator (forecast **+10** constant, “no-rule”), semi-automatic (discretionary forecast **−20…+20** + systematic stop), staunch systems (EWMAC + carry, etc.).
- Forecasts scaled so expected absolute value **~10**; **cap at ±20** (Gaussian: values **>20** ~**5%** of time). Combined forecasts also capped.
- Achievable Sharpe (his table, not a promise): single equity **~0.10**; **≥20** stocks / index **~0.20**; global **~0.25**; multi-asset static **~0.40**. Sustained SR **>1.0** rare; backtested **2–3** on one instrument is usually overfit. He uses **~25%** haircut for unrepeatable secular trends.
- Vol target: cash vol = **% target × capital**. Example **$1M × 10% = $100k/year**. Formula: set vol target **≈ expected SR** (SR **0.25** ⇒ **25%** vol). He personally used **25%**. Semi-auto: assume SR **0.20**, cap vol at **25%**. Table examples include **12% / 15% / 25% / 50%** depending on SR and risk appetite. **200%** vol is a worked *warning* example, not advice.
- Law of active management: SR scales with **√(independent bets/year)** before costs.
- **256** business days ⇒ annualized SR **~16×** daily.
- Costs decide speed: expensive instruments trade slower; some are untradeable.
- Prefer exchange-traded over OTC (CHF 2015 example).
- He trades **>40** futures with **8** rules; two rules (EWMAC + carry) **~85%** of *his* backtested performance (legal limits on disclosing the rest).
- Overfit correction: more rules/instruments ⇒ larger in-sample haircut.

**Discretionary vs mechanical:** Framework is mechanical. Forecasts may be discretionary (capped) or systematic. Stop-loss for semi-auto is systematic; do not meddle mid-trade.

**Data needs:** Daily prices minimum; vol estimates; cost/liquidity; for carry, term structure / yield. Backtest software optional if using his pre-configured system.

**Hype:** Kahneman epigraph: simple algorithms beat clever experts. No holy grail; **SR 2.0** single-name backtests are called dangerous.

**MT5-portable:** Forecast cap, vol targeting, cost-vs-speed, instrument weights — yes on FX/CFD with pip-value vol. Full 40-name futures book and carry on curve — only if MT5 universe includes those.

**Aegis mapping quality:** **Rough / P1.** ATR stops ≠ vol-targeted subsystem. No forecast **10/20** scale, no diversification multiplier, no turnover buffer.

**Priority:** **P1**

---

## 5. Alexander Elder — *The New Trading for a Living* (2014)

- **Filename:** `the-new-trading-for-a-living-psychology-discipline-trading-tools-and-systems-ris.md`
- **READ_COMPLETE:** YES (31 sections; psychology, Triple Screen/Impulse, 2%/6%, vehicles, records read in chunks)
- **Author / title:** Dr. Alexander Elder — *The New Trading for a Living*
- **Thesis:** Psychology + tactics + money management, tied by **records**. Less indicator clutter. No system removes losses. **2%** shark rule and **6%** monthly piranha rule are the safety nets.

**Actionable rules with numbers:**
- **2% Rule:** never risk more than **2%** of *trading* equity (not house/retirement) on one trade. **$30k → $600**; **$10k → $200**; **$50k → $1,000**. Pros often **0.5–1%**. Recalc from month-start equity.
- **Iron Triangle:** (A) max $ risk ≤ 2% equity; (B) $ from entry to stop; (C) **shares/contracts = A/B**, never more. If C < 1, skip.
- **6% Rule:** if month-to-date closed losses + open risk ≥ **6%** of month-start equity, **no new trades** until month-end or stops move to free risk. Example: three **2%** positions fill the budget; moving one stop to BE frees a slot.
- Pyramiding: each add is a new trade still under **2%** and **6%**.
- Comeback: cut size (example **500 → 100** shares); **+1** size step after **two** profitable weeks; drop a step after **one** losing week.
- Triple Screen: timeframes **~×5**. Trade only with the higher-TF tide; use lower-TF oscillator *against* the tide for entry. Weekly Impulse: **red = no buys**, **green = no shorts**, **blue = either**. Daily: **2-day EMA of Force Index** (needs volume). Day-trade example: **30-min** tide, **5-min** entry, **0.6%** channel, **2-bar** Force, channel containing **~95%** of prices for targets.
- Impulse: EMA slope + MACD-Histogram; auto buy-green/short-red **failed** in ranges — use as **censorship**, not a robot.
- Stops: SafeZone = multiple of average adverse penetration; wider stop ⇒ smaller size. Reward/risk example **~2:1** in silver/wheat illustrations.
- Day-trading: Massachusetts broker records — after **6 months** only **16%** of day-traders made money.
- Futures: **9/10** newcomers said to bust in months — from size, not from the contract. Gold **100 oz**, mini **20 oz**; **$50k** account cannot take **$4,075** silver risk (**0.815 × 5,000**) under 2%.
- Forex shops: **100:1** and **400:1** leverage called homicidal; CFTC proposed **10:1**. He prefers **currency futures**. Average FX-fraud victim **~$15,000** (cited journalism, not a strategy stat).
- Options: buyer needs to be right on **direction, distance, and speed** (3 rings). Writers: Delta **~0.10**, **2–3 months** to expiry sweet spot; buy back after **~50%** premium decay, by **80%** be out; if option **doubles**, cover; **10%** of writing profits to an insurance account.
- Channel systems and MACD **12-26-9** as tools, not guarantees.

**Discretionary vs mechanical:** Hybrid. Impulse/Triple Screen can be coded as gates; trade selection and “A-trade” scoring stay discretionary. Records are mandatory.

**Data needs:** OHLC + **volume** (Force Index). Multiple timeframes. Stocks/ETFs/futures; he is hostile to most retail FX CFDs.

**Hype:** Lifestyle intro vs later “boring homework.” No 100% WR. Impulse as auto-system is explicitly **rejected**.

**MT5-portable:** 2%/6% and Impulse color gates — yes. Force Index on FX is weak (no real volume). Triple Screen needs a true HTF series, not same-bar EMA.

**Aegis mapping quality:** **Partial / P1.** `RiskEngine` covers per-trade % and DD, not Elder’s **monthly 6% available-risk** ledger. `elder_impulse` proxy exists; no weekly screen, no Force Index, no SafeZone.

**Priority:** **P1** (2%/6% enforcement); Triple Screen HTF **P2**

---

## 6. Van K. Tharp — *Trade Your Way to Financial Freedom* (2006)

- **Filename:** `trade-your-way-to-financial-freedom-2006-mcgraw-hill-companies---libgen-li.md`
- **READ_COMPLETE:** YES (19 sections; objectives, expectancy, stops/exits, four sizing models read in chunks)
- **Author / title:** Van K. Tharp — *Trade Your Way to Financial Freedom*
- **Thesis:** Holy Grail is **you** (objectives, psychology, exits, position sizing), not a magic entry. Expectancy in **R**. Size answers “how much?” Entry is the least important piece.

**Actionable rules with numbers:**
- 12-step development: inventory → open mind → objectives → timeframe → study big historical moves → objectify concept → **stops + costs** → profit exits + expectancy → hunt large R → **optimize sizing** → improve → worst-case mental plan.
- Expectancy = (avg win × win% + avg loss × loss%) / |avg loss| = mean **R**. He wants this **high**; a footnote: live expectancy **≤ $0.15 per $1** may be psychology (not following the system).
- **1R** = initial stop distance in money. Position size so **1R = constant % of equity** (typical **1%**: **$100k → $1,000** risk).
- Tom Basso (quoted): own account **1–1.5%**; **2–3%** is pushing it with up to **20** markets. OPM: **<1%**. Tharp: under **3%** fine; over **3%** is “gunslinger.”
- Random-entry illustration: coin-flip entry, stop = **3×** 10-day EMA of ATR, trail same, **1%** risk, **10** markets, always in. **~38%** WR. **1 contract**: profitable on **~80%** of runs; with **1%** risk: **100%** of *those simulation runs* (not a live 100% WR).
- Reliability of that system should have been **~50%**; **~12%** extra losses from costs + having a stop.
- Models: (1) 1 unit per fixed $; (2) equal value; (3) **% risk**; (4) **% volatility**. Model 3 equalizes 1R across markets.
- Exits dominate expectancy; good systems have **3–4** exit types. Cut losses / let profits run is an **exit** axiom.
- Opportunity: more independent markets raise realized expectancy per calendar time.
- Liquidity: avoid stocks **<10,000** shares/day (1 round lot = **1%** of volume).
- Foreword performance (Mobley, not a system spec): **~40%+/year** net, **61%** 1996, **53%** 1997 — anecdote, not Aegis target.

**Discretionary vs mechanical:** Either, if expectancy and sizing are defined. Biases wreck both.

**Data needs:** Trade list in R, costs in expectancy, enough trades to see the R distribution (including rare large R).

**Hype:** Title “financial freedom” vs text: people flock to **80%** entry talks and ignore sizing. No 100% WR. Random entry + 3 ATR + 1% is a **teaching** system.

**MT5-portable:** % risk (already in `RiskEngine.size_units`), R reporting (post-audit cost-adjusted), 3 ATR trail — yes. SQN / ruin MC still thin.

**Aegis mapping quality:** **Partial / P1.** Cost-adjusted R exists post-audit; no R-multiple histogram gate, no 1% vs 3% regime, no Tharp-style opportunity count.

**Priority:** **P1**

---

## 7. Andreas F. Clenow — *Following the Trend* (2023, 2e)

- **Filename:** `following-the-trend-diversified-managed-futures-trading-wiley-trading-2023-wiley.md`
- **READ_COMPLETE:** YES (34 sections; construction, two basic strategies, risk, practicalities, caution read in chunks; year-by-year is narrative performance, not extra rules)
- **Author / title:** Andreas F. Clenow — *Following the Trend: Diversified Managed Futures Trading* (2e)
- **Thesis:** CTA trend-following is mostly **simple rules + ATR size + many markets**. Buy high/sell higher. Frequent small losses, rare large wins. Do not run this on one FX pair. **Keep it simple** (Parker/Covel forewords).

**Actionable rules with numbers:**
- Universe: liquid futures; typical CTA **~100** contracts; he starts with a liquid subset. Daily data, **properly back-adjusted**.
- Size: **contracts = floor(Equity × risk_factor / (ATR × point_value))**. Initial **risk_factor = 0.002 (20 bp)** so each position’s *theoretical* daily impact is **0.2%** of equity. Later core example **0.15%**. Gold: ATR **$10**, point **100** ⇒ **$1,000**/contract; **$1M** equity × **0.2%** = **$2,000** ⇒ **2** contracts. Round **down**.
- Size is set **at entry** and held (unless you explicitly tweak).
- Two basic models (parameters “reasonably arbitrary”): **EMA 50/100** crossover; plus a breakout variant (Donchian-style). Filters later: e.g. **200-day** MA so you do not fade the big trend.
- Costs in his tests: **$1** commission + **$1.50** exchange + volume-based slippage, conservative.
- Personality: DD **up to ~30%** and **a year+** to recover are normal at some risk settings. Notional exposure can print **>1000%** (example **1353%** gross on a date) while risk is vol-normalized — do not confuse notional with risk.
- Capital: **< $1M** for a diversified futures book is “reckless”; even **$1M** is tight because of whole contracts (half-contract problem).
- Buy-and-hold equity contrast: **~8%/year** with **55%** DD from 1976–2011 illustration — why CTAs exist as diversifiers.
- Counter-trend and term-structure chapters: optional overlays, not the core.
- Going live: do your own research; Python/Zipline mentioned; backtests lie.

**Discretionary vs mechanical:** Fully systematic. Discretion is choosing risk_factor and universe, then **do every trade**.

**Data needs:** Adjusted futures continuations, ATR, point values, FX conversion of P&L, volume for slippage. **Not** single-pair M1 Yahoo.

**Hype:** Replicates “magic” CTA boxes with simple methods. No 100% WR — **low** WR is the design. Triple-digit personal accounts with **60–70%** DD are distinguished from client-friendly risk.

**MT5-portable:** Donchian/EMA + ATR size — yes in spirit. True Clenow needs **many** futures (or a reduced FX basket with **correlation caps**). EURUSD-only Donchian is a **slice**, not the book.

**Aegis mapping quality:** **Partial / P1.** `sig_donchian55_trend` / `donch20` + ATR stops exist. Missing: **0.2% ATR risk_factor**, shared capital, point-value, sector diversification, 50/100 EMA as specified.

**Priority:** **P1**

---

## 8. Adam Grimes — *The Art and Science of Technical Analysis* (2012)

- **Filename:** `the-art-and-science-of-technical-analysis-market-structure-price-action-and-trad.md`
- **READ_COMPLETE:** YES (48 sections; Parts I–III templates, management, risk, psychology read in chunks; appendix trade table not re-scored)
- **Author / title:** Adam Grimes — *The Art and Science of Technical Analysis: Market Structure, Price Action, and Trading Strategies*
- **Thesis:** Markets are **nearly efficient**; most moves are noise. You need a **verifiable edge**. Structure (trend/range/interface) first; templates second. Simple patterns + “good psychology” do **not** print easy profits.

**Actionable rules with numbers:**
- Four trades from Wyckoff cycle: trend continuation, trend termination, range, breakout — each with different R:R and failure modes.
- Templates: failure test; pullback to S/R; LTF breakout in pullback; complex pullback; **Anti**; breakout from base; first pullback after breakout; failed breakout.
- Pullback depth rule of thumb: **~50%** of prior swing, expect **25–75%**, outliers both ways.
- Stops from **geometry**, not fear. Tight stops allow larger size but similar expectancy after costs; very tight re-entries pay the spread many times.
- Never move stop **into** more risk except two rare cases; hard cap remains **1× initial risk**.
- After **+1R**, consider BE / tighter stop. After first **2R** scale target, BE on remainder (swing style).
- Time stops if the imbalance does not pay quickly.
- Parabolic: trail under **prior day’s low** (example).
- **Do not reverse-pyramid** (1, 2, 4, 8…). Proper pyramid: largest size first, smaller adds.
- Portfolio: define **X** = % equity risked per trade. Equities: **≤ 2X–3X** in one correlated sector. Futures groups: **≤ 1.5X–2X**. Cap **total** portfolio if all stops hit the same day (avoid **50%** one-day account death).
- Gaps through stops: have a plan; equity gaps often fade; if price **presses** after a gap, dump.
- Track P&L in **R** (`PL%R`). Volatility: **20-day HV** or ATR; expect **3×** “normal” days and **10×** tails.
- Record-keeping and statistical review of *your* trades (Ch.12).

**Discretionary vs mechanical:** Discretionary **within** mechanical risk. Templates are patterns, not a single parameter set. He argues against rigid vendor systems.

**Data needs:** OHLC that can define swings; multiple TFs; for MACD/MA confirmation as in Ch.7. Tick not required for the swing templates.

**Hype:** Explicitly anti-hype. Title “art and science” ≠ easy money.

**MT5-portable:** Failure-test / failed-break and 1R geometry are portable. Swing-state engine is the work. Not an M1 firehose book.

**Aegis mapping quality:** **Rough / P1** for failed-break; **P2** for full structure engine. Generic pullback/breakout names overstate fidelity.

**Priority:** **P1** (failure test); rest **P2**

---

## 9. Jack D. Schwager — *Getting Started in Technical Analysis* (1999)

- **Filename:** `getting-started-in-technical-analysis-1999-wiley---libgen-li.md`
- **READ_COMPLETE:** YES (34 sections; tools, stops/objectives, systems testing, 82 rules, planned approach read in chunks)
- **Author / title:** Jack D. Schwager — *Getting Started in Technical Analysis*
- **Thesis:** TA is **when**, fundamentals **why**; both can work. Charts are an art that resists naive tests. Systems must be built and tested to **survive the future**, not the past. **82 rules** are empirically based opinions, not physics.

**Actionable rules with numbers (selected from Ch.16–17 and systems chapters):**
- Know the stop **before** entry. GTC stop or trusted mental stop.
- Cumulative implied risk on all opens: rough cap **25–35%** of equity (with **2%** per name this only binds at **≥13** positions).
- Diversify markets **and** systems/parameter sets if equity allows. Cut leverage in **correlated** groups (all USD shorts, all pharma, etc.).
- Size down when volatility rises; size with equity (**−20%** equity ⇒ **−20%** leverage).
- Discretionary: cut size or pause after a losing streak. **System** traders should **not** pause for mood — losing periods often precede system recovery.
- Evening routine **30–60 minutes**.
- Paper trade with the same notebook before going live.
- Segment results (long vs short, market, day vs swing). He suspects many day-trading P&Ls would shrink the day-trader population **~50%** if honestly split.
- **82 rules** (sample): distinguish major vs short-term (short-term **smaller** risk); don’t miss a major move to save a tick; no impulsive major entries; need a timing pattern; **cut losses short**; use **market** orders more than limits (his opinion); live long enough and you will be wrong about everything.
- Systems: few parameters, costs in, avoid overfitting; failure of a method has implications (don’t just ignore it).

**Discretionary vs mechanical:** Both valid if they fit personality. System trader vs discretionary have **opposite** losing-streak rules.

**Data needs:** Charts + (for systems) historical tests with costs. Software chapter is 1999-era.

**Hype:** Debunks BLASH (“buy low sell high” at new highs). Rogers vs Schwartz: no universal winner. No 100% WR.

**MT5-portable:** 2% / 25–35% open-risk, volatility size, journal fields — yes. “82 rules” are mostly gates and process, not a signal function.

**Aegis mapping quality:** **Partial / P2.** Donchian/EMA/RSI/ATR are generic proxies, not Schwager’s tested catalog. Journal exists; segmented live-vs-system compliance metrics do not.

**Priority:** **P2**

---

## 10. John J. Murphy — *Trading with Intermarket Analysis* (2012)

- **Filename:** `trading-with-intermarket-analysis-a-visual-approach-to-beating-the-financial-mar.md`
- **READ_COMPLETE:** YES (25 sections; principles, 2000/2007 case studies, business cycle/ETFs, “new normal,” conclusion recap)
- **Author / title:** John J. Murphy — *Trading with Intermarket Analysis: A Visual Approach to Beating the Financial Markets Using Exchange-Traded Funds*
- **Thesis:** Bonds, stocks, commodities, and currencies **are linked**. Chart the relationships; they **change** (deflation after 1997–98 and 2008). ETFs make the links tradable. Visual confirmation + correlation, not a single mechanical pair-trade.

**Actionable rules with numbers:**
- Four assets: stocks, bonds, commodities, currencies.
- **Dollar ⊥ commodities** (example correlation **−0.75** in much of 2011; |ρ| **~0.50** weak, **~0.75** strong).
- **Bond prices ⊥ commodities.**
- **Since 1998:** bond prices vs stocks **inverse** (old normal was often the opposite).
- **Since 2008:** stocks and commodities **more correlated**.
- Rotation at tops (more reliable than bottoms): **bonds first, stocks second, commodities third**. Yields peak first.
- Stocks lead the economy **~6–9 months**; 2000 top → recession next spring; Oct 2007 top → recession Dec; 2003/2009 recoveries lag stock bottoms by **~3 months**.
- Oil: spikes preceded many US recessions / stock peaks (1973–74, 1987, 1990, 1994, 2000, 2007). Crude often **peaks after** stocks (2008: stocks Oct 2007, oil Jul 2008).
- 2002–~10y illustration: commodities **+64%**, bonds **+23%**, US stocks **+9%**, dollar **−32%**; AUD **+101%**, euro **+50%**.
- Weaker dollar favors **foreign** stocks; stronger dollar favors **US**. EM tied to commodities.
- Sector cycle: discretionary / tech / transports / small-caps lead early expansion; **energy leadership near tops is a warning**; money then to staples / health / utilities.
- **10** sectors, **~90** industry groups; use ETFs to rotate.
- Fed QE can distort bond–stock links; 10-year yield **<1.5%** in 2012 cited as reward/risk warning for Treasuries — historical context, not a 2026 forecast.

**Discretionary vs mechanical:** Visual/discretionary with optional correlation **numbers**. Not a fully specified algo.

**Data needs:** Synchronized **DX, yields/TLT, SPX, CRB/DBC, oil, sector ETFs**, rolling correlation. Daily is enough.

**Hype:** Subtitle “beating the financial markets” vs text: relationships **regime-dependent**. No WR claims.

**MT5-portable:** Only if the account can trade the ETFs/CFDs or you ingest external series as **filters** on EURUSD. Single-pair MT5 cannot “do Murphy.”

**Aegis mapping quality:** **Absent / P3.** No intermarket feed or rolling ρ. Do not fake it with EURUSD-only.

**Priority:** **P3** (P1 later if multi-asset data exists)

---

## 11. Steve Nison — *Beyond Candlesticks* (1994)

- **Filename:** `beyond-candlesticks-new-japanese-charting-techniques-revealed-wiley-finance-1994.md`
- **READ_COMPLETE:** YES (28 sections; candle construction/patterns, disparity, 3-line break, renko, kagi, practice sessions)
- **Author / title:** Steve Nison — *Beyond Candlesticks: New Japanese Charting Techniques Revealed*
- **Thesis:** Candles are a **richer map** than bars, but **context** (trend, S/R) decides. Part 2 reveals **3-line break, renko, kagi** (price-driven, time-light) plus **disparity index**. Not standalone holy grails.

**Actionable rules with numbers:**
- Candle anatomy: real body + shadows; long white/black as support/resistance; doji = indecision (especially after a tall white in an uptrend); spinning tops; high-wave.
- Single: hammer, hanging man, shooting star.
- Dual: dark cloud, piercing, engulfing, last engulfing, harami, window (gap), two black gapping, gapping doji.
- Triple+: evening/morning star, three windows, record sessions.
- Trade only with **stops**, **R:R**, and **trend**. Where the candle appears matters more than the name. Computers need **explicit** pattern criteria (he flags the specification problem).
- Disparity index: close vs MA (dual-MA relative); golden/dead cross as Japanese MA language.
- **Three-line break:** new white/black lines from highs/lows; typical reversal after a **3-line** counter move; buy white / sell black; extra confirmation variants; “black shoe / white suit / neck” folklore patterns — encode before testing.
- **Renko:** brick size chosen in advance; trend following, lagging.
- **Kagi:** yang/yin thickness; **buy on yang, sell on yin**; shoulders/waists; multi-level breaks; three-Buddha; percentage kagi option.
- These three ignore time until a new extreme; slower than candles — used more by longer-term Japanese desks.
- Same-bar / historical brick construction can **look-ahead** if coded naively (aligns with Davey’s warning on exotic bars).

**Discretionary vs mechanical:** Candles as taught are **discretionary filters**. 3LB/renko/kagi are **more mechanical** once box/brick/reversal is fixed — still need stops.

**Data needs:** OHLC. Renko/kagi/3LB need a **stateful** transform with a frozen box size; walk-forward the box, don’t peek.

**Hype:** “Best charts in the world” is a translated Japanese boast. Nison still demands confirmation. No WR.

**MT5-portable:** Native candles yes; 3LB/renko/kagi need custom buffers. MT5 has some native Renko/Kagi in the wild — still must avoid look-ahead and test vs raw OHLC.

**Aegis mapping quality:** **Absent / P2.** No named Nison strategy. Do not treat random doji logic as this book.

**Priority:** **P2**

---

## 12. Jeremy du Plessis — *The Definitive Guide to Point and Figure* (2005)

- **Filename:** `the-definitive-guide-to-point-and-figure-2005---libgen-li.md`
- **READ_COMPLETE:** YES for construction, signals, counts, trendlines, breadth (55 sections; FTSE/NASDAQ worked examples sampled, not every chart reprint)
- **Author / title:** Jeremy du Plessis — *The Definitive Guide to Point and Figure*
- **Thesis:** P&F is the **voice of the market**: box + reversal filter noise, no time on X, no volume required. **1-box** vs **3-box** are different instruments. Counts give **targets** and R:R. Optimize box/reversal across regimes.

**Actionable rules with numbers:**
- Name charts **box × reversal** (e.g. **10×3**). Log vs arithmetic: log for long histories; stops on log charts need care.
- Construction: **1-box** (sensitive, one-step-back); **3-box** (asymmetric filter, most common); also **2-box** and **5-box**.
- End-of-day: **close-only** vs **high/low** (high/low has known problems). Intra-day vs EOD is a live debate in the book.
- Signals: double top/bottom (continuation **and** reversal); triples; triangles; catapults (3-box and 1-box); traps; shakeouts; poles; broadening; bullish/bearish pattern reversed.
- **45°** bullish support / bearish resistance on 3-box (log vs arithmetic changes the line).
- Targets: **vertical count** and **horizontal count** (3-box and 1-box methods differ; De Villiers & Taylor 3-box horizontal discussed). Use counts for **R:R**, not certainty.
- **Bullish percent** (breadth) as a market-level P&F tool.
- Overlays: MA, parabolic SAR, Bollinger on P&F — advanced, test separately.
- Stops and risk-reward from box geometry — the book’s count chapters are the numeric core.

**Discretionary vs mechanical:** Construction is mechanical. Which signals to take (ignore vs trend) can be discretionary unless you freeze a rule (e.g. only with-trend double-top).

**Data needs:** Prices (tick, OHLC, or close). Box size in price or %. Stateful column engine. Not a natural **M1 scalp** transform.

**Hype:** “Definitive” is about completeness of the method, not a promised edge. No 100% WR.

**MT5-portable:** Yes as a **separate engine** (box, reversal, counts). Poor fit for firehose M1. Walk-forward box size or you curve-fit.

**Aegis mapping quality:** **Absent / P2.** No P&F state machine.

**Priority:** **P2** (after Davey/Aronson holdout)

---

## Cross-book conflicts (keep configurable)

| Topic | Disagreement | Aegis default |
| --- | --- | --- |
| Win rate | Davey/Tharp/Clenow: WR is not the objective. Range scalps can *look* high WR with wide stops. Aronson: even 10% “best rule” can be noise. | Rank **cost-adjusted E[R]**, PF, DD — never 100% WR. |
| Optimization | Davey: WFA + don’t retouch. Aronson: penalize search size. Chan: train/test + costs. Carver: haircut in-sample SR. Murphy (older TAM) is weaker on “add costs later.” | **Davey+Aronson** win. |
| Sizing | Elder **2%/6%**; Tharp **1%** typical / **<3%**; Chan **Kelly/half-Kelly**; Carver **vol target ≈ SR**; Clenow **0.15–0.20% ATR impact**; Davey **MC-chosen f** (example **0.175**). | Keep `risk_percent` **≤2** as Elder cap; do not Kelly-full or Clenow-leverage a $100 FX account. |
| Losing streak | Schwager: discretionary **pause**; system **don’t pause**. Elder **6%** forces a pause. Davey: incubate/quit if monkeys catch up. | Config flag: `discretionary_pause` vs `systematic_hold`. |
| FX retail | Elder: avoid bucket shops, prefer futures. Davey: market orders + that broker’s data. Chan 2008: stocks first. | MT5 demo is fine for **process**; don’t assume interbank fills. |
| Exotic bars | Davey: avoid Renko/P&F in backtests. Nison/du Plessis: those charts *are* the method. | Separate research engines; never mix brick fills with OHLC assumptions. |

---

## What this basket does *not* authorize

- Any claim of **100% future win rate**.
- All-in / Martingale / 100% daily-loss configs.
- Treating bakeoff winners as Davey-incubated or Aronson-significant.
- Calling single-symbol BB or Donchian a full Chan 2008 or Clenow CTA book.
- Importing Murphy ETF rotations or P&F counts without the data/engine.

## Suggested Aegis order of work

1. **P0:** Frozen holdout + walk-forward + search-size log (Davey, Aronson).
2. **P1:** Elder monthly **6%** available-risk; Clenow ATR **risk_factor** on a **basket**; Carver forecast cap + vol target; Tharp R histogram; Chan half-Kelly **cap** (not full Kelly).
3. **P2:** Grimes failure-test; Nison 3LB/kagi **research-only**; P&F engine; Schwager segmented journal.
4. **P3:** Murphy intermarket when extra symbols exist.
