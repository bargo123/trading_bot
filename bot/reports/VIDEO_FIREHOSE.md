# Video firehose (1m OHLC max)

**Basket ~209 closed trades/day** across 8 pairs (measured).

Ceiling on yfinance 1m: one decision per bar → hundreds/day per pair, not thousands of tick round-trips.
True video firehose = MT5 tick/DMA on Windows.

```json
{
  "mode": "firehose_1m",
  "note": "1m OHLC ceiling; video-style thousands/day needs MT5 ticks",
  "basket_trades_per_day_approx": 209.4,
  "rows": [
    {
      "symbol": "EURUSD=X",
      "bars": 9889,
      "span_days": 8.94,
      "signals": 3205,
      "signals_per_day": 358.6,
      "trades": 233,
      "trades_per_day": 26.1,
      "win_rate": 0.567,
      "end_equity": 0.96
    },
    {
      "symbol": "GBPUSD=X",
      "bars": 9892,
      "span_days": 8.94,
      "signals": 5814,
      "signals_per_day": 650.6,
      "trades": 275,
      "trades_per_day": 30.8,
      "win_rate": 0.633,
      "end_equity": 0.99
    },
    {
      "symbol": "USDJPY=X",
      "bars": 9835,
      "span_days": 8.92,
      "signals": 2889,
      "signals_per_day": 324.0,
      "trades": 248,
      "trades_per_day": 27.8,
      "win_rate": 0.645,
      "end_equity": 1.0
    },
    {
      "symbol": "AUDUSD=X",
      "bars": 4942,
      "span_days": 8.94,
      "signals": 2456,
      "signals_per_day": 274.8,
      "trades": 181,
      "trades_per_day": 20.3,
      "win_rate": 0.569,
      "end_equity": 6.43
    },
    {
      "symbol": "USDCAD=X",
      "bars": 9838,
      "span_days": 8.93,
      "signals": 1463,
      "signals_per_day": 163.8,
      "trades": 300,
      "trades_per_day": 33.6,
      "win_rate": 0.66,
      "end_equity": 1.02
    },
    {
      "symbol": "NZDUSD=X",
      "bars": 4941,
      "span_days": 8.94,
      "signals": 2670,
      "signals_per_day": 298.8,
      "trades": 196,
      "trades_per_day": 21.9,
      "win_rate": 0.612,
      "end_equity": 12.3
    },
    {
      "symbol": "EURJPY=X",
      "bars": 9865,
      "span_days": 8.94,
      "signals": 3126,
      "signals_per_day": 349.8,
      "trades": 235,
      "trades_per_day": 26.3,
      "win_rate": 0.664,
      "end_equity": 1.01
    },
    {
      "symbol": "GBPJPY=X",
      "bars": 9874,
      "span_days": 8.94,
      "signals": 3124,
      "signals_per_day": 349.6,
      "trades": 203,
      "trades_per_day": 22.7,
      "win_rate": 0.665,
      "end_equity": 0.98
    }
  ]
}
```
