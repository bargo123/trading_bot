"""Direct, read-only MT5 raw-feed diagnostic.

This intentionally calls ``symbol_info_tick`` and ``copy_ticks_range`` rather
than the AEGIS Quote normalization layer.  It never sends, modifies, or
closes an order and does not call ``mt5.shutdown()`` after a read-only attach.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, TextIO

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aegis.config import load_config  # noqa: E402
from aegis.engines.mt5 import MT5Engine  # noqa: E402


def _value(source: Any, key: str, default: Any = None) -> Any:
    if isinstance(source, dict):
        return source.get(key, default)
    return getattr(source, key, default)


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None


def _raw_time_s(tick: Any) -> float | None:
    msc = _number(_value(tick, "time_msc", 0))
    if msc is not None and msc > 0:
        return msc / 1000.0
    seconds = _number(_value(tick, "time", 0))
    return seconds if seconds is not None and seconds > 0 else None


def _clock_offset_s(timestamp_s: float | None, local_now_s: float) -> float:
    """Estimate a coarse broker-clock offset without altering raw evidence."""
    if timestamp_s is None:
        return 0.0
    delta = float(timestamp_s) - float(local_now_s)
    return float(round(delta / (15 * 60)) * (15 * 60)) if abs(delta) >= 450 else 0.0


def _json_value(value: Any) -> Any:
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def raw_tick_record(api: Any, *, requested_symbol: str, resolved_symbol: str, local_now_s: float) -> dict[str, Any]:
    """Read one raw ``symbol_info_tick`` sample, with no Quote conversion."""
    tick = api.symbol_info_tick(resolved_symbol)
    if tick is None:
        return {
            "event": "raw_tick",
            "requested_symbol": requested_symbol,
            "resolved_symbol": resolved_symbol,
            "local_utc_now": local_now_s,
            "time_time": local_now_s,
            "tick": None,
            "error": _json_value(api.last_error()),
        }
    return {
        "event": "raw_tick",
        "requested_symbol": requested_symbol,
        "resolved_symbol": resolved_symbol,
        "local_utc_now": local_now_s,
        "time_time": local_now_s,
        "tick": {
            "time": _json_value(_value(tick, "time", 0)),
            "time_msc": _json_value(_value(tick, "time_msc", 0)),
            "bid": _json_value(_value(tick, "bid", 0)),
            "ask": _json_value(_value(tick, "ask", 0)),
            "last": _json_value(_value(tick, "last", 0)),
            "flags": _json_value(_value(tick, "flags", 0)),
        },
    }


def _copy_ticks_newest(api: Any, symbol: str, *, window_s: int = 30) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    start = now - timedelta(seconds=max(1, int(window_s)))
    flags = int(getattr(api, "COPY_TICKS_ALL", 0))
    source = "copy_ticks_range"
    rows = api.copy_ticks_range(symbol, start, now, flags)
    if rows is None or len(rows) == 0:
        copier = getattr(api, "copy_ticks_from", None)
        if callable(copier):
            source = "copy_ticks_from"
            rows = copier(symbol, start, 1000, flags)
    rows = rows if rows is not None else []
    newest: float | None = None
    for row in rows:
        msc = _number(_value(row, "time_msc", 0))
        seconds = msc / 1000.0 if msc and msc > 0 else _number(_value(row, "time", 0))
        if seconds is not None:
            newest = seconds if newest is None else max(newest, seconds)
    return {
        "source": source,
        "count": len(rows),
        "newest_raw_time_s": newest,
        "queried_at_s": now.timestamp(),
    }


def classify_tick_sources(
    *,
    symbol_time_utc_s: float | None,
    copy_time_utc_s: float | None,
    now_s: float,
    stale_after_s: float = 5.0,
    desync_tolerance_s: float = 1.0,
) -> str:
    """Classify normalized source timestamps without manufacturing freshness."""
    symbol_age = float("inf") if symbol_time_utc_s is None else now_s - symbol_time_utc_s
    copy_age = float("inf") if copy_time_utc_s is None else now_s - copy_time_utc_s
    if symbol_age < -desync_tolerance_s or copy_age < -desync_tolerance_s:
        return "TIMESTAMP_STILL_WRONG"
    if (
        copy_time_utc_s is not None
        and (symbol_time_utc_s is None or copy_time_utc_s > symbol_time_utc_s + desync_tolerance_s)
    ):
        return "MT5_PYTHON_TICK_CACHE_DESYNC"
    if symbol_age > stale_after_s and copy_age > stale_after_s:
        return "BROKER_FEED_STALLED"
    if symbol_time_utc_s is None and copy_time_utc_s is None:
        return "UNKNOWN_FEED_FAILURE"
    return "HEALTHY"


def source_series_advancing(values: list[float | None]) -> bool:
    """Return true only when a source's newest timestamp actually advances."""
    previous: float | None = None
    for value in values:
        if value is None:
            continue
        current = float(value)
        if previous is not None and current > previous:
            return True
        previous = current
    return False


