#!/usr/bin/env python3
"""Read-only live viewer for the broker Firehose journal and heartbeat."""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aegis.config import load_config  # noqa: E402


IMPORTANT_EVENTS = {
    "candidate_blocked",
    "global_opportunity_discovered",
    "global_opportunity_allocation",
    "quote_unusable_for_scan",
    "quote_not_executable_for_send",
    "quote_refresh_failed",
    "quote_refresh_invalid",
    "virtual_geometry_reject",
    "broker_geometry_reject",
    "sizing_skip",
    "margin_precheck_skip",
    "oms_reject",
    "order_blocked",
    "order_check",
    "order",
    "firehose_open",
    "rapid_exit_close",
    "pm_exit",
    "pm_lock",
    "confirmed_close_finalization",
    "firehose_close_unconfirmed",
    "firehose_close",
    "outcome_learning",
    "outcome_learning_error",
    "intel_brain_skip",
    "open_skip",
    "spread_skip",
    "exploration_limit_skip",
}

BLOCKED_EVENTS = {
    "candidate_blocked",
    "quote_unusable_for_scan",
    "quote_not_executable_for_send",
    "quote_refresh_failed",
    "quote_refresh_invalid",
    "virtual_geometry_reject",
    "broker_geometry_reject",
    "sizing_skip",
    "margin_precheck_skip",
    "oms_reject",
    "order_blocked",
    "open_skip",
    "spread_skip",
    "exploration_limit_skip",
    "intel_brain_skip",
}


def runtime_paths(config_path: Path) -> tuple[Path, Path]:
    """Resolve the same report paths used by ``run_broker_paper.py``."""
    config_path = Path(config_path).expanduser().resolve()
    cfg = load_config(config_path)
    test_name = Path(str(cfg.get("test_name") or "ib_paper")).name
    report_dir = config_path.parent / "reports"
    return report_dir / f"{test_name}_journal.jsonl", report_dir / "bot_heartbeat.json"


