# Forever-safe high-risk (best we can do)

## Hard truth
Douglas / Tharp / Elder: **no system is forever 100% wins**. We refuse to claim that.

## What “as safe as high-risk can be” means here
- Lock **80%** of start as protected principal (never sized)
- Put **20%** in a risk bankroll — high risk *inside that pocket only*
- Size so a stop cannot push equity below the protected floor (cost buffer)
- **Halt on first loss** / bankroll wipe
- Always use stops

Config: `config_100wr_forever_safe.yaml`

## 100WR sample + forever_safe ($100)
- Trades 11 · WR 100.0% · Final **$104.17**

## book_optimal (has losses) + forever_safe
- Final **$114.60** · Halt: forever_safe: first loss — locked (principal protected)
- vs unsafe 100% risk final **$-98.03** (ruined=True)

## Run
```bash
python scripts/run_backtest.py --config config_100wr_forever_safe.yaml
python scripts/run_paper.py --config config_100wr_forever_safe.yaml
```
