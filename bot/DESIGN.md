# Aegis design (library synthesis)

This bot is **not** a copy of one author. It combines recurring, practical ideas from the user's library into one mechanical system.

## Cross-book principles → code

| Principle | Sources (examples) | Implementation |
|---|---|---|
| Trade a defined edge mechanically | Douglas *Zone* / *Disciplined Trader*, Tendler | Signal rules only in live/paper loop; journal every action |
| Risk small fixed fraction; survive | Elder, Tharp | `risk_percent` position sizing from stop distance |
| Hard daily / overall loss limits | Elder 2%/6% spirit | `max_daily_loss_percent`, `max_total_drawdown_percent` |
| Don't fight regime | Grimes, Edwards/Magee, Clenow | ADX + EMA regime → trend vs range modes |
| Trend following when trending | Clenow, Carver | Donchian breakout + ATR trail |
| Mean reversion in ranges | Classic TA / oscillator practice | BB + RSI with fixed SL/TP |
| Keep systems simple & testable | Chan, Davey, Aronson | Two explicit modes, vectorized backtest, no curve-fit jungle |
| Costs matter | Harris microstructure | spread_bps + slippage_bps |
| Process over prediction | Schwager wizards themes | Expectancy/R reporting; kill switch |

## Intentionally not included (v1)

- Full futures portfolio diversification (Clenow multi-asset) — single symbol first
- Intermarket confirmation stack (Murphy) — can be added as optional filter
- Chart-pattern catalog automation (Bulkowski) — too discrete for v1 robustness
- Discretionary overrides — rejected by design (Douglas mechanical stage)

## Honest limits

Books improve **design quality**, not guaranteed edge. Walk-forward and out-of-sample testing (Davey/Chan/Aronson) should come before live capital.
