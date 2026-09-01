#!/usr/bin/env python3
"""Capture broker-native MGC quotes and gate paper execution on promotion."""
from __future__ import annotations

import argparse
import json
import math
import os
import signal
import sys
import time
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aegis.config import load_config  # noqa: E402
from aegis.engines import create_engine  # noqa: E402
from aegis.engines.base import OrderRequest, OrderResult  # noqa: E402
from aegis.mgc_firehose import (  # noqa: E402
    MomentumParams,
    QuoteTick,
    RegimeFlowParams,
    RegimeFlowSignal,
    SecondQuote,
    aggregate_second_quotes,
    regime_flow_signal,
)
from aegis.paper_control import ProcessLock, target_clears_costs  # noqa: E402


@dataclass(frozen=True)
class ExecutionMode:
    capture: bool
    send_orders: bool
    gate_reason: str


@dataclass(frozen=True)
class PaperRiskState:
    position_count: int = 0
    working_order_count: int = 0
    trades_last_hour: int = 0
    realized_pnl_today: float = 0.0
    consecutive_losses: int = 0
    cost_divergence_usd: float = 0.0


@dataclass(frozen=True)
class EntryDecision:
    allowed: bool
    reason: str


@dataclass(frozen=True)
class PaperSubmission:
    decision: EntryDecision
    expected_net_usd: float
    order_result: Optional[OrderResult]


def execution_mode(cfg: dict[str, Any]) -> ExecutionMode:
    """Validate the exact MGC safety envelope before capture or execution."""
    if str(cfg.get("engine", "")).casefold() != "ibkr":
        raise ValueError("MGC firehose requires engine: ibkr")
    if int(cfg.get("ib_port", 0) or 0) != 4002 or bool(cfg.get("allow_live", False)):
        raise ValueError("MGC firehose is restricted to IB Gateway paper port 4002")
    if str(cfg.get("symbol", "")).upper() != "MGC":
        raise ValueError("MGC firehose requires symbol: MGC")
    if float(cfg.get("order_quantity", 0) or 0) != 1.0:
        raise ValueError("MGC firehose requires exactly one contract")
    if float(cfg.get("contract_multiplier", 0) or 0) != 10.0:
        raise ValueError("MGC firehose requires contract_multiplier: 10")
    if float(cfg.get("tick_size", 0) or 0) != 0.1:
        raise ValueError("MGC firehose requires tick_size: 0.1")

    if not bool(cfg.get("paper_promoted", False)):
        return ExecutionMode(True, False, "paper_promoted is false")
    if bool(cfg.get("dry_run", True)):
        return ExecutionMode(True, False, "dry_run is true")
    if not bool(cfg.get("paper_trading_enabled", False)):
        return ExecutionMode(True, False, "paper_trading_enabled is false")
    if int(cfg.get("ib_market_data_type", 0) or 0) != 1:
        return ExecutionMode(True, False, "live market data type 1 required")
    return ExecutionMode(True, True, "promoted paper execution")


def paper_entry_decision(
    cfg: dict[str, Any],
    *,
    mode: ExecutionMode,
    feed_usable: bool,
    has_signal: bool,
    expected_net_usd: float,
    risk: PaperRiskState,
) -> EntryDecision:
    """Fail closed before any MGC paper-order mutation."""
    if not mode.send_orders:
        return EntryDecision(False, mode.gate_reason)
    if bool(cfg.get("kill_switch", False)):
        return EntryDecision(False, "kill switch enabled")
    if not feed_usable:
        return EntryDecision(False, "feed stale or spread too wide")
    if not has_signal:
        return EntryDecision(False, "no qualified regime-flow signal")
    if risk.position_count or risk.working_order_count:
        return EntryDecision(False, "existing MGC position or working order")
    if risk.trades_last_hour >= int(cfg.get("max_completed_trades_hour", 100)):
        return EntryDecision(False, "hourly trade limit reached")
    if risk.realized_pnl_today <= -abs(float(cfg.get("max_daily_loss_usd", 250))):
        return EntryDecision(False, "daily realized loss limit reached")
    if risk.consecutive_losses >= int(cfg.get("max_consecutive_losses", 5)):
        return EntryDecision(False, "consecutive loss limit reached")
    if risk.cost_divergence_usd >= abs(float(cfg.get("max_cost_divergence_usd", 100))):
        return EntryDecision(False, "cost divergence limit reached")
    if expected_net_usd < float(cfg.get("min_expected_net_usd", 1.0)):
        return EntryDecision(False, "target does not clear modeled costs")
    return EntryDecision(True, "qualified regime-flow paper entry")


