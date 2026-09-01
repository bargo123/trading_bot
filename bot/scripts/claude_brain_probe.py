#!/usr/bin/env python3
"""Read-only probe: what would the Intelligent Firehose decide, right now?

Runs the real brain over live MT5 M1 history for every configured symbol and
reports the decision plus full trade economics. Places no orders and never calls
the engine's order path - it only reads bars, ticks, and symbol specs.

Answers the two questions that matter after the EV gate landed:
  * does the firehose still fire (throughput preserved), and
  * what payoff structure do the trades it wants actually have?
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from statistics import mean

import pandas as pd

BOT = Path(__file__).resolve().parents[1]
if str(BOT) not in sys.path:
    sys.path.insert(0, str(BOT))

from aegis.config import configured_symbols, load_config, pip_size_for  # noqa: E402
from aegis.intel.firehose_brain import IntelligentFirehoseBrain  # noqa: E402
from aegis.strategy import prepare, signal_from_row  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(BOT / "config_mt5_demo_firehose_hw.yaml"))
    parser.add_argument("--bars", type=int, default=900)
    parser.add_argument("--output", default=str(BOT / "reports" / "claude" / "brain_probe.json"))
    args = parser.parse_args()

    cfg = load_config(args.config)
    if bool(cfg.get("allow_live", False)):
        raise SystemExit("refusing to probe with allow_live: true")

    import MetaTrader5 as mt5

    if not mt5.initialize(path=str(cfg.get("mt5_path") or "")):
        raise SystemExit(f"mt5.initialize failed: {mt5.last_error()}")

    account = mt5.account_info()
    demo = int(getattr(mt5, "ACCOUNT_TRADE_MODE_DEMO", 0))
    contest = int(getattr(mt5, "ACCOUNT_TRADE_MODE_CONTEST", 1))
    if account is None or int(getattr(account, "trade_mode", 2)) not in {demo, contest}:
        mt5.shutdown()
        raise SystemExit("refusing to probe a non-demo terminal")

    brain = IntelligentFirehoseBrain(cfg)
    snapshot = brain.snapshot()
    print(json.dumps({"brain": snapshot, "analogue_provenance": brain.analogues.provenance}, indent=2))

    rows: list[dict] = []
    for symbol in configured_symbols(cfg):
        raw = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, int(args.bars))
        tick = mt5.symbol_info_tick(symbol)
        info = mt5.symbol_info(symbol)
        if raw is None or len(raw) < 500 or tick is None or info is None:
            rows.append({"symbol": symbol, "action": "unavailable", "reason": "no_data"})
            continue

        frame = pd.DataFrame(raw)
        frame["time"] = pd.to_datetime(frame["time"], unit="s", utc=True)
        frame = frame.rename(columns={"tick_volume": "volume"})
        frame = frame[["time", "open", "high", "low", "close", "volume"]]
        completed = frame.iloc[:-1].copy()

        pip = float(pip_size_for(symbol, cfg))
        hint_cfg = {**cfg, "intel_enabled": False}
        try:
            prepared = prepare(completed, hint_cfg)
            hint = signal_from_row(prepared.iloc[-1], hint_cfg)
        except Exception as exc:  # noqa: BLE001 - probe must not die on one symbol
            hint = None
            print(f"{symbol}: signal hint failed: {exc}")

        row = completed.iloc[-1].copy()
        row["time"] = completed["time"].iloc[-1]
        row["ema_20"] = float(completed["close"].tail(20).mean())

        side = None if hint is None else hint.side
        entry = float(tick.ask if side == "buy" else tick.bid)
        spec = {
            "trade_tick_size": float(info.trade_tick_size),
            "trade_tick_value": float(info.trade_tick_value),
            "trade_tick_value_loss": float(info.trade_tick_value_loss),
            "trade_contract_size": float(info.trade_contract_size),
            "point": float(info.point),
            "volume_min": float(info.volume_min),
            "volume_step": float(info.volume_step),
            "volume_max": float(info.volume_max),
        }
        decision = brain.evaluate(
            symbol=symbol,
            row=row,
            completed_m1=completed,
            positions=[],
            equity=float(account.equity),
            pip=pip,
            core_side=side,
            spread_price=float(tick.ask - tick.bid),
            symbol_spec=spec,
            entry_price=entry,
        )
        journal = dict(decision.journal)
        rows.append(
            {
                "symbol": symbol,
                "action": decision.action,
                "reason": decision.reason,
                "core_hint_side": side,
                "brain_side": decision.side,
                "lots": decision.quantity,
                "sl": decision.sl,
                "tp": decision.tp,
                "analogue_n": decision.analogue_n,
                "spread_price": float(tick.ask - tick.bid),
                **{k: v for k, v in journal.items() if str(k).startswith(("econ_", "size_", "analogue_"))},
                "regime": journal.get("regime"),
                "structure": journal.get("structure"),
            }
        )
        print(
            f"{symbol:8s} {decision.action:6s} {decision.reason[:44]:44s} "
            f"n={decision.analogue_n:4d} payoff={journal.get('econ_payoff_ratio')} "
            f"ev={journal.get('econ_expected_net_usd')} lots={decision.quantity}"
        )

    mt5.shutdown()

    actions = Counter(row["action"] for row in rows)
    payoffs = [row["econ_payoff_ratio"] for row in rows if isinstance(row.get("econ_payoff_ratio"), (int, float))]
    evs = [row["econ_expected_net_usd"] for row in rows if isinstance(row.get("econ_expected_net_usd"), (int, float))]
    econ_reasons = Counter(str(row.get("econ_reason")) for row in rows if row.get("econ_reason"))
    summary = {
        "analogue_provenance": brain.analogues.provenance,
        "analogue_records": len(getattr(brain.analogues, "_records", [])),
        "analogue_measured": brain.analogues.is_measured,
        "champion": snapshot.get("champion"),
        "symbols": len(rows),
        "actions": dict(actions),
        "econ_reasons": dict(econ_reasons),
        "payoff_ratio_median": sorted(payoffs)[len(payoffs) // 2] if payoffs else None,
        "payoff_ratio_mean": mean(payoffs) if payoffs else None,
        "ev_positive_count": sum(1 for value in evs if value > 0),
        "ev_negative_count": sum(1 for value in evs if value <= 0),
        "reasons": dict(Counter(row["reason"] for row in rows)),
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"summary": summary, "rows": rows}, indent=2, default=str), encoding="utf-8")
    print("\n=== SUMMARY ===")
    print(json.dumps(summary, indent=2, default=str))
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
