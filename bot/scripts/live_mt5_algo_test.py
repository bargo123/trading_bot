#!/usr/bin/env python3
"""Send real DEMO orders on MT5, one algo at a time. Not live money. Not 100% WR.

Each liveable algo is checked on the latest closed MT5 bar. If it signals,
place 0.01 EURUSD with that algo's SL/TP, hold briefly, flatten, record PnL.
Algos with no signal are skipped — we do not invent entries.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aegis.config import load_config  # noqa: E402
from aegis.engines import OrderRequest, create_engine  # noqa: E402
from aegis.paper_control import ProcessLock, paper_execution_enabled  # noqa: E402
from aegis.session_algos import ALGOS  # noqa: E402
from aegis.strategy import prepare, signal_from_row  # noqa: E402

LIVE_BASE: dict = {
    "ema_fast": 50,
    "ema_slow": 200,
    "atr_period": 14,
    "adx_period": 14,
    "adx_trend_threshold": 25,
    "adx_range_max": 22,
    "adx_min": 15,
    "donchian_period": 55,
    "bb_period": 20,
    "bb_std": 2.0,
    "rsi_period": 14,
    "rsi_oversold": 30,
    "rsi_overbought": 70,
    "rsi_pullback": 45,
    "rsi_pullback_hi": 55,
    "atr_sl_mult": 2.5,
    "atr_tp_mult": 0.8,
    "atr_trail_mult": 3.0,
    "min_atr_pct": 0.0004,
    "min_rr": 1.5,
    "cost_buffer": 1.5,
    "spread_bps": 2.26,
    "slippage_bps": 0.4,
    "firehose_pip_size": 0.0001,
    "firehose_tp_pips": 16,
    "firehose_sl_pips": 8,
    "orb_bars": 2,
    "ib_bars": 4,
    "book_min_triggers": 1,
    "book_require_vwap": False,
    "book_adx_max": 50,
    "thomas_rr": 4.0,
    "ensemble_min_votes": 2,
    "ensemble_members": ["book_optimal", "breakout_adx", "trend_pullback", "hw_range"],
    "er_period": 10,
    "pa_min_er": 0.30,
    "pa_allow_trend": True,
    "pa_allow_range": True,
    "pa_require_h1": True,
    "pa_elder_censor": True,
    "pa_allow_pin": True,
    "pa_allow_engulf": True,
    "pa_allow_retest": True,
    "pa_sl_buffer_pips": 1.0,
    "pa_max_sl_pips": 12.0,
    "pa_tp_mode": "r_multiple",
    "pa_tp_r": 4.0,
    "pa_zone_pips": 8.0,
    "ntz_start_utc": 7,
    "ntz_end_utc": 8,
    "ntz_flatten_utc": 17,
    "ntz_min_atr": 0.3,
    "ntz_max_atr": 4.0,
    "ntz_asia_max_pct": 0.05,
    "ntz_max_trades_day": 0,
}

logger = logging.getLogger(__name__)

M1_NAMES = {
    "firehose",
    "firehose_every_bar",
    "volman_scalp",
    "chan_bb_scalp",
    "pulse_scalp",
    "cafb",
    "scalper_2h",
}


def bars_to_frame(bars) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "time": pd.Timestamp(b.time),
                "open": b.open,
                "high": b.high,
                "low": b.low,
                "close": b.close,
                "volume": b.volume,
            }
            for b in bars
        ]
    )


def algo_cfg(name: str, live: dict) -> dict:
    mode = "firehose" if name == "firehose_every_bar" else name
    if name == "aegis_regime":
        mode = ""
    cfg = {
        **LIVE_BASE,
        **live,
        "signal_mode": mode,
        "algo": mode or "regime",
        "symbol": "EURUSD",
        "session_start_utc": 0,
        "session_end_utc": 24,
        "allow_live": False,
        "firehose_every_bar": name == "firehose_every_bar",
        "firehose_book_filter": False,
        "firehose_chart_read": False,
        "min_rr": 0.01 if name.startswith("firehose") else float(LIVE_BASE.get("min_rr", 1.5)),
    }
    return cfg


def latest_sig(eng, name: str, live: dict):
    tf = "1m" if name in M1_NAMES else "15m"
    days = 3 if tf == "1m" else 40
    cfg = algo_cfg(name, live)
    cfg["timeframe"] = tf
    df = bars_to_frame(eng.bars("EURUSD", tf, days))
    if df.empty or len(df) < 30:
        return None, tf, None
    df["time"] = pd.to_datetime(df["time"], utc=True)
    frame = prepare(df, cfg)
    if len(frame) < 3:
        return None, tf, None
    row = frame.iloc[-2]
    return signal_from_row(row, cfg), tf, row


def main() -> None:
    parser = argparse.ArgumentParser(description="Live DEMO fills, one algo at a time")
    parser.add_argument("--hold-seconds", type=float, default=40.0)
    parser.add_argument("--max-fills", type=int, default=12)
    parser.add_argument("--max-loss-usd", type=float, default=2.50)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    live = load_config(ROOT / "config_mt5_demo_best.yaml")
    live["allow_live"] = False
    live["paper_trading_enabled"] = True
    live["mode"] = "mt5_demo"
    live["mt5_magic"] = 260815
    if not paper_execution_enabled(live):
        raise SystemExit("paper execution not enabled")

    names = [n for n in ALGOS if n not in {"ensemble_optimal", "all_books"}]
    names = ["firehose_every_bar"] + [n for n in names if n != "firehose"]
    names.append("scalper_2h")

    lock = ProcessLock(ROOT / "reports" / "run_broker_paper.lock")
    lock.acquire()
    journal = ROOT / "reports" / "mt5_live_algo_test.jsonl"
    journal.parent.mkdir(parents=True, exist_ok=True)
    eng = None

    try:
        eng = create_engine(live)
        eng.connect()
        acct = eng.account()
        if not acct.is_paper:
            raise SystemExit("Refusing live-money account. Demo only.")
        start_eq = float(acct.equity)
        logger.info(
            "LIVE DEMO TEST account=%s equity=%.2f qty=0.01 hold=%.0fs",
            acct.account_id,
            start_eq,
            args.hold_seconds,
        )
        if eng.positions("EURUSD"):
            logger.info("Flattening leftover EURUSD before test")
            eng.flatten_positions("EURUSD")

        fills = 0
        results: list[dict] = []
        for name in names:
            acct = eng.account()
            lost = start_eq - float(acct.equity)
            if fills >= args.max_fills:
                logger.info("Hit max fills %s — stopping", args.max_fills)
                break
            if lost >= args.max_loss_usd:
                logger.info("Hit max loss $%.2f — stopping", args.max_loss_usd)
                break
            try:
                sig, tf, _row = latest_sig(eng, name, live)
            except Exception:
                logger.exception("signal error %s", name)
                results.append({"algo": name, "event": "error"})
                continue
            if sig is None:
                logger.info("SKIP %s — no signal on last closed %s bar", name, tf)
                rec = {"algo": name, "event": "skip", "tf": tf}
                results.append(rec)
                journal.open("a", encoding="utf-8").write(json.dumps(rec) + "\n")
                continue

            eq_before = float(eng.account().equity)
            logger.info(
                "ORDER %s %s EURUSD 0.01 sl=%s tp=%s reason=%s",
                name,
                sig.side,
                sig.sl,
                sig.tp,
                sig.reason,
            )
            res = eng.place_order(
                OrderRequest(
                    symbol="EURUSD",
                    side=sig.side,
                    quantity=0.01,
                    kind="market",
                    stop_loss=float(sig.sl) if sig.sl is not None else None,
                    take_profit=float(sig.tp) if sig.tp is not None else None,
                    client_tag=f"aegis_{name}"[:31],
                )
            )
            if not res.ok:
                logger.warning("REJECT %s %s", name, res.message)
                rec = {"algo": name, "event": "reject", "msg": res.message, "tf": tf}
                results.append(rec)
                journal.open("a", encoding="utf-8").write(json.dumps(rec) + "\n")
                continue

            fills += 1
            opened = time.time()
            last_pnl = 0.0
            while time.time() - opened < args.hold_seconds:
                pos = eng.positions("EURUSD")
                if not pos:
                    break
                last_pnl = float(pos[0].unrealized_pnl)
                time.sleep(1.0)
            if eng.positions("EURUSD"):
                last_pnl = float(eng.positions("EURUSD")[0].unrealized_pnl)
                eng.flatten_positions("EURUSD")
            eq_after = float(eng.account().equity)
            rec = {
                "algo": name,
                "event": "fill",
                "tf": tf,
                "side": sig.side,
                "reason": sig.reason,
                "order_id": res.broker_order_id,
                "unrealized_at_exit": round(last_pnl, 4),
                "equity_delta": round(eq_after - eq_before, 4),
                "equity": eq_after,
                "ts": datetime.now(timezone.utc).isoformat(),
            }
            results.append(rec)
            journal.open("a", encoding="utf-8").write(json.dumps(rec) + "\n")
            logger.info(
                "FLAT %s pnl~%.2f equity_delta=%.2f equity=%.2f",
                name,
                last_pnl,
                eq_after - eq_before,
                eq_after,
            )

        if eng.positions("EURUSD"):
            eng.flatten_positions("EURUSD")
        end_eq = float(eng.account().equity)
        summary = {
            "event": "done",
            "account": acct.account_id,
            "start_equity": start_eq,
            "end_equity": end_eq,
            "fills": fills,
            "results": results,
        }
        out = ROOT / "reports" / "MT5_LIVE_ALGO_TEST.json"
        out.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
        print(json.dumps({k: summary[k] for k in ("start_equity", "end_equity", "fills")}, indent=2))
        for rec in results:
            print(rec)
        print(f"Wrote {out}")
    finally:
        try:
            if eng is not None:
                eng.disconnect()
        except Exception:
            pass
        lock.release()


if __name__ == "__main__":
    main()
