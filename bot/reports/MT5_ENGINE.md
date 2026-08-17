# MT5 engine (Windows) — 2026-08-12

## What landed
Real `MT5Engine` in `bot/aegis/engines/mt5.py` (no longer a stub). Same `BrokerEngine` interface as IBKR: connect, account, quote, bars, positions, place/cancel, cancel-all, flatten, plus `symbol_spec`, `copy_ticks`, `round_trip_spread_usd`.

Wired:
- `bot/scripts/engine_smoke.py --engine mt5`
- `bot/scripts/measure_mt5_costs.py` — read-only spread/contract snapshot
- `bot/scripts/measure_mt5_hw_range.py` — costed H1 `hw_range` on broker bars (no orders)
- `bot/scripts/run_broker_paper.py --config config_mt5_demo_eurusd.yaml`
- `bot/config_mt5_demo_eurusd.yaml` — EURUSD `hw_range`, **0.01 lots**, `risk_percent: 1`, `firehose_every_bar: false`, `allow_live: false`

This is **not** every-bar spray and **not** a 100% WR claim. Book gap matrix: `bot/reports/WINDOWS_BOOK_GAP_MATRIX.md`.

## Machine setup
- Python 3.12.10 64-bit
- `bot/.venv` with `requirements.txt` (includes `MetaTrader5` on Windows)
- MT5 terminal at `C:\Program Files\MetaTrader 5\terminal64.exe` (build 6111)

## Tests
`pytest tests/test_mt5_engine.py tests/test_engines_unit.py tests/test_paper_control.py -k "not ib_paper_config_defaults"`

Fake-MT5 coverage: demo connect, live refuse, not-logged-in, quote/bars, reject IB-style 20000 units, place+cancel limit, flatten, max-lots cap, spread USD, ticks/spec, paper-control gates.

## Live smoke (2026-08-12)

Demo login succeeded:

- Account `900907` on `SupremeFX-Server` (Sun Capital Markets Ltd.)
- `trade_mode=0` (demo), equity **$100**
- Broker symbol is `EURUSD.gc` (plain `EURUSD` is mapped)
- Quote/bars **SMOKE_OK**
- Orders failed **10026 AutoTrading disabled by server** while `trade_expert=False`

Do not claim the bot is “trading” until a filled demo deal exists.

## Safety
- Live accounts refused unless `allow_live: true`
- Quantity ≥ 100 treated as FX units and rejected (MT5 uses lots)
- Default cap `mt5_max_lots: 0.10`
- Do not enable `firehose_every_bar` to “see trades”
