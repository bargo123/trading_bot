#!/usr/bin/env python3
"""
Out-of-sample test (Mode B): forever_safe + hw_range on the LAST 14 days,
using longer history for indicators — not the original hunt window alone.
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
from aegis.session_algos import ALGOS
from aegis.strategy import prepare


def main() -> None:
    cfg = yaml.safe_load((ROOT / "config_paper_forever_safe_14d.yaml").read_text())
    cfg["lookback_days"] = 120
    cfg["starting_equity"] = 100.0
    print("Fetching 120d EURUSD 1h…", flush=True)
    df = add_spread_proxy(
        fetch_ohlcv(cfg["symbol"], cfg["timeframe"], int(cfg["lookback_days"])),
        float(cfg["spread_bps"]),
    )
    t1 = pd.Timestamp(df["time"].iloc[-1])
    cut = t1 - pd.Timedelta(days=14)
    print(f"Full span: {df['time'].iloc[0]} → {t1}", flush=True)
    print(f"OOS window: {cut} → {t1}", flush=True)

    # Full run then filter trades to last 14d (indicators warmed on prior bars)
    res = run_backtest(df, cfg, prepare_fn=prepare, signal_fn=ALGOS["hw_range"])
    trades = res.trades.copy() if res.trades is not None and not res.trades.empty else pd.DataFrame()
    if not trades.empty:
        et = "exit_time" if "exit_time" in trades.columns else "time"
        trades["exit_time"] = pd.to_datetime(trades[et])
        oos = trades[trades["exit_time"] >= cut].copy()
    else:
        oos = trades

    # Also: prior 14d window (days -28..-14) as second OOS slice
    cut0 = cut - pd.Timedelta(days=14)
    prior = trades[(trades["exit_time"] >= cut0) & (trades["exit_time"] < cut)].copy() if not trades.empty else trades

    def summarize(name: str, tdf: pd.DataFrame, start: float = 100.0) -> dict:
        if tdf is None or tdf.empty:
            return {"window": name, "trades": 0, "wr": 0.0, "pnl": 0.0, "final_approx": start, "min_equity_ok": True}
        wins = (tdf["pnl"] > 0).sum()
        n = len(tdf)
        pnl = float(tdf["pnl"].sum())
        # rough equity path from start for this window only
        eq = start + tdf["pnl"].cumsum()
        floor_ok = bool(eq.min() >= 80.0 - 1e-6) if len(eq) else True
        return {
            "window": name,
            "trades": n,
            "wins": int(wins),
            "wr": round(100.0 * wins / n, 1) if n else 0.0,
            "pnl": round(pnl, 2),
            "final_approx": round(float(eq.iloc[-1]), 2),
            "min_eq": round(float(eq.min()), 2),
            "floor_ok": floor_ok,
        }

    full = {
        "window": "full_120d_run",
        "trades": res.total_trades,
        "wr": round(res.win_rate, 1),
        "pnl": round(res.net_pnl, 2),
        "final": round(res.final_equity, 2),
        "halt": res.halt_reason or "",
        "floor_ok": res.final_equity >= 80.0,
    }
    last14 = summarize("last_14d_OOS", oos)
    prior14 = summarize("prior_14d_OOS", prior)

    print("\n=== Full forever_safe run (warm-up included) ===")
    print(format_report(res))
    print(f"floor_ok={full['floor_ok']}")
    print("\n=== Last 14d OOS trades only ===")
    print(last14)
    print("\n=== Prior 14d OOS trades only ===")
    print(prior14)

    rows = [full, last14, prior14]
    pd.DataFrame(rows).to_csv(ROOT / "reports" / "real_test_oos.csv", index=False)

    # Pass/fail for OOS (Mode B)
    # Pass if: protected floor held on full run; last 14d did not ruin
    b_pass = bool(full["floor_ok"] and last14.get("floor_ok", True))
    md = [
        "# Real test — Mode B out-of-sample",
        "",
        f"Generated: {pd.Timestamp.utcnow().isoformat()}",
        "",
        "## Setup",
        "- Config: `config_paper_forever_safe_14d.yaml`",
        "- Start: $100 · forever_safe 80/20 pocket · EURUSD 1h `hw_range`",
        "- OOS: last 14 calendar days of fetched history",
        "",
        "## Results",
        "",
        f"- Full run: trades={full['trades']} WR={full['wr']}% PnL=${full['pnl']} final=${full['final']} halt=`{full['halt']}` floor_ok={full['floor_ok']}",
        f"- Last 14d OOS: {last14}",
        f"- Prior 14d OOS: {prior14}",
        "",
        f"## Mode B verdict: {'PASS' if b_pass else 'FAIL'}",
        "",
        "PASS means protected floor (~$80) held — not that WR is forever 100%.",
        "",
        "## Mode A (paper) — you run this",
        "```bash",
        "cd ~/trading-llm/bot && source .venv/bin/activate",
        "python scripts/run_paper.py --config config_paper_forever_safe_14d.yaml",
        "```",
        "Leave it running 14 days. Journal: `reports/paper_journal.jsonl`",
        "Status check: `python scripts/real_test_status.py`",
        "",
        "## Pass / fail after 14 paper days",
        "- PASS if final equity ≥ $80 (protected floor)",
        "- PASS if first loss halted new entries (no revenge sizing)",
        "- FAIL if equity < $80 or account ruined",
        "- WR is recorded but **100% WR is not required to pass** (honesty rule)",
    ]
    (ROOT / "reports" / "REAL_TEST.md").write_text("\n".join(md) + "\n")
    print(f"\nMode B verdict: {'PASS' if b_pass else 'FAIL'}")
    print("Wrote reports/REAL_TEST.md")


if __name__ == "__main__":
    main()