def expected_signal_net_usd(cfg: dict[str, Any], signal: RegimeFlowSignal) -> float:
    """Price a target using executable entry/exit sides plus explicit fees/slippage."""
    _clears, net = target_clears_costs(
        quantity=float(cfg.get("order_quantity", 1)),
        contract_multiplier=float(cfg.get("contract_multiplier", 10)),
        entry=signal.entry_price,
        target=signal.take_profit,
        commission_round_trip_usd=float(cfg.get("ib_round_trip_commission_usd", 1.92)),
        spread_price=0.0,
        slippage_price=(
            float(cfg.get("slippage_ticks", 1)) * float(cfg.get("tick_size", 0.1))
        ),
        spread_bps=0.0,
        slippage_bps=0.0,
        min_expected_net_usd=float(cfg.get("min_expected_net_usd", 1.0)),
    )
    return net


def build_order_request(cfg: dict[str, Any], signal: RegimeFlowSignal) -> OrderRequest:
    return OrderRequest(
        symbol="MGC",
        side=signal.side,
        quantity=float(cfg.get("order_quantity", 1)),
        kind="limit",
        limit_price=signal.entry_price,
        stop_loss=signal.stop_loss,
        take_profit=signal.take_profit,
        client_tag="aegis_mgc_regime_flow",
    )


def submit_paper_signal(
    engine: Any,
    cfg: dict[str, Any],
    *,
    mode: ExecutionMode,
    signal: Optional[RegimeFlowSignal],
    feed_usable: bool,
    risk: PaperRiskState,
) -> PaperSubmission:
    expected_net = expected_signal_net_usd(cfg, signal) if signal is not None else 0.0
    decision = paper_entry_decision(
        cfg,
        mode=mode,
        feed_usable=feed_usable,
        has_signal=signal is not None,
        expected_net_usd=expected_net,
        risk=risk,
    )
    if not decision.allowed or signal is None:
        return PaperSubmission(decision, expected_net, None)
    result = engine.place_order(build_order_request(cfg, signal))
    return PaperSubmission(decision, expected_net, result)


def _json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    return value


def append_quote(path: Path, quote: QuoteTick) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {key: _json_value(value) for key, value in asdict(quote).items()}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, separators=(",", ":")) + "\n")


def append_second(path: Path, record: SecondQuote) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {key: _json_value(value) for key, value in asdict(record).items()}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, separators=(",", ":")) + "\n")


def load_quotes(path: Path) -> list[QuoteTick]:
    if not path.exists():
        return []
    out: list[QuoteTick] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        payload["time"] = datetime.fromisoformat(str(payload["time"]).replace("Z", "+00:00"))
        out.append(QuoteTick(**payload))
    return out


def load_recent_seconds(path: Path, limit: int) -> list[SecondQuote]:
    if not path.exists() or limit <= 0:
        return []
    lines = deque(path.read_text(encoding="utf-8").splitlines(), maxlen=limit)
    out: list[SecondQuote] = []
    for line in lines:
        if not line.strip():
            continue
        payload = json.loads(line)
        payload["time"] = datetime.fromisoformat(str(payload["time"]).replace("Z", "+00:00"))
        out.append(SecondQuote(**payload))
    return out


def count_second_records(path: Path) -> tuple[int, int]:
    """Count all captured seconds and all usable seconds across restarts."""
    if not path.exists():
        return 0, 0
    total = 0
    usable = 0
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            total += 1
            try:
                usable += int(bool(json.loads(line).get("usable", False)))
            except (json.JSONDecodeError, TypeError):
                continue
    return total, usable


def strategy_params(cfg: dict[str, Any]) -> RegimeFlowParams:
    return RegimeFlowParams(
        momentum=MomentumParams(
            lookback_seconds=int(cfg.get("mgc_lookback_seconds", 10)),
            breakout_seconds=int(cfg.get("mgc_breakout_seconds", 5)),
            min_efficiency=float(cfg.get("mgc_min_efficiency", 0.50)),
            target_ticks=int(cfg.get("mgc_target_ticks", 8)),
            stop_ticks=int(cfg.get("mgc_stop_ticks", 6)),
            max_hold_seconds=int(cfg.get("mgc_max_hold_seconds", 10)),
            cooldown_seconds=int(cfg.get("mgc_cooldown_seconds", 1)),
        ),
        min_book_imbalance=float(cfg.get("mgc_min_book_imbalance", 0.0)),
        min_microprice_bias_ticks=float(cfg.get("mgc_min_microprice_bias_ticks", 0.0)),
        min_trade_flow_imbalance=float(cfg.get("mgc_min_trade_flow_imbalance", 0.0)),
        max_spread_ticks=float(cfg.get("max_spread_ticks", 4.0)),
    )


