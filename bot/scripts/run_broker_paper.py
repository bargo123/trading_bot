#!/usr/bin/env python3
"""Run Aegis signals through a broker engine (IBKR paper first; MT5 later)."""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aegis.config import load_config  # noqa: E402
from aegis.engines import OrderRequest, create_engine  # noqa: E402
from aegis.high_risk import HighRiskController  # noqa: E402
from aegis.risk import RiskEngine  # noqa: E402
from aegis.strategy import prepare, signal_from_row  # noqa: E402

logger = logging.getLogger(__name__)


def bars_to_frame(bars) -> pd.DataFrame:
    rows = [
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
    return pd.DataFrame(rows)


def append_journal(path: Path, event: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, default=str) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Aegis broker-engine paper runner")
    parser.add_argument("--config", default=str(ROOT / "config_ib_paper_eurusd.yaml"))
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    cfg = load_config(args.config)
    if str(cfg.get("engine", "")).lower() == "mt5":
        raise SystemExit("MT5 engine not implemented yet — use engine: ibkr")

    eng = create_engine(cfg)
    eng.connect()
    journal = ROOT / "reports" / f"{cfg.get('test_name', 'ib_paper')}_journal.jsonl"
    heartbeat = ROOT / "reports" / "bot_heartbeat.json"
    risk = RiskEngine.from_config(cfg)
    symbol = str(cfg["symbol"])
    qty = float(cfg.get("order_quantity", 20000))
    last_bar_time = None
    hr = None
    position_opened_at: Optional[float] = None
    max_hold = float(cfg.get("max_hold_seconds", 0) or 0)

    def write_heartbeat(extra: Optional[dict] = None) -> None:
        payload = {
            "pid": os.getpid(),
            "ts": time.time(),
            "iso": datetime.now(timezone.utc).isoformat(),
            "symbol": symbol,
            "qty": qty,
        }
        if extra:
            payload.update(extra)
        heartbeat.parent.mkdir(parents=True, exist_ok=True)
        heartbeat.write_text(json.dumps(payload), encoding="utf-8")

    try:
        acct = eng.account()
        if not acct.is_paper and not bool(cfg.get("allow_live", False)):
            raise SystemExit("Not a paper session. Refusing to trade.")
        hr = HighRiskController.from_config(cfg, acct.equity)
        logger.info(
            "Connected engine=%s account=%s equity=%.2f paper=%s qty=%.0f",
            eng.name,
            acct.account_id,
            acct.equity,
            acct.is_paper,
            qty,
        )
        append_journal(
            journal,
            {"event": "start", "engine": eng.name, "account": acct.account_id, "equity": acct.equity},
        )
        write_heartbeat({"equity": acct.equity, "status": "running"})

        while True:
            try:
                write_heartbeat({"status": "running"})
                bars = eng.bars(symbol, str(cfg["timeframe"]), int(cfg.get("lookback_days", 30)))
                if len(bars) < 50:
                    logger.warning("Not enough bars yet (%s)", len(bars))
                    if args.once:
                        break
                    time.sleep(float(cfg.get("poll_seconds", 60)))
                    continue

                raw = bars_to_frame(bars)
                frame = prepare(raw, cfg)
                row = frame.iloc[-2]  # last closed bar
                bar_time = pd.Timestamp(row["time"])
                if last_bar_time is not None and bar_time <= last_bar_time:
                    if args.once:
                        print("No new bar")
                        break
                    time.sleep(float(cfg.get("poll_seconds", 60)))
                    continue
                last_bar_time = bar_time

                acct = eng.account()
                open_pos = eng.positions(symbol)
                equity = acct.equity

                # Already in a trade: hold, do not treat max_positions as a fatal halt
                if open_pos:
                    if position_opened_at is None:
                        position_opened_at = time.time()
                    held = time.time() - position_opened_at
                    # Flat tape: TP never hits — force flatten so firehose can cycle
                    if max_hold > 0 and held >= max_hold:
                        pos0 = open_pos[0]
                        close_side = "sell" if pos0.side == "buy" else "buy"
                        logger.info(
                            "Max hold %.0fs reached — flattening %s qty=%.0f",
                            max_hold,
                            pos0.side,
                            pos0.quantity,
                        )
                        try:
                            ibx = eng._require()  # type: ignore[attr-defined]
                            ibx.reqGlobalCancel()
                            ibx.sleep(0.5)
                        except Exception:
                            pass
                        flat = eng.place_order(
                            OrderRequest(
                                symbol=symbol,
                                side=close_side,
                                quantity=float(pos0.quantity),
                                kind="market",
                                client_tag="aegis_maxhold_flat",
                            )
                        )
                        append_journal(
                            journal,
                            {
                                "event": "flatten",
                                "reason": "max_hold",
                                "held_s": held,
                                "ok": flat.ok,
                                "msg": flat.message,
                                "equity": equity,
                            },
                        )
                        position_opened_at = None
                        time.sleep(float(cfg.get("poll_seconds", 60)))
                        continue

                    logger.info("Open position: %s — waiting (held=%.0fs)", open_pos[0], held)
                    append_journal(
                        journal,
                        {
                            "event": "position",
                            "side": open_pos[0].side,
                            "qty": open_pos[0].quantity,
                            "avg": open_pos[0].avg_price,
                            "bar": str(bar_time),
                            "equity": equity,
                        },
                    )
                    if args.once:
                        break
                    time.sleep(float(cfg.get("poll_seconds", 60)))
                    continue

                position_opened_at = None
                ok, reason = risk.allow(
                    equity,
                    open_positions=0,
                    now=bar_time.to_pydatetime() if hasattr(bar_time, "to_pydatetime") else bar_time,
                )
                if not ok:
                    logger.warning("Risk halt: %s (continuing watch)", reason)
                    append_journal(journal, {"event": "halt", "reason": reason, "equity": equity})
                    time.sleep(float(cfg.get("poll_seconds", 60)))
                    continue
                hr_ok, hr_reason = hr.allow(equity)
                if not hr_ok:
                    logger.warning("HR halt: %s (continuing watch)", hr_reason)
                    append_journal(journal, {"event": "hr_halt", "reason": hr_reason, "equity": equity})
                    time.sleep(float(cfg.get("poll_seconds", 60)))
                    continue

                sig = signal_from_row(row, cfg)
                if sig is None:
                    logger.info("No signal @ %s close=%.5f", bar_time, float(row["close"]))
                    if args.once:
                        break
                    time.sleep(float(cfg.get("poll_seconds", 60)))
                    continue

                # Tiny fixed quantity — never all-in on broker demo
                req = OrderRequest(
                    symbol=symbol,
                    side=sig.side,
                    quantity=qty,
                    kind="market",
                    stop_loss=float(sig.sl) if sig.sl is not None else None,
                    take_profit=float(sig.tp) if sig.tp is not None else None,
                    client_tag=f"aegis_{sig.reason}"[:40],
                )
                logger.info(
                    "SIGNAL %s %s qty=%.0f sl=%s tp=%s reason=%s",
                    sig.side,
                    symbol,
                    qty,
                    req.stop_loss,
                    req.take_profit,
                    sig.reason,
                )
                if bool(cfg.get("dry_run", False)):
                    append_journal(journal, {"event": "dry_run_signal", "signal": sig.__dict__})
                    print("dry_run — not sending order")
                else:
                    res = eng.place_order(req)
                    append_journal(
                        journal,
                        {
                            "event": "order",
                            "ok": res.ok,
                            "id": res.broker_order_id,
                            "msg": res.message,
                            "side": sig.side,
                            "qty": qty,
                            "sl": req.stop_loss,
                            "tp": req.take_profit,
                            "reason": sig.reason,
                            "bar": str(bar_time),
                        },
                    )
                    print(f"order ok={res.ok} id={res.broker_order_id} {res.message}")
                    if res.ok:
                        position_opened_at = time.time()

                if args.once:
                    break
                time.sleep(float(cfg.get("poll_seconds", 60)))
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                logger.exception("Loop error (will retry): %s", exc)
                try:
                    write_heartbeat({"status": "error", "error": str(exc)})
                except Exception:
                    pass
                time.sleep(float(cfg.get("poll_seconds", 60)))
                try:
                    eng.connect()
                except Exception:
                    pass
    finally:
        try:
            if heartbeat.exists():
                heartbeat.unlink()
        except Exception:
            pass
        eng.disconnect()


if __name__ == "__main__":
    main()