def _health_payload(api: Any) -> dict[str, Any]:
    term = api.terminal_info()
    account = api.account_info()
    return {
        "event": "terminal_health",
        "version": _json_value(api.version()),
        "last_error": _json_value(api.last_error()),
        "terminal_info": {
            key: _json_value(_value(term, key))
            for key in ("connected", "trade_allowed", "name", "path")
        },
        "account_info": {
            key: _json_value(_value(account, key))
            for key in ("login", "server", "trade_mode", "trade_allowed", "trade_expert")
        },
    }


def _symbol_payload(api: Any, engine: MT5Engine, requested: str) -> tuple[dict[str, Any], str | None]:
    try:
        resolved = engine._resolve_symbol(requested)
        selected = bool(api.symbol_select(resolved, True))
        info = api.symbol_info(resolved)
        return ({
            "event": "symbol_subscription",
            "requested_symbol": requested,
            "resolved_symbol": resolved,
            "symbol_select": selected,
            "visible": _json_value(_value(info, "visible")),
            "select": _json_value(_value(info, "select")),
            "trade_mode": _json_value(_value(info, "trade_mode")),
            "session_deals": _json_value(_value(info, "session_deals")),
            "session_buy_orders": _json_value(_value(info, "session_buy_orders")),
            "session_sell_orders": _json_value(_value(info, "session_sell_orders")),
        }, resolved)
    except Exception as exc:
        return ({
            "event": "symbol_subscription",
            "requested_symbol": requested,
            "resolved_symbol": None,
            "symbol_select": False,
            "error": f"{type(exc).__name__}:{exc}",
        }, None)


