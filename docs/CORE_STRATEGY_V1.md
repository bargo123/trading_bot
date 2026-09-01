# CORE_STRATEGY_V1 — frozen firehose (13 Aug 2026)

Educational/systems work only. **100% WR is a research target, not a claim.**
Hunt already printed 95% WR with negative expectancy.

Live bot YAML: `bot/config_mt5_demo_firehose_hw.yaml` (do not edit it for
intel experiments). Param snapshot: `bot/aegis/intel/frozen_v1.json`.

## How it identifies a trade

`sig_firehose` in `bot/aegis/session_algos.py` with `firehose_every_bar: true`:

1. Use the **closed** M1 bar (`prepare` uses `iloc[-2]` live).
2. If `close >= ema_20` → buy (`firehose_bar_up`); else sell (`firehose_bar_dn`).
3. TP **1 pip**, SL **30 pips** from that close (JPY pip 0.01).
4. Session 00–24 UTC. Size **0.01** lots. `max_positions: 40`.
5. Existing *around-core* gates (not the formula): spread cap 0.3 pip,
   Jansen score, Harris jump, OMS pre-trade, no-stack-if-red, give-back lock.

Classic prior-bar breakout (`firehose_up` / `firehose_dn`) is unused while
`firehose_every_bar` is true. **Do not flip that flag as the live system.**

## How it executes

`bot/scripts/run_broker_paper.py` + `MT5Engine`: market order, adopt leftovers,
stack same-side only if the symbol is already green.

## Research rule

CORE → signal → **intel meta** (default off) → ACCEPT / REJECT / WAIT → order.

Challengers live in `bot/intel/` and must beat `bot/intel/champion.json` on
walk-forward OOS expectancy after costs. Never promote on train WR alone.
