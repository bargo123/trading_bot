# New books digest — Fuller + Fabris + Brown + Silvani (Aug 2026)

Full cleaned text:
- `@docs/trading/books/pyramiding-full-text-extracted.md` (~1.8k words) — Nial Fuller
- `@docs/trading/books/forex-strategy-the-price-in-time---libgen-li.md` (~17k words) — Gabriele Fabris
- `@docs/trading/books/profitable-forex-trading-using-high-and-low-risk-strategies-2024---annas-arch-37.md` (~48k words) — Jim Brown
- `@docs/trading/books/beat-the-forex-dealer-an-insider-s-look-into-trading-today-s-foreign-exchange-ma.md` (~68k words) — Agustin Silvani

OCR note: Silvani text layer is noisy but readable; content below sticks to what’s in the extract.

---

## Nial Fuller — *Pyramiding* (2012 article)

**Thesis:** Scale into **winners** so total risk never exceeds predefined **1R**, while reward expands — only in strong trends / strong intra-day moves.

**Smart vs stupid:** Add only with predetermined levels **and** trail all stops so aggregate risk ≤ 1R. Adding without trailing = voluntarily more risk → never.

**Worked EURUSD short:** Entry 1.2550 / SL 1.2650 / 1R=$200; add @ +100 and +200 pips; trail so after 2nd add net risk ≈ 0R and potential ~1:6. Prefer full-position 1:2/1:3 **or** pyramid in; don’t impulsively scale out as policy.

**For Aegis:** Regime-gated adds at +N·R / +N·ATR; unify stop so `sum(risk) ≤ 1R`; set `pyramid_allowed` at entry. Skip ranges/chop.

---

## Gabriele Fabris — *Forex Strategy: The Price in Time* (2023)

**Thesis:** Edge = **Price + Time** only. Fixed GMT session structure → mechanical dual breakout of the London open range. No discretionary patterns.

**NTZ (No Trading Zone):** GMT **07:00–08:00** high/low. Trade only if width **W ∈ [10, 30] pips**. Skip if Asia already trending, holidays, NFP/FED/ECB, wars.

**Entries (~08:00):** BuyStop = NTZ_H+1; SellStop = NTZ_L−1. SL = opposite NTZ ±1. Targets = +1W…+4W (prefer half-pip early). ≤2 trades/day/pair; opposite side only after a stop; flatten ~17:00 GMT.

**Exit models (pick one per pair via backtest):** (1) trail SL to prior TP levels; (2) half at TP1, trail rest; (3) BE at TP1, fixed TP2.

**Risk:** 0.5–2% (author often 2% total across ≤3 pairs). Explicit: **no infallible method**.

**For Aegis:** Primary time-boxed range-breakout engine. Map clocks carefully on yfinance UTC. For BTC replace pip band with ATR%/$-range calibration. Pure OHLCV state machine.

---

## Jim Brown — *Profitable Forex Trading Using High & Low Risk Strategies* (2024)

**Thesis:** Indicator framework on **higher TFs** (Daily preferred) + four risk modes. Realistic **~2–6%/month**; management > entry; no holy grail. ~75% of traders lose; many who are “right on direction” still fail on management.

**Signals (closed bar → next open):** QMP-style MACD/QQE dots + filters: 50/100 EMA + 240 LWMA stack, BB 20/2 & 80/3, MACD zero-lag side of 0, QQE 35/50/65. Personal setups: Q12, Q26, BB80 mean-revert, OB/OS, bonus QQE trendline break.

**Risk modes:**
| Mode | Stops | Notes |
|------|-------|-------|
| Traditional (default) | Yes | 0.5–2% / ATR×1.5 SL |
| Loss recovery | Yes/no | Fib size 1,3,5,8… recover then leave base |
| Hedging | Often no | Lock loss, release with larger bias |
| DCA | No | Same-dir grid → BE; **highest ruin risk** |

**For Aegis:** Closed-bar filters + ATR/1R traditional path; partial→BE management. Reimplement QMP/QQE with open MACD/RSI-like formulas (closed-source JAGfx not available). **Do not** ship no-stop hedge/DCA as default.

---

## Agustin Silvani — *Beat the Forex Dealer* (Wiley, 2008)

**Thesis:** Retail FX is structurally stacked (spread, leverage marketing, dealer stop-runs). Survive by trading only when odds shift; professional MM; no holy-grail systems. Explicitly: **>90%** long-run failure; FXCM-era comment that few day traders stay profitable.

**Risk:** ≤1–2% equity/position; retail leverage ≤10× (pros often 2–5×); scale multiple minis in a 10–15 pip band.

**Tactics transferable without L2:** session clocks (prefer London–NY overlap); rolling **4h pivot** long/short bias; avoid thin hours (~3–7pm NY); dynamic stops (not tiny fixed at rounds/news); relative-strength via crosses; fade first news spike after dust settles; **Big Figure** time-boxed fade (~≤15 min); **Friday→Sunday** extension hypothesis (USD majors, 3–5pm NY entry).

**Does NOT transfer on yfinance Mac bot:** EBS/Reuters latency arb, knowing client stops, dealing-desk phone flow, invisible broker stops.

**For Aegis:** Gates (session/liquidity/news/cost/risk) around any signal engine; cost as first-class kill-switch; Big Figure / Friday-extension as optional micro-modules only.

---

## Combined Aegis policy from these four

1. **Signal core (Fabris):** time-boxed range breakout with width filter + flatten by session end.
2. **Gates (Silvani):** liquid sessions only, thin-hour blackout, news wait, 4h pivot bias, cost model, ≤1–2% risk.
3. **Management (Brown traditional + Fuller):** closed-bar manage; partial→BE; optional **pyramid into winners only** when trend regime passes and aggregate risk stays ≤1R.
4. **Explicit non-defaults:** Brown loss-recovery / hedge / DCA grids; Silvani latency arb; discretionary pin-bar first entries without coded rules.

## Implementation status (Aug 2026)

Wired into Aegis bot:
- `fabris_ntz` signal + NTZ features (`aegis/profile_features.py`)
- Fuller pyramiding in backtester (`pyramid_enabled`, `aegis/pyramid.py`)
- Configs: `bot/config_fabris_ntz.yaml`, `bot/config_fabris_pyramid.yaml`
- Tests: `bot/tests/test_fabris_fuller_unit.py`, `bot/scripts/test_fabris_fuller.py`
- Report: `bot/reports/FABRIS_FULLER_TEST.md`

## Constraint on $10–$50/day / 100% WR goals

All four reinforce Elder/Tharp/Davey/Aziz:
- No guaranteed wins / no infallible method
- Income scales with capital + expectancy, not leverage fantasy
- High-risk recovery/DCA + tiny account + income target = ruin path
