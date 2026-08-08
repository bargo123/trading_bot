#!/usr/bin/env python3
"""
Run every book high-risk mode on $100 book_optimal — unsafe vs solved cage.
Proves the safety cage stops account wipe patterns.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aegis.backtest import format_report, run_backtest
from aegis.data import add_spread_proxy, fetch_ohlcv
from aegis.high_risk import solved_policy_config
from aegis.session_algos import ALGOS
from aegis.strategy import prepare


def base() -> dict:
    c = yaml.safe_load((ROOT / "config_book_optimal.yaml").read_text())
    c["starting_equity"] = 100.0
    c["max_daily_loss_percent"] = 100.0  # let HR cage own the halt (except solved overrides)
    c["max_total_drawdown_percent"] = 100.0
    c["signal_mode"] = "book_optimal"
    c["algo"] = "book_optimal"
    return c


def main() -> None:
    b = base()
    print("Fetching…", flush=True)
    df = add_spread_proxy(fetch_ohlcv(b["symbol"], b["timeframe"], int(b["lookback_days"])), float(b["spread_bps"]))
    print(f"bars={len(df)}", flush=True)

    modes = [
        # (label, overrides)
        ("unsafe_80pct_fixed", {"high_risk_mode": "traditional", "risk_percent": 80, "high_risk_safe": False, "allow_unsafe_high_risk": True, "hr_risk_max_cap": 100, "hr_equity_floor_frac": 0.0, "hr_max_consecutive_losses": 99, "pyramid_enabled": False}),
        ("brown_recovery_unsafe", {"high_risk_mode": "brown_recovery", "risk_percent": 5, "high_risk_safe": False, "allow_unsafe_high_risk": True, "hr_risk_max_cap": 100, "hr_max_steps": 8, "hr_equity_floor_frac": 0.0, "hr_max_consecutive_losses": 99, "pyramid_enabled": False}),
        ("windsor_unsafe", {"high_risk_mode": "windsor_escalate", "risk_percent": 5, "high_risk_safe": False, "allow_unsafe_high_risk": True, "hr_risk_max_cap": 100, "hr_windsor_step_pct": 5, "hr_max_steps": 20, "hr_equity_floor_frac": 0.0, "hr_max_consecutive_losses": 99, "pyramid_enabled": False}),
        ("thomas_unsafe", {"high_risk_mode": "thomas_compound", "risk_percent": 5, "high_risk_safe": False, "allow_unsafe_high_risk": True, "hr_risk_max_cap": 100, "hr_thomas_win_frac": 0.5, "hr_equity_floor_frac": 0.0, "hr_max_consecutive_losses": 99, "pyramid_enabled": False}),
        ("brown_dca_unsafe", {"high_risk_mode": "brown_dca_size", "risk_percent": 5, "high_risk_safe": False, "allow_unsafe_high_risk": True, "hr_risk_max_cap": 100, "hr_max_steps": 8, "hr_equity_floor_frac": 0.0, "hr_max_consecutive_losses": 99, "pyramid_enabled": False}),
        # SOLVED variants
        ("traditional_safe_2pct", {"high_risk_mode": "traditional", "risk_percent": 2, **{k: v for k, v in solved_policy_config().items() if k != "high_risk_mode" and k != "risk_percent"}, "pyramid_enabled": False}),
        ("fuller_pyramid_solved", solved_policy_config({"risk_percent": 2.0})),
        ("brown_recovery_solved", solved_policy_config({"high_risk_mode": "brown_recovery", "risk_percent": 1.0, "pyramid_enabled": False})),
        ("windsor_solved_capped", solved_policy_config({"high_risk_mode": "windsor_escalate", "risk_percent": 1.0, "pyramid_enabled": False})),
        ("thomas_solved", solved_policy_config({"high_risk_mode": "thomas_compound", "risk_percent": 1.0, "pyramid_enabled": False})),
        ("brown_dca_solved", solved_policy_config({"high_risk_mode": "brown_dca_size", "risk_percent": 1.0, "pyramid_enabled": False})),
    ]

    rows = []
    for label, ov in modes:
        c = dict(b)
        c.update(ov)
        # solved policy brings daily/dd caps back
        if "solved" in label or label.endswith("safe_2pct") or label.startswith("fuller"):
            c["max_daily_loss_percent"] = float(c.get("max_daily_loss_percent", 6))
            c["max_total_drawdown_percent"] = float(c.get("max_total_drawdown_percent", 20))
        res = run_backtest(df, c, prepare_fn=prepare, signal_fn=ALGOS["book_optimal"])
        ruined = res.final_equity < 1.0
        row = {
            "mode": label,
            "trades": res.total_trades,
            "wr": round(res.win_rate, 2),
            "pnl": round(res.net_pnl, 2),
            "final": round(res.final_equity, 2),
            "dd": round(res.max_drawdown_pct, 2),
            "ruined": ruined,
            "halt": res.halt_reason or "",
        }
        rows.append(row)
        print(f"\n=== {label} ===", flush=True)
        print(format_report(res), flush=True)
        print(f"ruined={ruined}", flush=True)

    table = pd.DataFrame(rows)
    table.to_csv(ROOT / "reports" / "high_risk_modes_test.csv", index=False)

    unsafe = table[table["mode"].str.contains("unsafe")]
    solved = table[~table["mode"].str.contains("unsafe")]
    md = [
        "# High-risk book modes — handled & solved",
        "",
        "Start: **$100** · Engine: `book_optimal` · BTC 15m",
        "",
        "## Unsafe (book patterns without cage)",
        "",
        "| Mode | Trades | WR% | PnL | Final | DD% | Ruined | Halt |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for _, r in unsafe.iterrows():
        md.append(
            f"| `{r['mode']}` | {r['trades']} | {r['wr']:.1f} | {r['pnl']:.2f} | {r['final']:.2f} | "
            f"{r['dd']:.1f} | {r['ruined']} | {r['halt']} |"
        )
    md += [
        "",
        "## Solved (safety cage ON)",
        "",
        "| Mode | Trades | WR% | PnL | Final | DD% | Ruined | Halt |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for _, r in solved.iterrows():
        md.append(
            f"| `{r['mode']}` | {r['trades']} | {r['wr']:.1f} | {r['pnl']:.2f} | {r['final']:.2f} | "
            f"{r['dd']:.1f} | {r['ruined']} | {r['halt']} |"
        )
    md += [
        "",
        "## What was solved",
        "1. **Silvani/Brown/DraKoln** — traditional ≤2% with stops",
        "2. **Fuller** — pyramid winners only, aggregate ≤1R, risk capped",
        "3. **Brown recovery / DCA** — Fib steps allowed but **max 3 steps**, risk **≤5%**, always SL, reset on win",
        "4. **Windsor escalate** — cannot uncapped-ratchet unless `allow_unsafe_high_risk: true`; safe mode caps + resets",
        "5. **Thomas compound** — size from prior win but **clamped ≤5%**, reset after loss",
        "6. **Hard stops always** — no-stop hedge/DCA chapters not executable",
        "7. **Kill switches** — equity floor 50%, max 4 consecutive losses, daily/DD halts on solved configs",
        "",
        "Default live policy: `config_high_risk_solved.yaml`",
        "",
        f"CSV: `reports/high_risk_modes_test.csv`",
    ]
    (ROOT / "reports" / "HIGH_RISK_SOLVED.md").write_text("\n".join(md) + "\n")
    print("\n", table.to_string(index=False), flush=True)
    print("\nWrote reports/HIGH_RISK_SOLVED.md", flush=True)

    # Assert: solved modes do not ruin on this sample
    for _, r in solved.iterrows():
        if r["ruined"]:
            raise SystemExit(f"SOLVED mode still ruined: {r['mode']}")
    print("ASSERT OK: no solved mode ruined the $100 account on this sample", flush=True)


if __name__ == "__main__":
    main()
