"""Read-only MT5 + journal snapshot. Never calls disconnect()/shutdown()."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from aegis.optimizer.metrics import compute_trade_metrics, utc_hour_now
from aegis.optimizer.paths import HEARTBEAT, OPTIMIZER_DIR, REPORTS_DIR, ensure_runtime_dirs

logger = logging.getLogger(__name__)

DEAL_ENTRY_OUT = 1


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _read_jsonl(path: Path, limit: int = 50_000) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
                if len(rows) >= limit:
                    break
    except OSError:
        return rows
    return rows


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, default=str) + "\n")


def load_heartbeat(path: Path | None = None) -> dict[str, Any] | None:
    return _read_json(path or HEARTBEAT)


def journal_path_for(cfg: dict[str, Any], reports_dir: Path | None = None) -> Path:
    name = str(cfg.get("test_name") or "ib_paper")
    return (reports_dir or REPORTS_DIR) / f"{name}_journal.jsonl"


def trades_from_journal(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    trades: list[dict[str, Any]] = []
    for ev in events:
        if ev.get("event") != "flatten":
            continue
        trades.append(
            {
                "source": "journal_flatten",
                "symbol": ev.get("symbol"),
                "pnl": float(ev.get("pnl") or 0),
                "reason": ev.get("reason"),
                "ts": ev.get("ts") or ev.get("time"),
            }
        )
    return trades


def trades_from_deals(deals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    trades: list[dict[str, Any]] = []
    for d in deals:
        if int(d.get("entry") or 0) != DEAL_ENTRY_OUT:
            continue
        profit = float(d.get("profit") or 0) + float(d.get("commission") or 0) + float(d.get("swap") or 0)
        trades.append(
            {
                "source": "mt5_deal",
                "ticket": d.get("ticket"),
                "symbol": d.get("symbol"),
                "pnl": profit,
                "side": d.get("side"),
                "qty": d.get("qty"),
                "price": d.get("price"),
                "ts": d.get("time"),
                "comment": d.get("comment"),
            }
        )
    return trades


def journal_counts(events: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    flatten_reasons: dict[str, int] = {}
    last_start: dict[str, Any] = {}
    for ev in events:
        name = str(ev.get("event") or "unknown")
        counts[name] = counts.get(name, 0) + 1
        if name == "flatten":
            reason = str(ev.get("reason") or "unknown")
            flatten_reasons[reason] = flatten_reasons.get(reason, 0) + 1
        if name == "start":
            last_start = ev
    return {
        "event_counts": counts,
        "flatten_reasons": flatten_reasons,
        "spread_skips": int(counts.get("spread_skip", 0)),
        "orders": int(counts.get("order", 0)),
        "rejects": int(counts.get("halt", 0) + counts.get("hr_halt", 0)),
        "strategy_id": last_start.get("engine") or last_start.get("algo"),
        "start_symbols": last_start.get("symbols"),
    }


def _mt5_payload(engine: Any, lookback_days: int) -> dict[str, Any]:
    acct = engine.account()
    raw = acct.raw if isinstance(acct.raw, dict) else {}
    positions = []
    for p in engine.positions():
        positions.append(
            {
                "symbol": p.symbol,
                "side": p.side,
                "quantity": p.quantity,
                "avg_price": p.avg_price,
                "unrealized_pnl": p.unrealized_pnl,
                "ticket": getattr(p, "ticket", ""),
                "stop_loss": getattr(p, "stop_loss", 0.0),
                "take_profit": getattr(p, "take_profit", 0.0),
            }
        )
    deals = engine.history_deals(lookback_days) if hasattr(engine, "history_deals") else []
    orders = engine.history_orders(lookback_days) if hasattr(engine, "history_orders") else []
    return {
        "mt5_ok": True,
        "account_id": acct.account_id,
        "balance": float(raw.get("balance") or acct.equity),
        "equity": acct.equity,
        "margin_free": acct.available_funds,
        "is_paper": acct.is_paper,
        "positions": positions,
        "open": len(positions),
        "deals": deals,
        "orders": orders,
    }


def collect_snapshot(
    cfg: dict[str, Any],
    *,
    engine: Any | None = None,
    no_mt5: bool = False,
    lookback_days: int = 14,
    reports_dir: Path | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    """Merge MT5 history (optional) with journals/heartbeat. Never shutdown."""
    ensure_runtime_dirs()
    reports = reports_dir or REPORTS_DIR
    hb = load_heartbeat(reports / "bot_heartbeat.json")
    journal = _read_jsonl(journal_path_for(cfg, reports))
    jcounts = journal_counts(journal)
    jtrades = trades_from_journal(journal)

    mt5_error = ""
    mt5_data: dict[str, Any] = {
        "mt5_ok": False,
        "account_id": "",
        "balance": None,
        "equity": None,
        "margin_free": None,
        "is_paper": None,
        "positions": [],
        "open": int((hb or {}).get("open") or 0),
        "deals": [],
        "orders": [],
    }
    if not no_mt5:
        try:
            if engine is None:
                from aegis.engines import create_engine

                engine = create_engine(cfg)
                if hasattr(engine, "connect_readonly"):
                    engine.connect_readonly()
                else:
                    engine.connect()
            mt5_data = _mt5_payload(engine, lookback_days)
        except Exception as exc:
            mt5_error = str(exc)
            logger.warning("optimizer snapshot MT5 fallback to journals: %s", exc)

    deal_trades = trades_from_deals(mt5_data.get("deals") or [])
    trades = deal_trades or jtrades
    equity = mt5_data.get("equity")
    if equity is None and hb and hb.get("equity") is not None:
        equity = float(hb["equity"])
    start_eq = float(cfg.get("starting_equity") or equity or 0)
    metrics = compute_trade_metrics(trades, starting_equity=start_eq)
    now = datetime.now(timezone.utc)
    payload = {
        "ts": now.isoformat(),
        "session_hour_utc": utc_hour_now(),
        "test_name": cfg.get("test_name"),
        "algo": cfg.get("algo") or cfg.get("signal_mode"),
        "symbols": cfg.get("symbols") or [cfg.get("symbol")],
        "mt5_error": mt5_error,
        "heartbeat": hb,
        "heartbeat_age_s": (now.timestamp() - float(hb["ts"])) if hb and hb.get("ts") else None,
        **mt5_data,
        **jcounts,
        "metrics": metrics,
        "trade_source": "mt5_deals" if deal_trades else ("journal_flatten" if jtrades else "none"),
        "trade_count_used": len(trades),
    }
    if persist:
        metrics_dir = OPTIMIZER_DIR / "metrics"
        (metrics_dir / "latest.json").write_text(
            json.dumps(payload, default=str, indent=2), encoding="utf-8"
        )
        if equity is not None:
            _append_jsonl(
                metrics_dir / "equity.jsonl",
                {"ts": payload["ts"], "equity": equity, "open": payload.get("open")},
            )
        for t in trades[-500:]:
            row = dict(t)
            row.setdefault("snapshot_ts", payload["ts"])
            _append_jsonl(metrics_dir / "trades.jsonl", row)
    return payload