def _finite(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number if math.isfinite(number) else 0.0


def quote_from_ticker(ticker: Any, local_symbol: str) -> Optional[QuoteTick]:
    bid, ask = _finite(getattr(ticker, "bid", 0.0)), _finite(getattr(ticker, "ask", 0.0))
    if bid <= 0 or ask <= 0:
        return None
    timestamp = getattr(ticker, "time", None) or datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return QuoteTick(
        time=timestamp,
        bid=bid,
        ask=ask,
        bid_size=_finite(getattr(ticker, "bidSize", 0.0)),
        ask_size=_finite(getattr(ticker, "askSize", 0.0)),
        last=_finite(getattr(ticker, "last", 0.0)),
        last_size=_finite(getattr(ticker, "lastSize", 0.0)),
        local_symbol=local_symbol,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Aegis MGC paper shadow/firehose runner")
    parser.add_argument("--config", default=str(ROOT / "config_ib_paper_mgc_shadow.yaml"))
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    cfg = load_config(args.config)
    mode = execution_mode(cfg)

    lock = ProcessLock(ROOT / "reports" / "run_broker_paper.lock")
    lock.acquire()
    engine = create_engine(cfg)
    raw_path = ROOT / "reports" / "mgc_ticks.jsonl"
    second_path = ROOT / "reports" / "mgc_seconds.jsonl"
    journal_path = ROOT / "reports" / "mgc_firehose_journal.jsonl"
    state_path = ROOT / "reports" / "mgc_firehose_state.json"
    heartbeat = ROOT / "reports" / "bot_heartbeat.json"
    stop_requested = False
    subscription = None
    current_second: list[QuoteTick] = []
    current_bucket = None
    last_signature = None
    params = strategy_params(cfg)
    memory_limit = max(params.momentum.lookback_seconds, params.momentum.breakout_seconds) + 3
    recent_records = load_recent_seconds(second_path, memory_limit)
    records, usable_records = count_second_records(second_path)
    submission_times: deque[datetime] = deque()
    submissions_today = 0
    modeled_costs_today = 0.0
    last_regime = "waiting"
    last_signal_side: Optional[str] = None
    last_flow_score = 0.0
    last_expected_net = 0.0
    execution_halt = ""
    initial_equity = 0.0

    def append_event(event: str, **fields: Any) -> None:
        payload = {
            "time": datetime.now(timezone.utc).isoformat(),
            "event": event,
            **fields,
        }
        journal_path.parent.mkdir(parents=True, exist_ok=True)
        with journal_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, separators=(",", ":"), default=str) + "\n")

    def request_stop(_signum, _frame) -> None:
        nonlocal stop_requested
        stop_requested = True

    def write_heartbeat(*, feed_usable: bool, feed_age: Optional[float], gate_reason: str) -> None:
        metadata = engine.contract_metadata("MGC") if subscription is not None else {}
        payload = {
            "pid": os.getpid(),
            "ts": time.time(),
            "iso": datetime.now(timezone.utc).isoformat(),
            "status": "shadow_capture" if not mode.send_orders else "paper_execution",
            "symbol": "MGC",
            "local_symbol": metadata.get("local_symbol"),
            "contract_multiplier": 10.0,
            "tick_value_usd": 1.0,
            "feed_age_seconds": feed_age,
            "feed_usable": feed_usable,
            "market_data_type": int(cfg.get("ib_market_data_type", 1)),
            "records": records,
            "usable_records": usable_records,
            "trades_today": submissions_today,
            "modeled_costs_today": modeled_costs_today,
            "paper_promoted": bool(cfg.get("paper_promoted", False)),
            "gate_reason": execution_halt or gate_reason,
            "regime": last_regime,
            "signal_side": last_signal_side,
            "flow_score": last_flow_score,
            "expected_net_usd": last_expected_net,
        }
        heartbeat.write_text(json.dumps(payload), encoding="utf-8")

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    try:
        engine.connect()
        account = engine.account()
        if not account.is_paper:
            raise RuntimeError("broker did not identify as paper")
        initial_equity = account.equity
        metadata = engine.contract_metadata("MGC")
        subscription = engine.subscribe_quote("MGC")
        append_event(
            "runner_started",
            mode="paper_execution" if mode.send_orders else "shadow_capture",
            local_symbol=metadata.get("local_symbol"),
            gate_reason=mode.gate_reason,
        )
        while not stop_requested:
            engine._require().sleep(float(cfg.get("capture_poll_seconds", 0.1)))
            quote = quote_from_ticker(subscription.ticker, str(metadata["local_symbol"]))
            now = datetime.now(timezone.utc)
            if quote is None:
                write_heartbeat(feed_usable=False, feed_age=None, gate_reason="waiting for bid/ask")
                if args.once:
                    break
                continue
            signature = (quote.bid, quote.ask, quote.bid_size, quote.ask_size, quote.last, quote.last_size)
            feed_age = max(0.0, (now - quote.time.astimezone(timezone.utc)).total_seconds())
            if signature != last_signature:
                append_quote(raw_path, quote)
                last_signature = signature
            bucket = quote.time.astimezone(timezone.utc).replace(microsecond=0)
            if current_bucket is None:
                current_bucket = bucket
            if bucket != current_bucket and current_second:
                completed = aggregate_second_quotes(
                    current_second,
                    tick_size=0.1,
                    max_spread_ticks=float(cfg.get("max_spread_ticks", 4)),
                )
                for record in completed:
                    append_second(second_path, record)
                    records += 1
                    usable_records += int(record.usable)
                    recent_records.append(record)
                    if len(recent_records) > memory_limit:
                        recent_records = recent_records[-memory_limit:]

                    signal_value: Optional[RegimeFlowSignal] = None
                    if len(recent_records) >= 2:
                        signal_value = regime_flow_signal(
                            recent_records,
                            signal_index=len(recent_records) - 2,
                            params=params,
                            tick_size=float(cfg.get("tick_size", 0.1)),
                        )
                    last_signal_side = signal_value.side if signal_value else None
                    last_flow_score = signal_value.flow_score if signal_value else 0.0
                    last_regime = signal_value.regime if signal_value else "abstain"
                    last_expected_net = (
                        expected_signal_net_usd(cfg, signal_value) if signal_value else 0.0
                    )

                    if mode.send_orders and not execution_halt:
                        now_utc = datetime.now(timezone.utc)
                        while submission_times and submission_times[0] < now_utc - timedelta(hours=1):
                            submission_times.popleft()
                        positions = engine.positions("MGC")
                        working = engine.working_orders()
                        current_equity = engine.account().equity
                        risk = PaperRiskState(
                            position_count=len(positions),
                            working_order_count=len(working),
                            trades_last_hour=len(submission_times),
                            realized_pnl_today=current_equity - initial_equity,
                        )
                        submission = submit_paper_signal(
                            engine,
                            cfg,
                            mode=mode,
                            signal=signal_value,
                            feed_usable=record.usable,
                            risk=risk,
                        )
                        if submission.decision.allowed:
                            result = submission.order_result
                            append_event(
                                "paper_entry_submitted" if result and result.ok else "paper_entry_rejected",
                                side=signal_value.side if signal_value else None,
                                expected_net_usd=submission.expected_net_usd,
                                order_id=result.broker_order_id if result else "",
                                message=result.message if result else "missing order result",
                            )
                            if result is None or not result.ok:
                                engine.cancel_all_orders()
                                execution_halt = "paper bracket submission failed"
                            else:
                                submission_times.append(now_utc)
                                submissions_today += 1
                                modeled_costs_today += float(
                                    cfg.get("ib_round_trip_commission_usd", 1.92)
                                ) + (
                                    float(cfg.get("slippage_ticks", 1))
                                    * float(cfg.get("tick_size", 0.1))
                                    * float(cfg.get("contract_multiplier", 10))
                                )
                current_second = []
                current_bucket = bucket
            current_second.append(quote)
            usable = quote.ask >= quote.bid and (quote.ask - quote.bid) <= 0.4 and feed_age <= 2.0
            if int(cfg.get("ib_market_data_type", 1)) != 1:
                reason = "delayed broker data; capture only"
            else:
                reason = mode.gate_reason if usable else "feed stale or spread too wide"
            write_heartbeat(feed_usable=usable, feed_age=feed_age, gate_reason=reason)
            if args.once:
                break
    finally:
        try:
            if subscription is not None:
                engine.cancel_quote(subscription)
        finally:
            if mode.send_orders:
                try:
                    flattened = engine.flatten_positions("MGC")
                    append_event("runner_flatten", ok=flattened.ok, message=flattened.message)
                except Exception as exc:
                    append_event("runner_flatten_failed", message=str(exc))
            state_path.write_text(
                json.dumps(
                    {
                        "time": datetime.now(timezone.utc).isoformat(),
                        "submissions_today": submissions_today,
                        "modeled_costs_today": modeled_costs_today,
                        "halt_reason": execution_halt,
                        "paper_promoted": bool(cfg.get("paper_promoted", False)),
                    }
                ),
                encoding="utf-8",
            )
            if heartbeat.exists():
                heartbeat.unlink()
            engine.disconnect()
            lock.release()


if __name__ == "__main__":
    main()
