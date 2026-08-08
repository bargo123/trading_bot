# New books digest — Ponsi · Damir · DraKoln · Thomas · Afshari · Windsor (Aug 2026)

Full cleaned text under `@docs/trading/books/`:

| Book | File | ~Words |
|------|------|--------|
| Ed Ponsi — *Forex Patterns & Probabilities* (Wiley 2007) | `forex-patterns-probabilities-…md` | 67k |
| Laurentiu Damir — *Trade the Price Action* (2012) | `trade-the-price-action-…md` | 5k |
| Noble DraKoln — *Winning the Trading Game* (Wiley 2008) | `winning-the-trading-game-…md` | 105k |
| LR Thomas — *The 10XROI Trading System* (2014) | `the-10xroi-trading-system-…md` | 9k |
| Mostafa Afshari — *The Ultimate Forex Trading System* (©2016 / file 2021) | `the-ultimate-forex-trading-system-…md` | 12k |
| James Windsor — *The Holy Grail Forex Trading System* (2013) | `the-holy-grail-forex-trading-system-…md` | 24k |

---

## 1. Ed Ponsi — *Forex Patterns & Probabilities*

**Thesis:** Match technique to regime (trend vs range). Multi-timeframe structure + risk first. Anti–holy-grail; anti–10-pip scalping; pros obsess over losses, not win count.

**Core strategies (codeable):**
1. **MA proper order** — up: 10>20>50>200; ADX >35 rising = strong trend.
2. **MTF** — HTF bias only; LTF Fib pullback (38.2/50/61.8) + RSI(14) exit OB/OS → neutral; stop beyond extreme; scale at 1R → BE; soften S/R targets ~10% of range.
3. **FX-Ed** — *daily only*: proper-order + price on correct side of 10EMA ≥10 bars; enter on 10EMA touch; trail 0.5×ATR(14) daily; no forced TP; don’t stack correlated pairs.
4. **Squeeze** — flat 20EMA + ATR↓ + BB width↓ → triangle break both ways; stop inside; Fib/S/R exits.
5. **Flags/pennants** — entry = pole extreme ±10% pole; stop = 25% pole from entry; TP1=1R; TP2=measured pole.
6. **Round Trip** — fade first touch of xx00 on 5–15m after ≥20 pips from 20MA; stop 15+spread; spread cap 5; 1R→BE.
7. **Boomerang** — EURUSD only, ~17:00 ET open ±15, stop 15, target open; cancel if no fill in 2h.
8. **Carry** — long high-yield / short low-yield when differential widening (months).

**Risk:** Stop before entry; goals start 1–2%/month (aspirational compounding, not a guarantee). Prefer large R over scalping (spread tax math).

**Aegis:** Strong port candidates = FX-Ed daily ATR trail, MTF Fib+RSI, squeeze, flag %. Rescale pip recipes for BTC via ATR. Skip dealer folklore / swap carry on yfinance.

---

## 2. Laurentiu Damir — *Trade the Price Action*

**Thesis:** H4 price action + Fib + candles; daily 200EMA confirmation only. Few trades/month. Patience.

**System:**
- Trend = confirmed HH/HL or LH/LL (breach + impulse confirmation).
- Pullback Fib **50 → 61.8 → 78.2** (skip 38.2); confluence with S/R/trendline.
- Enter only after completed reversal candle (hammer, engulfing, morning/evening star, piercing/dark cloud…).
- SL = pattern extreme; TP = correction origin (conservative); require reward > risk; trail only confirmed pivots.

**Hype to discount:** Back-matter “200 pips/week,” “1000 pips/month,” sibling “50 pips a day” — no stats in the system chapter.

**Aegis:** H4 Fib pullback + EMA200 side + R>R gate is portable if candle patterns are strictly OHLC-defined.

---

## 3. Noble DraKoln — *Winning the Trading Game*

**Thesis:** ~90–95% fail because they bring stock buy-hold/DCA mentality into leveraged FX/futures. Pillars = **money management + TA + risk management**. No holy grail.

**Process (not one FX system):**
- Market filter: ATR volatility, liquidity/OI, affordable margins; FX “gear” ~3× cash vs margin.
- Liverpool TA: (1) 50DMA direction — wait 3 days after cross; no trade if sideways; (2) RSI using *market’s own* extremes not fixed 30/70; (3) horizontal S/R (+ Fib, BB).
- Micro: S/R break sustained 48–72h; ATR stop often 1.5× (0.5–2× by vol); price vs 9EMA/20/50 ≥2 days; candles confirm.
- If thesis fails in 2–3 days → exit.

**Risk numbers:** 2–5% per trade (CTA often ≤2%); never risk 1 to make <2; ≤⅓ account in one market; ≤~30% on margin; first 10 trades 1–2 contracts; monthly halt ~25%; ~50% account → full halt.

**Psychology:** Fear/greed cycle; be profitable not 100% right; don’t treat profits as “house money.”

**Aegis:** Take risk halts, regime gate, ATR stops, journal. Reject options hedges / “hard stop = option” / anti-stop dogma as no-SL. Unsourced 95% claim = industry folklore.

