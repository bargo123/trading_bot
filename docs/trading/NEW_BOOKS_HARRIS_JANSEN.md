# Harris + Jansen — Aegis digest (Aug 2026)

Full cleaned text is in `docs/trading/books/`. Educational/systems work only.
**Neither book authorizes 100% win rate, 100x equity, or profit.**

| Book | Full extract |
|------|----------------|
| Larry Harris — *Trading and Exchanges* (Oxford 2002) | `@docs/trading/books/trading-and-exchanges-market-microstructure-for-practitioners---full---2002-oxfo.md` |
| Stefan Jansen — *Hands-On Machine Learning for Algorithmic Trading* (Packt 2018) | `@docs/trading/books/hands-on-machine-learning-for-algorithmic-trading-jansen.md` |

---

## Harris — *Trading and Exchanges*

Market orders **pay the spread** (half-spread each side of a round trip). Dealers
widen after informed flow. **Adverse selection:** if you lift the offer right after
an informed jump, the next tick is more often against you.

Codeable censors already on the firehose:

1. `max_spread_pips` — skip when the take cannot beat cost (1-pip TP needs a tight quote).
2. `firehose_harris_jump` — if the closed bar’s range ≥ `harris_jump_atr` × ATR and
   the close is in the jump direction, **do not chase that side**. Fading the jump
   is still allowed.

This is a cost / selection filter, not a direction oracle.

---

## Jansen — *Hands-On ML for Algorithmic Trading* (2018)

A strategy is **data → alpha factors → backtest with costs → trade only when
factors agree**. The 2018 Packt text is factor engineering and walk-forward
validation, not a license to train a GBDT on every 1-second poll of an i5.

Codeable v1 (no lookahead, closed bar only):

- `ret_1` / `ret_5` / `ret_10` from `close.pct_change`
- `jansen_mom_z` = rolling z-score of `ret_5`
- `jansen_rsi_z` = (RSI − 50) / 50
- `jansen_er_z` from Kaufman efficiency
- `jansen_score` = 0.50 mom + 0.30 RSI + 0.20 ER

`firehose_jansen_filter`: buy only if `jansen_score ≥ jansen_score_min`; sell only
if `jansen_score ≤ −jansen_score_min`. Missing score → skip (do not spray).

This is **not** a trained model and **not** a 100% WR claim.

---

## Aegis flags

| Flag | Default in code | Live firehose (demo) |
|------|-----------------|----------------------|
| `firehose_jansen_filter` | off | on |
| `jansen_score_min` | 0.15 | 0.15 |
| `firehose_harris_jump` | off | on |
| `harris_jump_atr` | 1.8 | 1.8 |

Gates run even when `firehose_book_filter` is false. Existing positions are not
flattened; only **new entries** are censored.
