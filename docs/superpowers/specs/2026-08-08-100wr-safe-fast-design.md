# 100WR Safe Fast — Design

## Goal
Make `100wr_safe` feel closer to the video’s **rapid open/close** rhythm while keeping forever_safe + high-hit `hw_range` entries.

## Non-goals
- Not 100 trades/minute (needs tick feed + live broker).
- Not XAU stacking / video marketing equity curve.
- Do not change `config_100wr_forever_safe.yaml` defaults.

## Approach (approved: A, then book expectancy fix)
- Config: `bot/config_100wr_safe_fast.yaml`
- Stack: EURUSD, `hw_range`, `forever_safe` (80/20 pocket)
- **Books (Tharp/Ponsi/Elder):** fix −EV tiny scalps via larger TP + `min_rr` (not win-rate chasing)
- Measured +EV pick: 1h, `atr_sl_mult=2`, `atr_tp_mult=3`, `min_rr=1.3`
- Optional Elder mid-band TP remains as `tp_mode: bb_mid` in code (user said “box” = **books**, not Bollinger)

## Constraints
- Not video-speed / not 1M real trades
- Bootstrap compounding ≠ live forecast

## Success check
Report `bot/reports/100WR_SAFE_FAST.md`: before mean R −0.084 → after **+0.250**, PF≥1.05 on $10k@1%.