---

## 4. LR Thomas — *The 10XROI Trading System*

**Thesis:** Small clear stop + fixed ~**10×** reward → can win with low WR. D1 context → H1 entry. Explicitly: no holy grail.

**Rules:**
- **Push-pull:** strong push candle(s); pull toward prior close/open; enter near pullback extreme on H1 with clear S/R invalidation.
- Context: parabolic, breakouts, flags, S/R, candles hugging SMA(3) without piercing SMA(10).
- Stop ~15–40 pips typical (~25 avg in examples); TP = **10R** (or **8R** if stop large); BE only after first H1 pullback resumes.
- Risk **1–2%** (beginners 1%). Frequency ~1–4 setups/month if job-trading.

**Hype:** Hypothetical compounding (+thousands %) and “lose 70% still profit” assume every winner hits full 10R and ignore costs.

**Aegis:** Strong candidate `push_pull_10r` mode — separate from Fuller pyramiding (Thomas wants hold-for-10R, not add).

---

## 5. Mostafa Afshari — *The Ultimate Forex… 92% Winning Trades*

**Thesis (sold):** Multi-signal confluence → “92%.” **Reality:** Discretionary checklist soup; Ch.6 even admits no holy-grail indicator — contradicts the title.

**Fragments:** Patterns (triangle/H&S…), pin rejection, correlation lag (|ρ| 0.75–0.85, trade lagging, abort in 3h), VPA, Abandoned Baby + EMA(5) on D/W, sentiment Δ%, optional news.

**Risk:** ≤3% open risk (5% if “perfect”); R:R ≥2; SL often ≤35 pips from entry or skip; pair-specific pip tables.

**Probability theater:** Claims 1 signal ~70% → 2→82% → 3→92% via bogus `(0.3/0.7)³` math. **Do not use for sizing.**

**Aegis:** Keep only process (SL+TP first, R:R gate, MTF filter, journal). Reject 92%/95%/99% WR, confidence→size-up, leverage cheerleading.

---

## 6. James Windsor — *The Holy Grail Forex Trading System*

**Thesis:** Cautionary autobiography. Mechanical GBPUSD “Grail” + reckless MM turned £10k into ~£100k+ then crashed (~48–50%+ DD). Million target missed. Book reveals rules.

**Exact Grail (Appendix):**
1. At **08:00 UK**, GBPUSD price P.
2. BuyStop P+40 / SellStop P−40.
3. SL **80**, TP **240**, trail **60**.
4. OCO: one fill cancels other.
5. Flat by **18:00 UK**.

**Fatal MM (reject):** ratchet stakes never down; **increase £/pip on losing days**; “income” withdrawal while sizing as if cash still at risk → double leverage; celebrating 50–65% DD.

**Live lesson:** Worked in trending cable regime; died in doji/range months. Author later: overconfidence + insufficient regime coverage in testing.

**Aegis:** Codeable research template + **mandatory regime kill-switch**. Never ship loss-escalation MM. Similar spirit to Fabris (price+time) but fixed 2005 params — adapt or die.

---

## Combined Aegis policy from these six

| Keep / research | Reject |
|-----------------|--------|
| Ponsi FX-Ed, MTF Fib, squeeze, flag % | Holy-grail / 92% WR claims (Afshari, title culture) |
| Damir H4 Fib 50/61.8/78.2 + EMA200 + R>R | Damir/Afshari pips-per-week marketing |
| Thomas D1→H1 push-pull + 10R + delayed BE | Thomas compounding fantasy |
| DraKoln ≤2% risk, monthly halt, regime gate | DraKoln options-as-stops / anti-SL reading |
| Windsor 8am±40 breakout as **test subject** | Windsor martingale stake ratchet / 50% DD OK |
| All: no holy grail; process > prediction | Grid / no-stop / size-up-in-DD |

**Income realism unchanged:** Elder/Tharp/DraKoln/Ponsi — expectancy × capital; high WR with tiny targets still loses; undercapitalized “daily salary” goals = ruin path.

## Implementation status

**High-risk MM from these books is wired** (`aegis/high_risk.py`, `config_high_risk_solved.yaml`, `reports/HIGH_RISK_SOLVED.md`):
- traditional ≤2% · Fuller pyramid · Brown recovery/DCA (capped Fib steps) · Windsor escalate (capped) · Thomas compound (clamped)
- Default cage: `high_risk_safe: true`, risk ≤5% cap, max 3 steps, equity floor 50%, max 4 consecutive losses, stops required
- Uncapped Windsor/Brown only if `allow_unsafe_high_risk: true` (lab only)

Still not wired as dedicated signal algos (ingest + learn for these entries):
1. `ponsi_fxed` — daily 10EMA + 0.5 ATR trail  
2. `ponsi_squeeze` — ATR/BBW compression break  
3. `thomas_10r` — push-pull + 10R  
4. `windsor_grail` — research-only London breakout + **safe** %risk MM (MM path done; breakout signal optional)
