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

from aegis.config import configured_symbols, load_config, max_spread_for, pip_size_for  # noqa: E402
from aegis.engines import OrderRequest, OrderResult, create_engine  # noqa: E402
from aegis.execution_audit import (  # noqa: E402
    FireLatency,
    PendingRetryGuard,
    classify as classify_execution,
)
from aegis.exits import (  # noqa: E402
    giveback_reason,
    live_firehose_stops,
    load_mfe,
    mfe_after_quick_win,
    quick_win_clips,
    save_mfe,
    should_block_scratch_cooldown,
    should_scratch_never_green,
    update_mae,
    update_mfe,
)
from aegis.execution_circuit import ExecutionCircuit  # noqa: E402
from aegis.high_risk import HighRiskController  # noqa: E402
from aegis.oms import (  # noqa: E402
    TickToTrade,
    close_attempt_blocked,
    is_market_closed_retcode,
    oms_allows,
    open_attempt_blocked,
    quote_age_s,
    quote_future_skew_s,
    update_close_backoff,
)
from aegis.paper_control import (  # noqa: E402
    ProcessLock,
    firehose_can_add,
    firehose_consume_bar,
    jpy_cluster_blocks,
)
from aegis.risk import RiskEngine  # noqa: E402
from aegis.sizing import ContractSpec, size_lots_for_risk  # noqa: E402
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


def normalize_protective_stops(
    *,
    side: str,
    entry: float,
    sl: float | None,
    tp: float | None,
    spec: dict | None,
    fallback_step: float,
) -> tuple[float | None, float | None]:
    """Keep SL/TP outside broker stop-distance constraints for market orders."""
    if sl is None and tp is None:
        return None, None
    contract = dict(spec or {})
    point = float(contract.get("point") or 0.0) or float(contract.get("trade_tick_size") or 0.0) or float(
        fallback_step or 0.0
    )
    stops_level = max(
        int(contract.get("trade_stops_level") or 0),
        int(contract.get("trade_freeze_level") or 0),
    )
    min_distance = max(float(stops_level) * point, point * 2.0)
    side_l = str(side or "").lower()
    sl_out = None if sl is None else float(sl)
    tp_out = None if tp is None else float(tp)
    if side_l == "buy":
        if sl_out is not None:
            sl_out = min(sl_out, float(entry) - min_distance)
        if tp_out is not None:
            tp_out = max(tp_out, float(entry) + min_distance)
    elif side_l == "sell":
        if sl_out is not None:
            sl_out = max(sl_out, float(entry) + min_distance)
        if tp_out is not None:
            tp_out = min(tp_out, float(entry) - min_distance)
    return sl_out, tp_out


