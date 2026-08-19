#!/usr/bin/env python3
"""Read-only MT5 demo connectivity probe. Places no orders."""
from __future__ import annotations

import json
import sys
from pathlib import Path

BOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BOT))

from aegis.config import configured_symbols, load_config  # noqa: E402


def main() -> int:
    cfg = load_config(BOT / "config_mt5_demo_firehose_hw.yaml")
    report: dict[str, object] = {
        "allow_live_in_config": cfg.get("allow_live"),
        "mode": cfg.get("mode"),
        "engine": cfg.get("engine"),
    }
    try:
        import MetaTrader5 as mt5
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({**report, "error": f"MetaTrader5 import failed: {exc}"}, indent=2))
        return 1

    path = str(cfg.get("mt5_path") or "")
    ok = mt5.initialize(path=path) if path else mt5.initialize()
    if not ok:
        report["initialize"] = False
        report["last_error"] = mt5.last_error()
        print(json.dumps(report, indent=2, default=str))
        return 2

    report["initialize"] = True
    term = mt5.terminal_info()
    acct = mt5.account_info()
    report["terminal"] = (
        None
        if term is None
        else {
            "company": term.company,
            "name": term.name,
            "connected": term.connected,
            "trade_allowed": term.trade_allowed,
            "build": term.build,
        }
    )
    if acct is None:
        report["account"] = None
        report["account_error"] = mt5.last_error()
    else:
        mode = int(getattr(acct, "trade_mode", 2))
        report["account"] = {
            "login": acct.login,
            "server": acct.server,
            "currency": acct.currency,
            "balance": acct.balance,
            "equity": acct.equity,
            "margin_free": acct.margin_free,
            "leverage": acct.leverage,
            "trade_mode_raw": mode,
            "trade_mode": {0: "DEMO", 1: "CONTEST", 2: "REAL"}.get(mode, "UNKNOWN"),
        }

    symbols = configured_symbols(cfg)
    usable = []
    for sym in symbols:
        info = mt5.symbol_info(sym)
        if info is None:
            if not mt5.symbol_select(sym, True):
                continue
            info = mt5.symbol_info(sym)
        if info is None:
            continue
        tick = mt5.symbol_info_tick(sym)
        bars = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M1, 0, 10)
        usable.append(
            {
                "symbol": sym,
                "visible": bool(info.visible),
                "spread_points": int(getattr(info, "spread", -1)),
                "point": float(info.point),
                "volume_min": float(info.volume_min),
                "volume_step": float(info.volume_step),
                "trade_mode": int(getattr(info, "trade_mode", -1)),
                "bid": None if tick is None else float(tick.bid),
                "ask": None if tick is None else float(tick.ask),
                "m1_bars_available": 0 if bars is None else len(bars),
            }
        )
    report["symbols_configured"] = len(symbols)
    report["symbols_usable"] = len(usable)
    report["symbol_detail"] = usable
    mt5.shutdown()

    out = BOT / "reports" / "claude" / "mt5_demo_check.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    compact = {k: v for k, v in report.items() if k != "symbol_detail"}
    print(json.dumps(compact, indent=2, default=str))
    if usable:
        print("\nfirst 3 symbols:")
        for row in usable[:3]:
            print(json.dumps(row, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
