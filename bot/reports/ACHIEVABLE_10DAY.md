# Achievable $10/day

## Goal
**~$10/day** average over time (not every single day).

## Engine
- `breakout_adx` · `BTC-USD` · `1h`
- WR ~**57%** · ~0.7 trades/day · positive expectancy
- **Required capital: ~$15,500** at 1% risk/trade
- Replay check at that size: ~**$10.02/day** avg

## From $100
Fund to ~**$15,500**, then:
```bash
python scripts/run_paper.py --config config_objective_10day.yaml
```

### Deposit calendar (from $100)
- **$50/week** → ~**308 weeks** (~71.6 months)
- **$100/week** → ~**154 weeks** (~35.8 months)
- **$200/week** → ~**77 weeks** (~17.9 months)
- **$500/week** → ~**31 weeks** (~7.2 months)

Vs old $50/day goal: needs ~⅕ the capital (~$15k vs ~$52k).

Config: `config_objective_10day.yaml`
