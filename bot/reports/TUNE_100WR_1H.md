# One-hour 100% WR tuning

## Search summary (measured)
- Long hunt (~55 min): tested **12240**, measured 100% WR hits (n≥5): **5553**
- Focused tuner (~20 min): tested **5228**, hits: **2451**
- Finalize + mutate pass: **280** unique param sets re-scored with neighbor windows + $100 all-in
- Combined compute ≈ **1h+**; hit logs overlap (same grid region). Numbers below are measured only.

## Best pick (measured)
- EURUSD=X 1h 60d · trades **29** · WR **100.0%** · E[R] **0.150**
- Params: SL=3.0 ATR · TP=0.45 ATR · RSI 40/65 · ADX<24 · BB 24/1.8
- Session UTC 0–21 · cost_buffer=1.15
- Neighbor windows with 100% WR: **3** / 4 · avg WR nearby **99.3%**
- $100 all-in verify: **$533.75** · trades 29 · WR 100.0% · E[R] 0.150

Config: `config_tuned_100wr.yaml`

> Measured on historical yfinance bars only. Not a claim of future or forever 100% WR.

## Neighbor windows
- 45d: n=24 WR=100.0% E[R]=0.150 pnl=70.65
- 60d: n=29 WR=100.0% E[R]=0.150 pnl=86.71
- 75d: n=31 WR=100.0% E[R]=0.150 pnl=93.33
- 90d: n=36 WR=97.2% E[R]=0.118 pnl=49.67

## Runner-ups considered
- Long-hunt raw pick (n=44, E[R]=0.075, $100→$177.12, neighbor 100% WR **2**/4, avgWR 98.6%): kept as lower quality vs best (lower E[R] and all-in equity).
- High-n focused interim: n=43 E[R]=0.070 $100→$198.37 (perfect=3/4) — more trades, weaker expectancy/compounding.
- High-trade robust alt: n=36 E[R]=0.114 perfect=3 $100→$371.25.

## Ranking note
Best selected among candidates with **≥3/4** neighbor windows at 100% WR, maximizing `100*perfect + 200*n*E[R] + $100_equity`.
