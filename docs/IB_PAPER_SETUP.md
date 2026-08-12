# Broker engines

Aegis strategies do not talk to a broker directly. They go through:

`engine: ibkr` → Interactive Brokers (Mac-friendly, paper port 7497)  
`engine: mt5` → MetaTrader 5 (stub today; implement later on Windows)

```text
signal (hw_range, …) → run_broker_paper.py → BrokerEngine → IBKR / MT5
```

## Files
- `bot/aegis/engines/base.py` — interface
- `bot/aegis/engines/ibkr.py` — IBKR
- `bot/aegis/engines/mt5.py` — stub
- `bot/aegis/engines/factory.py` — `create_engine(cfg)`
- `bot/scripts/engine_smoke.py` — connection smoke test
- `bot/scripts/run_broker_paper.py` — live paper loop
- `bot/config_ib_paper_eurusd.yaml` — safe EURUSD paper config (`dry_run: true` by default)

## IBKR paper setup
1. Client Portal → enable **Paper Trading**
2. Install **IB Gateway** (or TWS), log in as **paper**
3. API settings: enable socket clients, **uncheck Read-Only API**, allow `127.0.0.1`
4. Ports: **IB Gateway paper = 4002**, Gateway live = 4001, TWS paper = 7497, TWS live = 7496
5. Keep Gateway/TWS running

```bash
cd bot
pip install ib_insync
python scripts/engine_smoke.py --port 4002
python scripts/engine_smoke.py --port 4002 --order
# when ready to send real paper orders:
# set dry_run: false in config_ib_paper_eurusd.yaml
python scripts/run_broker_paper.py --config config_ib_paper_eurusd.yaml --once
```

## Adding MT5 later
Implement methods on `MT5Engine` in `aegis/engines/mt5.py` using the `MetaTrader5` package on Windows, then set:

```yaml
engine: mt5
mode: mt5_demo
symbol: EURUSD
```

Same runner (`run_broker_paper.py`) — no strategy rewrite.