def _first(source: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = source.get(key)
        if value is not None and value != "":
            return value
    return None


def _timestamp(event: Mapping[str, Any]) -> str:
    value = _first(event, "timestamp", "observed_at", "ts", "bar", "bar_time")
    if isinstance(value, (int, float)):
        return time.strftime("%H:%M:%S", time.localtime(float(value)))
    return str(value or "-")


def _side(value: Any) -> str | None:
    text = str(value or "").strip()
    return text.upper() if text else None


def _reasons(event: Mapping[str, Any]) -> list[str]:
    raw = event.get("reasons")
    if isinstance(raw, (list, tuple)):
        values = [str(value) for value in raw if str(value)]
        if values:
            return values
    for key in ("reject_reason", "reason", "error", "message", "msg"):
        value = event.get(key)
        if value:
            return [str(value)]
    return []


def expand_event(event: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Flatten nested brain candidate evaluations into displayable events."""
    raw = dict(event)
    evaluations = raw.get("candidate_evaluations")
    if isinstance(evaluations, list) and evaluations:
        expanded: list[dict[str, Any]] = []
        for evaluation in evaluations:
            if not isinstance(evaluation, Mapping):
                continue
            reasons = [str(value) for value in evaluation.get("reasons") or []]
            expanded.append({
                "event": "candidate_blocked",
                "source_event": str(raw.get("event") or ""),
                "timestamp": _first(raw, "timestamp", "observed_at", "ts", "bar"),
                "candidate_id": _first(
                    evaluation, "candidate_id", "variant_id", "hypothesis_id"
                ),
                "symbol": _first(evaluation, "symbol") or raw.get("symbol"),
                "side": _first(evaluation, "side"),
                "mechanism": _first(evaluation, "mechanism", "family")
                or raw.get("setup_family"),
                "horizon_s": _first(evaluation, "horizon_s", "max_hold_s"),
                "lane": _first(evaluation, "lane") or raw.get("exploration_lane"),
                "p_captured_win": _first(
                    evaluation, "p_captured_win", "p_green", "probability"
                ),
                "selection_score": _first(evaluation, "selection_score"),
                "expected_net_ev": _first(
                    evaluation, "expected_net_value_usd", "expected_net_ev"
                ),
                "spread": _first(evaluation, "spread", "spread_pips"),
                "quote_age_s": _first(evaluation, "quote_age_s"),
                "entry": _first(evaluation, "entry", "econ_entry"),
                "stop": _first(evaluation, "stop", "virtual_stop", "econ_invalidation"),
                "target": _first(evaluation, "target", "virtual_target", "econ_target"),
                "lots": _first(evaluation, "lots", "quantity", "requested_lot"),
                "risk_usd": _first(evaluation, "risk_usd", "estimated_risk_usd"),
                "distance_to_eligibility": evaluation.get("distance_to_eligibility") or {},
                "reject_reason": ", ".join(reasons) or str(
                    _first(raw, "exploration_skip", "reason") or "UNKNOWN"
                ),
                "state": "GENERATED -> BUY_SELL_EVALUATED -> BLOCKED",
                "final_status": "BLOCKED",
                "candidate_details": dict(evaluation),
            })
        if expanded:
            return expanded

    if raw.get("event") == "intel_brain_skip":
        prediction = raw.get("short_horizon_prediction")
        prediction = prediction if isinstance(prediction, Mapping) else {}
        return [{
            **raw,
            "event": "candidate_blocked",
            "source_event": "intel_brain_skip",
            "candidate_id": _first(raw, "variant_id", "hypothesis_id", "thesis_key"),
            "mechanism": _first(raw, "setup_family", "micro_mechanism"),
            "horizon_s": _first(raw, "search_horizon_s", "max_hold_s"),
            "p_captured_win": _first(raw, "p_captured_win", "econ_p_win")
            or prediction.get("probability"),
            "expected_net_ev": _first(raw, "econ_expected_net_usd", "expected_net_ev"),
            "reject_reason": str(
                _first(raw, "exploration_skip", "short_horizon_gate", "reason")
                or "UNKNOWN"
            ),
            "state": "GENERATED -> BUY_SELL_EVALUATED -> BLOCKED",
            "final_status": "BLOCKED",
        }]
    return [raw]


def _event_symbol(event: Mapping[str, Any]) -> str:
    symbol = event.get("symbol")
    if symbol:
        return str(symbol).upper()
    details = event.get("candidate_details")
    if isinstance(details, Mapping) and details.get("symbol"):
        return str(details["symbol"]).upper()
    return ""


def is_blocked(event: Mapping[str, Any]) -> bool:
    name = str(event.get("event") or "")
    if name in BLOCKED_EVENTS:
        return True
    if name == "firehose_funnel.v1":
        return not bool(event.get("submitted") or event.get("filled")) and str(
            event.get("terminal") or ""
        ) not in {"GLOBAL_SELECTED", "EXPLORATION_ELIGIBLE", "VALIDATED_MATCH"}
    if name in {"order", "order_check"}:
        return event.get("ok") is False or str(event.get("execution_status") or "").upper() in {
            "BROKER_REJECT", "REJECTED", "ERROR"
        }
    return False


def should_display(
    event: Mapping[str, Any], *, all_events: bool = False,
    blocked_only: bool = False, symbol: str | None = None,
) -> bool:
    if symbol and _event_symbol(event) != str(symbol).upper():
        return False
    if blocked_only:
        return is_blocked(event)
    return all_events or str(event.get("event") or "") in IMPORTANT_EVENTS or is_blocked(event)


def _format_value(value: Any) -> str:
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, separators=(",", ":"), default=str)
    return str(value)


def format_event(event: Mapping[str, Any]) -> str:
    """Render one candidate/runtime event without hiding its rejection detail."""
    details = event.get("candidate_details")
    details = details if isinstance(details, Mapping) else {}
    lines = ["-" * 60, f"TIME: {_timestamp(event)}", f"EVENT: {event.get('event', '-')}"]
    fields = (
        ("CANDIDATE", ("candidate_id",)),
        ("SYMBOL", ("symbol",)),
        ("SIDE", ("side",)),
        ("MECHANISM", ("mechanism", "setup_family")),
        ("HORIZON", ("horizon_s", "search_horizon_s")),
        ("LANE", ("lane", "exploration_lane")),
        ("P_CAPTURED_WIN", ("p_captured_win", "p_green", "econ_p_win")),
        ("SELECTION_SCORE", ("selection_score",)),
        ("EXPECTED_EV", ("expected_net_ev", "expected_net_value_usd", "econ_expected_net_usd")),
        ("SPREAD", ("spread", "spread_pips", "econ_spread_pips")),
        ("QUOTE_AGE", ("quote_age_s", "broker_tick_age_s")),
        ("ENTRY", ("entry", "econ_entry")),
        ("STOP", ("stop", "virtual_stop", "sl", "econ_invalidation")),
        ("TARGET", ("target", "virtual_target", "tp", "econ_target")),
        ("LOTS", ("lots", "quantity", "qty", "requested_lot")),
        ("RISK_USD", ("risk_usd", "estimated_risk_usd", "econ_expected_loss_usd")),
    )
    for label, keys in fields:
        value = _first(event, *keys)
        if value is None:
            value = _first(details, *keys)
        if value is not None:
            if label == "HORIZON":
                value = f"{value}s"
            elif label == "SIDE":
                value = _side(value)
            lines.append(f"{label}: {_format_value(value)}")

    state = _first(event, "state")
    if state:
        lines.append(f"STATE: {state}")
    final_status = _first(event, "final_status", "execution_status", "status")
    if final_status:
        lines.append(f"FINAL STATUS: {final_status}")
    reason = _first(event, "reject_reason", "reason", "error", "msg")
    if reason:
        lines.append(f"BLOCK_REASON: {reason}")
    distance = event.get("distance_to_eligibility")
    if isinstance(distance, Mapping) and distance:
        lines.append("DISTANCE_TO_PASS:")
        for key, value in distance.items():
            lines.append(f"  {key}={_format_value(value)}")

    detail_sources: list[Mapping[str, Any]] = [event, details]
    for key in ("quote_diagnostics", "acquisition", "sizing", "execution_detail"):
        value = event.get(key)
        if isinstance(value, Mapping):
            detail_sources.append(value)
    detail_keys = (
        "raw_tick_time", "raw_tick_time_msc", "normalized_quote_time",
        "broker_tick_age_s", "local_acquisition_age_ms", "previous_tick_time_msc",
        "new_tick_time_msc", "bid", "ask", "bid_changed", "ask_changed",
        "timestamp_changed", "fresh_tick_attempts", "fresh_tick_timeout_ms",
        "volume_min", "volume_step", "minimum_lot", "min_lot_risk_usd",
        "estimated_risk_usd", "max_risk_usd", "broker_min_stop_distance",
        "broker_emergency_stop", "virtual_stop", "virtual_target",
    )
    printed_detail = False
    for key in detail_keys:
        value = next((source.get(key) for source in detail_sources if source.get(key) is not None), None)
        if value is not None:
            if not printed_detail:
                lines.append("DETAIL:")
                printed_detail = True
            lines.append(f"  {key}={_format_value(value)}")
    return "\n".join(lines)


def _number(source: Mapping[str, Any], *keys: str, default: int = 0) -> int:
    for key in keys:
        try:
            return int(source.get(key) or 0)
        except (TypeError, ValueError):
            continue
    return default


def heartbeat_summary(heartbeat: Mapping[str, Any]) -> str:
    telemetry = heartbeat.get("firehose_telemetry")
    telemetry = telemetry if isinstance(telemetry, Mapping) else {}
    oms = telemetry.get("OMS_REJECTS_BY_REASON")
    oms_count = sum(int(value or 0) for value in oms.values()) if isinstance(oms, Mapping) else 0
    risk_count = _number(telemetry, "RISK_FAIL") + _number(telemetry, "RISK_REJECT")
    lines = [
        "",
        "================ FIREHOSE LIVE =================",
        f"STATUS={heartbeat.get('status', '-')} PHASE={heartbeat.get('runtime_phase', '-')} ACTIVE={telemetry.get('FIREHOSE_ACTIVE', heartbeat.get('status') == 'running')} ELIGIBLE={heartbeat.get('trading_eligible', '-')}",
        f"SCANS={_number(telemetry, 'SCANS')}",
        f"BUY_VARIANTS={_number(telemetry, 'BUY_VARIANTS_TESTED')}",
        f"SELL_VARIANTS={_number(telemetry, 'SELL_VARIANTS_TESTED')}",
        f"GLOBAL_CANDIDATES={_number(telemetry, 'GLOBAL_CANDIDATES')}",
        f"GLOBAL_SELECTED={_number(telemetry, 'GLOBAL_SELECTED')}",
        f"BEST_BUY={telemetry.get('BEST_BUY_SCORE')}",
        f"BEST_SELL={telemetry.get('BEST_SELL_SCORE')}",
        f"BEST_OVERALL_SIDE={telemetry.get('BEST_OVERALL_SIDE')}",
        f"FRESH_TICK_ATTEMPTS={_number(telemetry, 'FRESH_TICK_ACQUISITION_ATTEMPTS')}",
        f"FRESH_TICK_ACQUIRED={_number(telemetry, 'FRESH_TICK_ACQUIRED')}",
        f"BLOCKED_STALE={_number(telemetry, 'STALE_REJECT')}",
        f"BLOCKED_GEOMETRY={_number(telemetry, 'GEOMETRY_FAIL', 'GEOMETRY_REJECT')}",
        f"BLOCKED_RISK={risk_count}",
        f"BLOCKED_MARGIN={_number(telemetry, 'MARGIN_REJECT')}",
        f"BLOCKED_OMS={oms_count}",
        f"ORDER_SEND_ATTEMPTS={_number(telemetry, 'ORDER_SEND_ATTEMPTS')}",
        f"SUBMITTED={_number(telemetry, 'SUBMITTED')}",
        f"FILLS={_number(telemetry, 'FILLS')}",
        f"OPEN_POSITIONS={_number(telemetry, 'OPEN_TICKETS', 'OPEN_POSITIONS')}",
        f"WINS={_number(telemetry, 'WIN_EXITS')}",
        f"LOSSES={_number(telemetry, 'LOSS_EXITS')}",
        f"NO_ORDER_REASON={telemetry.get('NO_ORDER_REASON', telemetry.get('WHY_NO_ORDER'))}",
        "=================================================",
    ]
    return "\n".join(lines)


def _read_heartbeat(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _iter_new_events(handle: Any) -> Iterable[dict[str, Any]]:
    while True:
        line = handle.readline()
        if not line:
            return
        try:
            event = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(event, dict):
            yield event


def watch(
    config_path: Path, *, interval_s: float = 10.0, all_events: bool = False,
    blocked_only: bool = False, symbol: str | None = None,
    from_start: bool = False, once: bool = False,
) -> None:
    journal_path, heartbeat_path = runtime_paths(config_path)
    print(f"WATCHER=READ_ONLY\nJOURNAL_SOURCE={journal_path}\nHEARTBEAT_SOURCE={heartbeat_path}", flush=True)
    offset = 0
    if not from_start:
        try:
            offset = journal_path.stat().st_size
        except OSError:
            offset = 0
    next_summary = 0.0
    last_error = ""
    while True:
        now = time.monotonic()
        if now >= next_summary:
            print(heartbeat_summary(_read_heartbeat(heartbeat_path)), flush=True)
            next_summary = now + max(1.0, float(interval_s))
        try:
            with journal_path.open("rb") as handle:
                size = journal_path.stat().st_size
                if size < offset:
                    offset = 0
                handle.seek(offset)
                for event in _iter_new_events(handle):
                    offset = handle.tell()
                    for display_event in expand_event(event):
                        if should_display(
                            display_event, all_events=all_events,
                            blocked_only=blocked_only, symbol=symbol,
                        ):
                            print(format_event(display_event), flush=True)
        except OSError as exc:
            message = f"journal unavailable: {exc}"
            if message != last_error:
                print(message, flush=True)
                last_error = message
        if once:
            return
        time.sleep(0.25)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only live Firehose diagnostic viewer")
    parser.add_argument("--config", type=Path, default=ROOT / "config_mt5_demo_firehose_hw.yaml")
    parser.add_argument("--interval", type=float, default=10.0)
    parser.add_argument("--all", dest="all_events", action="store_true")
    parser.add_argument("--blocked-only", action="store_true")
    parser.add_argument("--symbol")
    parser.add_argument("--from-start", action="store_true")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args(argv)
    watch(
        args.config,
        interval_s=args.interval,
        all_events=args.all_events,
        blocked_only=args.blocked_only,
        symbol=args.symbol,
        from_start=args.from_start,
        once=args.once,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
