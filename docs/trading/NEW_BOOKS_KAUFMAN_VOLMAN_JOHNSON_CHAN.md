# Kaufman / Volman / Johnson / Chan — high-frequency basket scalp

## Source PDFs (this machine)
| Book | Extract |
|------|---------|
| **Bob Volman** *Forex Price Action Scalping* (2011) | **PDF not on this PC** — digest notes only |
| **Ernie Chan** *Algorithmic Trading* (2013) | `@docs/trading/books/algorithmic-trading-winning-strategies-chan-2013.md` |
| **Perry Kaufman** *Trading Systems and Methods* | **PDF not on this PC** — cannot extract. Efficiency ratio is cited via Tharp. |
| **Barry Johnson** *Algorithmic Trading and DMA* (2010) | `@docs/trading/books/algorithmic-trading-and-dma-johnson-2010.md` (OCR) |

## What the readable books allow
### Volman
- Intraday FX scalp on **one chart**, setups around **20 EMA** (DD / First Break / Second Break / Block / Range breaks).
- **Spread must stay tiny** (≪ 1 pip) or the edge dies.
- Example money management: risk **~2%** on a **~10 pip** stop; targets often **~5 pip** — he shows compounding math, **not** 100% WR.

### Chan (2013)
- Mean-reversion (Bollinger / linear / Kalman) and **baskets/pairs** (ETF, FX, futures spreads).
- **Kelly** sizing tempered by fat tails / black swans.
- Explicitly: prototypes omit costs → **inflated** results; not trade-as-is.
- HFT / dark pools make some MR harder — not a retail DMA stack.

### Kaufman (still no extract) / Johnson (OCR on disk)
- Kaufman (from citations elsewhere): systems design, efficiency/noise filters, costs matter.
- Johnson: **DMA / exchange microstructure / latency** — needs co-lo + real order book; **not** yfinance paper on Mac. Full OCR: `@docs/trading/books/algorithmic-trading-and-dma-johnson-2010.md`.

## What we built
- `volman_scalp` — 20 EMA + double-doji micro-range break + pip TP/SL  
- `chan_bb_scalp` — Bollinger fade to mid (Chan prototype)  
- Basket hunt: EUR/GBP/AUD/NZD × 1m/5m × aggressive risk  
- Config: `config_volman_chan_basket.yaml`  
- Script: `scripts/hunt_volman_chan_basket.py`

## Measured (aggressive $100 basket hunt)
| Result | Value |
|--------|------:|
| Configs with ≥5 trades | 36 |
| **100% WR hits** | **0** |
| Best WR | **~70%** (GBPUSD Volman 5m) |
| Best equity @ 20% risk | **~$35** (still lost vs $100) |

**100% WR + HFT basket + aggressive sizing is not supported by these books on our data.** Volman’s best measured WR here was ~70% and still lost money at 20% risk because losses are larger than 5-pip wins after costs.
