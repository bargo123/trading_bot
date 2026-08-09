# Volman + Chan basket scalp hunt

## Books
- **Bob Volman** *Forex Price Action Scalping*: M-scalps around **20 EMA**; DD/FB/… setups; **spread ≪ 1 pip**; example **~5 pip** targets / **~10 pip** stops — **not** 100% WR.
- **Ernie Chan** *Algorithmic Trading* (2013): Bollinger / linear MR; FX/ETF **baskets**; Kelly + fat-tail caution; costs inflate naive backtests.
- **Perry Kaufman** / **Barry Johnson**: PDFs are **image scans** here (no extract). Johnson’s DMA/HFT stack is **not** runnable on this yfinance bot.

Full digest: `docs/trading/NEW_BOOKS_KAUFMAN_VOLMAN_JOHNSON_CHAN.md`

## Code
- Algos: `volman_scalp`, `chan_bb_scalp`
- Config: `config_volman_chan_basket.yaml`
- Hunt: `python scripts/hunt_volman_chan_basket.py`

## Hunt results (measured)
Configs with ≥5 trades: **36**  
Measured **100% WR hits: 0**

Best: GBPUSD Volman 5m ~**70% WR**, equity **~$35** from $100 @ 20% risk (still a net loss). Aggressive size + scalp RR does **not** produce video-style forever wins.
