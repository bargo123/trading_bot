# High-risk book modes — handled & solved

Start: **$100** · Engine: `book_optimal` · BTC 15m

## Unsafe (book patterns without cage)

| Mode | Trades | WR% | PnL | Final | DD% | Ruined | Halt |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| `unsafe_80pct_fixed` | 14 | 57.1 | -102.09 | -2.09 | 100.3 | True | max_drawdown 100.31% |
| `brown_recovery_unsafe` | 33 | 54.5 | 507.91 | 607.91 | 41.5 | False |  |
| `windsor_unsafe` | 33 | 54.5 | 236.48 | 336.48 | 28.1 | False |  |
| `thomas_unsafe` | 33 | 54.5 | 71.02 | 171.02 | 20.2 | False |  |
| `brown_dca_unsafe` | 33 | 54.5 | 507.91 | 607.91 | 41.5 | False |  |

## Solved (safety cage ON)

| Mode | Trades | WR% | PnL | Final | DD% | Ruined | Halt |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| `traditional_safe_2pct` | 33 | 54.5 | 26.10 | 126.10 | 8.1 | False |  |
| `fuller_pyramid_solved` | 5 | 20.0 | -3.36 | 96.64 | 4.9 | False | max_consecutive_losses (4) |
| `brown_recovery_solved` | 33 | 54.5 | 42.21 | 142.21 | 11.8 | False |  |
| `windsor_solved_capped` | 33 | 54.5 | 26.86 | 126.86 | 7.6 | False |  |
| `thomas_solved` | 33 | 54.5 | 12.62 | 112.62 | 4.1 | False |  |
| `brown_dca_solved` | 33 | 54.5 | 42.21 | 142.21 | 11.8 | False |  |

## What was solved
1. **Silvani/Brown/DraKoln** — traditional ≤2% with stops
2. **Fuller** — pyramid winners only, aggregate ≤1R, risk capped
3. **Brown recovery / DCA** — Fib steps allowed but **max 3 steps**, risk **≤5%**, always SL, reset on win
4. **Windsor escalate** — cannot uncapped-ratchet unless `allow_unsafe_high_risk: true`; safe mode caps + resets
5. **Thomas compound** — size from prior win but **clamped ≤5%**, reset after loss
6. **Hard stops always** — no-stop hedge/DCA chapters not executable
7. **Kill switches** — equity floor 50%, max 4 consecutive losses, daily/DD halts on solved configs

Default live policy: `config_high_risk_solved.yaml`

CSV: `reports/high_risk_modes_test.csv`
