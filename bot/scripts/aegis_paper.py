#!/usr/bin/env python3
"""Single operator command for the local Aegis IBKR paper stack."""
from __future__ import annotations

import argparse
import json
import os
import plistlib
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aegis.config import load_config  # noqa: E402
from aegis.engines import create_engine  # noqa: E402
from aegis.engines.ibkr_order_state import (  # noqa: E402
    cancelling_trades,
    working_trades,
)
from aegis.paper_control import (  # noqa: E402
    assert_paper_mutation_allowed,
    heartbeat_max_age,
    paper_execution_enabled,
)


def service_label() -> str:
    return "com.aegis.ibpaper"


def launch_agent_payload(root: Path, python: Path, config: Path) -> dict[str, Any]:
    reports = root / "reports"
    return {
        "Label": service_label(),
        "ProgramArguments": [
            str(python),
            "-u",
            str(root / "scripts" / "watchdog.py"),
            "--config",
            str(config),
        ],
        "WorkingDirectory": str(root),
        "RunAtLoad": True,
        "KeepAlive": True,
        "ProcessType": "Interactive",
        "ThrottleInterval": 5,
        "StandardOutPath": str(reports / "watchdog_launchd.log"),
        "StandardErrorPath": str(reports / "watchdog_launchd.log"),
        "EnvironmentVariables": {
            "PYTHONUNBUFFERED": "1",
            "PYTHONPYCACHEPREFIX": "/private/tmp/aegis-paper-pycache",
        },
    }


def heartbeat_status(
    heartbeat: dict[str, Any] | None,
    *,
    now: float | None = None,
    max_age: float = 15.0,
) -> dict[str, Any]:
    current = time.time() if now is None else float(now)
    payload = heartbeat or {}
    timestamp = float(payload.get("ts", 0.0) or 0.0)
    age = max(0.0, current - timestamp) if timestamp else None
    status = {
        "running": bool(timestamp and age is not None and age <= max_age),
        "pid": int(payload.get("pid", 0) or 0) or None,
        "age_seconds": age,
        "status": payload.get("status"),
        "updated_at": payload.get("iso"),
    }
    for key in (
        "symbol",
        "local_symbol",
        "contract_multiplier",
        "tick_value_usd",
        "feed_age_seconds",
        "feed_usable",
        "market_data_type",
        "records",
        "usable_records",
        "trades_today",
        "modeled_costs_today",
        "paper_promoted",
        "gate_reason",
    ):
        if key in payload:
            status[key] = payload[key]
    return status


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None


def _tcp_up(host: str, port: int, timeout: float = 0.4) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _service_target() -> str:
    return f"gui/{os.getuid()}/{service_label()}"


