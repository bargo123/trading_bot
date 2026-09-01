#!/usr/bin/env python3
"""Aegis Desk — local web UI for paper account / positions / fills."""
from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aegis.config import load_config  # noqa: E402
from aegis.paper_control import heartbeat_max_age  # noqa: E402

logger = logging.getLogger("aegis.dashboard")
DASHBOARD_DIR = ROOT / "dashboard"
INDEX_HTML = DASHBOARD_DIR / "index.html"
HEARTBEAT_FIELDS = (
    "symbol",
    "local_symbol",
    "feed_usable",
    "feed_age_seconds",
    "trades_today",
    "modeled_costs_today",
    "paper_promoted",
    "gate_reason",
    "regime",
    "signal_side",
    "flow_score",
    "expected_net_usd",
    "intelligent_firehose",
    "counts",
    "champion",
    "analogue_records",
    "knowledge_rows",
)


def collect_order_rows(ib) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    working: list[dict[str, object]] = []
    cancelling: list[dict[str, object]] = []
    active = {"PendingSubmit", "PreSubmitted", "Submitted", "ApiPending", "PendingCancel"}
    for trade in list(ib.reqAllOpenOrders() or []):
        status = str(trade.orderStatus.status or "")
        if status not in active:
            continue
        order = trade.order
        raw_price = (
            order.lmtPrice
            if order.orderType == "LMT"
            else order.auxPrice if order.orderType == "STP" else None
        )
        row: dict[str, object] = {
            "id": order.orderId,
            "action": order.action,
            "type": order.orderType,
            "quantity": float(order.totalQuantity),
            "price": float(raw_price) if raw_price not in (None, 0, 0.0) else None,
            "status": status,
        }
        (cancelling if status == "PendingCancel" else working).append(row)
    return working, cancelling


