# Achievable $50/day — book-aligned plan

## What the books require
| Author | Rule | Applied here |
|---|---|---|
| **Tharp** | Set objective first, then capitalize / position-size so it is a *low-risk* idea | Size account to ~$50/day |
| **Elder** | Tiny account + income target = overtrading / ruin | Reject $50/day on $100 |
| **Davey** | Undercapitalization ruins good systems | Fund before income mode |
| **Chan** | Costs kill forced overtrading | Prefer fewer +EV trades, not spam |

## Achievable engine (measured)
- **Algo:** `breakout_adx` (Clenow/Turtle-style ADX breakout)
- **Market:** `BTC-USD` **1h**
- **Win rate:** ~**57%**
- **Frequency:** ~**0.7 trades/day**
- **Expectancy:** positive (~**0.14R**)
- **On $10k sample:** ~**$6.50/day**
- **Capital for ~$50/day at 1% risk:** **~$51,600**

Config: `config_objective_50day.yaml`

### Higher WR alternatives (cost more capital)
| WR | Need for ~$50/day | Notes |
|---|---|---|
| ~62% | ~$56k | Same family, slightly fewer $/R |
| ~67% | ~$78k | More wins, smaller edge per trade |
| ~93% EURUSD HW | **$600k–$1.2M+** | Almost no trades/day — income needs huge bankroll |

## Path from $100 (this is how you “make it achievable”)
1. **$100 = school money** — paper/process only (`config.yaml` / `config_100_2h.yaml`). Not income.
2. **Fund** trading capital to ~**$51,600** (job/savings — Tharp: acquire capital outside the market if needed).
3. **Then** run:
   ```bash
   python scripts/run_paper.py --config config_objective_50day.yaml
   ```

### Deposit calendar (funding only; no fantasy 50%/day compounding)
| Weekly deposit | Time to ~$51.6k |
|---|---|
| $100 | ~10 years |
| $200 | ~5 years |
| $500 | ~2 years |
| $1,000 | ~1 year |

### If you compound every win (keep it in the account)
Measured from $100:

| Engine | After sample | Path to ~$52k |
|---|---|---|
| BTC 1h breakout (best) | **$100 → ~$125** in ~1 year | ~**30 years** if that growth repeated |
| EURUSD 93% WR | **$100 → ~$100.48** | thousands of years |
| BTC 5m high-WR | **$100 → ~$65** | goes down |

### If you “use” / spend every win
Worse: wins leave the account, losses stay → bankroll shrinks (BTC breakout sim: account can go negative while you only pocket small wins).

**Compounding is correct (Tharp), but $100 compounding alone does not unlock $50/day in a human timeframe.** Deposits + compounding does.

## Bottom line
The books do **not** say “hack the bot until $100 prints $50/day.”  
They say: **change capital (or the objective) until the math is sane.**

$50/day is achievable at ~**$52k** with this measured BTC breakout engine — not at $100.