def _service_loaded() -> bool:
    result = subprocess.run(
        ["launchctl", "print", _service_target()],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def _order_summary(trade) -> dict[str, Any]:
    order = trade.order
    return {
        "id": int(order.orderId),
        "client_id": int(getattr(order, "clientId", 0) or 0),
        "perm_id": int(getattr(order, "permId", 0) or 0),
        "action": str(order.action),
        "type": str(order.orderType),
        "quantity": float(order.totalQuantity),
        "status": str(getattr(trade.orderStatus, "status", "") or ""),
    }


def _ib_readonly_status(cfg: dict[str, Any]) -> dict[str, Any]:
    from ib_insync import IB

    ib = IB()
    try:
        ib.connect(
            str(cfg.get("ib_host", "127.0.0.1")),
            int(cfg.get("ib_port", 4002)),
            clientId=int(cfg.get("ib_status_client_id", 79)),
            readonly=True,
            timeout=5,
        )
        values: dict[str, str] = {}
        for value in ib.accountValues():
            if value.currency == "USD":
                values[value.tag] = value.value
        if "NetLiquidation" not in values:
            for value in ib.accountValues():
                if value.currency in {"BASE", ""}:
                    values.setdefault(value.tag, value.value)

        positions = []
        for position in ib.positions():
            quantity = float(position.position)
            if abs(quantity) < 1e-12:
                continue
            positions.append(
                {
                    "symbol": f"{position.contract.symbol}{getattr(position.contract, 'currency', '')}",
                    "quantity": quantity,
                    "avg_price": float(position.avgCost),
                }
            )

        refreshed = list(ib.reqAllOpenOrders() or [])
        working = [_order_summary(trade) for trade in working_trades(refreshed)]
        cancelling = [_order_summary(trade) for trade in cancelling_trades(refreshed)]
        latest_fill = None
        fills = sorted(
            ib.fills(),
            key=lambda fill: getattr(fill.execution, "time", ""),
            reverse=True,
        )
        if fills:
            execution = fills[0].execution
            report = fills[0].commissionReport
            latest_fill = {
                "time": str(execution.time),
                "side": str(execution.side),
                "quantity": float(execution.shares),
                "price": float(execution.price),
                "commission": float(report.commission or 0.0) if report else 0.0,
                "ref": str(execution.orderRef or ""),
            }
        accounts = ib.managedAccounts() or [""]
        return {
            "connected": True,
            "paper": int(cfg.get("ib_port", 4002)) in {4002, 7497},
            "account_id": str(accounts[0]),
            "equity": float(values["NetLiquidation"]) if "NetLiquidation" in values else None,
            "available_funds": float(values.get("AvailableFunds", values.get("ExcessLiquidity", 0))),
            "positions": positions,
            "working_orders": working,
            "cancelling_orders": cancelling,
            "last_fill": latest_fill,
        }
    except Exception as exc:
        return {
            "connected": False,
            "paper": int(cfg.get("ib_port", 4002)) in {4002, 7497},
            "error": str(exc),
            "positions": [],
            "working_orders": [],
            "cancelling_orders": [],
            "last_fill": None,
        }
    finally:
        if ib.isConnected():
            ib.disconnect()


def collect_status(cfg: dict[str, Any]) -> dict[str, Any]:
    host = str(cfg.get("ib_host", "127.0.0.1"))
    gateway_port = int(cfg.get("ib_port", 4002))
    dashboard_port = int(cfg.get("dashboard_port", 8787))
    gateway_up = _tcp_up(host, gateway_port)
    broker = _ib_readonly_status(cfg) if gateway_up else {
        "connected": False,
        "paper": gateway_port in {4002, 7497},
        "error": "gateway port is closed",
        "positions": [],
        "working_orders": [],
        "cancelling_orders": [],
        "last_fill": None,
    }
    return {
        "gateway": {"up": gateway_up, "host": host, "port": gateway_port},
        "launch_agent_loaded": _service_loaded(),
        "bot": heartbeat_status(
            _read_json(ROOT / "reports" / "bot_heartbeat.json"),
            max_age=heartbeat_max_age(cfg),
        ),
        "dashboard": {
            "up": _tcp_up(str(cfg.get("dashboard_host", "127.0.0.1")), dashboard_port),
            "url": f"http://127.0.0.1:{dashboard_port}/",
        },
        "broker": broker,
    }


def _print_status(status: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(status, indent=2, sort_keys=True, default=str))
        return
    broker = status["broker"]
    print(f"Gateway: {'UP' if status['gateway']['up'] else 'DOWN'} {status['gateway']['host']}:{status['gateway']['port']}")
    print(f"LaunchAgent: {'LOADED' if status['launch_agent_loaded'] else 'STOPPED'}")
    print(f"Bot: {'UP' if status['bot']['running'] else 'STOPPED'}")
    bot = status["bot"]
    if bot.get("symbol"):
        print(f"Instrument: {bot.get('local_symbol') or bot.get('symbol')}")
        if bot.get("symbol") == "MGC":
            print(
                "MGC feed: "
                f"{'USABLE' if bot.get('feed_usable') else 'WAITING'} "
                f"age={bot.get('feed_age_seconds')}s records={bot.get('usable_records', 0)} "
                f"type={bot.get('market_data_type', 'unknown')}"
            )
            print(
                f"MGC trades today: {bot.get('trades_today', 0)} "
                f"modeled costs=${float(bot.get('modeled_costs_today', 0) or 0):,.2f}"
            )
            print(
                f"Paper promoted: {bool(bot.get('paper_promoted', False))} "
                f"gate={bot.get('gate_reason', 'unknown')}"
            )
    print(f"Dashboard: {'UP' if status['dashboard']['up'] else 'STOPPED'} {status['dashboard']['url']}")
    print(f"IB: {'CONNECTED' if broker.get('connected') else 'UNAVAILABLE'} paper={broker.get('paper')}")
    if broker.get("connected"):
        print(f"Equity: ${broker.get('equity', 0):,.2f}")
        print(f"Positions: {len(broker.get('positions', []))}")
        print(f"Working orders: {len(broker.get('working_orders', []))}")
        print(f"Cancelling orders: {len(broker.get('cancelling_orders', []))}")
        print(f"Last fill: {broker.get('last_fill') or 'none'}")
    else:
        print(f"IB error: {broker.get('error', 'unknown')}")


def _plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{service_label()}.plist"


def start_service(config: Path) -> None:
    if _service_loaded():
        print("Aegis paper LaunchAgent is already loaded")
        return
    current = heartbeat_status(_read_json(ROOT / "reports" / "bot_heartbeat.json"))
    if current["running"] or _tcp_up("127.0.0.1", 8787):
        raise RuntimeError("manual bot/dashboard process is already active; stop it before launchd takeover")

    plist_path = _plist_path()
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    # Preserve the virtualenv launcher path. Resolving this symlink writes the
    # system/Xcode interpreter into launchd and discards the repo environment.
    python = Path(os.path.abspath(sys.executable))
    payload = launch_agent_payload(ROOT, python, config.resolve())
    with plist_path.open("wb") as handle:
        plistlib.dump(payload, handle, sort_keys=False)
    subprocess.run(
        ["launchctl", "bootstrap", f"gui/{os.getuid()}", str(plist_path)],
        check=True,
    )
    print(f"Started {service_label()} (paper observation mode follows config safety gates)")


def _mutate_broker(cfg: dict[str, Any], action: str) -> None:
    assert_paper_mutation_allowed(cfg)
    control_cfg = dict(cfg)
    control_cfg["ib_client_id"] = int(cfg.get("ib_control_client_id", 72))
    engine = create_engine(control_cfg)
    try:
        engine.connect()
        account = engine.account()
        if not account.is_paper:
            raise RuntimeError("broker did not identify as paper; refusing mutation")
        if action == "cancel-all":
            result = engine.cancel_all_orders()
        else:
            result = engine.flatten_positions(str(cfg.get("symbol", "EURUSD")))
        print(result.message)
        if not result.ok:
            raise RuntimeError(result.message)
    finally:
        engine.disconnect()


def stop_service(cfg: dict[str, Any], *, process_only: bool) -> None:
    if _service_loaded():
        subprocess.run(["launchctl", "bootout", _service_target()], check=True)
        deadline = time.monotonic() + 10.0
        while _service_loaded():
            if time.monotonic() >= deadline:
                raise RuntimeError(f"timed out waiting for {service_label()} to unload")
            time.sleep(0.1)
        print(f"Stopped {service_label()}")
    else:
        print("Aegis paper LaunchAgent is not loaded")
    # Quiesce the signal process before touching broker state so it cannot race
    # the control client by opening a new position during flatten.
    if not process_only and paper_execution_enabled(cfg):
        _mutate_broker(cfg, "flatten")


def main() -> None:
    parser = argparse.ArgumentParser(description="Control the Aegis IBKR paper stack")
    parser.add_argument("action", choices=("start", "stop", "restart", "status", "flatten", "cancel-all"))
    parser.add_argument("--config", default=str(ROOT / "config_ib_paper_eurusd.yaml"))
    parser.add_argument("--json", action="store_true", help="JSON output for status")
    parser.add_argument(
        "--process-only",
        action="store_true",
        help="stop processes without flattening a paper position",
    )
    args = parser.parse_args()
    config = Path(args.config).expanduser().resolve()
    cfg = load_config(config)

    if args.action == "status":
        _print_status(collect_status(cfg), args.json)
    elif args.action == "start":
        start_service(config)
    elif args.action == "stop":
        stop_service(cfg, process_only=args.process_only)
    elif args.action == "restart":
        stop_service(cfg, process_only=args.process_only)
        start_service(config)
    else:
        _mutate_broker(cfg, args.action)


if __name__ == "__main__":
    main()
