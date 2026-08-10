# One-hour 100% WR tuning

## Search summary (measured)
- Long hunt (still/was running): tested **10600**, 100% WR hits **4829**
- Focused tuner: tested **5228**, 100% WR hits **2451**
- Finalize+mutate candidates kept: **280** (unique param sets evaluated in this pass)
- Quality score = `100*perfect_windows + 200*n*E[R] + $100_equity` (among primary-window 100% WR)

## Best pick (measured)
- EURUSD=X 1h 60d · trades **29** · WR **100.0%** · E[R] **0.150**
- Params: SL=3.0 ATR · TP=0.45 ATR · RSI 40/65 · ADX<24 · BB 24/1.8
- Session UTC 0–21 · cost_buffer=1.15
- Neighbor windows with 100% WR: **3** / 4 · avg WR nearby **99.3%**
- $100 all-in verify: **$533.75** · trades 29 · WR 100.0% · E[R] 0.150
- Quality score: **1703.8**

Config: `config_tuned_100wr.yaml`

> Measured on historical yfinance bars only. Not a claim of future or forever 100% WR.

## Neighbor windows
- 45d: n=24 WR=100.0% E[R]=0.150 pnl=70.65
- 60d: n=29 WR=100.0% E[R]=0.150 pnl=86.71
- 75d: n=31 WR=100.0% E[R]=0.150 pnl=93.33
- 90d: n=36 WR=97.2% E[R]=0.118 pnl=49.67

## Top by quality (perfect≥3 preferred)
- q=1703.8 n=29 E=0.150 perfect=3 $100→$533.75 sl=3.0 tp=0.45 rsi=40/65 adx<24 60d
- q=1564.2 n=30 E=0.125 perfect=3 $100→$514.23 sl=4.0 tp=0.5 rsi=40/65 adx<26 45d
- q=1564.2 n=30 E=0.125 perfect=3 $100→$514.23 sl=4.0 tp=0.5 rsi=40/65 adx<26 45d
- q=1564.2 n=30 E=0.125 perfect=3 $100→$514.23 sl=4.0 tp=0.5 rsi=40/65 adx<26 45d
- q=1494.1 n=36 E=0.114 perfect=3 $100→$371.25 sl=3.5 tp=0.4 rsi=40/65 adx<26 60d
- q=1468.5 n=29 E=0.129 perfect=3 $100→$422.78 sl=3.5 tp=0.45 rsi=40/65 adx<24 60d
- q=1443.2 n=24 E=0.137 perfect=3 $100→$483.15 sl=4.0 tp=0.55 rsi=40/65 adx<24 45d
- q=1443.2 n=24 E=0.137 perfect=3 $100→$483.15 sl=4.0 tp=0.55 rsi=40/65 adx<24 45d
- q=1443.2 n=24 E=0.137 perfect=3 $100→$483.15 sl=4.0 tp=0.55 rsi=40/65 adx<24 45d
- q=1424.8 n=39 E=0.100 perfect=3 $100→$344.76 sl=4.0 tp=0.4 rsi=40/65 adx<26 60d
