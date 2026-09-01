# Aegis Bot — synthesized from your trading library

Systematic multi-regime bot designed from principles across your books
(Tharp, Elder, Douglas, Carver, Chan, Davey, Clenow, Grimes, Aronson, Harris, etc.).

**Not a profit guarantee.** Paper/backtest first.

## What it does

1. **Regime filter** — ADX + dual EMA → trend vs range  
2. **Trend mode** — Donchian breakout + ATR trailing stop  
3. **Range mode** — Bollinger + RSI mean reversion with SL/TP  
4. **Risk** — % equity risk per trade, daily loss halt, max drawdown halt (Elder/Tharp spirit)  
5. **Mechanical execution** — no discretionary overrides in the loop (Douglas)  
6. **Costs** — spread/slippage drag (Harris)  
7. **Journal** — every paper entry/exit logged  

## Setup (Mac)

```bash
cd ~/trading-llm/bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Backtest

```bash
python scripts/run_backtest.py
```

## Strategy bake-off

Runs 11 book-inspired systems on the same EURUSD 1h data (shared risk/costs, no look-ahead):

```bash
python scripts/run_bakeoff.py
```

Results land in `reports/BAKEOFF.md` and `reports/bakeoff_results.csv`.

Latest winner: **Aegis Range HW** (~96.6% WR, PF ~2.9 on sample) — already the profile in `config.yaml`.

## $100 / 2-hour aggressive play

Optimized for **max chance of a green 2h session** (see `reports/OPTIMIZE_2H.md`):

```bash
python scripts/optimize_2h_highwr.py
python scripts/run_paper.py --config config_100_2h.yaml
```

Current profile: BTC 5m high-WR practice mode (see `reports/OPTIMIZE_2H.md`).

## Aziz + Steidlmayer strategies

Wired from the new books (ORB/VWAP + Market Profile IB):

```bash
python scripts/test_aziz_steidl.py
python scripts/run_backtest.py --config config_aziz_orb.yaml
python scripts/run_backtest.py --config config_steidl_ib.yaml
```

Report: `reports/AZIZ_STEIDL_TEST.md`

## Fabris NTZ + Fuller pyramiding

Wired from *Price in Time* + Fuller’s scale-in article:

```bash
python tests/test_fabris_fuller_unit.py
python scripts/test_fabris_fuller.py
python scripts/run_backtest.py --config config_fabris_ntz.yaml
python scripts/run_backtest.py --config config_fabris_pyramid.yaml
```

Report: `reports/FABRIS_FULLER_TEST.md`

## Book-optimal (all-library confluence)

Synthesized from the full book library + parameter search:

```bash
python scripts/search_book_optimal.py
python scripts/run_backtest.py --config config_book_optimal.yaml
```

Report: `reports/BOOK_OPTIMAL.md`

## High-risk book modes (solved cage)

Implements Brown recovery/DCA, Windsor escalate, Thomas compound, Fuller pyramid, and traditional sizing — with a default safety cage so uncapped risk cannot silently wipe the account.

```bash
python tests/test_high_risk_unit.py
python scripts/test_high_risk_modes.py
python scripts/run_backtest.py --config config_high_risk_solved.yaml
```

Report: `reports/HIGH_RISK_SOLVED.md`  
Key flags: `high_risk_mode`, `high_risk_safe: true`, `allow_unsafe_high_risk: false`, `hr_risk_max_cap: 5`.

## Measured 100% WR profile

Found by exhaustive hunt on EURUSD 1h `hw_range` (verified 11/11 wins on 45d sample):

```bash
python scripts/run_backtest.py --config config_100wr.yaml
```

Report: `reports/HUNT_100WR.md`

## $10/day objective (book method)

More realistic than $50/day. Measured BTC 1h breakout needs about **$15,500** at 1% risk:

```bash
python scripts/run_paper.py --config config_objective_10day.yaml
```

Details: `reports/ACHIEVABLE_10DAY.md`

## $50/day objective (book method)

`$50/day` on `$100` is rejected by Elder/Tharp/Davey (undercapitalized income target).

Achievable path: fund ~**$52k**, then run the measured BTC 1h breakout engine:

```bash
python scripts/show_objective_plan.py
python scripts/run_paper.py --config config_objective_50day.yaml
```

Details: `reports/ACHIEVABLE_50DAY.md`

## Paper loop

```bash
python scripts/run_paper.py --once
python scripts/run_paper.py
```

Edit `config.yaml` for symbol (`EURUSD=X` or `BTC-USD`), risk, and timeframe.

## Design notes

See [DESIGN.md](DESIGN.md) for how each major book idea maps into the system.