def run_diagnostic(
    config_path: Path,
    *,
    symbols: tuple[str, ...] = ("EURUSD", "GBPUSD", "USDJPY"),
    duration_s: float = 60.0,
    interval_s: float = 0.2,
    copy_interval_s: float = 5.0,
    output: Path | None = None,
) -> dict[str, Any]:
    cfg = load_config(config_path)
    engine = MT5Engine(cfg)
    engine.connect_readonly()
    api = engine._api()
    sink: TextIO | None = output.open("w", encoding="utf-8") if output else None

    def emit(payload: dict[str, Any]) -> None:
        line = json.dumps(payload, separators=(",", ":"), default=str)
        if sink is not None:
            sink.write(line + "\n")
            sink.flush()
        else:
            print(line, flush=True)

    emit(_health_payload(api))
    resolved: dict[str, str] = {}
    stats: dict[str, dict[str, Any]] = {}
    for requested in symbols:
        payload, name = _symbol_payload(api, engine, requested)
        emit(payload)
        if name is not None:
            resolved[requested] = name
            stats[requested] = {
                "requested_symbol": requested,
                "resolved_symbol": name,
                "raw_samples": [],
                "time_msc": set(),
                "bid_ask": set(),
                "max_gap_s": 0.0,
                "last_signature": None,
                "last_advance_s": None,
                "copy": {},
                "copy_newest_series": [],
            }

    started = time.time()
    next_copy = started
    try:
        while time.time() - started < max(0.0, float(duration_s)):
            local_now = time.time()
            for requested, name in resolved.items():
                record = raw_tick_record(
                    api,
                    requested_symbol=requested,
                    resolved_symbol=name,
                    local_now_s=local_now,
                )
                emit(record)
                tick = record.get("tick")
                stat = stats[requested]
                if not isinstance(tick, dict):
                    continue
                raw_time = _raw_time_s(tick)
                bid = _number(tick.get("bid"))
                ask = _number(tick.get("ask"))
                signature = (tick.get("time_msc"), bid, ask)
                stat["raw_samples"].append({"time_s": raw_time, "local_s": local_now})
                if tick.get("time_msc"):
                    stat["time_msc"].add(tick.get("time_msc"))
                stat["bid_ask"].add((bid, ask))
                if stat["last_signature"] is None or signature != stat["last_signature"]:
                    previous = stat["last_advance_s"]
                    if previous is not None:
                        stat["max_gap_s"] = max(stat["max_gap_s"], local_now - previous)
                    stat["last_advance_s"] = local_now
                stat["last_signature"] = signature
            if local_now >= next_copy:
                for requested, name in resolved.items():
                    stat = stats[requested]
                    stat["copy"] = _copy_ticks_newest(api, name)
                    newest = stat["copy"].get("newest_raw_time_s")
                    stat["copy_newest_series"].append(newest)
                next_copy = local_now + max(0.5, float(copy_interval_s))
            time.sleep(max(0.01, float(interval_s)))
    finally:
        if sink is not None:
            sink.close()

    now_s = time.time()
    reports: dict[str, Any] = {}
    statuses: list[str] = []
    for requested, stat in stats.items():
        samples = stat["raw_samples"]
        raw_times = [row["time_s"] for row in samples if row["time_s"] is not None]
        offsets = [row["time_s"] - row["local_s"] for row in samples if row["time_s"] is not None]
        offset = float(round(statistics.median(offsets) / (15 * 60)) * (15 * 60)) if offsets else 0.0
        newest_raw = max(raw_times) if raw_times else None
        normalized_newest = newest_raw - offset if newest_raw is not None else None
        copy = stat["copy"]
        copy_raw = copy.get("newest_raw_time_s") if isinstance(copy, dict) else None
        copy_offset = _clock_offset_s(copy_raw, now_s)
        copy_utc = copy_raw - copy_offset if copy_raw is not None else None
        status = classify_tick_sources(
            symbol_time_utc_s=normalized_newest,
            copy_time_utc_s=copy_utc,
            now_s=now_s,
        )
        statuses.append(status)
        reports[requested] = {
            "requested_symbol": requested,
            "resolved_symbol": stat["resolved_symbol"],
            "raw_ticks_observed": len(samples),
            "unique_time_msc": len(stat["time_msc"]),
            "unique_bid_ask_changes": len(stat["bid_ask"]),
            "raw_tick_age_vs_local_utc_s": (now_s - newest_raw) if newest_raw is not None else None,
            "server_clock_offset_s": offset,
            "newest_raw_tick_age_s": (now_s - normalized_newest) if normalized_newest is not None else None,
            "maximum_period_without_advancement_s": stat["max_gap_s"],
            "copy_ticks_source": copy.get("source") if isinstance(copy, dict) else None,
            "copy_ticks_count": copy.get("count") if isinstance(copy, dict) else 0,
            "copy_ticks_advancing": source_series_advancing(stat["copy_newest_series"]),
            "copy_ticks_newest_age_s": (now_s - copy_utc) if copy_utc is not None else None,
            "source_classification": status,
        }
    overall = (
        "MT5_PYTHON_TICK_CACHE_DESYNC" if "MT5_PYTHON_TICK_CACHE_DESYNC" in statuses
        else "BROKER_FEED_STALLED" if statuses and all(s == "BROKER_FEED_STALLED" for s in statuses)
        else "SYMBOL_ALIAS_WRONG" if len(resolved) != len(symbols)
        else "HEALTHY" if statuses and all(s == "HEALTHY" for s in statuses)
        else "UNKNOWN_FEED_FAILURE"
    )
    result = {
        "event": "feed_summary",
        "feed_status": overall,
        "feed_stall_detected": overall == "BROKER_FEED_STALLED",
        "symbol_info_tick_advancing": any(row["unique_time_msc"] > 1 for row in reports.values()),
        "copy_ticks_advancing": any(row["copy_ticks_advancing"] for row in reports.values()),
        "symbols": reports,
    }
    print(json.dumps(result, indent=2, default=str), flush=True)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Direct read-only MT5 raw-feed diagnostic")
    parser.add_argument("--config", type=Path, default=ROOT / "config_mt5_demo_firehose_hw.yaml")
    parser.add_argument("--duration", type=float, default=60.0)
    parser.add_argument("--interval-ms", type=float, default=200.0)
    parser.add_argument("--copy-interval", type=float, default=5.0)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--symbols", nargs="+", default=["EURUSD", "GBPUSD", "USDJPY"])
    args = parser.parse_args(argv)
    run_diagnostic(
        args.config,
        symbols=tuple(args.symbols),
        duration_s=args.duration,
        interval_s=float(args.interval_ms) / 1000.0,
        copy_interval_s=args.copy_interval,
        output=args.output,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
