# Coulling VPA · Brooks Ranges · Damir 2016 — Aegis digest (Aug 2026)

Full cleaned text is in `docs/trading/books/`. Educational/systems work only. **None of these books authorize 100% open-direction accuracy.**

| Book | Full extract |
|------|----------------|
| Anna Coulling — *A Complete Guide To Volume Price Analysis* (2013) | `@docs/trading/books/a-complete-guide-to-volume-price-analysis-coulling.md` |
| Anna Coulling — *Stock Trading & Investing Using Volume Price Analysis* | `@docs/trading/books/stock-trading-investing-using-volume-price-analysis-coulling.md` |
| Al Brooks — *Trading Price Action Ranges* (Wiley 2012) | `@docs/trading/books/trading-price-action-ranges-brooks.md` |
| Laurentiu Damir — *Price Action Breakdown* (2016) | `@docs/trading/books/price-action-breakdown-damir-2016.md` |

---

## Coulling (both VPA books)

**Law of effort vs result:** volume (effort) should match the bar’s range (result).

Codeable censors (tick volume vs its SMA; range vs its SMA):

1. **Wide bar + high volume + close in the direction** → effort with result. Allow that side.
2. **Wide bar + low volume** → anomaly / trap. Skip that side (`vpa_no_demand` on a wide up bar; `vpa_no_supply` on a wide down bar).
3. **Narrow bar + high volume** → absorption (effort, no result). Skip both sides (`vpa_absorption`).
4. **Narrow bar + low volume** → agreement; not a direction signal by itself.
5. After congestion: a **low-volume test** that closes back near the open is “no demand / no supply” — campaign may continue. A **high-volume test** that follows through is a failed test — do not chase.

The 200-examples book does not add a second mechanical system; it repeats the same anomalies on charts.

**Aegis:** `firehose_vpa_filter` (default off in code). Live firehose can turn it on. If tick volume is missing, the gate passes so FX is not starved.

---

## Brooks — *Trading Price Action Ranges*

Range tells: overlapping bars (~50%+), many tails/dojis, relatively flat moving average, vacuum spikes at the edges that fail.

**How he wants the range traded (Ch. 21):**

- Maxim: **buy low, sell high**. Treat trades as **scalps**, not breakout swings.
- About **80%** of strong rallies to the top of a range fail to become a bull trend; same for sell-offs to the bottom. Expect failure until a breakout actually sticks.
- **Skip the middle third** of the range (and of a range day). Do not enter on stops there.
- Fade **failed breakouts** back into the range.
- Tight overlapping “barbwire” is often better left alone.

This **disagrees** with firehose `close >= ema20 → buy` in the middle of overlapping M1 bars.

**Aegis:** `firehose_brooks_range` only when `brooks_in_range` (rolling overlap). Then skip mid-third; buy the bottom / sell the top; allow failed-break fades. When overlap is low (trend), EMA firehose is left alone.

---

## Damir 2016 — *Price Action Breakdown*

Market-profile-inspired, not the 2012 Fib pullback book.

- **Fair value** = area where price spent the most time (bulk of trading). **Excess / tails** = brief trips outside that come back; less time outside = stronger rejection.
- **Control** ≈ middle of value (pivotal S/R).
- **Responsive** = buy value-low / sell value-high while balanced. **Initiative** = forceful move *away* from value (needs volume).
- **HH/HL vs LH/LL** still used, as a complement, not a substitute.
- **Do not buy in excess above value; do not sell in excess below value.**
- Uptrend: buy from excess-below through just above control; sell only excess-above.
- Downtrend: sell from excess-above through just below control; buy only excess-below.
- Horizontal value: buy bottom / below, sell top / above (same idea as Brooks).
- Enter after **rejection** (pin/tail or small value + excess) on a **lower** timeframe; stop beyond that tail; reward > risk. Skip vertical tape with no value.

Hype to discount: “very lucrative,” month-after-month profits — no stats in the book. Author: not an expert advisor.

**Aegis:** `firehose_damir_structure` uses confirmed swing HH/HL (`structure_frame`) plus `range_loc` vs the prior 20-bar envelope. Blocks buy-into-down / sell-into-up, blocks buying the top of an up-move (`range_loc >= 0.85`), and in a classified range uses the same bottom/top split as Brooks.

---

## Authors disagree — keep flags

| Topic | Coulling | Brooks | Damir 2016 | Firehose today |
|-------|----------|--------|------------|----------------|
| Direction oracle | No | No | No | EMA side every bar |
| Volume | Required | Not used | Helpful, not required | Tick volume now optional via VPA |
| In a range | Wait for VPA at edges | Fade extremes, skip mid | Buy low / sell high of value | EMA spray including mid |
| In a trend | Follow effort | Don’t fade a spike blindly | Buy pullbacks; don’t buy excess-high | EMA still sprays |

Live YAML can enable the three gates on **new entries only**. Do not flatten. Do not change TP/SL while the book is open. Still not 100% direction.

## Implementation

- Features: `aegis/features.py` → `add_direction_features`
- Gates: `aegis/direction.py` → `direction_allows` (called from `_firehose_book_allows`)
- Flags: `firehose_vpa_filter`, `firehose_brooks_range`, `firehose_damir_structure` (code default **false**)
- Tests: `bot/tests/test_direction.py`