class DeskState:
    def __init__(self, cfg: dict[str, Any], journal: Path) -> None:
        self.cfg = cfg
        self.journal = journal
        self.lock = threading.Lock()
        self.snapshot: dict[str, Any] = {
            "ib_connected": False,
            "updated_at": None,
            "error": "starting",
        }
        self._ib = None
        self._stop = threading.Event()
        self._baseline: Optional[float] = None

    def start(self) -> None:
        t = threading.Thread(target=self._loop, name="desk-poll", daemon=True)
        t.start()

    def stop(self) -> None:
        self._stop.set()
        self._disconnect()

    def get(self) -> dict[str, Any]:
        with self.lock:
            return dict(self.snapshot)

    def _disconnect(self) -> None:
        if self._ib is not None:
            try:
                self._ib.disconnect()
            except Exception:
                pass
            self._ib = None

    def _connect(self):
        from ib_insync import IB

        if self._ib is not None and self._ib.isConnected():
            return self._ib
        self._disconnect()
        ib = IB()
        host = str(self.cfg.get("ib_host", "127.0.0.1"))
        port = int(self.cfg.get("ib_port", 4002))
        # Separate from trading bot client_id (default 7)
        client_id = int(self.cfg.get("ib_dashboard_client_id", 71))
        ib.connect(host, port, clientId=client_id, readonly=True, timeout=6)
        self._ib = ib
        return ib

    def _bot_running(self) -> bool:
        hb = ROOT / "reports" / "bot_heartbeat.json"
        try:
            if hb.exists():
                data = json.loads(hb.read_text(encoding="utf-8"))
                age = time.time() - float(data.get("ts", 0))
                if age <= heartbeat_max_age(self.cfg):
                    return True
        except Exception:
            pass
        try:
            out = subprocess.check_output(["pgrep", "-fl", "run_broker_paper"], text=True)
            return "run_broker_paper" in out
        except Exception:
            return False

    def _heartbeat_fields(self) -> dict[str, Any]:
        path = ROOT / "reports" / "bot_heartbeat.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return {key: payload[key] for key in HEARTBEAT_FIELDS if key in payload}

    def _set_market_data_type(self, ib) -> None:
        ib.reqMarketDataType(int(self.cfg.get("ib_market_data_type", 3)))

    def _read_journal(self, limit: int = 25) -> list[dict[str, Any]]:
        if not self.journal.exists():
            return []
        lines = self.journal.read_text(encoding="utf-8").splitlines()
        rows: list[dict[str, Any]] = []
        for line in reversed(lines[-200:]):
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            event = str(ev.get("event", "?"))
            detail_bits = []
            for k in ("side", "qty", "avg", "id", "msg", "reason", "sl", "tp", "equity", "bar"):
                if k in ev and ev[k] is not None:
                    detail_bits.append(f"{k}={ev[k]}")
            rows.append({"event": event, "detail": " · ".join(detail_bits) or json.dumps(ev)[:160]})
            if len(rows) >= limit:
                break
        return rows

    def _usd_tags(self, ib) -> dict[str, float]:
        # Use cached accountValues — do not call accountSummary() every poll (IB Error 322)
        out: dict[str, float] = {}
        for v in ib.accountValues():
            if v.currency != "USD":
                continue
            try:
                out[v.tag] = float(v.value)
            except (TypeError, ValueError):
                continue
        if "NetLiquidation" not in out:
            for v in ib.accountValues():
                if v.currency not in ("BASE", ""):
                    continue
                try:
                    out.setdefault(v.tag, float(v.value))
                except (TypeError, ValueError):
                    continue
        return out

    def _poll_once(self) -> dict[str, Any]:
        now = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
        data: dict[str, Any] = {
            "updated_at": now,
            "bot_running": self._bot_running(),
            "journal": self._read_journal(),
            "symbol": str(self.cfg.get("symbol", "EURUSD")),
            "algo": str(self.cfg.get("algo", self.cfg.get("signal_mode", ""))),
            "order_quantity": float(self.cfg.get("order_quantity", 0)),
            **self._heartbeat_fields(),
        }
        try:
            ib = self._connect()
            self._set_market_data_type(ib)
            # Ensure position stream is subscribed (otherwise positions() can look empty)
            try:
                ib.reqPositions()
                ib.sleep(0.3)
            except Exception:
                pass
            usd = self._usd_tags(ib)
            accts = ib.managedAccounts() or [""]
            equity = float(usd.get("NetLiquidation", 0.0))
            avail = float(usd.get("AvailableFunds", usd.get("ExcessLiquidity", 0.0)))
            if self._baseline is None and equity > 0:
                self._baseline = equity
            day_pnl = equity - self._baseline if self._baseline is not None else 0.0

            positions = []
            for p in ib.positions():
                qty = float(p.position)
                if abs(qty) < 1e-9:
                    continue
                side = "buy" if qty > 0 else "sell"
                positions.append(
                    {
                        "symbol": getattr(p.contract, "localSymbol", None) or p.contract.symbol,
                        "side": side,
                        "quantity": abs(qty),
                        "avg_price": float(p.avgCost),
                        "mark": None,
                        "unrealized_pnl": 0.0,
                    }
                )
            # Prefer portfolio unrealized when available
            by_sym = {getattr(x.contract, "localSymbol", x.contract.symbol): x for x in ib.portfolio()}
            for pos in positions:
                pf = by_sym.get(pos["symbol"])
                if pf is not None:
                    pos["unrealized_pnl"] = float(pf.unrealizedPNL or 0.0)
                    if getattr(pf, "marketPrice", None):
                        pos["mark"] = float(pf.marketPrice)

            # Live FX mark + computed unrealized (portfolio often empty for cash forex)
            mark = None
            try:
                from ib_insync import Forex

                sym = str(self.cfg.get("symbol", "EURUSD")).upper().replace("=X", "")
                contract = Forex(sym)
                ib.qualifyContracts(contract)
                ticker = ib.reqMktData(contract, "", False, False)
                ib.sleep(1.0)
                bid = float(ticker.bid or 0)
                ask = float(ticker.ask or 0)
                if bid > 0 and ask > 0:
                    mark = (bid + ask) / 2.0
                elif bid > 0:
                    mark = bid
                elif ask > 0:
                    mark = ask
                try:
                    ib.cancelMktData(contract)
                except Exception:
                    pass
            except Exception as exc:
                logger.debug("mark quote failed: %s", exc)

            open_pnl = 0.0
            # Prefer last fill price as entry (IB avgCost on FX is often not the trade price)
            entry_hint = None
            try:
                fills_sorted = sorted(ib.fills(), key=lambda x: x.execution.time, reverse=True)
                for f in fills_sorted:
                    if abs(float(f.execution.shares)) > 0:
                        entry_hint = float(f.execution.price)
                        break
            except Exception:
                pass

            for pos in positions:
                entry = entry_hint if entry_hint else float(pos["avg_price"])
                if mark is not None:
                    pos["mark"] = mark
                    if pos["side"] == "buy":
                        upnl = (mark - entry) * float(pos["quantity"])
                    else:
                        upnl = (entry - mark) * float(pos["quantity"])
                    pos["avg_price"] = entry
                    pos["unrealized_pnl"] = round(upnl, 2)
                open_pnl += float(pos.get("unrealized_pnl") or 0.0)

            # Day P&L = equity change; if flat equity, surface open unrealized so UI moves
            day_pnl = (equity - self._baseline) if self._baseline is not None else 0.0
            if abs(day_pnl) < 1e-9 and abs(open_pnl) > 1e-9:
                day_pnl = open_pnl

            open_orders = []
            try:
                ib.reqAllOpenOrders()
                ib.sleep(0.2)
            except Exception:
                pass
            active = {"PendingSubmit", "PreSubmitted", "Submitted", "ApiPending", "PendingCancel"}
            for t in ib.openTrades():
                status = str(t.orderStatus.status or "")
                if status not in active:
                    continue
                o = t.order
                price = o.lmtPrice if o.orderType == "LMT" else (o.auxPrice if o.orderType == "STP" else None)
                open_orders.append(
                    {
                        "id": o.orderId,
                        "action": o.action,
                        "type": o.orderType,
                        "quantity": float(o.totalQuantity),
                        "price": float(price) if price not in (None, 0, 0.0) else None,
                        "status": status,
                    }
                )

            fills = []
            for f in sorted(ib.fills(), key=lambda x: x.execution.time, reverse=True)[:30]:
                e = f.execution
                cr = f.commissionReport
                fills.append(
                    {
                        "time": str(e.time),
                        "side": e.side,
                        "quantity": float(e.shares),
                        "price": float(e.price),
                        "commission": float(cr.commission) if cr and cr.commission else 0.0,
                        "ref": e.orderRef or "",
                    }
                )

            data.update(
                {
                    "ib_connected": True,
                    "error": None,
                    "account_id": str(accts[0]),
                    "equity": equity,
                    "available_funds": avail,
                    "currency": "USD",
                    "is_paper": int(self.cfg.get("ib_port", 4002)) in {4002, 7497},
                    "day_pnl": day_pnl,
                    "open_pnl": open_pnl,
                    "mark": mark,
                    "baseline_equity": self._baseline,
                    "positions": positions,
                    "open_orders": open_orders,
                    "fills": fills,
                }
            )
        except Exception as exc:
            logger.warning("IB poll failed: %s", exc)
            data.update(
                {
                    "ib_connected": False,
                    "error": str(exc),
                    "account_id": None,
                    "equity": None,
                    "available_funds": None,
                    "currency": "USD",
                    "is_paper": True,
                    "day_pnl": None,
                    "positions": [],
                    "open_orders": [],
                    "fills": [],
                }
            )
            self._disconnect()
        return data

    def _loop(self) -> None:
        import asyncio

        # ib_insync needs an event loop in this worker thread
        asyncio.set_event_loop(asyncio.new_event_loop())
        while not self._stop.is_set():
            snap = self._poll_once()
            with self.lock:
                self.snapshot = snap
            self._stop.wait(2.0)


def make_handler(state: DeskState):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args) -> None:
            logger.debug("%s - " + fmt, self.address_string(), *args)

        def _send(self, code: int, body: bytes, content_type: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path in ("/", "/index.html"):
                self._send(200, INDEX_HTML.read_bytes(), "text/html; charset=utf-8")
                return
            if path == "/api/status":
                payload = json.dumps(state.get(), default=str).encode("utf-8")
                self._send(200, payload, "application/json; charset=utf-8")
                return
            self._send(404, b"not found", "text/plain; charset=utf-8")

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description="Aegis Desk web dashboard")
    parser.add_argument("--config", default=str(ROOT / "config_ib_paper_eurusd.yaml"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    cfg = load_config(args.config)
    journal = ROOT / "reports" / f"{cfg.get('test_name', 'ib_paper')}_journal.jsonl"
    state = DeskState(cfg, journal)
    state.start()

    handler = make_handler(state)
    httpd = ThreadingHTTPServer((args.host, args.port), handler)
    url = f"http://{args.host}:{args.port}/"
    logger.info("Aegis Desk at %s (IB readonly clientId=%s)", url, cfg.get("ib_dashboard_client_id", 71))
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        state.stop()
        httpd.server_close()


if __name__ == "__main__":
    main()