def main() -> None:
    parser = argparse.ArgumentParser(description="Aegis broker-engine paper runner")
    parser.add_argument("--config", default=str(ROOT / "config_ib_paper_eurusd.yaml"))
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    cfg = load_config(args.config)
    engine_name = str(cfg.get("engine", "")).lower()
    if engine_name == "mt5":
        from aegis.paper_control import paper_execution_enabled

        send_orders = paper_execution_enabled(cfg)
    else:
        send_orders = not bool(cfg.get("dry_run", False))

    lock = ProcessLock(ROOT / "reports" / "run_broker_paper.lock")
    lock.acquire()
    try:
        eng = create_engine(cfg)
        eng.connect()
    except Exception:
        lock.release()
        raise
    journal = ROOT / "reports" / f"{cfg.get('test_name', 'ib_paper')}_journal.jsonl"
    heartbeat = ROOT / "reports" / "bot_heartbeat.json"
    risk_path = ROOT / "reports" / "risk_state.json"
    risk = RiskEngine.from_config(cfg)
    risk.load_json(risk_path)
    circuit_path = ROOT / "reports" / "execution_circuit.json"
    circuit = ExecutionCircuit(
        limit=int(cfg.get("no_money_reject_limit", 3) or 3),
        window_s=float(cfg.get("no_money_window_s", 300) or 300),
        backoff_s=float(cfg.get("execution_backoff_s", 900) or 900),
    )
    circuit.load_json(circuit_path)
    symbols = configured_symbols(cfg)
    qty = float(cfg.get("order_quantity", 0.01 if engine_name == "mt5" else 20000))
    last_bar_time: dict[str, pd.Timestamp] = {}
    hr = None
    position_opened_at: dict[str, float] = {}
    last_entry_at: dict[str, float] = {}
    last_scratch_at: dict[str, float] = {}
    max_hold = float(cfg.get("max_hold_seconds", 0) or 0)
    max_positions = int(cfg.get("max_positions", 1) or 1)
    jpy_cluster_max = int(cfg.get("firehose_jpy_cluster_max", 0) or 0)
    flatten_profit = float(cfg.get("flatten_if_profit_usd", 0) or 0)
    scratch_losers = bool(cfg.get("scratch_losers", True))
    stack_clips = bool(cfg.get("firehose_stack", False))
    max_per_symbol = int(cfg.get("firehose_max_per_symbol", 1) or 1)
    clip_interval_s = float(cfg.get("firehose_clip_interval_s", 0) or 0)
    mfe_path = ROOT / "reports" / "firehose_mfe.json"
    mfe = load_mfe(mfe_path)
    mae_path = ROOT / "reports" / "firehose_mae.json"
    mae = load_mfe(mae_path)
    pa_select_mode = str(cfg.get("signal_mode") or cfg.get("algo") or "").lower() in {"pa_select"}
    day_trades = 0
    day_stamp = None
    last_halt_journal = 0.0
    margin_block_until = 0.0
    last_nomoney_journal = 0.0
    last_mktclosed_journal = 0.0
    last_intel_journal: dict[str, float] = {}
    intelligent_brain = None
    from aegis.intel.lifecycle import ingest_deals, load_cursor, save_cursor

    reconcile_cursor_path = ROOT / "reports" / "reconcile_cursor.json"
    deal_cursor = load_cursor(reconcile_cursor_path)
    margin_cooldown_s = 30.0
    close_block_until = 0.0
    t2t = TickToTrade()
    fire_retry_guard = PendingRetryGuard()
    execution_status_counts: dict[str, int] = {}
    quote_refresh_counts: dict[str, int] = {
        "stale_observed_at_send": 0,
        "fresh_quote_recovered": 0,
        "candidate_invalidated_after_refresh": 0,
        "order_sent_after_refresh": 0,
        "margin_precheck_skip": 0,
        "min_lot_precheck_skip": 0,
    }
    fast_exit_error_count: int = 0
    # Quote buffer for genuine sub-minute features
    from aegis.intel.quote_buffer import QuoteBuffer
    quote_buffer = QuoteBuffer(max_points_per_symbol=3600)
    # Exact ticket->hypothesis metadata persistence
    from aegis.intel.ticket_metadata import TicketMetadataStore, create_ticket_metadata
    ticket_metadata_store = TicketMetadataStore(ROOT / "intel" / "ticket_metadata.json")
    # Intelligent per-thesis profit management (spec B-H, O, P).
    from aegis.intel.profit_management import ProfitManager

    profit_manager = ProfitManager(
        cfg, persist_path=ROOT / "intel" / "pm_tickets.json"
    )
    # Fast exit state machine for FAST_TURNOVER_FIREHOSE tickets.
    from aegis.intel.fast_firehose import FastExitStateMachine, FastExitConfig
    from aegis.intel.fast_exit_runner import FastExitContext, evaluate_fast_exit, MissingLiquidationMarkError

    fast_exit_sm = FastExitStateMachine()
    last_inventory_journal: dict[str, float] = {"ts": 0.0}

    def write_heartbeat(extra: Optional[dict] = None) -> None:
        payload = {
            "pid": os.getpid(),
            "ts": time.time(),
            "iso": datetime.now(timezone.utc).isoformat(),
            "symbols": symbols,
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
        live_symbols: list[str] = []
        for name in symbols:
            try:
                eng.quote(name)
                live_symbols.append(name)
            except Exception as exc:
                logger.warning("Dropping %s from watchlist: %s", name, exc)
        if not live_symbols:
            raise SystemExit("No tradeable symbols on this MT5 account.")
        symbols = live_symbols
        logger.info(
            "Connected engine=%s account=%s equity=%.2f paper=%s qty=%s symbols=%s",
            eng.name,
            acct.account_id,
            acct.equity,
            acct.is_paper,
            qty,
            ",".join(symbols),
        )
        append_journal(
            journal,
            {
                "event": "start",
                "engine": eng.name,
                "account": acct.account_id,
                "equity": acct.equity,
                "symbols": symbols,
            },
        )
        loaded = risk.load_json(risk_path)
        logger.info(
            "Risk state loaded=%s day=%s start=%.2f halted=%s reason=%s",
            loaded,
            risk.state.day,
            float(risk.state.day_start_equity or 0),
            risk.state.halted,
            risk.state.reason,
        )
        write_heartbeat({"equity": acct.equity, "status": "running", "open": 0})
        # allow() clears a persisted daily_loss halt when max_daily_loss_percent <= 0.
        try:
            open_n = len(eng.positions())
        except Exception:
            open_n = 0
        risk.allow(acct.equity, open_positions=open_n)
        risk.save_json(risk_path)
        append_journal(
            journal,
            {
                "event": "risk_state",
                "loaded": loaded,
                **risk.dump(),
                "equity": acct.equity,
            },
        )

        leftover = eng.positions()
        if leftover:
            logger.info(
                "Adopting %s leftover position(s); not flattening: %s",
                len(leftover),
                ", ".join(f"{p.symbol}:{p.side}" for p in leftover),
            )
            now_s = time.time()
            for pos in leftover:
                position_opened_at.setdefault(pos.symbol, now_s)
                last_entry_at.setdefault(pos.symbol, now_s)
            append_journal(
                journal,
                {
                    "event": "adopt_positions",
                    "count": len(leftover),
                    "held": [f"{p.symbol}:{p.side}" for p in leftover],
                    "equity": acct.equity,
                },
            )

        def flatten_open(sym: str, open_pos, equity: float, held: float, reason: str = "max_hold"):
            nonlocal close_block_until
            now_ts = time.time()
            if close_attempt_blocked(now_ts, close_block_until):
                return OrderResult(ok=False, message="market_closed_backoff")
            pos0 = open_pos[0]
            logger.info(
                "Flatten %s %s qty=%s reason=%s held=%.0fs pnl=%.2f",
                sym,
                pos0.side,
                pos0.quantity,
                reason,
                held,
                float(pos0.unrealized_pnl),
            )
            if hasattr(eng, "flatten_positions"):
                flat = eng.flatten_positions(sym)
            else:
                close_side = "sell" if pos0.side == "buy" else "buy"
                flat = eng.place_order(
                    OrderRequest(
                        symbol=sym,
                        side=close_side,
                        quantity=float(pos0.quantity),
                        kind="market",
                        client_tag=f"aegis_{reason}"[:40],
                    )
                )
            if not flat.ok:
                prev_until = close_block_until
                close_block_until = update_close_backoff(
                    close_block_until, flat.message, datetime.now(timezone.utc)
                )
                if close_block_until > prev_until:
                    logger.warning(
                        "%s close blocked until %.0f (%s); %s",
                        sym,
                        close_block_until,
                        reason,
                        flat.message,
                    )
            append_journal(
                journal,
                {
                    "event": "flatten",
                    "symbol": sym,
                    "reason": reason,
                    "held_s": held,
                    "pnl": float(pos0.unrealized_pnl),
                    "ok": flat.ok,
                    "msg": flat.message,
                    "equity": equity,
                    **(
                        {
                            "market_closed": True,
                            "close_block_until": close_block_until,
                        }
                        if is_market_closed_retcode(flat.message)
                        else {}
                    ),
                },
            )
            return flat

        def close_quick_wins(sym: str, winners, equity: float, held: float):
            """Close only clips at/above flatten_if_profit_usd. Leave the rest."""
            nonlocal close_block_until
            now_ts = time.time()
            if close_attempt_blocked(now_ts, close_block_until):
                return OrderResult(ok=False, message="market_closed_backoff")
            if hasattr(eng, "close_ticket"):
                closed = 0
                last_fail = ""
                for pos in winners:
                    ticket = str(getattr(pos, "ticket", "") or "").strip()
                    pnl = float(pos.unrealized_pnl)
                    if not ticket:
                        logger.warning(
                            "Quick-win %s skip clip with no ticket pnl=%.2f",
                            sym,
                            pnl,
                        )
                        append_journal(
                            journal,
                            {
                                "event": "flatten",
                                "symbol": sym,
                                "reason": "quick_win",
                                "ticket": "",
                                "held_s": held,
                                "pnl": pnl,
                                "ok": False,
                                "msg": "no ticket",
                                "equity": equity,
                            },
                        )
                        last_fail = "no ticket"
                        continue
                    logger.info(
                        "Quick-win close %s ticket=%s pnl=%.2f held=%.0fs",
                        sym,
                        ticket,
                        pnl,
                        held,
                    )
                    res = eng.close_ticket(ticket)
                    if not res.ok:
                        prev_until = close_block_until
                        close_block_until = update_close_backoff(
                            close_block_until, res.message, datetime.now(timezone.utc)
                        )
                        if close_block_until > prev_until:
                            logger.warning(
                                "%s close_ticket blocked until %.0f (quick_win); %s",
                                sym,
                                close_block_until,
                                res.message,
                            )
                    append_journal(
                        journal,
                        {
                            "event": "flatten",
                            "symbol": sym,
                            "reason": "quick_win",
                            "ticket": ticket,
                            "held_s": held,
                            "pnl": pnl,
                            "ok": res.ok,
                            "msg": res.message,
                            "equity": equity,
                            **(
                                {
                                    "market_closed": True,
                                    "close_block_until": close_block_until,
                                }
                                if is_market_closed_retcode(res.message)
                                else {}
                            ),
                        },
                    )
                    if res.ok:
                        closed += 1
                    else:
                        last_fail = res.message
                        if is_market_closed_retcode(res.message):
                            break
                if closed:
                    return OrderResult(ok=True, message=f"closed {closed} ticket(s)")
                return OrderResult(ok=False, message=last_fail or "no winning tickets closed")
            open_now = list(eng.positions(sym))
            if open_now and len(quick_win_clips(open_now, flatten_profit)) >= len(open_now):
                return flatten_open(sym, open_now, equity, held, reason="quick_win")
            append_journal(
                journal,
                {
                    "event": "flatten",
                    "symbol": sym,
                    "reason": "quick_win",
                    "held_s": held,
                    "ok": False,
                    "msg": "no close_ticket; mixed book left intact",
                    "equity": equity,
                },
            )
            return OrderResult(ok=False, message="no close_ticket; mixed book left intact")

        def maybe_enter(sym: str, equity: float, open_count: int) -> None:
            nonlocal day_trades, day_stamp, last_halt_journal, close_block_until
            nonlocal margin_block_until
            brain_decision = None
            if open_attempt_blocked(time.time(), close_block_until):
                return
            bars = eng.bars(sym, str(cfg["timeframe"]), int(cfg.get("lookback_days", 30)))
            if len(bars) < 50:
                logger.warning("%s: not enough bars yet (%s)", sym, len(bars))
                return
            raw = bars_to_frame(bars)
            prep_cfg = cfg
            if pa_select_mode:
                from aegis.pa_select import fetch_mtf_frames

                bar_time_raw = pd.Timestamp(raw.iloc[-2]["time"])
                prev_raw = last_bar_time.get(sym)
                if prev_raw is not None and bar_time_raw <= prev_raw:
                    return
                prep_cfg = dict(cfg)
                prep_cfg["pa_mtf_frames"] = fetch_mtf_frames(eng, sym, cfg)
            frame = prepare(raw, prep_cfg)
            row = frame.iloc[-2]
            bar_time = pd.Timestamp(row["time"])
            prev = last_bar_time.get(sym)
            if prev is not None and bar_time <= prev:
                return

            q = eng.quote(sym)
            # Quote already recorded in polling loop; use current quote for this evaluation
            t0 = time.perf_counter()
            now_ts = time.time()
            live_spread = max(0.0, float(q.ask) - float(q.bid))
            mid = (float(q.bid) + float(q.ask)) / 2.0 if q.bid and q.ask else 0.0
            live_bps = (live_spread / mid * 10000.0) if mid > 0 else 0.0
            pip = pip_size_for(sym, cfg)
            loop_cfg = dict(prep_cfg)
            loop_cfg["spread_bps"] = max(live_bps, float(cfg.get("spread_bps_floor", 0.2) or 0.0))
            loop_cfg["firehose_pip_size"] = pip
            loop_cfg["volman_pip_size"] = pip

            if bool(cfg.get("oms_pretrade", False)):
                max_age = float(cfg.get("max_quote_age_s", 5.0) or 0.0)
                age = quote_age_s(q)
                if max_age > 0 and age > max_age:
                    t2t.note_reject("stale_quote")
                    append_journal(
                        journal,
                        {
                            "event": "quote_stale",
                            "symbol": sym,
                            "age_s": age,
                            "max_s": max_age,
                            "bar": str(bar_time),
                        },
                    )
                    return
                # quote_age_s clamps at zero, so a future-stamped tick reports age 0.0
                # and would look perfectly fresh here. Reject it explicitly.
                max_skew = float(cfg.get("max_quote_future_skew_s", max_age) or 0.0)
                skew = quote_future_skew_s(q)
                if max_skew > 0 and skew > max_skew:
                    t2t.note_reject("future_quote")
                    append_journal(
                        journal,
                        {
                            "event": "quote_future",
                            "symbol": sym,
                            "skew_s": skew,
                            "max_s": max_skew,
                            "bar": str(bar_time),
                        },
                    )
                    return

            # Live daily-loss is UTC wall clock. Bar timestamps can be yesterday
            # (or a stale MT5 bar) and would wipe a persisted halt on restart.
            ok, reason = risk.allow(equity, open_positions=open_count)
            if not ok:
                logger.warning("Risk halt: %s (continuing watch)", reason)
                risk.save_json(risk_path)
                now_s = time.time()
                if now_s - last_halt_journal >= 60:
                    last_halt_journal = now_s
                    append_journal(journal, {"event": "halt", "reason": reason, "equity": equity})
                return
            c_ok, c_reason = circuit.allow(now=time.time())
            if not c_ok:
                logger.warning("Execution circuit: %s (continuing watch)", c_reason)
                now_s = time.time()
                if now_s - last_halt_journal >= 60:
                    last_halt_journal = now_s
                    append_journal(
                        journal,
                        {"event": "halt", "reason": c_reason, "equity": equity},
                    )
                return
            hr_ok, hr_reason = hr.allow(equity)
            if not hr_ok:
                logger.warning("HR halt: %s (continuing watch)", hr_reason)
                append_journal(journal, {"event": "hr_halt", "reason": hr_reason, "equity": equity})
                return

            max_spread = max_spread_for(sym, cfg)
            if max_spread > 0 and live_spread > max_spread + 1e-12:
                logger.info(
                    "Skip %s: live spread %.5f > max %.5f",
                    sym,
                    live_spread,
                    max_spread,
                )
                append_journal(
                    journal,
                    {
                        "event": "spread_skip",
                        "symbol": sym,
                        "spread": live_spread,
                        "max": max_spread,
                        "bar": str(bar_time),
                    },
                )
                return

            if flatten_profit > 0 and hasattr(eng, "round_trip_spread_usd"):
                try:
                    rt_usd = float(eng.round_trip_spread_usd(sym, qty))
                except Exception:
                    rt_usd = 0.0
                if rt_usd >= flatten_profit:
                    logger.info(
                        "Skip %s: round-trip spread $%.2f >= quick-win $%.2f",
                        sym,
                        rt_usd,
                        flatten_profit,
                    )
                    return

            if pa_select_mode:
                max_day = int(cfg.get("ntz_max_trades_day", 0) or 0)
                bar_day = bar_time.tz_convert("UTC").date() if getattr(bar_time, "tzinfo", None) else bar_time.date()
                if day_stamp != bar_day:
                    day_stamp = bar_day
                    day_trades = 0
                if max_day > 0 and day_trades >= max_day:
                    logger.info("Skip %s: daily trade cap %s", sym, max_day)
                    return

            intelligent_mode = bool(cfg.get("intelligent_firehose", False))
            sig = None
            if intelligent_mode:
                nonlocal intelligent_brain
                from aegis.intel.firehose_brain import IntelligentFirehoseBrain
                from aegis.strategy import Signal

                if intelligent_brain is None:
                    intelligent_brain = IntelligentFirehoseBrain(cfg)
                completed = raw.iloc[:-1].copy() if len(raw) >= 2 else raw
                hint_cfg = dict(loop_cfg)
                hint_cfg["intel_enabled"] = False
                hint = signal_from_row(row, hint_cfg)
                # The brain prices the prospective trade, so it needs this moment's
                # spread and the broker's contract spec. Without them it cannot tell
                # a 1-pip target over a 30-pip stop from a real edge.
                try:
                    brain_spec = eng.symbol_spec(sym)
                except Exception as exc:
                    logger.warning("%s symbol_spec unavailable for economics: %s", sym, exc)
                    brain_spec = None
                brain_side = None if hint is None else hint.side
                brain_entry = float(q.ask if brain_side == "buy" else q.bid) if brain_side else None
                decision = intelligent_brain.evaluate(
                    symbol=sym,
                    row=row,
                    completed_m1=completed,
                    positions=eng.positions(),
                    equity=equity,
                    pip=pip,
                    core_side=brain_side,
                    spread_price=float(live_spread),
                    symbol_spec=brain_spec,
                    entry_price=brain_entry,
                    actual_bid=float(q.bid),
                    actual_ask=float(q.ask),
                    quote_buffer=quote_buffer,
                    now_ts=now_ts,
                )
                brain_decision = decision
                if decision.action in {"exit", "reduce"}:
                    open_pos = list(eng.positions(sym))
                    thesis_key_now = str(decision.journal.get("thesis_key") or "")
                    owned_tickets: set[str] = set()
                    if intelligent_brain is not None and thesis_key_now:
                        mem = intelligent_brain.memory.theses.get(thesis_key_now)
                        if mem is not None and mem.tickets:
                            owned_tickets = {
                                t for t in mem.tickets
                                if any(str(getattr(p, "ticket", "") or "") == t for p in open_pos)
                            }
                    close_n = int(decision.close_clips or (len(open_pos) if decision.action == "exit" else 1))
                    closed = 0
                    if hasattr(eng, "close_ticket") and open_pos:
                        if owned_tickets:
                            # Defect 15: a thesis closes ONLY its own clips.
                            ranked = [p for p in open_pos
                                      if str(getattr(p, "ticket", "") or "") in owned_tickets]
                        else:
                            ranked = sorted(open_pos, key=lambda pos: float(pos.unrealized_pnl))
                        for pos in ranked[: max(close_n, 0)]:
                            ticket = str(getattr(pos, "ticket", "") or "").strip()
                            if not ticket:
                                continue
                            res = eng.close_ticket(ticket)
                            append_journal(
                                journal,
                                {
                                    "event": "intel_brain_exit" if decision.action == "exit" else "intel_brain_reduce",
                                    "symbol": sym,
                                    "action": decision.action,
                                    "reason": decision.reason,
                                    "ticket": ticket,
                                    "pnl": float(pos.unrealized_pnl),
                                    "ok": res.ok,
                                    "msg": res.message,
                                    "bar": str(bar_time),
                                    **dict(decision.journal),
                                },
                            )
                            if res.ok:
                                closed += 1
                                # Sequential learning: exploration closes
                                # update their experiment's evidence.
                                exp_hyp = str(decision.journal.get("hypothesis_id") or "")
                                if (
                                    decision.journal.get("exploration")
                                    and exp_hyp
                                    and intelligent_brain is not None
                                ):
                                    try:
                                        intelligent_brain.record_exploration_close(
                                            hypothesis_id=exp_hyp,
                                            pnl=float(pos.unrealized_pnl),
                                            session=str(decision.journal.get("session") or ""),
                                            regime=str(decision.journal.get("regime") or ""),
                                        )
                                    except Exception:
                                        pass
                                try:
                                    from aegis.intel.outcome_log import append_outcome

                                    append_outcome(
                                        {
                                            "event_type": "position_exit",
                                            "is_exit": True,
                                            "symbol": sym,
                                            "side": pos.side,
                                            "pnl": float(pos.unrealized_pnl),
                                            "reason": decision.reason,
                                            "action": decision.action,
                                            "information_id": decision.information_id,
                                            "analogue_n": decision.analogue_n,
                                        }
                                    )
                                except Exception:
                                    pass
                    leftover = eng.positions(sym)
                    intelligent_brain.memory.apply(
                        sym,
                        "exit" if not leftover else "reduce",
                        side=decision.side,
                        information_id=decision.information_id,
                        target_risk=0.0 if not leftover else max(0.0, float(decision.journal.get("expectancy") or 0.0)),
                        clips=len(leftover),
                        key=thesis_key_now or None,
                    )
                    if firehose_consume_bar(no_signal=True):
                        last_bar_time[sym] = bar_time
                    return
                if decision.action not in {"fire", "scale"}:
                    now_s = time.time()
                    event = "intel_brain_hold" if decision.action == "hold" else "intel_brain_skip"
                    key = f"{sym}:{decision.reason}"
                    if now_s - last_intel_journal.get(key, 0.0) >= 15.0:
                        last_intel_journal[key] = now_s
                        append_journal(
                            journal,
                            {
                                "event": event,
                                "symbol": sym,
                                "action": decision.action,
                                "reason": decision.reason,
                                "analogue_n": decision.analogue_n,
                                "bar": str(bar_time),
                                **dict(decision.journal),
                            },
                        )
                    if decision.action != "hold" and firehose_consume_bar(no_signal=True):
                        last_bar_time[sym] = bar_time
                    return
                sig = Signal(
                    decision.side or "buy",
                    "intelligent_firehose",
                    float(row["close"]),
                    float(decision.sl) if decision.sl is not None else float(row["close"]),
                    float(decision.tp) if decision.tp is not None else None,
                    None,
                    bar_time,
                    decision.reason,
                )
            else:
                sig = signal_from_row(row, loop_cfg)
                if sig is None:
                    if bool(cfg.get("intel_enabled", False)):
                        from aegis.intel.decide import last_intel

                        info = last_intel()
                        if info.get("decision") in ("reject", "wait") and info.get("reason") not in (
                            "",
                            "intel_off",
                        ):
                            now_s = time.time()
                            key = f"{sym}:{info.get('reason')}"
                            if now_s - last_intel_journal.get(key, 0.0) >= 30.0:
                                last_intel_journal[key] = now_s
                                append_journal(
                                    journal,
                                    {
                                        "event": "intel_skip",
                                        "symbol": sym,
                                        "side": info.get("side"),
                                        "decision": info.get("decision"),
                                        "reason": info.get("reason"),
                                        "quality": info.get("quality"),
                                        "mega_votes": info.get("mega_votes"),
                                        "mega_names": info.get("mega_names"),
                                        "bar": str(bar_time),
                                    },
                                )
                    logger.info("No signal %s @ %s close=%.5f", sym, bar_time, float(row["close"]))
                    if firehose_consume_bar(no_signal=True):
                        last_bar_time[sym] = bar_time
                    return
            if sig is None:
                return
            if should_block_scratch_cooldown(
                since_s=None if sym not in last_scratch_at else time.time() - last_scratch_at[sym],
                cfg=cfg,
            ):
                return
            if not intelligent_mode:
                held_now = [p.side for p in eng.positions(sym)]
                age = None if sym not in last_entry_at else time.time() - last_entry_at[sym]
                if not firehose_can_add(
                    open_total=len(eng.positions()),
                    max_positions=max_positions,
                    held_sides=held_now,
                    signal_side=sig.side,
                    stack=stack_clips,
                    max_per_symbol=max_per_symbol,
                    last_entry_age_s=age,
                    clip_interval_s=clip_interval_s,
                    held_pnl=sum(float(p.unrealized_pnl) for p in eng.positions(sym)),
                    no_stack_if_red=bool(cfg.get("firehose_no_stack_if_red", False)),
                ):
                    return
            else:
                age = None if sym not in last_entry_at else time.time() - last_entry_at[sym]
                interval = float(clip_interval_s or 0.0)
                if interval > 0 and age is not None and float(age) < interval:
                    return
                if len(eng.positions()) >= max_positions:
                    return

            sl = float(sig.sl) if sig.sl is not None else None
            tp = float(sig.tp) if sig.tp is not None else None
            if bool(cfg.get("firehose_anchor_quote", True)) and not intelligent_mode:
                anchored = live_firehose_stops(sig.side, q.bid, q.ask, loop_cfg, pip)
                if anchored is None:
                    append_journal(
                        journal,
                        {
                            "event": "spread_skip",
                            "symbol": sym,
                            "reason": "take_vs_live_spread",
                            "spread": live_spread,
                            "bid": float(q.bid),
                            "ask": float(q.ask),
                            "bar": str(bar_time),
                        },
                    )
                    return
                sl, tp = anchored
            order_qty = qty
            if brain_decision is not None and brain_decision.quantity is not None:
                order_qty = float(brain_decision.quantity)
            if str(cfg.get("position_sizing_mode") or "").lower() == "risk" and sl is not None and not intelligent_mode:
                entry = float(q.ask if sig.side == "buy" else q.bid)
                try:
                    spec = ContractSpec.from_mapping(sym, eng.symbol_spec(sym))
                    decision = size_lots_for_risk(
                        equity=float(equity),
                        risk_percent=float(cfg.get("risk_percent", 0) or 0),
                        entry=entry,
                        stop=float(sl),
                        spec=spec,
                    )
                except Exception as exc:
                    logger.warning("%s risk sizing failed: %s", sym, exc)
                    append_journal(
                        journal,
                        {
                            "event": "sizing_skip",
                            "symbol": sym,
                            "reason": str(exc),
                            "bar": str(bar_time),
                        },
                    )
                    return
                if not decision.allowed or decision.lots <= 0:
                    append_journal(
                        journal,
                        {
                            "event": "sizing_skip",
                            "symbol": sym,
                            "reason": decision.reason,
                            "budget": decision.budget_usd,
                            "bar": str(bar_time),
                        },
                    )
                    return
                order_qty = decision.lots
            entry = float(q.ask if sig.side == "buy" else q.bid)
            spec_map = None
            if sl is not None or tp is not None:
                try:
                    spec_map = eng.symbol_spec(sym)
                except Exception:
                    spec_map = None
                sl, tp = normalize_protective_stops(
                    side=sig.side,
                    entry=entry,
                    sl=sl,
                    tp=tp,
                    spec=spec_map,
                    fallback_step=pip,
                )
            req = OrderRequest(
                symbol=sym,
                side=sig.side,
                quantity=order_qty,
                kind="market",
                stop_loss=sl,
                take_profit=tp,
                client_tag=(
                    # Exploration orders carry a compact hypothesis tag so
                    # broker-side SL/TP closes can be attributed back to the
                    # experiment (MT5 comments are short).
                    f"EXP{str(brain_decision.journal.get('hypothesis_id') or '')[-12:]}"
                    if brain_decision is not None and brain_decision.journal.get("exploration")
                    else f"aegis_{sig.reason}"[:40]
                ),
            )
            oms_ok, oms_why = oms_allows(
                req,
                q,
                cfg,
                open_count=len(eng.positions()),
                check_quote_age=False,
            )
            if not oms_ok:
                t2t.note_reject(oms_why)
                append_journal(
                    journal,
                    {
                        "event": "oms_reject",
                        "reason": oms_why,
                        "symbol": sym,
                        "side": sig.side,
                        "qty": order_qty,
                        "sl": req.stop_loss,
                        "tp": req.take_profit,
                        "bar": str(bar_time),
                    },
                )
                logger.info("OMS reject %s %s (%s)", sym, sig.side, oms_why)
                return
            logger.info(
                "SIGNAL %s %s qty=%s sl=%s tp=%s reason=%s spread=%.5f",
                sig.side,
                sym,
                order_qty,
                req.stop_loss,
                req.take_profit,
                sig.reason,
                live_spread,
            )
            client_tag = req.client_tag or f"aegis_{sig.reason}"[:40]
            req = OrderRequest(
                symbol=req.symbol,
                side=req.side,
                quantity=req.quantity,
                kind=req.kind,
                limit_price=req.limit_price,
                stop_loss=req.stop_loss,
                take_profit=req.take_profit,
                client_tag=client_tag,
            )
            if brain_decision is not None:
                append_journal(
                    journal,
                    {
                        "event": "intel_brain_fire",
                        "symbol": sym,
                        "action": brain_decision.action,
                        "reason": brain_decision.reason,
                        "side": brain_decision.side,
                        "analogue_n": brain_decision.analogue_n,
                        "expected_net_value": brain_decision.expected_net_value,
                        "information_id": brain_decision.information_id,
                        "sl": sl,
                        "tp": tp,
                        "qty": order_qty,
                        "bar": str(bar_time),
                        **dict(brain_decision.journal),
                    },
                )
            if not send_orders:
                append_journal(
                    journal,
                    {"event": "dry_run_signal", "symbol": sym, "signal": sig.__dict__},
                )
                print(f"dry_run — not sending {sym}")
                if firehose_consume_bar(order_ok=True, stack_more=stack_clips):
                    last_bar_time[sym] = bar_time
                return
            latency = FireLatency(decision_ts=t0, quote_ts=getattr(q, "time", 0.0) or t0)
            positions_before = list(eng.positions(sym))
            if fire_retry_guard.was_sent(sym, client_tag, now=time.time()):
                # Same thesis was already sent within the window. Do not blindly
                # resend: reconcile first. If exposure appeared, treat as done.
                grew = len(eng.positions(sym)) > len(positions_before)
                if grew:
                    latency.confirmed_ts = time.time()
                    append_journal(
                        journal,
                        {
                            "event": "fire_dedup_reconciled",
                            "symbol": sym,
                            "client_tag": client_tag,
                            "status": "POSITION_CONFIRMED",
                            "bar": str(bar_time),
                        },
                    )
                    if firehose_consume_bar(order_ok=True, stack_more=stack_clips):
                        last_bar_time[sym] = bar_time
                    return
                append_journal(
                    journal,
                    {
                        "event": "fire_dedup_skip",
                        "symbol": sym,
                        "client_tag": client_tag,
                        "status": "TIMEOUT_NO_EXPOSURE",
                        "bar": str(bar_time),
                    },
                )
                return
            # --- Exploration hard limits enforced against BROKER truth
            # (position comments survive runner restarts) plus brain pending
            # reservations for the in-flight window.
            if brain_decision is not None and brain_decision.journal.get("exploration"):
                from aegis.intel.exploration import (
                    ExplorationLimits, exploration_room_reason,
                )

                limits_run = ExplorationLimits.from_cfg(cfg)
                exp_positions = [
                    p for p in eng.positions()
                    if "EXP" in str(getattr(p, "comment", "") or "")
                ]
                total_exp, sym_exp = intelligent_brain.exploration_open_counts(sym)
                # Prospective: take the WORST of broker truth and brain state
                # (pending reservations included) without double counting.
                total_exp = max(total_exp, len(exp_positions))
                sym_exp = max(
                    sym_exp,
                    len([p for p in exp_positions
                         if str(p.symbol).upper() == str(sym).upper()]),
                )
                skip_reason = exploration_room_reason(
                    total_open=total_exp, symbol_open=sym_exp,
                    limits=limits_run,
                )
                if skip_reason is None:
                    # Margin pressure (spec K): broker-measured; block NEW
                    # exploration first - never close a high-EV winner to make
                    # room for an unvalidated experiment. All three controls:
                    # min free-margin, max exploration fraction, min margin level.
                    try:
                        _acct_e = eng.account()
                        _free = float(getattr(_acct_e, "available_funds", 0) or 0)
                        _eq = float(getattr(_acct_e, "equity", 0) or 0)
                        _raw = getattr(_acct_e, "raw", {}) or {}
                        _mlvl = float(_raw.get("margin_level") or 0)
                    except Exception:
                        _free, _eq, _mlvl = None, 0.0, 0.0
                    min_free = float(cfg.get("exploration_min_free_margin_usd", 20) or 20)
                    max_frac = float(cfg.get("exploration_max_margin_fraction", 0.4) or 0.4)
                    min_mlvl = float(cfg.get("exploration_min_margin_level", 300) or 300)
                    used_frac = (
                        (_eq - _free) / _eq if (_eq and _free is not None and _eq > 0)
                        else 0.0
                    )
                    if _free is not None and (_free < min_free or used_frac > max_frac):
                        skip_reason = (
                            f"exploration_margin_pressure:free={_free:.2f},"
                            f"used={used_frac:.0%}"
                        )
                    elif _mlvl > 0 and _mlvl < min_mlvl:
                        skip_reason = f"exploration_min_margin_level:{_mlvl:.0f}"
                if skip_reason:
                    append_journal(
                        journal,
                        {
                            "event": "exploration_limit_skip",
                            "reason": skip_reason,
                            "symbol": sym,
                            "hypothesis_id": str(brain_decision.journal.get("hypothesis_id") or ""),
                            "bar": str(bar_time),
                        },
                    )
                    return
                # Reservation happens HERE (post-guard) so the guard doesn't
                # see its own decision as a conflict.
                _thesis_key = str(brain_decision.journal.get("thesis_key") or "")
                if _thesis_key:
                    intelligent_brain.memory.exploration_pending.setdefault(
                        _thesis_key, []).append(time.time())
                    _mem = intelligent_brain.memory.theses.get(_thesis_key)
                    if _mem is not None:
                        _mem.symbol = sym.upper()
                        _mem.side = brain_decision.side
                        _mem.setup_family = str(brain_decision.journal.get("setup_family") or "")
            # --- Pre-send refresh (P8): the decision was priced on quote q,
            # fetched before the brain ran. If that quote is now stale, fetch
            # ONE fresh tick and re-validate; never send on stale pricing and
            # never disable stale protection to force trades through.
            from aegis.intel.send_guard import (
                margin_precheck_ok,
                estimate_margin,
                min_lot_ok,
                needs_quote_refresh,
                refresh_verdict,
            )

            max_age_send = float(cfg.get("max_quote_age_s", 5.0) or 0.0)
            if needs_quote_refresh(quote_age_s(q), max_age_s=max_age_send):
                quote_refresh_counts["stale_observed_at_send"] += 1
                try:
                    q = eng.quote(sym)
                except Exception as exc:
                    quote_refresh_counts["candidate_invalidated_after_refresh"] += 1
                    append_journal(
                        journal,
                        {
                            "event": "quote_refresh_failed",
                            "symbol": sym,
                            "why": str(exc)[:120],
                            "bar": str(bar_time),
                        },
                    )
                    return
                refreshed_age = quote_age_s(q)
                live_spread = max(0.0, float(q.ask) - float(q.bid))
                verdict = refresh_verdict(
                    new_age_s=refreshed_age,
                    new_spread=live_spread,
                    max_age_s=max_age_send,
                    max_spread=max_spread,
                )
                if not verdict.ok:
                    quote_refresh_counts["candidate_invalidated_after_refresh"] += 1
                    append_journal(
                        journal,
                        {
                            "event": "quote_refresh_invalid",
                            "symbol": sym,
                            "reason": verdict.reason,
                            "age_s": refreshed_age,
                            "spread": live_spread,
                            "max_spread": max_spread,
                            "bar": str(bar_time),
                        },
                    )
                    return
                quote_refresh_counts["fresh_quote_recovered"] += 1
                latency.quote_ts = getattr(q, "time", 0.0) or time.time()
            # --- Margin / min-lot pre-checks: 89% of historical order failures
            # were 10019 No money. Check before hitting the broker.
            try:
                spec_pre = eng.symbol_spec(sym)
            except Exception:
                spec_pre = None
            vmin = float((spec_pre or {}).get("volume_min", 0.0) or 0.0)
            if not min_lot_ok(float(order_qty), vmin):
                quote_refresh_counts["min_lot_precheck_skip"] += 1
                append_journal(
                    journal,
                    {
                        "event": "sizing_skip",
                        "reason": "min_lot_broker",
                        "symbol": sym,
                        "qty": order_qty,
                        "volume_min": vmin,
                        "bar": str(bar_time),
                    },
                )
                return
            try:
                acct_pre = eng.account()
                funds = float(acct_pre.available_funds)
                leverage = float((getattr(acct_pre, "raw", {}) or {}).get("leverage") or 100.0)
            except Exception:
                funds = None
                leverage = 100.0
            if funds is not None:
                contract = float((spec_pre or {}).get("trade_contract_size", 100000.0) or 100000.0)
                ref_price = float(getattr(q, "ask", 0.0) or getattr(q, "bid", 0.0) or 0.0)
                est_margin = estimate_margin(
                    price=ref_price, lots=float(order_qty),
                    contract_size=contract, leverage=leverage,
                )
                if not margin_precheck_ok(funds, est_margin):
                    quote_refresh_counts["margin_precheck_skip"] += 1
                    append_journal(
                        journal,
                        {
                            "event": "margin_precheck_skip",
                            "symbol": sym,
                            "est_margin": round(est_margin, 2),
                            "funds": round(funds, 2),
                            "qty": order_qty,
                            "bar": str(bar_time),
                        },
                    )
                    return
            latency.request_ts = time.time()
            res = eng.place_order(req)
            latency.response_ts = time.time()
            audit = classify_execution(
                ok=res.ok,
                message=res.message,
                filled=res.filled,
                positions_before=positions_before,
                positions_after=list(eng.positions(sym)),
            )
            status = audit["status"]
            execution_status_counts[status] = int(execution_status_counts.get(status, 0)) + 1
            if status in {"POSITION_CONFIRMED", "DEAL_EXECUTED"}:
                latency.confirmed_ts = time.time()
            # Only uncertain outcomes arm the dedup guard. Definitive rejections
            # (e.g. 10016 invalid stops from a stale quote) are safe to retry.
            if status == "TIMEOUT":
                fire_retry_guard.mark_sent(sym, client_tag, time.time())
            t2t_ms = (time.perf_counter() - t0) * 1000.0
            t2t.record_ms(t2t_ms)
            intel_q = None
            if bool(cfg.get("intel_enabled", False)):
                from aegis.intel.decide import last_intel as _last_intel

                intel_q = _last_intel().get("quality")
            mkt_closed_extra: dict = {}
            if not res.ok and is_market_closed_retcode(res.message):
                prev_until = close_block_until
                close_block_until = update_close_backoff(
                    close_block_until, res.message, datetime.now(timezone.utc)
                )
                mkt_closed_extra = {
                    "market_closed": True,
                    "close_block_until": close_block_until,
                }
                if close_block_until > prev_until:
                    logger.warning(
                        "%s open blocked until %.0f; %s",
                        sym,
                        close_block_until,
                        res.message,
                    )
            append_journal(
                journal,
                {
                    "event": "order",
                    "ok": res.ok,
                    "id": res.broker_order_id,
                    "msg": res.message,
                    "symbol": sym,
                    "side": sig.side,
                    "qty": order_qty,
                    "sl": req.stop_loss,
                    "tp": req.take_profit,
                    "reason": sig.reason,
                    "client_tag": client_tag,
                    "spread": live_spread,
                    "bar": str(bar_time),
                    "t2t_ms": round(t2t_ms, 3),
                    "quote_age_s": round(quote_age_s(q), 3),
                    "intel_quality": intel_q,
                    "execution_status": status,
                    "execution_detail": audit.get("detail"),
                    "execution_retcode": audit.get("retcode"),
                    "duplicate_risk": bool(audit.get("duplicate_risk")),
                    "information_id": (
                        brain_decision.information_id if brain_decision is not None else None
                    ),
                    **latency.as_dict(),
                    **mkt_closed_extra,
                },
            )
            print(f"order {sym} ok={res.ok} id={res.broker_order_id} {res.message} status={status}")
            if status in {"POSITION_CONFIRMED", "DEAL_EXECUTED"}:
                circuit.observe(res.message or "", now=time.time(), ok=True)
                if firehose_consume_bar(order_ok=True, stack_more=stack_clips):
                    last_bar_time[sym] = bar_time
                now_s = time.time()
                last_entry_at[sym] = now_s
                position_opened_at[sym] = now_s
                if intelligent_mode and intelligent_brain is not None and brain_decision is not None:
                    # Defect 15: bind the tickets this order actually opened to
                    # THIS thesis, so no other thesis can close them.
                    before_tickets = {
                        str(getattr(p, "ticket", "") or "") for p in positions_before
                    }
                    new_tickets = [
                        str(getattr(p, "ticket", "") or "")
                        for p in eng.positions(sym)
                        if str(getattr(p, "ticket", "") or "") not in before_tickets
                    ]
                    thesis_key_now = str(brain_decision.journal.get("thesis_key") or "") or None
                    if new_tickets and thesis_key_now:
                        intelligent_brain.memory.bind_tickets(thesis_key_now, sym, new_tickets)
                        # Persist exact ticket->hypothesis metadata for PM/FastExit/restart.
                        hypothesis_id = str(brain_decision.journal.get("hypothesis_id") or "")
                        strategy_family = str(brain_decision.journal.get("setup_family") or "")
                        expected_mechanism = str(brain_decision.journal.get("micro_mechanism") or strategy_family)
                        side = brain_decision.side or sig.side
                        entry_price = float(brain_decision.journal.get("entry_price")
                                            or (q.ask if side == "buy" else q.bid))
                        stop_loss = float(brain_decision.sl) if brain_decision.sl is not None else 0.0
                        target_price = brain_decision.tp
                        max_hold_s = int(brain_decision.journal.get("max_hold_s") or 120)
                        regime = str(brain_decision.journal.get("regime") or "")
                        session = str(brain_decision.journal.get("session") or "")
                        information_id = brain_decision.information_id
                        for tk in new_tickets:
                            meta = create_ticket_metadata(
                                ticket=tk,
                                hypothesis_id=hypothesis_id,
                                thesis_key=thesis_key_now,
                                strategy_family=strategy_family,
                                expected_mechanism=expected_mechanism,
                                side=side,
                                entry_price=entry_price,
                                stop_loss=stop_loss,
                                target_price=target_price,
                                max_hold_s=max_hold_s,
                                regime=regime,
                                session=session,
                                information_id=information_id,
                                symbol=sym,
                            )
                            ticket_metadata_store.add(meta)
                    intelligent_brain.memory.apply(
                        sym,
                        brain_decision.action,
                        side=brain_decision.side,
                        information_id=brain_decision.information_id,
                        target_risk=float(brain_decision.expected_net_value or 0.0) or 1.0,
                        clips=len(eng.positions(sym)),
                        key=thesis_key_now,
                    )
                if pa_select_mode:
                    day_trades += 1
            else:
                last_bar_time.pop(sym, None)
                msg = res.message or ""
                if not mkt_closed_extra:
                    if "10019" in msg or "No money" in msg:
                        circuit.observe(msg, now=time.time())
                        try:
                            circuit.save_json(circuit_path)
                        except Exception:
                            pass
                        margin_block_until = time.time() + margin_cooldown_s
                        logger.warning(
                            "%s order not accepted (margin); pause new entries %.0fs. %s",
                            sym,
                            margin_cooldown_s,
                            msg,
                        )
                    else:
                        logger.warning(
                            "%s order status=%s — will retry this bar (dedup-guarded). %s",
                            sym,
                            status,
                            msg,
                        )

        cfg_path = Path(args.config)
        cfg_mtime = 0.0

        def reload_live_yaml() -> None:
            """Pick up YAML fine-tunes without a second runner. Never allow_live."""
            nonlocal cfg, qty, max_hold, max_positions, flatten_profit, scratch_losers
            nonlocal stack_clips, max_per_symbol, clip_interval_s, symbols, cfg_mtime
            nonlocal jpy_cluster_max
            try:
                mtime = cfg_path.stat().st_mtime
            except OSError:
                return
            if mtime <= cfg_mtime:
                return
            try:
                new = load_config(cfg_path)
            except Exception:
                logger.exception("live yaml reload failed")
                return
            new["allow_live"] = False
            cfg.clear()
            cfg.update(new)
            cfg_mtime = mtime
            qty = float(cfg.get("order_quantity", 0.01 if engine_name == "mt5" else 20000))
            max_hold = float(cfg.get("max_hold_seconds", 0) or 0)
            max_positions = int(cfg.get("max_positions", 1) or 1)
            flatten_profit = float(cfg.get("flatten_if_profit_usd", 0) or 0)
            scratch_losers = bool(cfg.get("scratch_losers", True))
            stack_clips = bool(cfg.get("firehose_stack", False))
            max_per_symbol = int(cfg.get("firehose_max_per_symbol", 1) or 1)
            clip_interval_s = float(cfg.get("firehose_clip_interval_s", 0) or 0)
            jpy_cluster_max = int(cfg.get("firehose_jpy_cluster_max", 0) or 0)
            symbols[:] = configured_symbols(cfg)
            risk.risk_percent = float(cfg.get("risk_percent", 0.75))
            risk.max_daily_loss_percent = float(cfg.get("max_daily_loss_percent", 0) or 0)
            risk.max_total_drawdown_percent = float(cfg.get("max_total_drawdown_percent", 0) or 0)
            risk.max_positions = max_positions
            risk.kill_switch = bool(cfg.get("kill_switch", False))
            circuit.reconfigure(
                limit=int(cfg.get("no_money_reject_limit", 3) or 3),
                window_s=float(cfg.get("no_money_window_s", 300) or 300),
                backoff_s=float(cfg.get("execution_backoff_s", 900) or 900),
            )
            logger.info(
                "Reloaded live yaml tp=%s sl=%s dd=%s intel=%s rsi_ext=%s",
                cfg.get("firehose_tp_pips"),
                cfg.get("firehose_sl_pips"),
                risk.max_total_drawdown_percent,
                cfg.get("intel_enabled"),
                cfg.get("intel_skip_rsi_ext"),
            )

        while True:
            try:
                reload_live_yaml()
                if intelligent_brain is not None:
                    intelligent_brain.refresh()
                poll = float(cfg.get("poll_seconds", 60))
                acct = eng.account()
                equity = acct.equity
                all_pos = eng.positions()
                # Continuously sample quotes for ALL watched symbols (not just on new M1 bar)
                now_ts = time.time()
                for sym in symbols:
                    try:
                        q = eng.quote(sym)
                        if q.bid and q.ask:
                            quote_buffer.record_from_quote(sym, {"bid": q.bid, "ask": q.ask, "time": now_ts})
                    except Exception:
                        pass
                extra_hb = {
                    "status": "running",
                    "equity": equity,
                    "open": len(all_pos),
                    "held": [f"{p.symbol}:{p.side}" for p in all_pos],
                    "max_positions": max_positions,
                    "firehose_every_bar": bool(cfg.get("firehose_every_bar")),
                    "position_sizing_mode": str(cfg.get("position_sizing_mode") or ""),
                    "risk_halted": bool(risk.state.halted),
                    "risk_reason": str(risk.state.reason or ""),
                    "circuit_blocked_until": float(circuit.blocked_until or 0),
                }
                _risk_ok, _risk_why = risk.allow(equity, open_positions=len(all_pos))
                extra_hb["risk_halted"] = bool(risk.state.halted) or (not _risk_ok)
                extra_hb["risk_reason"] = str(risk.state.reason or _risk_why or "")
                _c_ok, _c_why = circuit.allow(now=time.time())
                extra_hb["circuit_ok"] = bool(_c_ok)
                if not _c_ok:
                    extra_hb["circuit_reason"] = _c_why
                extra_hb.update(t2t.snapshot())
                if execution_status_counts:
                    extra_hb["execution_status"] = dict(execution_status_counts)
                extra_hb["quote_refresh"] = dict(quote_refresh_counts)
                extra_hb["fast_exit_errors"] = fast_exit_error_count
                if intelligent_brain is not None:
                    extra_hb.update(intelligent_brain.snapshot())
                    # Profit-management reporting (spec O) + exposure metrics
                    # (spec J): per-ticket table answers, for every open
                    # winner, WHY it is still being held.
                    try:
                        extra_hb["profit_management"] = profit_manager.snapshot()
                        # Spec J (audited): self-hedge is PER SYMBOL, then
                        # aggregated - not portfolio-wide long vs short.
                        _per_sym: dict[str, dict[str, float]] = {}
                        for _p in eng.positions():
                            _q = float(getattr(_p, "quantity", 0) or 0)
                            _s = str(getattr(_p, "symbol", "?"))
                            d = _per_sym.setdefault(_s, {"long": 0.0, "short": 0.0})
                            if str(getattr(_p, "side", "")).lower() == "buy":
                                d["long"] += _q
                            else:
                                d["short"] += _q
                        gross_l = gross_s = hedged = hedge_cost = 0.0
                        for _s, d in _per_sym.items():
                            gross_l += d["long"]
                            gross_s += d["short"]
                            h = min(d["long"], d["short"])
                            hedged += h
                            # Estimated double-spread cost of fighting
                            # ourselves: 1.0 pip typical spread * $10/pip/lot.
                            hedge_cost += h * 2.0 * 1.0 * 10.0
                        extra_hb["exposure"] = {
                            "gross_long_exposure": round(gross_l, 4),
                            "gross_short_exposure": round(gross_s, 4),
                            "net_exposure": round(gross_l - gross_s, 4),
                            "hedged_exposure": round(hedged, 4),
                            "cost_of_internal_hedge_usd_est": round(hedge_cost, 2),
                            "per_symbol_hedged": {
                                s: round(min(d["long"], d["short"]), 4)
                                for s, d in sorted(_per_sym.items())
                                if min(d["long"], d["short"]) > 0
                            },
                        }
                    except Exception:
                        pass
                    extra_hb["intelligent_firehose"] = True
                else:
                    extra_hb["intelligent_firehose"] = bool(cfg.get("intelligent_firehose", False))
                if hasattr(eng, "history_deals"):
                    try:
                        for event in ingest_deals(eng.history_deals(1), deal_cursor):
                            # Attribution map: ENTRY deals carry the original
                            # EXP comment; SL/TP exit deals get theirs overwritten
                            # by MT5 ('[sl ...]'/'[tp ...]'), so match via
                            # position_id instead of the comment.
                            exp_store = (
                                intelligent_brain.experiments
                                if intelligent_brain is not None else None
                            )
                            if exp_store is not None:
                                tag = str(event.get("comment") or "")
                                idx = tag.find("EXP")
                                if int(event.get("entry") or 0) == 0 and idx >= 0:
                                    rec = intelligent_brain.find_experiment_by_tag(tag)
                                    if rec is not None:
                                        exp_store.remember_position(
                                            str(event.get("position_id") or ""),
                                            str(rec["hypothesis_id"]),
                                        )
                            if event.get("is_exit"):
                                from aegis.intel.outcome_log import append_outcome

                                append_outcome(
                                    {
                                        **event,
                                        "event_type": "position_exit",
                                        "source": "reconcile",
                                    }
                                )
                                if exp_store is not None:
                                    hyp_id = exp_store.hypothesis_for_position(
                                        str(event.get("position_id") or "")
                                    )
                                    if not hyp_id:
                                        exp_rec = intelligent_brain.find_experiment_by_tag(
                                            str(event.get("comment") or "")
                                        )
                                        hyp_id = (
                                            str(exp_rec["hypothesis_id"]) if exp_rec else None
                                        )
                                    if hyp_id:
                                        try:
                                            intelligent_brain.record_exploration_close(
                                                hypothesis_id=hyp_id,
                                                pnl=float(event.get("pnl") or 0.0),
                                                session="",
                                                regime="",
                                            )
                                        except Exception:
                                            pass
                        save_cursor(deal_cursor, reconcile_cursor_path)
                    except Exception as exc:
                        logger.error(
                            "reconciliation failed: %s (cursor preserved)",
                            exc,
                            exc_info=True,
                        )
                if close_block_until > 0:
                    extra_hb["close_block_until"] = close_block_until
                    extra_hb["close_block_until_iso"] = datetime.fromtimestamp(
                        close_block_until, timezone.utc
                    ).isoformat()
                write_heartbeat(extra_hb)
                try:
                    risk.save_json(risk_path)
                except Exception:
                    pass

                holding: list[str] = []
                # Intelligent mode flag is finalized per-symbol below; the
                # profit-management pre-pass only needs the config truth.
                intelligent_mode = bool(cfg.get("intelligent_firehose", False))
                # --- Intelligent per-thesis profit management (spec B-H,P):
                # runs BEFORE the symbol loop so every open ticket gets a
                # HOLD/LOCK/EXIT decision with an explicit explanation.
                if intelligent_mode and intelligent_brain is not None:
                    try:
                        all_open = eng.positions()
                        meta_by_ticket: dict[str, dict] = {}
                        # FIRST: use exact ticket metadata as source of truth
                        for _p in all_open:
                            _tk = str(getattr(_p, "ticket", "") or "")
                            if not _tk:
                                continue
                            _ticket_meta = ticket_metadata_store.get(_tk)
                            if _ticket_meta is not None:
                                # Fresh ticket: exact metadata exists - use it exclusively
                                meta_by_ticket[_tk] = {
                                    "thesis_key": _ticket_meta.thesis_key,
                                    "hypothesis_id": _ticket_meta.hypothesis_id,
                                    "stage": "EXPLORATION_CANARY",
                                    "family": _ticket_meta.strategy_family,
                                    "target": _ticket_meta.target_price,
                                    "max_hold_s": _ticket_meta.max_hold_s,
                                    "regime": _ticket_meta.regime,
                                    "session": _ticket_meta.session,
                                    "side": _ticket_meta.side,
                                    "entry": _ticket_meta.entry_price,
                                    "stop": _ticket_meta.stop_loss,
                                    "mechanism": _ticket_meta.expected_mechanism,
                                    "information_id": _ticket_meta.information_id,
                                }
                            # else: legacy ticket - will be handled below
                        # SECOND: legacy tickets without exact metadata - fallback to experiment scan
                        for _p in all_open:
                            _tk = str(getattr(_p, "ticket", "") or "")
                            if _tk in meta_by_ticket:
                                continue
                            # Adopt broker-held exploration tickets by tag so
                            # PM covers positions opened before a restart.
                            _tag = str(getattr(_p, "comment", "") or "")
                            if "EXP" in _tag:
                                _rec = intelligent_brain.find_experiment_by_tag(_tag)
                                if _rec is not None:
                                    meta_by_ticket[_tk] = {
                                        "thesis_key": "",
                                        "hypothesis_id": str(_rec["hypothesis_id"]),
                                        "stage": "EXPLORATION_CANARY",
                                        "family": str(_rec.get("strategy_family") or ""),
                                    }
                        profit_manager.sync(all_open, meta_by_ticket=meta_by_ticket)
                        # Live marks for remaining-EV (audited fix 3): use
                        # current bid (buy exit) / ask (sell exit), not entry.
                        live_marks: dict[str, dict[str, float]] = {}
                        for pos in all_open:
                            sym_l = str(getattr(pos, "symbol", ""))
                            if sym_l in live_marks:
                                continue
                            try:
                                _q = eng.quote(sym_l)
                                live_marks[sym_l] = {
                                    "bid": float(_q.bid), "ask": float(_q.ask)}
                            except Exception:
                                pass
                        # Position inventory (audited defect 3): classify EVERY
                        # open ticket - origin, exploration?, hypothesis,
                        # thesis, legacy/unattributed, broker comment, risk.
                        inventory = []
                        for pos in all_open:
                            tk = str(getattr(pos, "ticket", "") or "")
                            meta_t = meta_by_ticket.get(tk) or {}
                            _ticket_meta = ticket_metadata_store.get(tk)
                            comment = str(getattr(pos, "comment", "") or "")
                            is_exp = "EXP" in comment
                            if _ticket_meta is not None:
                                hyp_id = _ticket_meta.hypothesis_id
                                thesis_id = _ticket_meta.thesis_key
                                legacy_unattributed = False
                            else:
                                hyp_id = (
                                    meta_t.get("hypothesis_id")
                                    or (intelligent_brain.find_experiment_by_tag(comment)
                                        and intelligent_brain.find_experiment_by_tag(
                                            comment)["hypothesis_id"])
                                    or ""
                                )
                                thesis_id = meta_t.get("thesis_key") or ""
                                legacy_unattributed = is_exp and not meta_t.get("thesis_key")
                            inventory.append({
                                "ticket": tk,
                                "symbol": str(getattr(pos, "symbol", "")),
                                "side": str(getattr(pos, "side", "")),
                                "quantity": float(getattr(pos, "quantity", 0) or 0),
                                "origin": ("exploration" if is_exp else
                                           ("core" if not intelligent_mode else
                                            "intelligent_unattributed")),
                                "exploration": bool(is_exp),
                                "hypothesis_id": hyp_id,
                                "thesis_id": thesis_id,
                                "legacy_unattributed": legacy_unattributed,
                                "client_comment": comment[:40],
                                "risk_usd_est": round(
                                    abs(float(getattr(pos, "unrealized_pnl", 0) or 0)),
                                    4),
                            })
                        now_inv = time.time()
                        if now_inv - last_inventory_journal.get("ts", 0) >= 300:
                            last_inventory_journal["ts"] = now_inv
                            append_journal(
                                journal,
                                {"event": "position_inventory",
                                 "positions": inventory,
                                 "unattributed_exploration": sum(
                                     1 for i in inventory
                                     if i["exploration"] and i["legacy_unattributed"]),
                                 },
                            )
                        acct_pm = eng.account()
                        free_margin = float(getattr(acct_pm, "available_funds", 0) or 0)
                        equity_pm = float(getattr(acct_pm, "equity", 0) or 0)
                        margin_pressure = (
                            equity_pm > 0
                            and free_margin < float(cfg.get("pm_min_free_margin_usd", 20) or 20)
                        )
                        for pos in all_open:
                            tk = str(getattr(pos, "ticket", "") or "")
                            # Current remaining-EV estimate (audited fix 3):
                            # live exit mark = bid for buy, ask for sell.
                            _rem_ev, _rem_status = None, "UNKNOWN"
                            _track = profit_manager.tracks.get(tk)
                            if _track is not None:
                                _tgt = _track.target
                                _inv = _track.invalidation or _track.current_sl
                                _sym_l = str(getattr(pos, "symbol", ""))
                                marks = live_marks.get(_sym_l, {})
                                _cur = (
                                    marks.get("bid") if str(_track.side) == "buy"
                                    else marks.get("ask")
                                )
                                _px = float(_track.entry_price or 0)
                                spread_cost = 0.0
                                if marks.get("bid") and marks.get("ask"):
                                    spread_cost = marks["ask"] - marks["bid"]
                                if _tgt and _inv and _px and _cur:
                                    sign = 1.0 if str(_track.side) == "buy" else -1.0
                                    rem_rr = ((_tgt - _cur) * sign) / max(
                                        abs(_cur - _inv), 1e-9)
                                    init_rr = abs(_tgt - _px) / max(
                                        abs(_px - _inv), 1e-9)
                                    base_ev = float(_track.entry_ev_at_open or 0.0)
                                    _rem_ev = round(
                                        base_ev * max(0.0, min(2.0, rem_rr / max(init_rr, 1e-9))),
                                        4)
                                    _rem_status = "ESTIMATED"
                            verdict = profit_manager.evaluate(
                                ticket=tk,
                                volume=float(getattr(pos, "quantity", 0) or 0),
                                volume_min=0.01,
                                regime_now=str((intelligent_brain.regime_by_symbol or {})
                                               .get(str(getattr(pos, "symbol", "")), "")),
                                margin_pressure=margin_pressure,
                                remaining_ev=_rem_ev,
                                remaining_ev_status=_rem_status,
                            )
                            # Fast exit state machine governs FAST tickets.
                            _is_fast = False
                            _ticket_meta = ticket_metadata_store.get(tk)
                            if _ticket_meta is not None:
                                # Fresh ticket with exact metadata - use it for fast exit
                                _is_fast = True
                            elif meta_by_ticket.get(tk, {}).get("hypothesis_id") and "EXP" in str(getattr(pos, "comment", "")):
                                # Legacy ticket - fallback to experiment scan
                                _is_fast = True
                            if _is_fast and intelligent_brain is not None:
                                try:
                                    _sym = str(getattr(pos, "symbol", ""))
                                    _side_l = str(getattr(pos, "side", "")).lower()
                                    # Build context for production FastExit helper
                                    from aegis.intel.fast_exit_runner import FastExitContext, evaluate_fast_exit, MissingLiquidationMarkError
                                    from aegis.intel.broker_math import BrokerSymbolSpec
                                    _pip_sz = pip_size_for(_sym, cfg) if _sym else 0.0001
                                    _entry_px = float(getattr(pos, "avg_price", 0) or 0)
                                    _cur_bid = live_marks.get(_sym, {}).get("bid")
                                    _cur_ask = live_marks.get(_sym, {}).get("ask")
                                    # Determine legacy hypothesis ID for legacy ticket fallback
                                    _legacy_hyp_id = None
                                    if _ticket_meta is None:
                                        _legacy_hyp_id = meta_by_ticket.get(tk, {}).get("hypothesis_id")
                                    fast_exit_ctx = FastExitContext(
                                        symbol=_sym,
                                        ticket=tk,
                                        side=_side_l,
                                        entry_price=_entry_px,
                                        current_bid=_cur_bid or 0.0,
                                        current_ask=_cur_ask or 0.0,
                                        avg_price=_entry_px,
                                        stop_loss=float(getattr(pos, "stop_loss", 0) or 0),
                                        quantity=float(getattr(pos, "quantity", 0.01)),
                                        mfe_usd=float(_track.mfe_usd or 0),
                                        mae_usd=float(_track.mae_usd or 0),
                                        opened_ts=_track.opened_ts,
                                        regime_at_entry=_track.regime_at_entry,
                                        track_target=_track.target if _track else 0.0,
                                        track_invalidation=_track.invalidation if _track else 0.0,
                                        track_entry_ev=float(_track.entry_ev_at_open or 0.0),
                                        track_side=_side_l,
                                        ticket_meta=_ticket_meta,
                                        engine_spec=eng.symbol_spec(_sym) if hasattr(eng, 'symbol_spec') else None,
                                        config=cfg,
                                        live_marks=live_marks,
                                        intelligent_brain=intelligent_brain,
                                        profit_manager=profit_manager,
                                        now_ts=time.time(),
                                        legacy_hypothesis_id=_legacy_hyp_id,
                                    )
                                    try:
                                        fast_verdict = evaluate_fast_exit(fast_exit_ctx)
                                    except MissingLiquidationMarkError:
                                        fast_exit_error_count += 1
                                        append_journal(journal, {
                                            "event": "fast_exit_error",
                                            "ticket": tk,
                                            "symbol": _sym,
                                            "error_type": "MissingLiquidationMarkError",
                                            "message": f"Missing liquidation mark for {_side_l.upper()}",
                                            "bar": str(bar_time),
                                        })
                                        continue
                                    if fast_verdict["action"] in {"TAKE", "SCRATCH", "ABORT", "TIME_EXIT"}:
                                        verdict = {
                                            "action": "EXIT",
                                            "reason": f"fast_{fast_verdict['action'].lower()}:{fast_verdict['reason']}",
                                            "why": fast_verdict["why"],
                                            "policy": f"fast_{fast_verdict['policy']}",
                                        }
                                except Exception as fast_exc:
                                    fast_exit_error_count += 1
                                    append_journal(journal, {
                                        "event": "fast_exit_error",
                                        "ticket": tk,
                                        "symbol": str(getattr(pos, "symbol", "")),
                                        "error_type": type(fast_exc).__name__,
                                        "message": str(fast_exc)[:200],
                                        "bar": str(bar_time),
                                    })
                            if verdict["action"] == "EXIT" and hasattr(eng, "close_ticket"):
                                res_close = eng.close_ticket(tk)
                                summary = profit_manager.close_summary(
                                    tk, exit_reason=verdict["reason"]
                                )
                                append_journal(
                                    journal,
                                    {
                                        "event": "pm_exit",
                                        "ticket": tk,
                                        "symbol": str(getattr(pos, "symbol", "")),
                                        "ok": bool(res_close.ok),
                                        "policy": verdict.get("policy"),
                                        "why": verdict.get("why"),
                                        **(summary or {}),
                                    },
                                )
                                # Remove ticket metadata on successful close.
                                if res_close.ok:
                                    ticket_metadata_store.remove(tk)
                                if (
                                    res_close.ok
                                    and summary
                                    and summary.get("hypothesis_id")
                                    and intelligent_brain is not None
                                ):
                                    try:
                                        intelligent_brain.record_exploration_close(
                                            hypothesis_id=str(summary["hypothesis_id"]),
                                            pnl=float(summary["realized_pnl"]),
                                            mfe=summary.get("mfe_before_close"),
                                            mae=summary.get("mae_before_close"),
                                            duration_min=(
                                                summary.get("duration_s", 0) / 60.0
                                            ),
                                            session=str(summary.get("session") or ""),
                                            regime=str(summary.get("regime") or ""),
                                            **{
                                                k: v for k, v in summary.items()
                                                if k.startswith(("pl_", "cf_"))
                                            },
                                        )
                                    except Exception:
                                        pass
                            elif verdict["action"] == "LOCK":
                                # 0.01-lot reality: protective STOP ADJUSTMENT
                                # only - never pretend partial close exists.
                                lock_sl = None
                                side_l = str(getattr(pos, "side", "")).lower()
                                px = float(getattr(pos, "avg_price", 0) or 0)
                                buffer_usd = float(
                                    cfg.get("pm_breakeven_buffer_usd", 0.05) or 0.05
                                )
                                spec_lock = BrokerSymbolSpec.from_mapping(
                                    eng.symbol_spec(str(pos.symbol)) if hasattr(eng, 'symbol_spec') else None)
                                from aegis.intel.broker_math import lock_buffer_price
                                pip_l = float((spec_lock.trade_tick_size
                                               or pip_size_for(str(pos.symbol), cfg)))
                                _lot_sz = float(getattr(pos, "quantity", 0.01))
                                price_buffer = lock_buffer_price(buffer_usd, spec_lock, _lot_sz)
                                if side_l == "buy":
                                    lock_sl = px + price_buffer
                                    cur = float(getattr(pos, "stop_loss", 0) or 0)
                                    if cur > 0 and cur >= lock_sl:
                                        lock_sl = None  # never loosen
                                else:
                                    lock_sl = px - price_buffer
                                    cur = float(getattr(pos, "stop_loss", 0) or 0)
                                    if cur > 0 and cur <= lock_sl:
                                        lock_sl = None
                                if lock_sl and hasattr(eng, "modify_stops"):
                                    res_mod = eng.modify_stops(
                                        tk, stop_loss=float(lock_sl)
                                    )
                                    if getattr(res_mod, "ok", False):
                                        track_l = profit_manager.tracks.get(tk)
                                        if track_l is not None:
                                            track_l.lock_armed = True
                                            track_l.locked_profit_usd = buffer_usd
                                            track_l.current_sl = float(lock_sl)
                                append_journal(
                                    journal,
                                    {
                                        "event": "pm_lock",
                                        "ticket": tk,
                                        "symbol": str(getattr(pos, "symbol", "")),
                                        "lock_sl": lock_sl,
                                        "why": verdict.get("why"),
                                    },
                                )
                    except Exception as exc:
                        logger.warning("profit-management cycle error: %s", exc)
                for sym in symbols:
                    try:
                        open_pos = eng.positions(sym)
                        if open_pos:
                            opened = position_opened_at.get(sym)
                            if opened is None:
                                opened = time.time()
                                position_opened_at[sym] = opened
                            held = time.time() - opened
                            pnl = float(open_pos[0].unrealized_pnl)
                            prev_peak = mfe.get(sym)
                            peak = update_mfe(prev_peak, pnl)
                            if prev_peak is None or peak != prev_peak:
                                mfe[sym] = peak
                                save_mfe(mfe_path, mfe)
                            prev_trough = mae.get(sym)
                            trough = update_mae(prev_trough, pnl)
                            if prev_trough is None or trough != prev_trough:
                                mae[sym] = trough
                                save_mfe(mae_path, mae)
                            gb = giveback_reason(peak, pnl, cfg)
                            closed_now = False
                            pnls = [float(p.unrealized_pnl) for p in open_pos]
                            intelligent_mode = bool(cfg.get("intelligent_firehose", False))
                            winners = (
                                quick_win_clips(open_pos, flatten_profit)
                                if flatten_profit > 0 and not intelligent_mode
                                else []
                            )
                            if winners:
                                flat = close_quick_wins(sym, winners, equity, held)
                                leftover_pos = eng.positions(sym)
                                if flat.ok:
                                    peak_left = mfe_after_quick_win(
                                        [float(p.unrealized_pnl) for p in leftover_pos]
                                    )
                                    if peak_left is None:
                                        mfe.pop(sym, None)
                                    else:
                                        mfe[sym] = peak_left
                                    save_mfe(mfe_path, mfe)
                                    mae.pop(sym, None)
                                    save_mfe(mae_path, mae)
                                    if not leftover_pos:
                                        position_opened_at.pop(sym, None)
                                        last_entry_at.pop(sym, None)
                                    closed_now = True
                            elif (not intelligent_mode) and gb:
                                flat = flatten_open(sym, open_pos, equity, held, reason=gb)
                                if flat.ok:
                                    position_opened_at.pop(sym, None)
                                    last_entry_at.pop(sym, None)
                                    last_scratch_at[sym] = time.time()
                                    mfe.pop(sym, None)
                                    save_mfe(mfe_path, mfe)
                                    mae.pop(sym, None)
                                    save_mfe(mae_path, mae)
                                    closed_now = True
                            elif (not intelligent_mode) and should_scratch_never_green(
                                held_s=held, peak=peak, pnls=pnls, cfg=cfg
                            ):
                                flat = flatten_open(
                                    sym, open_pos, equity, held, reason="never_green"
                                )
                                if flat.ok:
                                    position_opened_at.pop(sym, None)
                                    last_entry_at.pop(sym, None)
                                    last_scratch_at[sym] = time.time()
                                    mfe.pop(sym, None)
                                    save_mfe(mfe_path, mfe)
                                    mae.pop(sym, None)
                                    save_mfe(mae_path, mae)
                                    closed_now = True
                            elif max_hold > 0 and held >= max_hold:
                                if scratch_losers or pnl >= 0:
                                    flat = flatten_open(sym, open_pos, equity, held, reason="max_hold")
                                    if flat.ok:
                                        position_opened_at.pop(sym, None)
                                        last_entry_at.pop(sym, None)
                                        mfe.pop(sym, None)
                                        save_mfe(mfe_path, mfe)
                                        mae.pop(sym, None)
                                        save_mfe(mae_path, mae)
                                        closed_now = True
                            if not closed_now:
                                holding.append(f"{sym} {open_pos[0].side} {held:.0f}s pnl={pnl:.2f}")
                                if not stack_clips:
                                    continue
                            open_pos = eng.positions(sym)
                            if open_pos and not stack_clips:
                                continue
                        if not open_pos:
                            position_opened_at.pop(sym, None)
                            if sym in mfe:
                                mfe.pop(sym, None)
                                save_mfe(mfe_path, mfe)
                            if sym in mae:
                                mae.pop(sym, None)
                                save_mfe(mae_path, mae)
                        if len(eng.positions()) >= max_positions:
                            continue
                        if jpy_cluster_blocks(
                            [p.symbol for p in eng.positions()],
                            sym,
                            jpy_cluster_max,
                        ):
                            continue
                        if open_attempt_blocked(time.time(), close_block_until):
                            now_s = time.time()
                            if now_s - last_mktclosed_journal >= 60:
                                last_mktclosed_journal = now_s
                                append_journal(
                                    journal,
                                    {
                                        "event": "open_skip",
                                        "reason": "market_closed_backoff",
                                        "until": close_block_until,
                                        "equity": equity,
                                        "open": len(eng.positions()),
                                    },
                                )
                            continue
                        if time.time() < margin_block_until:
                            now_s = time.time()
                            if now_s - last_nomoney_journal >= 60:
                                last_nomoney_journal = now_s
                                append_journal(
                                    journal,
                                    {
                                        "event": "margin_skip",
                                        "until": margin_block_until,
                                        "equity": equity,
                                        "open": len(eng.positions()),
                                    },
                                )
                            continue
                        maybe_enter(sym, equity, len(eng.positions()))
                    except Exception:
                        logger.exception("Symbol loop error %s", sym)

                if holding:
                    logger.info("Holding %s equity=%.2f", "; ".join(holding), equity)
                if args.once:
                    break
                time.sleep(poll)
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
            risk.save_json(risk_path)
        except Exception:
            pass
        try:
            circuit.save_json(circuit_path)
        except Exception:
            pass
        try:
            lock.release()
        except Exception:
            pass
        try:
            write_heartbeat({"status": "stopped", "pid": os.getpid()})
        except Exception:
            pass
        # Detach only. mt5.shutdown() kills the terminal and the demo session.
        if hasattr(eng, "disconnect"):
            try:
                eng.disconnect()
            except Exception:
                pass


if __name__ == "__main__":
    main()
