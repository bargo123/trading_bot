#!/usr/bin/env python3
"""Run Aegis signals through a broker engine (IBKR paper first; MT5 later)."""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import os
import sys
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

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
    firehose_stop_requested,
    jpy_cluster_blocks,
)
from aegis.risk import RiskEngine, demo_global_loss_halt_disabled  # noqa: E402
from aegis.sizing import ContractSpec, size_lots_for_risk  # noqa: E402
from aegis.strategy import prepare, signal_from_row  # noqa: E402
from aegis.intel.firehose_basket import BasketMetadataStore  # noqa: E402
from aegis.intel.firehose_runtime_evidence import (  # noqa: E402
    attach_runtime_evidence,
    build_runtime_snapshot,
)
from aegis.intel.ticket_metadata import (  # noqa: E402
    create_ticket_metadata,
    firehose_lifecycle_identity,
)
from aegis.intel.send_guard import candidate_spread_limit  # noqa: E402
from aegis.intel.lifecycle import aggregate_confirmed_exit_deals  # noqa: E402
from aegis.intel.opportunity_engine import (  # noqa: E402
    FrozenOpportunity,
    freeze_opportunity,
)

logger = logging.getLogger(__name__)


def video_style_signal_for_scan(
    completed_m1: pd.DataFrame,
    *,
    symbol: str,
    enabled: bool,
):
    """Return the shared video-style signal used to align prediction direction."""
    if not enabled:
        return None
    from aegis.intel.video_style import video_style_signal

    try:
        return video_style_signal(completed_m1, symbol=symbol)
    except (AttributeError, KeyError, TypeError, ValueError):
        return None


def intelligent_refresh_spread_limit(decision, cfg) -> float:
    """Return the selected intelligent candidate's executable spread budget.

    Legacy modes keep the configured universal spread ceiling. Intelligent
    candidates use their already-priced reward geometry and cost inputs;
    missing candidate economics fail closed with a zero budget.
    """
    journal = dict(getattr(decision, "journal", {}) or {})
    nested = journal.get("exploration_economics")
    economics = dict(nested) if isinstance(nested, dict) else journal
    try:
        entry = float(economics["econ_entry"])
        target = float(economics["econ_target"])
        per_unit = economics.get("econ_usd_per_price_unit")
        commission = float(cfg.get("commission_round_trip_usd", 0.0) or 0.0)
        slippage_bps = abs(float(cfg.get("slippage_bps", 0.0) or 0.0))
        slippage_price = abs(entry) * slippage_bps / 10000.0
    except (KeyError, TypeError, ValueError, OverflowError):
        return 0.0
    return candidate_spread_limit(
        entry=entry,
        target=target,
        slippage_price=slippage_price,
        commission_round_trip_usd=commission,
        usd_per_price_unit=per_unit,
    )


def firehose_decision_snapshot(
    *,
    decision,
    symbol: str,
    scan_id: str,
    bar_time,
    side: str,
    qty: float,
    entry: float,
    stop: float | None,
    target: float | None,
    spread: float,
    quote_age: float,
) -> dict[str, object]:
    """Build the durable explanation attached to every submitted order.

    This is intentionally a snapshot of inputs available before the broker
    mutation.  It does not infer missing model or cost evidence.
    """
    journal = dict(getattr(decision, "journal", {}) or {})
    prediction = journal.get("short_horizon_prediction")
    prediction = dict(prediction) if isinstance(prediction, dict) else {}
    comparison = prediction.get("side_comparison")
    comparison = dict(comparison) if isinstance(comparison, dict) else {}
    side_predictions = comparison.get("predictions")
    side_predictions = side_predictions if isinstance(side_predictions, dict) else {}
    economics = {
        "expected_net_value": getattr(decision, "expected_net_value", None),
        "expected_net_usd": journal.get("econ_expected_net_usd"),
        "p_win": journal.get("econ_p_win"),
        "p_win_source": journal.get("econ_p_win_source"),
        "payoff_ratio": journal.get("econ_payoff_ratio"),
        "cost_usd": journal.get("econ_cost_usd"),
        "ok": journal.get("econ_ok"),
        "reason": journal.get("econ_reason"),
    }
    market_state = {
        "bar_time": str(bar_time),
        "regime": journal.get("regime"),
        "structure": journal.get("structure"),
        "session": journal.get("session"),
        "setup_family": journal.get("setup_family"),
        "feature_snapshot": prediction.get("feature_snapshot"),
    }
    return {
        "why": f"WHY_{str(side).upper()}",
        "symbol": str(symbol).upper(),
        "side": str(side).lower(),
        "scan_id": scan_id,
        "lane": "exploration" if journal.get("exploration") else "validated",
        "hypothesis_id": journal.get("hypothesis_id"),
        "mechanism": journal.get("micro_mechanism") or journal.get("setup_family"),
        "model": {
            "status": prediction.get("artifact_status"),
            "execution_status": prediction.get("execution_status"),
            "dataset_hash": prediction.get("dataset_hash"),
            "validation_hash": prediction.get("validation_hash"),
            "artifact_path": prediction.get("artifact_path"),
            "model_version": prediction.get("model_version"),
            "model_count": prediction.get("model_count"),
        },
        "prediction": prediction,
        "predicted_buy": bool(
            isinstance(side_predictions.get("buy"), dict)
            and side_predictions["buy"].get("decision")
            and not side_predictions["buy"].get("abstain", True)
        ),
        "predicted_sell": bool(
            isinstance(side_predictions.get("sell"), dict)
            and side_predictions["sell"].get("decision")
            and not side_predictions["sell"].get("abstain", True)
        ),
        "predicted_abstain": bool(
            not comparison.get("selected_side")
            or prediction.get("abstain", True)
        ),
        "ranking": comparison.get("ranking", []),
        "market_state": market_state,
        "economics": economics,
        "risk": {
            "quantity": float(qty),
            "entry": float(entry),
            "stop": stop,
            "target": target,
            "spread": float(spread),
            "quote_age_s": float(quote_age),
        },
    }


def frozen_opportunity_from_decision(
    *,
    decision: Any,
    symbol: str,
    scan_id: str,
    bar_time: Any,
    bid: float,
    ask: float,
    stop: float | None,
    target: float | None,
    quantity: float,
) -> FrozenOpportunity:
    """Freeze the exact brain-approved candidate before global allocation.

    The selected object is later quote-revalidated, but no second brain pass is
    permitted to replace its identity or geometry.
    """
    journal = dict(getattr(decision, "journal", {}) or {})
    economics = journal.get("exploration_economics")
    economics = dict(economics) if isinstance(economics, dict) else {}
    prediction = journal.get("short_horizon_prediction")
    prediction = dict(prediction) if isinstance(prediction, dict) else {}
    authorization = journal.get("capture_authorization")
    authorization = dict(authorization) if isinstance(authorization, dict) else {}
    exploration = bool(journal.get("exploration"))
    variant_id = str(journal.get("variant_id") or journal.get("hypothesis_id") or "")
    horizon = (
        journal.get("search_horizon_s")
        or prediction.get("decision_horizon_s")
        or journal.get("max_hold_s")
    )
    try:
        horizon = int(horizon) if horizon is not None else None
    except (TypeError, ValueError):
        horizon = None
    expected_ev = getattr(decision, "expected_net_value", None)
    if expected_ev is None:
        expected_ev = economics.get("econ_expected_net_usd")
    authority_probability = authorization.get("probability")
    authority_lcb = authorization.get("lower_95")
    capture_probability = (
        authority_probability if exploration else prediction.get("p_captured_win")
    )
    if capture_probability is None and not exploration:
        capture_probability = prediction.get("probability")
    capture_lcb = (
        authority_lcb if exploration else prediction.get("p_captured_win_lcb95")
    )
    if capture_lcb is None and not exploration:
        capture_lcb = prediction.get("probability_lcb95")
    candidate_id = f"{scan_id}:{variant_id}" if variant_id else scan_id
    return freeze_opportunity({
        "candidate_id": candidate_id,
        "candidate_created_at": time.time(),
        "scan_id": str(scan_id),
        "bar_time": str(bar_time),
        "symbol": str(symbol).upper(),
        "side": str(getattr(decision, "side", "") or "").lower(),
        "lane": str(
            journal.get("exploration_lane")
            or ("exploration" if exploration else "validated")
        ),
        "mechanism": str(journal.get("setup_family") or journal.get("micro_mechanism") or ""),
        "variant_id": variant_id,
        "thesis_key": str(journal.get("thesis_key") or candidate_id),
        "horizon_s": horizon,
        "entry": float(ask if str(getattr(decision, "side", "")).lower() == "buy" else bid),
        "stop": float(stop) if stop is not None else None,
        "target": float(target) if target is not None else None,
        "quantity": float(quantity),
        "bid": float(bid),
        "ask": float(ask),
        "spread": max(0.0, float(ask) - float(bid)),
        "p_captured_win": capture_probability,
        "p_captured_win_lcb95": capture_lcb,
        "authority_type": journal.get("authority_type"),
        "calibration_status": journal.get("calibration_status"),
        "selection_score": journal.get("selection_score"),
        "selection_score_type": journal.get("selection_score_type"),
        "authority_probability": authority_probability,
        "authority_capture_lcb95": authority_lcb,
        "authority_expected_net_ev": expected_ev,
        "expected_net_ev": expected_ev,
        "expected_net_ev_lcb95": (
            economics.get("econ_expected_net_lcb95")
            if exploration else prediction.get("expected_net_pnl_lcb95")
        ),
        "marginal_risk_usd": economics.get("econ_expected_loss_usd"),
        "portfolio_ok": True,
        "shadow_model_probability": journal.get("shadow_model_probability"),
        "authority_evidence_source": authorization.get("evidence_source"),
        "authority_evidence_n": authorization.get("observations"),
        "uncertainty": prediction.get("uncertainty"),
        "expected_time_to_green_s": prediction.get("expected_time_to_green_s"),
        "tail_loss_probability": prediction.get("tail_loss_probability"),
        "fast_winner_similarity": journal.get("fast_winner_similarity", 0.0),
        "fast_loser_similarity": journal.get("fast_loser_similarity", 0.0),
        "decision_journal": journal,
    })


def pending_order_lifecycle_metadata(
    *, decision, snapshot: dict[str, object], symbol: str, side: str,
    entry: float, stop: float | None, target: float | None, client_tag: str,
    config: dict,
) -> dict[str, object]:
    """Serialize point-in-time entry identity before broker mutation."""
    journal = dict(getattr(decision, "journal", {}) or {})
    prediction = snapshot.get("prediction")
    prediction = dict(prediction) if isinstance(prediction, dict) else {}
    model = snapshot.get("model")
    model = dict(model) if isinstance(model, dict) else {}
    economics = snapshot.get("economics")
    economics = dict(economics) if isinstance(economics, dict) else {}
    authorization = journal.get("capture_authorization")
    authorization = dict(authorization) if isinstance(authorization, dict) else {}
    exploration = bool(journal.get("exploration"))
    authority_probability = authorization.get("probability")
    authority_expected_ev = getattr(decision, "expected_net_value", None)
    if authority_expected_ev is None:
        authority_expected_ev = journal.get("authority_expected_net_ev")
    if authority_expected_ev is None:
        authority_expected_ev = economics.get("econ_expected_net_usd")
    p_captured_win = (
        authority_probability
        if exploration
        else prediction.get("probability") or economics.get("p_win")
    )
    selected_horizon = (
        journal.get("search_horizon_s")
        or prediction.get("decision_horizon_s")
        or journal.get("max_hold_s")
    )
    try:
        selected_horizon = int(selected_horizon) if selected_horizon is not None else None
    except (TypeError, ValueError):
        selected_horizon = None
    shadow_probability = journal.get("shadow_model_probability")
    if shadow_probability is None:
        shadow_probability = prediction.get("probability")
    return {
        "client_tag": str(client_tag),
        "symbol": str(symbol).upper(),
        "side": str(side).lower(),
        "hypothesis_id": journal.get("hypothesis_id"),
        "thesis_key": journal.get("thesis_key"),
        "strategy_family": journal.get("setup_family"),
        "expected_mechanism": journal.get("micro_mechanism") or journal.get("setup_family"),
        "selected_horizon_s": selected_horizon,
        "max_hold_s": selected_horizon,
        "entry_price": float(entry),
        "stop_loss": float(stop) if stop is not None else None,
        "target_price": float(target) if target is not None else None,
        "regime": journal.get("regime"),
        "session": journal.get("session"),
        "information_id": getattr(decision, "information_id", None),
        "entry_ev": authority_expected_ev,
        "decision_snapshot": dict(snapshot),
        "model_artifact": model,
        "prediction_snapshot": prediction,
        "feature_snapshot": prediction.get("feature_snapshot"),
        "p_captured_win": p_captured_win,
        "expected_net_pnl": authority_expected_ev if exploration else prediction.get("expected_net_pnl"),
        "expected_net_pnl_lcb95": prediction.get("expected_net_pnl_lcb95"),
        "expected_mfe": prediction.get("expected_mfe"),
        "expected_mae": prediction.get("expected_mae"),
        "expected_time_to_green_s": prediction.get("expected_time_to_green_s"),
        "tail_loss_probability": prediction.get("tail_loss_probability"),
        "spread_assumption": snapshot.get("risk", {}).get("spread") if isinstance(snapshot.get("risk"), dict) else None,
        "slippage_assumption": config.get("slippage_bps"),
        "commission_assumption": config.get("commission_round_trip_usd"),
        "decision_reasons": [
            str(value) for value in (
                getattr(decision, "reason", None),
                journal.get("exploration_authority"),
            ) if value
        ],
        "sell_rejection_reason": journal.get("sell_rejection_reason"),
        "abstain_reason": prediction.get("abstain_reason"),
        "authority_type": journal.get("authority_type") if exploration else "validated_model",
        "authority_probability": authority_probability if exploration else prediction.get("probability"),
        "authority_capture_lcb95": authorization.get("lower_95"),
        "authority_expected_net_ev": authority_expected_ev,
        "authority_horizon_s": selected_horizon,
        "authority_evidence_source": authorization.get("evidence_source") or journal.get("evidence_provenance"),
        "authority_observations": authorization.get("observations") or journal.get("evidence_n"),
        "shadow_model_probability": shadow_probability,
        "basket_metadata": {
            "basket_id": f"firehose-pending-{client_tag}",
            "hypothesis_id": journal.get("hypothesis_id"),
            "family": journal.get("setup_family") or journal.get("micro_mechanism"),
            "symbol": str(symbol).upper(),
            "side": str(side).lower(),
            "trigger_id": str(getattr(decision, "information_id", "") or "pending"),
            "risk_budget": float(config.get("exploration_max_risk_per_trade_usd", 0.15) or 0.15),
            "clip_cap": 1,
            "regime": journal.get("regime"),
            "session": journal.get("session"),
            "cost_evidence": {
                "spread_price": float(snapshot.get("risk", {}).get("spread") or 0.0)
                if isinstance(snapshot.get("risk"), dict) else 0.0,
            },
        },
    }


def exploration_order_risk_check(
    *,
    order_qty: float,
    entry: float,
    stop: float | None,
    pip: float,
    max_risk_usd: float,
    spec: dict | None,
) -> dict[str, object]:
    """Revalidate exploration risk against the quote used for the order.

    The brain sizes from its decision-time quote. A later fresh quote can make
    the same stop/lot pair riskier, so the runner must fail closed immediately
    before ``place_order``.
    """
    if stop is None:
        return {"allowed": False, "reason": "exploration_stop_required", "max_lots": 0.0}
    broker_spec = dict(spec or {})
    tick_values = [
        float(broker_spec.get(name) or 0.0)
        for name in ("trade_tick_value_profit", "trade_tick_value_loss", "trade_tick_value")
    ]
    tick_value = max(tick_values) if any(tick_values) else None
    from aegis.intel.exploration import risk_lots_for_exploration

    sizing = risk_lots_for_exploration(
        max_risk_usd=float(max_risk_usd),
        entry=float(entry),
        invalidation=float(stop),
        pip=float(pip),
        contract_size=float(broker_spec.get("trade_contract_size") or 100000.0),
        tick_value=tick_value,
        tick_size=float(broker_spec.get("trade_tick_size") or 0.0) or None,
        volume_min=float(broker_spec.get("volume_min") or 0.01),
        volume_step=float(broker_spec.get("volume_step") or 0.01),
    )
    max_lots = float(sizing.get("lots") or 0.0)
    if not bool(sizing.get("allowed")):
        return {
            "allowed": False,
            "reason": str(sizing.get("reason") or "exploration_risk_rejected"),
            "max_lots": round(max_lots, 8),
        }
    if float(order_qty) > max_lots + 1e-12:
        return {
            "allowed": False,
            "reason": "exploration_risk_exceeds_budget",
            "max_lots": round(max_lots, 8),
        }
    return {"allowed": True, "reason": "ok", "max_lots": round(max_lots, 8)}


def resize_order_quantity_to_risk(
    *,
    requested_quantity: float,
    max_lots: float,
    volume_min: float,
    volume_step: float,
) -> float | None:
    """Reduce a revalidated order to the broker step without exceeding risk."""
    try:
        requested = float(requested_quantity)
        maximum = float(max_lots)
        minimum = float(volume_min)
        step = float(volume_step)
    except (TypeError, ValueError, OverflowError):
        return None
    if (
        not all(math.isfinite(value) for value in (requested, maximum, minimum, step))
        or requested <= 0
        or maximum <= 0
        or minimum <= 0
        or step <= 0
        or maximum + 1e-12 < minimum
    ):
        return None
    candidate = min(requested, maximum)
    steps = math.floor((candidate + 1e-12) / step)
    resized = round(steps * step, 8)
    if resized + 1e-12 < minimum:
        return None
    return resized


def order_margin_for_send(
    eng,
    *,
    symbol: str,
    side: str,
    quantity: float,
    price: float,
    contract_size: float,
    leverage: float,
) -> tuple[float, str]:
    """Return required margin in account currency, preferring MT5's calculator."""
    native = getattr(eng, "order_margin", None)
    if callable(native):
        try:
            value = float(native(symbol, side, float(quantity), float(price)))
            if math.isfinite(value) and value >= 0.0:
                return value, "broker_native"
        except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
            pass
    from aegis.intel.send_guard import estimate_margin

    return (
        estimate_margin(
            price=float(price), lots=float(quantity),
            contract_size=float(contract_size), leverage=float(leverage),
        ),
        "conservative_formula",
    )


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


def fast_exit_error_event(
    *, ticket: str, symbol: str, error_type: str, message: str, observed_at: object,
) -> dict:
    """Build a FastExit diagnostic without depending on the symbol scan loop."""
    return {
        "event": "fast_exit_error",
        "ticket": ticket,
        "symbol": symbol,
        "error_type": error_type,
        "message": message,
        "bar": str(observed_at),
    }


def firehose_scan_id(symbol: str, bar: object) -> str:
    """Stable identity for one symbol/completed-bar evaluation."""
    payload = f"firehose-scan|{str(symbol).upper()}|{bar}"
    return "scan_" + hashlib.sha256(payload.encode()).hexdigest()[:20]


def meaningful_quote_change(
    previous: Mapping[str, float] | None,
    *,
    bid: float,
    ask: float,
    pip: float,
    fraction_of_pip: float = 0.1,
) -> bool:
    """Whether a fresh executable quote warrants same-bar reevaluation."""
    if previous is None:
        return True
    try:
        threshold = max(abs(float(pip)) * float(fraction_of_pip), 1e-12)
        return (
            abs(float(bid) - float(previous["bid"])) >= threshold
            or abs(float(ask) - float(previous["ask"])) >= threshold
        )
    except (KeyError, TypeError, ValueError):
        return True


def funnel_terminal_for_reason(reason: object) -> str:
    text = str(reason or "").lower()
    if "stale" in text or "future_quote" in text or "quote_refresh" in text:
        return "STALE_REJECT"
    if "spread" in text:
        return "SPREAD_REJECT"
    if "economics" in text or "expected" in text or "ev_" in text:
        return "ECONOMICS_REJECT"
    if "geometry" in text or "stop" in text or "target" in text:
        return "GEOMETRY_REJECT"
    if any(token in text for token in (
        "risk", "margin", "sizing", "lot", "position", "circuit", "halt", "daily_loss",
    )):
        return "RISK_REJECT"
    return "OTHER_REJECT"


def firehose_funnel_risk_row(
    *,
    scan_id: str,
    symbol: str,
    bar: object,
    reason: object,
) -> dict[str, object]:
    """Record a risk terminal without creating broker intent or an order."""
    text = str(reason or "")
    return {
        "event": "firehose_funnel.v1",
        "scan_id": str(scan_id),
        "symbol": str(symbol),
        "bar": str(bar),
        "terminal": funnel_terminal_for_reason(text),
        "micro_candidate_count": 0,
        "book_supported": False,
        "validated_match": False,
        "exploration_eligible": False,
        "brain_intent": False,
        "submitted": False,
        "filled": False,
        "reason": text,
    }


def merge_firehose_funnel_counts(
    base: dict[str, object] | None,
    observed: dict[str, object] | None,
) -> dict[str, object]:
    """Merge cumulative runner observations without decreasing brain counts."""
    stage_aliases = {
        stage.lower(): stage
        for stage in (
            "SCANS", "MICRO_CANDIDATES", "BOOK_SUPPORTED", "VALIDATED_MATCH",
            "EXPLORATION_ELIGIBLE", "SPREAD_REJECT", "ECONOMICS_REJECT",
            "GEOMETRY_REJECT", "RISK_REJECT", "STALE_REJECT", "OTHER_REJECT",
            "FIRES", "FILLS",
        )
    }
    merged: dict[str, int] = {}
    for source in (base or {}, observed or {}):
        for stage, value in source.items():
            try:
                count = max(0, int(value or 0))
            except (TypeError, ValueError):
                continue
            key = stage_aliases.get(str(stage).lower(), str(stage))
            merged[key] = max(merged.get(key, 0), count)
    # The funnel also carries diagnostic values, not counters. Keep these
    # values truthful instead of coercing ``None``/text to zero.
    for key in (
        "BEST_REJECTED_CANDIDATE_EV",
        "BEST_REJECTED_CANDIDATE_P_GREEN",
        "BEST_REJECTED_REASON",
    ):
        if key in (observed or {}):
            merged[key] = (observed or {})[key]
        elif key in (base or {}):
            merged[key] = (base or {})[key]
    return merged


def record_funnel_execution(
    counts: dict[str, int], *, submitted: bool, filled: bool
) -> None:
    """Record only broker execution outcomes in the runner-owned funnel."""
    if submitted:
        counts["FIRES"] = int(counts.get("FIRES", 0)) + 1
    if filled:
        counts["FILLS"] = int(counts.get("FILLS", 0)) + 1


def write_runner_heartbeat(
    path: Path,
    *,
    pid: int,
    symbols: list[str],
    qty: float,
    metrics,
    extra: Optional[dict] = None,
    now: float | None = None,
) -> None:
    """Persist runner health and observed Firehose metrics without research calls."""
    timestamp = time.time() if now is None else float(now)
    payload = {
        "pid": pid,
        "ts": timestamp,
        "iso": datetime.fromtimestamp(timestamp, timezone.utc).isoformat(),
        "symbols": symbols,
        "qty": qty,
        "firehose_turnover": metrics.snapshot(timestamp),
    }
    if extra:
        payload.update(extra)
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_text_atomically(path, json.dumps(payload))


def _write_text_atomically(path: Path, text: str) -> None:
    """Replace a shared runtime report without exposing a partial/truncated file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(str(text), encoding="utf-8")
        os.replace(str(temporary), str(path))
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


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


def validate_virtual_strategy_geometry(
    *,
    side: str,
    entry: float,
    stop: float | None,
    target: float | None,
) -> tuple[bool, str]:
    """Validate controller-owned strategy geometry without broker distances."""
    try:
        entry_f = float(entry)
        stop_f = None if stop is None else float(stop)
        target_f = None if target is None else float(target)
    except (TypeError, ValueError, OverflowError):
        return False, "virtual_geometry_non_numeric"
    if not math.isfinite(entry_f) or entry_f <= 0:
        return False, "virtual_entry_invalid"
    if stop_f is None or not math.isfinite(stop_f) or stop_f <= 0:
        return False, "virtual_stop_invalid"
    side_l = str(side or "").lower()
    if side_l == "buy" and stop_f >= entry_f:
        return False, "virtual_buy_stop_not_below_entry"
    if side_l == "sell" and stop_f <= entry_f:
        return False, "virtual_sell_stop_not_above_entry"
    if target_f is not None:
        if not math.isfinite(target_f) or target_f <= 0:
            return False, "virtual_target_invalid"
        if side_l == "buy" and target_f <= entry_f:
            return False, "virtual_buy_target_not_above_entry"
        if side_l == "sell" and target_f >= entry_f:
            return False, "virtual_sell_target_not_below_entry"
    if side_l not in {"buy", "sell"}:
        return False, "virtual_side_invalid"
    return True, ""


def reprice_frozen_virtual_geometry(
    *,
    side: str,
    discovery_entry: float,
    discovery_stop: float | None,
    discovery_target: float | None,
    fresh_entry: float,
) -> tuple[float, float | None] | None:
    """Reprice the same strategy geometry from a fresh executable entry.

    The side, mechanism, horizon, and thesis identity remain frozen. Only the
    quote-relative virtual levels move with the fresh entry; broker minimum
    stop-distance normalization is deliberately not applied here.
    """
    valid, _ = validate_virtual_strategy_geometry(
        side=side,
        entry=discovery_entry,
        stop=discovery_stop,
        target=discovery_target,
    )
    if not valid:
        return None
    try:
        fresh = float(fresh_entry)
        stop = fresh + (float(discovery_stop) - float(discovery_entry))
        target = (
            None
            if discovery_target is None
            else fresh + (float(discovery_target) - float(discovery_entry))
        )
    except (TypeError, ValueError, OverflowError):
        return None
    valid, _ = validate_virtual_strategy_geometry(
        side=side, entry=fresh, stop=stop, target=target
    )
    return (stop, target) if valid else None


def emergency_broker_stop(
    *,
    symbol: str,
    side: str,
    entry: float,
    virtual_stop: float | None,
    quantity: float,
    spec: dict | None,
    max_risk_usd: float,
    width_multiple: float = 4.0,
    clamp_to_risk: bool = False,
    market_bid: float | None = None,
    market_ask: float | None = None,
) -> float | None:
    """Return a wide catastrophe stop without changing virtual strategy geometry.

    Normal Firehose exits are controller-owned.  This broker stop is only an
    emergency backstop, and is rejected if its wider distance would exceed the
    already-approved per-trade risk budget.
    """
    if virtual_stop is None:
        return None
    try:
        contract = ContractSpec.from_mapping(symbol, dict(spec or {}))
        entry_price = float(entry)
        stop_price = float(virtual_stop)
        lots = float(quantity)
        risk_cap = float(max_risk_usd)
        width = max(1.0, float(width_multiple))
        point = float((spec or {}).get("point") or contract.tick_size)
        stops_level = max(
            int((spec or {}).get("trade_stops_level") or 0),
            int((spec or {}).get("trade_freeze_level") or 0),
        )
    except (TypeError, ValueError, OverflowError):
        return None
    if not all(math.isfinite(value) and value > 0 for value in (entry_price, lots, risk_cap, point)):
        return None
    virtual_distance = abs(entry_price - stop_price)
    if not math.isfinite(virtual_distance) or virtual_distance <= 0:
        return None
    minimum_distance = max(point * 2.0, point * float(stops_level))
    side_l = str(side or "").lower()
    try:
        bid = None if market_bid is None else float(market_bid)
        ask = None if market_ask is None else float(market_ask)
        if bid is not None and ask is not None and bid > 0 and ask >= bid:
            if side_l == "buy":
                minimum_distance = max(minimum_distance, entry_price - bid + point)
            elif side_l == "sell":
                minimum_distance = max(minimum_distance, ask - entry_price + point)
    except (TypeError, ValueError, OverflowError):
        return None
    desired_distance = max(virtual_distance * width, minimum_distance)
    usd_per_price = contract.tick_value / contract.tick_size
    allowed_distance = risk_cap / (usd_per_price * lots) if usd_per_price > 0 else 0.0
    if desired_distance > allowed_distance + 1e-12:
        if not clamp_to_risk or allowed_distance < minimum_distance:
            return None
        # Forced DEMO exploration may use the smallest valid strategy geometry
        # even when a 4R emergency backstop would exceed the same approved risk
        # cap. Keep the broker protection, but never exceed that cap.
        desired_distance = allowed_distance
    if side_l == "buy":
        return entry_price - desired_distance
    if side_l == "sell":
        return entry_price + desired_distance
    return None


def persist_confirmed_firehose_basket(
    *,
    root: Path,
    ticket_id: str | None,
    metadata: dict,
    contract: dict | None,
    volume: float,
) -> dict[str, str | float]:
    """Persist an initial exact basket only after an already-confirmed fill."""
    if not ticket_id:
        return {"status": "NO_EVIDENCE", "reason": "unconfirmed_fill"}
    symbol = str(metadata.get("symbol") or "").upper()
    try:
        trusted_contract = ContractSpec.from_mapping(symbol, dict(contract or {}))
        if not symbol or trusted_contract.symbol.upper() != symbol:
            raise ValueError("symbol")
        basket_id = str(metadata["basket_id"])
        store = BasketMetadataStore(
            Path(root) / "intel" / "firehose_baskets" / f"{symbol}.json",
            trusted_contract=trusted_contract,
        )
        basket = store.get_basket(basket_id)
        if basket is None:
            basket = store.create_basket(
                basket_id=basket_id,
                hypothesis_id=str(metadata["hypothesis_id"]),
                family=str(metadata["family"]),
                symbol=symbol,
                side=str(metadata["side"]),
                risk_budget=float(metadata["risk_budget"]),
                clip_cap=int(metadata["clip_cap"]),
                tick_value=trusted_contract.tick_value,
                tick_size=trusted_contract.tick_size,
                regime=str(metadata["regime"]),
                session=str(metadata["session"]),
                entry_geometry={
                    "entry_price": float(metadata["entry_price"]),
                    "stop_loss": float(metadata["stop_loss"]),
                },
            )
        if store.get_ticket(str(ticket_id)) is None:
            store.record_ticket(
                basket.basket_id,
                ticket_id=str(ticket_id),
                trigger_id=str(metadata["trigger_id"]),
                clip_sequence=1,
                entry_price=float(metadata["entry_price"]),
                stop_loss=float(metadata["stop_loss"]),
                volume=float(volume),
                cost_evidence=dict(metadata["cost_evidence"]),
                regime=str(metadata["regime"]),
                session=str(metadata["session"]),
            )
    except (KeyError, TypeError, ValueError, OSError):
        return {"status": "NO_EVIDENCE", "reason": "invalid_broker_contract"}
    recorded = store.get_ticket(str(ticket_id))
    if recorded is None:
        return {"status": "NO_EVIDENCE", "reason": "missing_persisted_ticket"}
    return {
        "status": "PERSISTED",
        "basket_id": basket_id,
        "ticket_id": str(ticket_id),
        "initial_risk_usd": recorded.initial_risk,
        "entry_price": recorded.entry_geometry["entry_price"],
        "stop_loss": recorded.entry_geometry["stop_loss"],
    }


def confirmed_position_geometry(position) -> dict[str, float | str]:
    """Return only broker-confirmed fill geometry needed for exact basket risk."""
    try:
        entry_price = float(getattr(position, "avg_price"))
        stop_loss = float(getattr(position, "stop_loss"))
        volume = float(getattr(position, "quantity"))
    except (AttributeError, TypeError, ValueError):
        return {"status": "NO_EVIDENCE", "reason": "missing_confirmed_geometry"}
    if entry_price <= 0 or stop_loss <= 0 or volume <= 0:
        return {"status": "NO_EVIDENCE", "reason": "missing_confirmed_geometry"}
    return {"entry_price": entry_price, "stop_loss": stop_loss, "volume": volume}


def virtual_stop_for_fill(
    *, side: str, entry: float, candidate_stop: object, broker_stop: float,
) -> float:
    """Keep strategy invalidation separate from the broker emergency stop."""
    try:
        value = float(candidate_stop)
        filled = float(entry)
        if str(side or "").lower() == "buy" and value < filled:
            return value
        if str(side or "").lower() == "sell" and value > filled:
            return value
    except (TypeError, ValueError):
        pass
    return float(broker_stop)


def ticket_metadata_from_pending(
    *, ticket: str, pending: dict[str, object], position,
):
    """Rebind pre-send identity to a broker-confirmed position after restart."""
    geometry = confirmed_position_geometry(position)
    if geometry.get("status") == "NO_EVIDENCE":
        return None
    required = (
        pending.get("hypothesis_id"), pending.get("thesis_key"),
        pending.get("strategy_family"), pending.get("expected_mechanism"),
        pending.get("side"), pending.get("symbol") or getattr(position, "symbol", ""),
    )
    if any(not str(value or "").strip() for value in required):
        return None
    virtual_stop = virtual_stop_for_fill(
        side=str(pending["side"]),
        entry=float(geometry["entry_price"]),
        candidate_stop=pending.get("stop_loss"),
        broker_stop=float(geometry["stop_loss"]),
    )
    try:
        max_hold_s = int(
            pending.get("selected_horizon_s")
            or pending.get("max_hold_s")
            or 120
        )
    except (TypeError, ValueError):
        return None
    return create_ticket_metadata(
        ticket=str(ticket),
        hypothesis_id=str(pending["hypothesis_id"]),
        thesis_key=str(pending["thesis_key"]),
        strategy_family=str(pending["strategy_family"]),
        expected_mechanism=str(pending["expected_mechanism"]),
        side=str(pending["side"]),
        entry_price=float(geometry["entry_price"]),
        stop_loss=virtual_stop,
        target_price=pending.get("target_price"),
        max_hold_s=max_hold_s,
        regime=str(pending.get("regime") or ""),
        session=str(pending.get("session") or ""),
        information_id=(
            str(pending["information_id"])
            if pending.get("information_id") is not None else None
        ),
        symbol=str(pending.get("symbol") or getattr(position, "symbol", "")),
        entry_geometry={
            "entry_price": float(geometry["entry_price"]),
            "stop_loss": virtual_stop,
        },
        initial_risk=pending.get("initial_risk"),
        cost_evidence=pending.get("cost_evidence"),
        entry_ev=pending.get("entry_ev"),
        authority_type=pending.get("authority_type"),
        authority_probability=pending.get("authority_probability"),
        authority_capture_lcb95=pending.get("authority_capture_lcb95"),
        authority_expected_net_ev=pending.get("authority_expected_net_ev"),
        authority_horizon_s=pending.get("authority_horizon_s"),
        authority_evidence_source=pending.get("authority_evidence_source"),
        authority_observations=pending.get("authority_observations"),
        shadow_model_probability=pending.get("shadow_model_probability"),
        decision_snapshot=pending.get("decision_snapshot"),
        selected_horizon_s=max_hold_s,
        model_artifact=pending.get("model_artifact"),
        prediction_snapshot=pending.get("prediction_snapshot"),
        feature_snapshot=pending.get("feature_snapshot"),
        p_captured_win=pending.get("p_captured_win"),
        expected_net_pnl=pending.get("expected_net_pnl"),
        expected_net_pnl_lcb95=pending.get("expected_net_pnl_lcb95"),
        expected_mfe=pending.get("expected_mfe"),
        expected_mae=pending.get("expected_mae"),
        expected_time_to_green_s=pending.get("expected_time_to_green_s"),
        tail_loss_probability=pending.get("tail_loss_probability"),
        spread_assumption=pending.get("spread_assumption"),
        slippage_assumption=pending.get("slippage_assumption"),
        commission_assumption=pending.get("commission_assumption"),
        decision_reasons=pending.get("decision_reasons"),
        sell_rejection_reason=pending.get("sell_rejection_reason"),
        abstain_reason=pending.get("abstain_reason"),
    )


def record_confirmed_firehose_open(
    *, root: Path, metadata_store, metrics, journal: Path, ticket_id: str,
    position, basket_metadata: dict, ticket_metadata, opened_at: float,
    slot_capacity: int, contract: dict | None = None,
    decision_reasons: list[str] | None = None, expected_net_value: float | None = None,
    decision_snapshot: dict | None = None,
) -> dict[str, str | float]:
    """Persist exact fill ownership before emitting its Firehose lifecycle."""
    geometry = confirmed_position_geometry(position)
    if geometry.get("status") == "NO_EVIDENCE":
        return geometry
    virtual_stop = virtual_stop_for_fill(
        side=str(getattr(ticket_metadata, "side", "")),
        entry=float(geometry["entry_price"]),
        candidate_stop=getattr(ticket_metadata, "stop_loss", None),
        broker_stop=float(geometry["stop_loss"]),
    )

    basket_result = {"status": "NO_EVIDENCE"}
    if str(basket_metadata.get("trigger_id") or "").strip():
        if not metadata_store.begin_pending_basket_cleanup(
            ticket_id,
            str(basket_metadata.get("basket_id") or ""),
            str(basket_metadata.get("symbol") or ""),
        ):
            logger.error("Failed to persist basket cleanup for untracked ticket %s", ticket_id)
            return {"status": "NO_EVIDENCE", "reason": "pending_basket_cleanup_persistence_failed"}
        basket_result = persist_confirmed_firehose_basket(
            root=root,
            ticket_id=ticket_id,
            metadata={
                **basket_metadata,
                "entry_price": geometry["entry_price"],
                "stop_loss": virtual_stop,
            },
            contract=contract,
            volume=float(geometry["volume"]),
        )
        if basket_result.get("status") != "PERSISTED":
            return basket_result
    persisted = basket_result.get("status") == "PERSISTED"
    snapshot = decision_snapshot
    if snapshot is None:
        snapshot = getattr(ticket_metadata, "decision_snapshot", None)
    metadata = replace(
        ticket_metadata,
        entry_price=float(geometry["entry_price"]),
        stop_loss=virtual_stop,
        basket_id=basket_result.get("basket_id") if persisted else None,
        trigger_id=str(basket_metadata["trigger_id"]) if persisted else None,
        clip_sequence=1 if persisted else None,
        entry_geometry={
            "entry_price": float(basket_result["entry_price"]),
            "stop_loss": float(basket_result["stop_loss"]),
        } if persisted else None,
        initial_risk=float(basket_result["initial_risk_usd"]) if persisted else None,
        cost_evidence=dict(basket_metadata["cost_evidence"]) if persisted else None,
        decision_snapshot=dict(snapshot) if isinstance(snapshot, dict) else None,
    )
    if not metadata_store.add(metadata):
        return {"status": "NO_EVIDENCE", "reason": "ticket_metadata_persistence_failed"}
    if persisted and not metadata_store.clear_pending_basket_cleanup(ticket_id):
        logger.error("Failed to clear basket cleanup for tracked ticket %s", ticket_id)
        return {"status": "NO_EVIDENCE", "reason": "pending_basket_cleanup_persistence_failed"}

    metrics.record_open(ticket_id, opened_at=opened_at, slot_capacity=slot_capacity)
    append_journal(
        journal,
        {
            "event": "firehose_open",
            "ticket": ticket_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "symbol": metadata.symbol,
            "side": metadata.side.upper(),
            "slot_capacity": slot_capacity,
            **firehose_lifecycle_identity(metadata),
        },
    )
    from aegis.intel.firehose_turnover import basket_lifecycle_trace

    basket_trace = basket_lifecycle_trace(
        metadata,
        event="firehose_basket_open",
        timestamp=datetime.now(timezone.utc).isoformat(),
        confirmed=True,
        observation={
            "clips": metadata.clip_sequence,
            "decision_reasons": decision_reasons or [],
            "ev": expected_net_value,
            "turnover": 0.0,
            "decision_snapshot": snapshot,
        },
    )
    if basket_trace is not None:
        append_journal(journal, basket_trace)
    return {"status": "PERSISTED", "ticket_id": ticket_id}


def remove_confirmed_firehose_basket(
    *, root: Path, ticket_id: str, symbol: str, contract: dict | None,
    expected_basket_id: str | None = None,
) -> dict[str, str | bool]:
    """Remove exact persisted basket ownership after broker close confirmation."""
    normalized_symbol = str(symbol or "").upper()
    try:
        trusted_contract = ContractSpec.from_mapping(normalized_symbol, dict(contract or {}))
        if not normalized_symbol or trusted_contract.symbol.upper() != normalized_symbol:
            raise ValueError("symbol")
        store = BasketMetadataStore(
            Path(root) / "intel" / "firehose_baskets" / f"{normalized_symbol}.json",
            trusted_contract=trusted_contract,
        )
        basket_id, basket_closed = store.remove_ticket(
            str(ticket_id), expected_basket_id=expected_basket_id,
        )
    except (OSError, TypeError, ValueError):
        return {"status": "NO_EVIDENCE", "reason": "invalid_broker_contract"}
    if basket_id is None:
        return {"status": "NO_EVIDENCE", "reason": "missing_persisted_ticket"}
    return {"status": "REMOVED", "basket_id": basket_id, "basket_closed": basket_closed}


def confirmed_firehose_basket_ownership(
    *, root: Path, ticket_id: str, symbol: str, basket_id: str, contract: dict | None,
) -> dict[str, str]:
    """Verify the exact persisted basket owns the ticket before mutation."""
    normalized_symbol = str(symbol or "").upper()
    try:
        trusted_contract = ContractSpec.from_mapping(normalized_symbol, dict(contract or {}))
        if not normalized_symbol or trusted_contract.symbol.upper() != normalized_symbol:
            raise ValueError("symbol")
        store = BasketMetadataStore(
            Path(root) / "intel" / "firehose_baskets" / f"{normalized_symbol}.json",
            trusted_contract=trusted_contract,
        )
        basket = store.get_basket(str(basket_id))
    except (OSError, TypeError, ValueError):
        return {"status": "NO_EVIDENCE", "reason": "invalid_broker_contract"}
    if basket is None or str(ticket_id) not in basket.ticket_ids:
        return {"status": "NO_EVIDENCE", "reason": "missing_persisted_ticket"}
    return {"status": "PERSISTED"}


def remove_confirmed_firehose_basket_then_cleanup(
    *, root: Path, metadata_store, guard, ticket_id: str,
    quote_fingerprint: str | None, closed_at: float, contract: dict | None,
    recover_missing_basket: bool = False,
) -> dict:
    """Keep exact basket ownership until its persisted removal succeeds."""
    metadata = metadata_store.get(ticket_id)
    if metadata is None:
        return {"status": "NO_EVIDENCE", "reason": "missing_ticket_metadata"}
    basket_removal = {"status": "NO_EVIDENCE"}
    if metadata.basket_id:
        pending = metadata_store.pending_cleanup(ticket_id)
        if pending is None:
            ownership = confirmed_firehose_basket_ownership(
                root=root,
                ticket_id=ticket_id,
                symbol=metadata.symbol,
                basket_id=metadata.basket_id,
                contract=contract,
            )
            if ownership["status"] != "PERSISTED":
                return ownership
            if not metadata_store.begin_pending_cleanup(ticket_id, {
                "basket_id": metadata.basket_id,
                "symbol": metadata.symbol,
                "quote_fingerprint": quote_fingerprint,
                "closed_at": closed_at,
                "basket_removed": False,
            }):
                return {"status": "NO_EVIDENCE", "reason": "ticket_metadata_persistence_failed"}
            pending = metadata_store.pending_cleanup(ticket_id)
        if pending.get("basket_id") != metadata.basket_id or pending.get("symbol") != metadata.symbol:
            return {"status": "NO_EVIDENCE", "reason": "pending_cleanup_mismatch"}
        if not pending.get("basket_removed"):
            basket_removal = remove_confirmed_firehose_basket(
                root=root,
                ticket_id=ticket_id,
                symbol=metadata.symbol,
                contract=contract,
                expected_basket_id=metadata.basket_id,
            )
            if basket_removal["status"] != "REMOVED":
                if not (
                    recover_missing_basket
                    and basket_removal == {"status": "NO_EVIDENCE", "reason": "missing_persisted_ticket"}
                ):
                    return basket_removal
                basket_removal = {
                    "status": "REMOVED",
                    "basket_id": metadata.basket_id,
                    "basket_closed": False,
                }
            if basket_removal["basket_id"] != metadata.basket_id:
                return {"status": "NO_EVIDENCE", "reason": "basket_id_mismatch"}
            if not metadata_store.mark_pending_basket_removed(
                ticket_id, basket_closed=bool(basket_removal["basket_closed"]),
            ):
                return {"status": "NO_EVIDENCE", "reason": "ticket_metadata_persistence_failed"}
        else:
            basket_removal = {
                "status": "REMOVED",
                "basket_id": metadata.basket_id,
                "basket_closed": bool(pending.get("basket_closed")),
            }
    from aegis.intel.firehose_turnover import confirmed_close_cleanup

    cleanup = confirmed_close_cleanup(
        metadata_store, guard, ticket_id,
        quote_fingerprint=quote_fingerprint, closed_at=closed_at,
    )
    if not cleanup.metadata_removed:
        return {"status": "NO_EVIDENCE", "reason": cleanup.reason or "local_cleanup_failed"}
    return {
        "status": "CLEANED",
        "basket_removal": basket_removal,
        "close_cleanup": cleanup,
    }


def reconcile_confirmed_firehose_basket_cleanups(
    *, root: Path, metadata_store, guard, positions, contract_for_symbol, closed_at: float,
) -> list[dict]:
    """Retry persisted cleanup only after a fresh broker snapshot confirms absence."""
    results = []
    for ticket_id, pending in metadata_store.pending_basket_cleanups().items():
        if any(str(getattr(position, "ticket", "")) == str(ticket_id) for position in positions):
            continue
        metadata = metadata_store.get(ticket_id)
        try:
            contract = contract_for_symbol(pending["symbol"])
        except (AttributeError, OSError, TypeError, ValueError):
            contract = None
        if (
            metadata is not None
            and str(metadata.basket_id) == pending["basket_id"]
            and str(metadata.symbol).upper() == pending["symbol"]
        ):
            cleanup_result = remove_confirmed_firehose_basket_then_cleanup(
                root=root,
                metadata_store=metadata_store,
                guard=guard,
                ticket_id=ticket_id,
                quote_fingerprint=None,
                closed_at=closed_at,
                contract=contract,
                recover_missing_basket=True,
            )
            if cleanup_result["status"] != "CLEANED":
                event = {"ticket_id": ticket_id, "status": cleanup_result["status"]}
                if "reason" in cleanup_result:
                    event["reason"] = cleanup_result["reason"]
                results.append(event)
                continue
            if not metadata_store.clear_pending_basket_cleanup(ticket_id):
                results.append({
                    "ticket_id": ticket_id,
                    "status": "NO_EVIDENCE",
                    "reason": "pending_basket_cleanup_persistence_failed",
                })
                continue
            results.append({
                "ticket_id": ticket_id,
                "status": "CLEANED",
                "basket_removal": cleanup_result["basket_removal"],
            })
            continue
        basket_removal = remove_confirmed_firehose_basket(
            root=root,
            ticket_id=ticket_id,
            symbol=pending["symbol"],
            contract=contract,
            expected_basket_id=pending["basket_id"],
        )
        if basket_removal == {"status": "NO_EVIDENCE", "reason": "missing_persisted_ticket"}:
            basket_removal = {
                "status": "REMOVED",
                "basket_id": pending["basket_id"],
                "basket_closed": False,
            }
        elif basket_removal["status"] != "REMOVED":
            event = {"ticket_id": ticket_id, "status": basket_removal["status"]}
            if "reason" in basket_removal:
                event["reason"] = basket_removal["reason"]
            results.append(event)
            continue
        if not metadata_store.clear_pending_basket_cleanup(ticket_id):
            results.append({
                "ticket_id": ticket_id,
                "status": "NO_EVIDENCE",
                "reason": "pending_basket_cleanup_persistence_failed",
            })
            continue
        results.append({
            "ticket_id": ticket_id,
            "status": "REMOVED",
            "basket_removal": basket_removal,
        })
    for ticket_id, pending in metadata_store.pending_cleanups().items():
        if not close_ticket_confirmed(positions, ticket_id):
            continue
        metadata = metadata_store.get(ticket_id)
        if metadata is None:
            results.append({"ticket_id": ticket_id, "status": "NO_EVIDENCE", "reason": "missing_ticket_metadata"})
            continue
        try:
            contract = contract_for_symbol(metadata.symbol)
        except (AttributeError, OSError, TypeError, ValueError):
            contract = None
        result = remove_confirmed_firehose_basket_then_cleanup(
            root=root,
            metadata_store=metadata_store,
            guard=guard,
            ticket_id=ticket_id,
            quote_fingerprint=pending.get("quote_fingerprint"),
            closed_at=float(pending.get("closed_at", closed_at)),
            contract=contract,
            recover_missing_basket=True,
        )
        event = {"ticket_id": ticket_id, "status": result["status"]}
        if "reason" in result:
            event["reason"] = result["reason"]
        if "basket_removal" in result:
            event["basket_removal"] = result["basket_removal"]
        results.append(event)
    return results


def close_ticket_confirmed(positions, ticket: str) -> bool:
    """Confirm a close only when the exact ticket has no remaining volume."""
    ticket_s = str(ticket)
    return not any(
        str(getattr(position, "ticket", "")) == ticket_s
        and float(getattr(position, "quantity", 0) or 0) > 0
        for position in positions
    )


def broker_close_evidence(deals, *, ticket: str) -> dict[str, object]:
    """Return exact broker close facts, never substituting floating PnL."""
    facts = aggregate_confirmed_exit_deals(deals, position_id=str(ticket))
    if facts is None:
        return {
            "status": "INCOMPLETE_BROKER_EVIDENCE",
            "reason": "exact_exit_deal_not_available",
        }
    return {"status": "BROKER_CONFIRMED", **facts}


def outcome_features_from_ticket_metadata(
    metadata: Any,
    *,
    event: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Reconstruct the exact point-in-time state captured before a fill."""
    event_values = dict(event or {})
    snapshot = getattr(metadata, "decision_snapshot", None)
    snapshot = dict(snapshot) if isinstance(snapshot, Mapping) else {}
    prediction = getattr(metadata, "prediction_snapshot", None)
    prediction = dict(prediction) if isinstance(prediction, Mapping) else {}
    if not prediction and isinstance(snapshot.get("prediction"), Mapping):
        prediction = dict(snapshot["prediction"])
    feature_snapshot = getattr(metadata, "feature_snapshot", None)
    feature_snapshot = dict(feature_snapshot) if isinstance(feature_snapshot, Mapping) else {}
    if not feature_snapshot and isinstance(prediction.get("feature_snapshot"), Mapping):
        feature_snapshot = dict(prediction["feature_snapshot"])

    state: dict[str, Any] = dict(feature_snapshot)
    derived_context = {
        "short_returns": {
            key: value for key, value in feature_snapshot.items()
            if "return" in str(key).lower()
        },
        "quote_tick_dynamics": {
            key: value for key, value in feature_snapshot.items()
            if any(token in str(key).lower() for token in ("quote", "tick"))
        },
        "volatility_context": {
            key: value for key, value in feature_snapshot.items()
            if "volatility" in str(key).lower() or key in {"vol", "atr"}
        },
        "m1_context": {
            key: value for key, value in feature_snapshot.items()
            if str(key).lower().startswith("m1")
        },
        "m5_context": {
            key: value for key, value in feature_snapshot.items()
            if str(key).lower().startswith("m5")
        },
        "m15_context": {
            key: value for key, value in feature_snapshot.items()
            if str(key).lower().startswith("m15")
        },
    }
    state.update({key: value for key, value in derived_context.items() if value})
    observed = {
        "symbol": getattr(metadata, "symbol", None) or event_values.get("symbol"),
        "side": getattr(metadata, "side", None) or event_values.get("side"),
        "mechanism": (
            getattr(metadata, "expected_mechanism", None)
            or getattr(metadata, "strategy_family", None)
            or event_values.get("mechanism")
            or event_values.get("family")
        ),
        "horizon_s": (
            getattr(metadata, "selected_horizon_s", None)
            or getattr(metadata, "max_hold_s", None)
            or event_values.get("horizon_s")
        ),
        "selected_horizon_s": getattr(metadata, "selected_horizon_s", None),
        "session": getattr(metadata, "session", None) or event_values.get("session"),
        "regime": getattr(metadata, "regime", None) or event_values.get("regime"),
        "entry_time": getattr(metadata, "opened_ts", None),
        "entry_price": getattr(metadata, "entry_price", None),
        "stop_price": getattr(metadata, "stop_loss", None),
        "target_price": getattr(metadata, "target_price", None),
        "entry_geometry": getattr(metadata, "entry_geometry", None),
        "geometry": getattr(metadata, "entry_geometry", None),
        "initial_risk_usd": getattr(metadata, "initial_risk", None),
        "p_captured_win": getattr(metadata, "p_captured_win", None),
        "entry_ev": getattr(metadata, "entry_ev", None),
        "spread_assumption": getattr(metadata, "spread_assumption", None),
        "expected_net_pnl": getattr(metadata, "expected_net_pnl", None),
        "cost_assumptions": {
            "spread": getattr(metadata, "spread_assumption", None),
            "slippage": getattr(metadata, "slippage_assumption", None),
            "commission": getattr(metadata, "commission_assumption", None),
        },
        "cost_evidence": getattr(metadata, "cost_evidence", None),
        "prediction_snapshot": prediction,
        "model_artifact": getattr(metadata, "model_artifact", None),
        "decision_snapshot": snapshot,
    }
    for key, value in observed.items():
        if value is not None:
            state[key] = value
    return state


def broker_replay_usd_per_price_unit(
    engine: Any,
    *,
    symbol: str,
    close_facts: Mapping[str, Any],
) -> float:
    """Use broker-native money conversion for post-close research replay."""
    try:
        from aegis.intel.broker_math import BrokerSymbolSpec

        spec = BrokerSymbolSpec.from_mapping(engine.symbol_spec(symbol))
        quantity = float(close_facts.get("entry_quantity") or 0.0)
        unit = spec.usd_per_price_unit_per_lot() * quantity
        return unit if math.isfinite(unit) and unit > 0 else 1.0
    except (AttributeError, OSError, TypeError, ValueError, OverflowError):
        return 1.0


def record_broker_confirmed_outcome_learning(
    *,
    outcome_memory: Any,
    outcome_id: str,
    close_facts: Mapping[str, Any],
    metadata: Any,
    lifecycle_detail: Mapping[str, Any] | None,
    quote_buffer: Any = None,
    event: Mapping[str, Any] | None = None,
    counterfactual_geometries: Mapping[str, Mapping[str, Any]] | None = None,
    alternative_horizons_s: tuple[int, ...] | list[int] | None = None,
    usd_per_price_unit: float = 1.0,
) -> dict[str, Any]:
    """Record or stage one completed ticket without using floating PnL."""
    from aegis.intel.outcome_memory import _finite

    state = outcome_features_from_ticket_metadata(metadata, event=event)
    detail = dict(lifecycle_detail or {})
    symbol = str(state.get("symbol") or "").upper()
    entry_time = state.get("entry_time")
    close_timestamp = close_facts.get("close_timestamp") if isinstance(close_facts, Mapping) else None
    try:
        closed_at = (
            datetime.fromisoformat(str(close_timestamp).replace("Z", "+00:00")).timestamp()
            if close_timestamp else (
                float(event["time_msc"]) / 1000.0
                if event is not None and event.get("time_msc") else time.time()
            )
        )
    except (TypeError, ValueError, OverflowError):
        closed_at = time.time()
    quotes: list[Mapping[str, Any]] = []
    if quote_buffer is not None and symbol and entry_time is not None:
        try:
            quotes = quote_buffer.quotes_between(symbol, float(entry_time), closed_at)
        except (AttributeError, TypeError, ValueError):
            quotes = []
    cost_usd = abs(
        float(close_facts.get("round_trip_cost_usd", close_facts.get("cost_usd", 0.0)) or 0.0)
    ) if isinstance(close_facts, Mapping) else 0.0
    if counterfactual_geometries is None and isinstance(
        state.get("counterfactual_geometries"), Mapping
    ):
        counterfactual_geometries = state["counterfactual_geometries"]
    common = {
        "outcome_id": str(outcome_id),
        "features": state,
        "mfe_usd": detail.get("mfe_usd"),
        "mae_usd": detail.get("mae_usd"),
        "time_to_green_s": detail.get("first_green_s"),
        "counterfactual_quotes": quotes,
        "counterfactual_geometries": counterfactual_geometries,
        "alternative_horizons_s": alternative_horizons_s,
        "counterfactual_cost_usd": cost_usd,
        "counterfactual_usd_per_price_unit": usd_per_price_unit,
        "exit_reason": detail.get("exit_reason") or (
            event.get("close_reason") if event is not None else None
        ),
    }
    if close_facts.get("status") != "BROKER_CONFIRMED":
        return outcome_memory.stage_pending_close(**common)
    if _finite(close_facts.get("realized_net_usd")) is None:
        return outcome_memory.stage_pending_close(**common)
    return outcome_memory.record_confirmed_close(
        **common,
        broker_facts=close_facts,
    )


def legacy_normal_exit_enabled(intelligent_mode: bool) -> bool:
    """Keep legacy CORE exits out of the intelligent Firehose lane."""
    return not bool(intelligent_mode)


def main() -> None:
    parser = argparse.ArgumentParser(description="Aegis broker-engine paper runner")
    parser.add_argument("--config", default=str(ROOT / "config_ib_paper_eurusd.yaml"))
    parser.add_argument("--once", action="store_true")
    parser.add_argument(
        "--video-style",
        action="store_true",
        help="enable the shared universal video-style Firehose candidate policy",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    cfg = load_config(args.config)
    stop_file = ROOT / "reports" / "FIREHOSE_STOP"
    video_style_mode = bool(args.video_style)
    if video_style_mode:
        # Video-style behavior selects a candidate horizon; it must not
        # replace that identity with a blanket hold override.
        cfg.pop("_video_style_max_hold_s", None)
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
    last_quote_state: dict[str, dict[str, float]] = {}
    deferred_opportunities: list[FrozenOpportunity] = []
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
    submitted_count = 0
    fill_count = 0
    hot_path_discovery_to_send_ms: list[float] = []
    oms_reject_reasons: dict[str, int] = {}
    quote_refresh_counts: dict[str, int] = {
        "stale_observed_at_send": 0,
        "fresh_quote_recovered": 0,
        "candidate_invalidated_after_refresh": 0,
        "virtual_geometry_reject": 0,
        "broker_geometry_reject": 0,
        "risk_resized": 0,
        "order_sent_after_refresh": 0,
        "margin_precheck_skip": 0,
        "min_lot_precheck_skip": 0,
        "risk_budget_precheck_skip": 0,
    }
    observed_funnel_counts: dict[str, int] = {"SCANS": 0, "RISK_REJECT": 0}
    global_opportunity_counts: dict[str, int] = {
        "GLOBAL_CANDIDATES": 0,
        "GLOBAL_RANKED": 0,
        "GLOBAL_SELECTED": 0,
        "GLOBAL_REVALIDATED": 0,
        "GLOBAL_INVALIDATED_ON_REFRESH": 0,
    }
    fast_exit_error_count: int = 0
    # Quote buffer for genuine sub-minute features
    from aegis.intel.quote_buffer import QuoteBuffer
    quote_buffer = QuoteBuffer(max_points_per_symbol=3600)
    from aegis.intel.short_horizon_runtime import ShortHorizonPredictor, seed_quote_buffer
    short_horizon_predictor = ShortHorizonPredictor.from_config(cfg)
    # Exact ticket->hypothesis metadata persistence
    from aegis.intel.ticket_metadata import TicketMetadataStore, create_ticket_metadata
    ticket_metadata_store = TicketMetadataStore(ROOT / "intel" / "ticket_metadata.json")
    from aegis.intel.firehose_turnover import (
        FirehoseReentryGuard, TurnoverMetrics, basket_lifecycle_trace,
        quote_fingerprint,
    )
    firehose_turnover = TurnoverMetrics()
    firehose_reentry_guard = FirehoseReentryGuard(
        ROOT / "reports" / "firehose_reentry_guard.json"
    )
    # Intelligent per-thesis profit management (spec B-H, O, P).
    from aegis.intel.profit_management import ProfitManager

    profit_manager = ProfitManager(
        cfg, persist_path=ROOT / "intel" / "pm_tickets.json"
    )
    from aegis.intel.fast_exit_runner import (
        FastExitContext, evaluate_fast_exit, firehose_exit_trace,
        MissingLiquidationMarkError, spread_r_from_geometry,
        REMAINING_EV_EXIT_POLICY_ID, estimate_remaining_ev,
    )
    from aegis.intel.profit_harvester import load_validated_harvest_policy
    from aegis.intel.trade_controller import TradeController
    from aegis.intel.opportunity_engine import rank_and_allocate

    trade_controller = TradeController()
    harvest_policy = load_validated_harvest_policy(cfg)
    last_inventory_journal: dict[str, float] = {"ts": 0.0}

    def write_heartbeat(extra: Optional[dict] = None) -> None:
        write_runner_heartbeat(
            heartbeat, pid=os.getpid(), symbols=symbols, qty=qty,
            metrics=firehose_turnover, extra=extra,
        )

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
        if short_horizon_predictor.pipeline is not None:
            seeded = 0
            for name in symbols:
                try:
                    seeded += seed_quote_buffer(
                        quote_buffer,
                        name,
                        eng.copy_ticks(name, lookback_seconds=90),
                    )
                except Exception as exc:
                    logger.debug("short-horizon seed skipped symbol=%s error=%s", name, type(exc).__name__)
            logger.info("[SHORT HORIZON] seeded quote history points=%s symbols=%s", seeded, len(symbols))
        logger.info(
            "Connected engine=%s account=%s equity=%.2f paper=%s qty=%s symbols=%s",
            eng.name,
            acct.account_id,
            acct.equity,
            acct.is_paper,
            qty,
            ",".join(symbols),
        )
        if video_style_mode:
            logger.info("[VIDEO-STYLE FIREHOSE] ACTIVE across %d eligible symbols", len(symbols))
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
        _risk_ok, _risk_reason = risk.allow(acct.equity, open_positions=open_n)
        risk.save_json(risk_path)
        if engine_name == "mt5" and acct.is_paper:
            logger.info("[MT5 DEMO] CONNECTED")
            logger.info("[DEMO ORDER PATH] %s", "ENABLED" if send_orders else "DISABLED")
        logger.info(
            "[TOTAL_DRAWDOWN_DEMO_HALT] %s",
            "DISABLED" if risk.demo_global_loss_halt_disabled else "ACTIVE",
        )
        logger.info("[PER_TRADE_RISK] %s", "ACTIVE" if risk.risk_percent > 0 else "DISABLED")
        logger.info(
            "[PREDICTION_ENGINE] %s",
            "ACTIVE" if short_horizon_predictor.pipeline is not None else "ABSTAIN",
        )
        logger.info("[FAST_EXIT] ACTIVE")
        logger.info("[TRADING_ELIGIBLE] %s", str(bool(_risk_ok)).upper())
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
                ticket = str(getattr(pos, "ticket", "") or "")
                if ticket_metadata_store.get(ticket) is None:
                    comment = str(getattr(pos, "comment", "") or "")
                    pending_tag = comment if ticket_metadata_store.pending_order(comment) else None
                    pending = ticket_metadata_store.pending_order(comment)
                    if pending is None:
                        for tag, candidate in ticket_metadata_store.pending_orders().items():
                            if tag and (tag == comment or tag in comment or comment in tag):
                                pending_tag, pending = tag, candidate
                                break
                    if pending is not None and pending_tag is not None:
                        restored_meta = ticket_metadata_from_pending(
                            ticket=ticket, pending=pending, position=pos
                        )
                        basket_metadata = pending.get("basket_metadata")
                        if restored_meta is not None and isinstance(basket_metadata, dict):
                            try:
                                restored_contract = eng.symbol_spec(pos.symbol)
                            except (AttributeError, OSError, TypeError, ValueError):
                                restored_contract = None
                            restored = record_confirmed_firehose_open(
                                root=ROOT,
                                metadata_store=ticket_metadata_store,
                                metrics=firehose_turnover,
                                journal=journal,
                                ticket_id=ticket,
                                position=pos,
                                basket_metadata=basket_metadata,
                                ticket_metadata=restored_meta,
                                opened_at=float(getattr(pos, "opened_ts", 0) or now_s),
                                slot_capacity=max_positions,
                                contract=restored_contract,
                                decision_reasons=list(pending.get("decision_reasons") or []),
                                expected_net_value=pending.get("entry_ev"),
                                decision_snapshot=pending.get("decision_snapshot"),
                            )
                            if restored.get("status") == "PERSISTED":
                                ticket_metadata_store.clear_pending_order(pending_tag)
                                logger.info(
                                    "Restored exact pending lifecycle ticket=%s horizon=%s",
                                    ticket, restored_meta.selected_horizon_s,
                                )
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

        def maybe_enter(
            sym: str,
            equity: float,
            open_count: int,
            *,
            collect_only: bool = False,
            selected_execution: bool = False,
            frozen_opportunity: FrozenOpportunity | None = None,
        ) -> None:
            nonlocal day_trades, day_stamp, last_halt_journal, close_block_until
            nonlocal margin_block_until
            nonlocal submitted_count, fill_count
            nonlocal global_opportunity_counts
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
            scan_id = firehose_scan_id(sym, bar_time)

            q = eng.quote(sym)
            fresh_quote_at = time.time()
            candidate_created_at = fresh_quote_at
            global_rank_started_at = 0.0
            global_rank_finished_at = 0.0
            if frozen_opportunity is not None:
                try:
                    candidate_created_at = float(
                        frozen_opportunity.get("candidate_created_at") or fresh_quote_at
                    )
                    global_rank_started_at = float(
                        frozen_opportunity.get("global_rank_started_at") or 0.0
                    )
                    global_rank_finished_at = float(
                        frozen_opportunity.get("global_rank_finished_at") or 0.0
                    )
                except (TypeError, ValueError, OverflowError):
                    candidate_created_at = fresh_quote_at
            if selected_execution:
                global_opportunity_counts["GLOBAL_REVALIDATED"] += 1
            # Quote already recorded in polling loop; use current quote for this evaluation
            t0 = time.perf_counter()
            now_ts = time.time()
            live_spread = max(0.0, float(q.ask) - float(q.bid))
            mid = (float(q.bid) + float(q.ask)) / 2.0 if q.bid and q.ask else 0.0
            live_bps = (live_spread / mid * 10000.0) if mid > 0 else 0.0
            pip = pip_size_for(sym, cfg)
            prev = last_bar_time.get(sym)
            if (
                not selected_execution
                and prev is not None
                and bar_time <= prev
                and not meaningful_quote_change(
                    last_quote_state.get(sym),
                    bid=float(q.bid), ask=float(q.ask), pip=pip,
                )
            ):
                return
            last_quote_state[sym] = {"bid": float(q.bid), "ask": float(q.ask)}
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
                            "candidate_id": scan_id,
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
                            "candidate_id": scan_id,
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
                observed_funnel_counts["SCANS"] += 1
                observed_funnel_counts["RISK_REJECT"] += 1
                append_journal(
                    journal,
                    firehose_funnel_risk_row(
                        scan_id=scan_id,
                        symbol=sym,
                        bar=bar_time,
                        reason=reason,
                    ),
                )
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

            intelligent_mode = bool(cfg.get("intelligent_firehose", False))
            max_spread = max_spread_for(sym, cfg)
            # Intelligent Firehose applies the measured per-symbol/session p90 in
            # its brain. Legacy modes retain the configured universal guard.
            if not intelligent_mode and max_spread > 0 and live_spread > max_spread + 1e-12:
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

            sig = None
            if frozen_opportunity is not None:
                from aegis.intel.firehose_brain import DemoDecision
                from aegis.strategy import Signal

                frozen_journal = dict(frozen_opportunity.get("decision_journal") or {})
                frozen_journal["frozen_global_selection"] = True
                frozen_journal["frozen_candidate_id"] = frozen_opportunity.get("candidate_id")
                frozen_side = str(frozen_opportunity.get("side") or "").lower()
                if frozen_side not in {"buy", "sell"}:
                    return
                brain_decision = DemoDecision(
                    "fire",
                    "frozen_global_selection",
                    side=frozen_side,
                    sl=frozen_opportunity.get("stop"),
                    tp=frozen_opportunity.get("target"),
                    quantity=frozen_opportunity.get("quantity"),
                    expected_net_value=frozen_opportunity.get("expected_net_ev"),
                    information_id=frozen_journal.get("information_id"),
                    analogue_n=int(frozen_opportunity.get("authority_evidence_n") or 0),
                    journal=frozen_journal,
                )
                sig = Signal(
                    frozen_side,
                    "intelligent_firehose",
                    float(frozen_opportunity.get("entry")),
                    float(frozen_opportunity.get("stop")),
                    frozen_opportunity.get("target"),
                    None,
                    bar_time,
                    "frozen_global_selection",
                )
                _terminal = "EXPLORATION_ELIGIBLE"
                _micro_count = 1
            elif intelligent_mode:
                nonlocal intelligent_brain
                from aegis.intel.firehose_brain import IntelligentFirehoseBrain
                from aegis.strategy import Signal

                if intelligent_brain is None:
                    intelligent_brain = IntelligentFirehoseBrain(cfg)
                    try:
                        intelligent_brain.outcome_memory.import_historical_confirmed_trades(
                            ROOT / "intel" / "outcome_log.jsonl"
                        )
                    except Exception as exc:
                        logger.warning("historical outcome import skipped: %s", exc)
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
                video_signal_hint = video_style_signal_for_scan(
                    completed,
                    symbol=sym,
                    enabled=video_style_mode,
                )
                side_comparison = short_horizon_predictor.predict_sides(
                    symbol=sym,
                    quote_buffer=quote_buffer,
                    now_ts=now_ts,
                    broker_spec=brain_spec,
                    quantity=float(qty),
                )
                predicted_side = side_comparison.get("selected_side")
                entry_side = (
                    video_signal_hint.side
                    if video_signal_hint is not None
                    else (brain_side or predicted_side)
                )
                brain_entry = (
                    float(q.ask if entry_side == "buy" else q.bid)
                    if entry_side else None
                )
                selected_prediction = dict(side_comparison)
                if predicted_side and entry_side and predicted_side != entry_side:
                    # The video/structural candidate is directional. If the
                    # independent side comparison prefers the opposite side,
                    # preserve the evidence but fail closed instead of pairing
                    # an opposite prediction with the wrong geometry.
                    selected_prediction.update({
                        "selected_side": predicted_side,
                        "calibration_status": "unavailable",
                        "decision": False,
                        "abstain": True,
                        "abstain_reason": "side_selection_mismatch",
                        "prediction_reason": "side_selection_mismatch",
                    })
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
                    video_style=video_style_mode,
                    short_horizon_prediction=selected_prediction,
                    previous_row=(frame.iloc[-3] if len(frame) >= 3 else None),
                )
                brain_decision = decision
                _book_logic = decision.journal.get("book_logic") or {}
                _micro_count = int(
                    decision.journal.get(
                        "search_candidate_count",
                        decision.journal.get("micro_candidate_count", 0),
                    )
                    or 0
                )
                _is_exploration = bool(decision.journal.get("exploration"))
                _terminal = (
                    "EXPLORATION_ELIGIBLE" if decision.action in {"fire", "scale"} and _is_exploration
                    else "VALIDATED_MATCH" if decision.action in {"fire", "scale"}
                    else funnel_terminal_for_reason(decision.reason)
                )
                append_journal(
                    journal,
                    {
                        "event": "firehose_funnel.v1",
                        "scan_id": scan_id,
                        "symbol": sym,
                        "bar": str(bar_time),
                        "terminal": _terminal,
                        "micro_candidate_count": _micro_count,
                        "book_supported": bool(_book_logic.get("source_book")),
                        "validated_match": decision.action in {"fire", "scale"} and not _is_exploration,
                        "exploration_eligible": decision.action in {"fire", "scale"} and _is_exploration,
                        "brain_intent": decision.action in {"fire", "scale"},
                        "submitted": False,
                        "filled": False,
                    },
                )
                if decision.action in {"exit", "reduce"}:
                    controller_exit = trade_controller.decide(
                        {
                            "action": "EXIT" if decision.action == "exit" else "SCRATCH",
                            "reason": decision.reason,
                            "why": f"brain management decision: {decision.reason}",
                            "policy": "brain_management",
                        },
                        {
                            "action": "HOLD",
                            "reason": "per_ticket_management_deferred",
                            "why": "per-ticket controller will re-evaluate live executable evidence",
                        },
                        evidence_snapshot=dict(decision.journal),
                    )
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
                    close_n = int(
                        decision.close_clips
                        or (len(open_pos) if controller_exit["action"] == "ABORT" else 1)
                    )
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
                                    "action": controller_exit["action"],
                                    "reason": controller_exit["reason"],
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
                                # Broker confirmation and realized economics
                                # arrive through the deal reconciliation loop;
                                # the floating mark here is diagnostic only.
                                append_journal(
                                    journal,
                                    {
                                        "event": "close_requested",
                                        "ticket": ticket,
                                        "symbol": sym,
                                        "floating_pnl_at_request": float(pos.unrealized_pnl),
                                        "broker_confirmed": False,
                                        "reason": controller_exit["reason"],
                                    },
                                )
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
                _thesis_key = str(decision.journal.get("thesis_key") or "")
                _quote_fingerprint = quote_fingerprint(
                    sym, str(decision.side or ""), q.bid, q.ask,
                )
                _reentry_ok, _reentry_reason = firehose_reentry_guard.allows(
                    _thesis_key, _quote_fingerprint, now_ts,
                )
                if not _reentry_ok:
                    append_journal(
                        journal,
                        {
                            "event": "open_skip",
                            "symbol": sym,
                            "reason": _reentry_reason,
                            "thesis_key": _thesis_key,
                            "bar": str(bar_time),
                        },
                    )
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
                video_style=video_style_mode,
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
                if eng.positions(sym) and interval > 0 and age is not None and float(age) < interval:
                    return
                if len(eng.positions()) >= max_positions:
                    return

            sl = float(sig.sl) if sig.sl is not None else None
            tp = float(sig.tp) if sig.tp is not None else None
            frozen_geometry = frozen_opportunity is not None
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
            if sl is not None or tp is not None or intelligent_mode:
                try:
                    spec_map = eng.symbol_spec(sym)
                except Exception:
                    spec_map = None
                if not intelligent_mode:
                    sl, tp = normalize_protective_stops(
                        side=sig.side,
                        entry=entry,
                        sl=sl,
                        tp=tp,
                        spec=spec_map,
                        fallback_step=pip,
                    )
            broker_sl = None
            broker_tp = None
            # The intelligent emergency stop is deliberately deferred until
            # after the one allowed fresh-tick refresh and any risk
            # down-sizing. Computing it from the discovery quote could reject
            # a candidate before its same-identity geometry is repriced.
            req = OrderRequest(
                symbol=sym,
                side=sig.side,
                quantity=order_qty,
                kind="market",
                stop_loss=sl,
                take_profit=tp,
                broker_stop_loss=broker_sl,
                broker_take_profit=broker_tp,
                client_tag=(
                    # Exploration orders carry a compact hypothesis tag so
                    # broker-side SL/TP closes can be attributed back to the
                    # experiment (MT5 comments are short).
                    f"EXP{str(brain_decision.journal.get('hypothesis_id') or '')[-12:]}"
                    if brain_decision is not None and brain_decision.journal.get("exploration")
                    else f"aegis_{sig.reason}"[:40]
                ),
            )
            oms_ok, oms_why = (
                (True, "")
                if intelligent_mode
                else oms_allows(
                    req,
                    q,
                    cfg,
                    open_count=len(eng.positions()),
                    check_quote_age=False,
                )
            )
            if not oms_ok:
                t2t.note_reject(oms_why)
                oms_reject_reasons[oms_why] = oms_reject_reasons.get(oms_why, 0) + 1
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
                broker_stop_loss=req.broker_stop_loss,
                broker_take_profit=req.broker_take_profit,
                client_tag=client_tag,
            )
            if brain_decision is not None:
                append_journal(
                    journal,
                    {
                        "event": "intel_brain_fire",
                        "scan_id": scan_id,
                        "submitted": False,
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
            # --- Pre-send refresh (P8): the decision was priced on quote q,
            # fetched before the brain ran. If that quote is now stale, fetch
            # ONE fresh tick and re-validate; never send on stale pricing and
            # never disable stale protection to force trades through.
            from aegis.intel.send_guard import (
                margin_precheck_ok,
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
                    if selected_execution:
                        global_opportunity_counts["GLOBAL_INVALIDATED_ON_REFRESH"] += 1
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
                    candidate_spread_limit=(
                        intelligent_refresh_spread_limit(brain_decision, cfg)
                        if intelligent_mode and brain_decision is not None
                        else None
                    ),
                )
                if not verdict.ok:
                    quote_refresh_counts["candidate_invalidated_after_refresh"] += 1
                    if selected_execution:
                        global_opportunity_counts["GLOBAL_INVALIDATED_ON_REFRESH"] += 1
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
                fresh_quote_at = time.time()
            entry = float(q.ask if sig.side == "buy" else q.bid)
            if intelligent_mode:
                if frozen_geometry:
                    repriced = reprice_frozen_virtual_geometry(
                        side=sig.side,
                        discovery_entry=float(frozen_opportunity.get("entry")),
                        discovery_stop=frozen_opportunity.get("stop"),
                        discovery_target=frozen_opportunity.get("target"),
                        fresh_entry=entry,
                    )
                    if repriced is None:
                        quote_refresh_counts["virtual_geometry_reject"] += 1
                        if selected_execution:
                            global_opportunity_counts["GLOBAL_INVALIDATED_ON_REFRESH"] += 1
                        append_journal(
                            journal,
                            {
                                "event": "virtual_geometry_reject",
                                "symbol": sym,
                                "candidate_id": frozen_opportunity.get("candidate_id"),
                                "reason": "same_identity_geometry_invalid_after_reprice",
                                "entry": entry,
                                "stop": frozen_opportunity.get("stop"),
                                "target": frozen_opportunity.get("target"),
                                "bar": str(bar_time),
                            },
                        )
                        return
                    sl, tp = repriced
                virtual_ok, virtual_reason = validate_virtual_strategy_geometry(
                    side=sig.side, entry=entry, stop=sl, target=tp
                )
                if not virtual_ok:
                    quote_refresh_counts["virtual_geometry_reject"] += 1
                    append_journal(
                        journal,
                        {
                            "event": "virtual_geometry_reject",
                            "symbol": sym,
                            "candidate_id": (
                                frozen_opportunity.get("candidate_id")
                                if frozen_opportunity is not None else None
                            ),
                            "reason": virtual_reason,
                            "entry": entry,
                            "stop": sl,
                            "target": tp,
                            "bar": str(bar_time),
                        },
                    )
                    return
                broker_sl = emergency_broker_stop(
                    symbol=sym,
                    side=sig.side,
                    entry=entry,
                    virtual_stop=sl,
                    quantity=order_qty,
                    spec=spec_map,
                    max_risk_usd=float(
                        cfg.get("exploration_max_risk_per_trade_usd", 0.15) or 0.15
                    ),
                    clamp_to_risk=bool(
                        brain_decision is not None
                        and str(
                            brain_decision.journal.get("authority_type") or ""
                        ).upper() == "FORCED_DEMO_EXPLORATION"
                    ),
                    market_bid=float(q.bid),
                    market_ask=float(q.ask),
                )
                if broker_sl is None:
                    quote_refresh_counts["broker_geometry_reject"] += 1
                    append_journal(
                        journal,
                        {
                            "event": "broker_geometry_reject",
                            "symbol": sym,
                            "candidate_id": (
                                frozen_opportunity.get("candidate_id")
                                if frozen_opportunity is not None else None
                            ),
                            "reason": "emergency_stop_exceeds_risk_or_broker_geometry",
                            "entry": entry,
                            "virtual_stop": sl,
                            "bar": str(bar_time),
                        },
                    )
                    return
                # The request was originally built on the discovery quote.
                # Replace only quote-relative price/quantity fields; identity
                # remains frozen and virtual levels stay controller-owned.
                req = replace(
                    req,
                    quantity=float(order_qty),
                    stop_loss=sl,
                    take_profit=tp,
                    broker_stop_loss=broker_sl,
                    broker_take_profit=broker_tp,
                )
            # --- Margin / min-lot pre-checks: 89% of historical order failures
            # were 10019 No money. Check before hitting the broker.
            try:
                spec_pre = eng.symbol_spec(sym)
            except Exception:
                spec_pre = None
            vmin = float((spec_pre or {}).get("volume_min", 0.01) or 0.01)
            vstep = float((spec_pre or {}).get("volume_step", 0.01) or 0.01)
            if (
                brain_decision is not None
                and _terminal == "EXPLORATION_ELIGIBLE"
                and sl is not None
            ):
                risk_check = exploration_order_risk_check(
                    order_qty=float(order_qty),
                    entry=float(q.ask if sig.side == "buy" else q.bid),
                    stop=float(sl),
                    pip=float(pip),
                    max_risk_usd=float(cfg.get("exploration_max_risk_per_trade_usd", 0.15) or 0.15),
                    spec=spec_pre,
                )
                if not bool(risk_check["allowed"]):
                    resized = resize_order_quantity_to_risk(
                        requested_quantity=float(order_qty),
                        max_lots=float(risk_check.get("max_lots") or 0.0),
                        volume_min=vmin,
                        volume_step=vstep,
                    )
                    if resized is None or resized >= float(order_qty) - 1e-12:
                        quote_refresh_counts["risk_budget_precheck_skip"] += 1
                        append_journal(
                            journal,
                            {
                                "event": "sizing_skip",
                                "reason": str(risk_check["reason"]),
                                "symbol": sym,
                                "qty": float(order_qty),
                                "max_lots": risk_check.get("max_lots"),
                                "risk_budget_usd": float(
                                    cfg.get("exploration_max_risk_per_trade_usd", 0.15) or 0.15
                                ),
                                "bar": str(bar_time),
                            },
                        )
                        return
                    original_qty = float(order_qty)
                    order_qty = float(resized)
                    quote_refresh_counts["risk_resized"] += 1
                    append_journal(
                        journal,
                        {
                            "event": "sizing_resize",
                            "symbol": sym,
                            "requested_qty": original_qty,
                            "resized_qty": order_qty,
                            "max_lots": risk_check.get("max_lots"),
                            "risk_budget_usd": float(
                                cfg.get("exploration_max_risk_per_trade_usd", 0.15) or 0.15
                            ),
                            "bar": str(bar_time),
                        },
                    )
                    broker_sl = emergency_broker_stop(
                        symbol=sym,
                        side=sig.side,
                        entry=entry,
                        virtual_stop=sl,
                        quantity=order_qty,
                        spec=spec_map,
                        max_risk_usd=float(
                            cfg.get("exploration_max_risk_per_trade_usd", 0.15) or 0.15
                        ),
                        clamp_to_risk=True,
                        market_bid=float(q.bid),
                        market_ask=float(q.ask),
                    )
                    if broker_sl is None:
                        quote_refresh_counts["broker_geometry_reject"] += 1
                        append_journal(
                            journal,
                            {
                                "event": "broker_geometry_reject",
                                "symbol": sym,
                                "reason": "resized_quantity_still_missing_valid_emergency_stop",
                                "qty": order_qty,
                                "bar": str(bar_time),
                            },
                        )
                        return
                    req = replace(
                        req,
                        quantity=order_qty,
                        stop_loss=sl,
                        take_profit=tp,
                        broker_stop_loss=broker_sl,
                        broker_take_profit=broker_tp,
                    )
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
                ref_price = float(
                    (q.ask if sig.side == "buy" else q.bid)
                    or getattr(q, "ask", 0.0)
                    or getattr(q, "bid", 0.0)
                    or 0.0
                )
                est_margin, margin_source = order_margin_for_send(
                    eng,
                    symbol=sym,
                    side="buy" if sig.side == "buy" else "sell",
                    quantity=float(order_qty),
                    price=ref_price,
                    contract_size=contract,
                    leverage=leverage,
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
                            "source": margin_source,
                            "bar": str(bar_time),
                        },
                    )
                    return
            if intelligent_mode:
                oms_ok, oms_why = oms_allows(
                    req,
                    q,
                    cfg,
                    open_count=len(eng.positions()),
                    check_quote_age=False,
                )
                if not oms_ok:
                    quote_refresh_counts["broker_geometry_reject"] += 1
                    t2t.note_reject(oms_why)
                    oms_reject_reasons[oms_why] = oms_reject_reasons.get(oms_why, 0) + 1
                    append_journal(
                        journal,
                        {
                            "event": "oms_reject",
                            "execution_stage": "fresh_revalidation",
                            "reason": oms_why,
                            "symbol": sym,
                            "side": sig.side,
                            "qty": order_qty,
                            "sl": req.broker_stop_loss,
                            "tp": req.broker_take_profit,
                            "bar": str(bar_time),
                        },
                    )
                    return
            # Reserve only after every pre-send guard passes. A rejected
            # candidate must not consume an exploration slot for 180 seconds.
            if collect_only:
                deferred_before = len(deferred_opportunities)
                if brain_decision is None or brain_decision.action not in {"fire", "scale"}:
                    return
                decision_journal = dict(brain_decision.journal)
                prediction_journal = decision_journal.get("short_horizon_prediction") or {}
                economics_journal = (
                    decision_journal.get("exploration_economics")
                    or decision_journal
                )
                viable_candidates = decision_journal.get("viable_candidates")
                if isinstance(viable_candidates, list) and viable_candidates:
                    for candidate_row in viable_candidates:
                        if not isinstance(candidate_row, dict):
                            continue
                        candidate_journal = candidate_row.get("decision_journal")
                        if not isinstance(candidate_journal, dict):
                            continue
                        candidate_decision = replace(
                            brain_decision,
                            side=str(candidate_row.get("side") or "").lower(),
                            sl=candidate_row.get("stop"),
                            tp=candidate_row.get("target"),
                            quantity=candidate_row.get("quantity"),
                            expected_net_value=candidate_row.get("expected_net_ev"),
                            journal=dict(candidate_journal),
                        )
                        deferred_opportunities.append(frozen_opportunity_from_decision(
                            decision=candidate_decision,
                            symbol=str(candidate_row.get("symbol") or sym),
                            scan_id=scan_id,
                            bar_time=bar_time,
                            bid=float(q.bid),
                            ask=float(q.ask),
                            stop=candidate_row.get("stop"),
                            target=candidate_row.get("target"),
                            quantity=float(candidate_row.get("quantity") or order_qty),
                        ))
                else:
                    deferred_opportunities.append(frozen_opportunity_from_decision(
                        decision=brain_decision,
                        symbol=sym,
                        scan_id=scan_id,
                        bar_time=bar_time,
                        bid=float(q.bid),
                        ask=float(q.ask),
                        stop=req.stop_loss,
                        target=req.take_profit,
                        quantity=float(order_qty),
                    ))
                global_opportunity_counts["GLOBAL_CANDIDATES"] += (
                    len(deferred_opportunities) - deferred_before
                )
                append_journal(
                    journal,
                    {
                        "event": "global_opportunity_discovered",
                        "scan_id": scan_id,
                        "symbol": sym,
                        "side": sig.side,
                        "expected_net_ev": brain_decision.expected_net_value,
                        "p_captured_win": deferred_opportunities[-1].get(
                            "p_captured_win"
                        ),
                    },
                )
                return
            if brain_decision is not None and brain_decision.journal.get("exploration"):
                _thesis_key = str(brain_decision.journal.get("thesis_key") or "")
                if _thesis_key:
                    intelligent_brain.memory.exploration_pending.setdefault(
                        _thesis_key, []).append(time.time())
                    _mem = intelligent_brain.memory.theses.get(_thesis_key)
                    if _mem is not None:
                        _mem.symbol = sym.upper()
                        _mem.side = brain_decision.side
                        _mem.setup_family = str(brain_decision.journal.get("setup_family") or "")
            pending_snapshot = firehose_decision_snapshot(
                decision=brain_decision,
                symbol=sym,
                scan_id=scan_id,
                bar_time=bar_time,
                side=sig.side,
                qty=order_qty,
                entry=float(q.ask if sig.side == "buy" else q.bid),
                stop=req.stop_loss,
                target=req.take_profit,
                spread=live_spread,
                quote_age=quote_age_s(q),
            )
            if brain_decision is not None and send_orders:
                pending_metadata = pending_order_lifecycle_metadata(
                    decision=brain_decision,
                    snapshot=pending_snapshot,
                    symbol=sym,
                    side=sig.side,
                    entry=float(q.ask if sig.side == "buy" else q.bid),
                    stop=req.stop_loss,
                    target=req.take_profit,
                    client_tag=client_tag,
                    config=cfg,
                )
                if not ticket_metadata_store.begin_pending_order(
                    client_tag, pending_metadata
                ):
                    append_journal(
                        journal,
                        {
                            "event": "order_blocked",
                            "symbol": sym,
                            "side": sig.side,
                            "reason": "pending_lifecycle_persistence_failed",
                            "client_tag": client_tag,
                            "bar": str(bar_time),
                        },
                    )
                    return
            if brain_decision is not None:
                append_journal(
                    journal,
                    {
                        "event": "firehose_funnel.v1",
                        "scan_id": scan_id,
                        "symbol": sym,
                        "bar": str(bar_time),
                        "terminal": _terminal,
                        "micro_candidate_count": _micro_count,
                        "book_supported": bool(_book_logic.get("source_book")),
                        "validated_match": bool(_terminal == "VALIDATED_MATCH"),
                        "exploration_eligible": bool(_terminal == "EXPLORATION_ELIGIBLE"),
                        "brain_intent": True,
                        "submitted": True,
                        "filled": False,
                    },
                )
            order_send_at = time.time()
            latency.request_ts = order_send_at
            if frozen_opportunity is not None and candidate_created_at > 0:
                hot_path_discovery_to_send_ms.append(
                    max(0.0, (order_send_at - candidate_created_at) * 1000.0)
                )
                if len(hot_path_discovery_to_send_ms) > 256:
                    del hot_path_discovery_to_send_ms[:-256]
                append_journal(
                    journal,
                    {
                        "event": "firehose_hot_path_timing",
                        "candidate_id": frozen_opportunity.get("candidate_id"),
                        "candidate_created_at": candidate_created_at,
                        "global_rank_started_at": global_rank_started_at,
                        "global_rank_finished_at": global_rank_finished_at,
                        "fresh_quote_at": fresh_quote_at,
                        "order_send_at": order_send_at,
                        "discovery_to_rank_ms": (
                            max(0.0, (global_rank_finished_at - candidate_created_at) * 1000.0)
                            if global_rank_finished_at > 0 else None
                        ),
                        "rank_to_refresh_ms": (
                            max(0.0, (fresh_quote_at - global_rank_finished_at) * 1000.0)
                            if global_rank_finished_at > 0 else None
                        ),
                        "refresh_to_send_ms": max(
                            0.0, (order_send_at - fresh_quote_at) * 1000.0
                        ),
                        "candidate_age_at_send_ms": max(
                            0.0, (order_send_at - candidate_created_at) * 1000.0
                        ),
                    },
                )
            submitted_count += 1
            record_funnel_execution(
                observed_funnel_counts, submitted=True, filled=False
            )
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
            if brain_decision is not None:
                append_journal(
                    journal,
                    {
                        "event": "firehose_funnel.v1",
                        "scan_id": scan_id,
                        "symbol": sym,
                        "bar": str(bar_time),
                        "terminal": _terminal,
                        "micro_candidate_count": _micro_count,
                        "book_supported": bool(_book_logic.get("source_book")),
                        "validated_match": bool(_terminal == "VALIDATED_MATCH"),
                        "exploration_eligible": bool(_terminal == "EXPLORATION_ELIGIBLE"),
                        "brain_intent": True,
                        "submitted": True,
                        "filled": status in {"POSITION_CONFIRMED", "DEAL_EXECUTED"},
                    },
                )
            execution_status_counts[status] = int(execution_status_counts.get(status, 0)) + 1
            if status in {"POSITION_CONFIRMED", "DEAL_EXECUTED"}:
                record_funnel_execution(
                    observed_funnel_counts, submitted=False, filled=True
                )
                fill_count += 1
                latency.confirmed_ts = time.time()
            # Only uncertain outcomes arm the dedup guard. Definitive rejections
            # (e.g. 10016 invalid stops from a stale quote) are safe to retry.
            if status == "TIMEOUT":
                fire_retry_guard.mark_sent(sym, client_tag, time.time())
            elif status not in {"POSITION_CONFIRMED", "DEAL_EXECUTED", "ORDER_ACCEPTED"}:
                ticket_metadata_store.clear_pending_order(client_tag)
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
            decision_snapshot = firehose_decision_snapshot(
                decision=brain_decision,
                symbol=sym,
                scan_id=scan_id,
                bar_time=bar_time,
                side=sig.side,
                qty=order_qty,
                entry=entry,
                stop=req.stop_loss,
                target=req.take_profit,
                spread=live_spread,
                quote_age=quote_age_s(q),
            )
            append_journal(
                journal,
                {
                    "event": "order",
                    "scan_id": scan_id,
                    "submitted": True,
                    "filled": status in {"POSITION_CONFIRMED", "DEAL_EXECUTED"},
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
                    "decision_snapshot": decision_snapshot,
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
                        regime = str(brain_decision.journal.get("regime") or "")
                        session = str(brain_decision.journal.get("session") or "")
                        information_id = brain_decision.information_id
                        prediction_snapshot = decision_snapshot.get("prediction")
                        prediction_snapshot = (
                            dict(prediction_snapshot)
                            if isinstance(prediction_snapshot, dict) else {}
                        )
                        model_artifact = decision_snapshot.get("model")
                        model_artifact = (
                            dict(model_artifact)
                            if isinstance(model_artifact, dict) else {}
                        )
                        selected_horizon = (
                            brain_decision.journal.get("search_horizon_s")
                            or prediction_snapshot.get("decision_horizon_s")
                            or brain_decision.journal.get("max_hold_s")
                        )
                        try:
                            selected_horizon = int(selected_horizon)
                        except (TypeError, ValueError):
                            selected_horizon = int(brain_decision.journal.get("max_hold_s") or 120)
                        max_hold_s = selected_horizon
                        for tk in new_tickets:
                            position = next(
                                (item for item in eng.positions(sym) if str(getattr(item, "ticket", "")) == tk),
                                None,
                            )
                            geometry = confirmed_position_geometry(position) if position is not None else {
                                "status": "NO_EVIDENCE", "reason": "missing_confirmed_geometry",
                            }
                            if geometry.get("status") == "NO_EVIDENCE":
                                continue
                            meta = create_ticket_metadata(
                                ticket=tk,
                                hypothesis_id=hypothesis_id,
                                thesis_key=thesis_key_now,
                                strategy_family=strategy_family,
                                expected_mechanism=expected_mechanism,
                                side=side,
                                entry_price=float(geometry["entry_price"]),
                                stop_loss=float(geometry["stop_loss"]),
                                target_price=target_price,
                                max_hold_s=max_hold_s,
                                regime=regime,
                                session=session,
                                information_id=information_id,
                                symbol=sym,
                                entry_ev=brain_decision.expected_net_value,
                                authority_type=brain_decision.journal.get("authority_type"),
                                authority_probability=brain_decision.journal.get(
                                    "authority_probability"
                                ),
                                authority_capture_lcb95=brain_decision.journal.get(
                                    "authority_capture_lcb95"
                                ),
                                authority_expected_net_ev=brain_decision.journal.get(
                                    "authority_expected_net_ev"
                                ),
                                authority_horizon_s=selected_horizon,
                                authority_evidence_source=brain_decision.journal.get(
                                    "evidence_provenance"
                                ),
                                authority_observations=brain_decision.journal.get(
                                    "authority_observations"
                                ),
                                shadow_model_probability=brain_decision.journal.get(
                                    "shadow_model_probability"
                                ),
                                decision_snapshot=decision_snapshot,
                                selected_horizon_s=selected_horizon,
                                model_artifact=model_artifact,
                                prediction_snapshot=prediction_snapshot,
                                feature_snapshot=prediction_snapshot.get("feature_snapshot"),
                                p_captured_win=(
                                    brain_decision.journal.get("authority_probability")
                                    if brain_decision.journal.get("exploration")
                                    else prediction_snapshot.get("probability")
                                ),
                                expected_net_pnl=(
                                    brain_decision.expected_net_value
                                    if brain_decision.journal.get("exploration")
                                    else prediction_snapshot.get("expected_net_pnl")
                                ),
                                expected_net_pnl_lcb95=prediction_snapshot.get("expected_net_pnl_lcb95"),
                                expected_mfe=prediction_snapshot.get("expected_mfe"),
                                expected_mae=prediction_snapshot.get("expected_mae"),
                                expected_time_to_green_s=prediction_snapshot.get("expected_time_to_green_s"),
                                tail_loss_probability=prediction_snapshot.get("tail_loss_probability"),
                                spread_assumption=(
                                    decision_snapshot.get("risk", {}).get("spread")
                                    if isinstance(decision_snapshot.get("risk"), dict) else None
                                ),
                                slippage_assumption=cfg.get("slippage_bps"),
                                commission_assumption=cfg.get("commission_round_trip_usd"),
                                decision_reasons=[str(brain_decision.reason)],
                                sell_rejection_reason=prediction_snapshot.get("sell_rejection_reason"),
                                abstain_reason=prediction_snapshot.get("abstain_reason"),
                            )
                            try:
                                contract = eng.symbol_spec(sym)
                            except (AttributeError, OSError, TypeError, ValueError):
                                contract = None
                            open_record = record_confirmed_firehose_open(
                                root=ROOT,
                                metadata_store=ticket_metadata_store,
                                metrics=firehose_turnover,
                                journal=journal,
                                ticket_id=tk,
                                position=position,
                                basket_metadata={
                                    "basket_id": f"firehose-{tk}",
                                    "hypothesis_id": hypothesis_id,
                                    "family": strategy_family,
                                    "symbol": sym,
                                    "side": side,
                                    "trigger_id": str(information_id),
                                    "risk_budget": float(cfg.get("exploration_max_risk_per_trade_usd", 0.15)),
                                    "clip_cap": 1,
                                    "regime": regime,
                                    "session": session,
                                    "cost_evidence": {"spread_price": max(0.0, float(q.ask) - float(q.bid))},
                                },
                                ticket_metadata=meta,
                                opened_at=now_s,
                                slot_capacity=max_positions,
                                contract=contract,
                                decision_reasons=[sig.reason],
                                expected_net_value=brain_decision.expected_net_value,
                                decision_snapshot=decision_snapshot,
                            )
                            if open_record.get("status") == "PERSISTED":
                                ticket_metadata_store.clear_pending_order(client_tag)
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
            risk.demo_global_loss_halt_disabled = demo_global_loss_halt_disabled(cfg)
            risk.max_total_drawdown_percent = (
                0.0
                if risk.demo_global_loss_halt_disabled
                else float(cfg.get("max_total_drawdown_percent", 0) or 0)
            )
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
                if firehose_stop_requested(stop_file):
                    logger.warning("[FIREHOSE] STOP FIREHOSE requested; exiting")
                    append_journal(
                        journal,
                        {"event": "operator_stop", "reason": "STOP FIREHOSE"},
                    )
                    break
                if intelligent_brain is not None:
                    intelligent_brain.refresh()
                poll = float(cfg.get("poll_seconds", 60))
                acct = eng.account()
                equity = acct.equity
                all_pos = eng.positions()
                reconcile_confirmed_firehose_basket_cleanups(
                    root=ROOT,
                    metadata_store=ticket_metadata_store,
                    guard=firehose_reentry_guard,
                    positions=all_pos,
                    contract_for_symbol=lambda symbol: eng.symbol_spec(symbol),
                    closed_at=time.time(),
                )
                # Continuously sample quotes for ALL watched symbols (not just on new M1 bar)
                now_ts = time.time()
                deferred_opportunities.clear()
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
                    "video_style_mode": bool(video_style_mode),
                    "firehose_every_bar": bool(cfg.get("firehose_every_bar")),
                    "position_sizing_mode": str(cfg.get("position_sizing_mode") or ""),
                    "risk_halted": bool(risk.state.halted),
                    "risk_reason": str(risk.state.reason or ""),
                    "total_drawdown_demo_halt_disabled": bool(
                        risk.demo_global_loss_halt_disabled
                    ),
                    "per_trade_risk_active": bool(risk.risk_percent > 0),
                    "circuit_blocked_until": float(circuit.blocked_until or 0),
                }
                _risk_ok, _risk_why = risk.allow(equity, open_positions=len(all_pos))
                extra_hb["risk_halted"] = bool(risk.state.halted) or (not _risk_ok)
                extra_hb["risk_reason"] = str(risk.state.reason or _risk_why or "")
                extra_hb["trading_eligible"] = bool(_risk_ok)
                _c_ok, _c_why = circuit.allow(now=time.time())
                extra_hb["circuit_ok"] = bool(_c_ok)
                if not _c_ok:
                    extra_hb["circuit_reason"] = _c_why
                extra_hb.update(t2t.snapshot())
                if execution_status_counts:
                    extra_hb["execution_status"] = dict(execution_status_counts)
                extra_hb["quote_refresh"] = dict(quote_refresh_counts)
                extra_hb["oms_rejects_by_reason"] = dict(oms_reject_reasons)
                _hot_path = sorted(hot_path_discovery_to_send_ms)
                extra_hb["hot_path"] = {
                    "candidate_discovery_to_send_p50_ms": (
                        round(_hot_path[len(_hot_path) // 2], 3) if _hot_path else None
                    ),
                    "candidate_discovery_to_send_p95_ms": (
                        round(_hot_path[int(0.95 * (len(_hot_path) - 1))], 3)
                        if _hot_path else None
                    ),
                    "n": len(_hot_path),
                }
                extra_hb["fast_exit_errors"] = fast_exit_error_count
                extra_hb["short_horizon_model"] = short_horizon_predictor.snapshot()
                extra_hb["trade_management"] = {
                    "authority": "TradeController",
                    "profit_harvester": (
                        "VALIDATED" if harvest_policy is not None else "UNAVAILABLE"
                    ),
                    "legacy_normal_exits": legacy_normal_exit_enabled(
                        bool(cfg.get("intelligent_firehose", False))
                    ),
                }
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
                extra_hb["funnel"] = merge_firehose_funnel_counts(
                    extra_hb.get("funnel"), observed_funnel_counts
                )
                if hasattr(eng, "history_deals"):
                    try:
                        deal_rows = eng.history_deals(1)
                        reconciled_events = ingest_deals(deal_rows, deal_cursor)
                        learned_positions: set[str] = set()
                        memory_recorded_positions: set[str] = set()
                        for event in reconciled_events:
                            position_id = str(
                                event.get("position")
                                or event.get("position_id")
                                or event.get("ticket")
                                or ""
                            )
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
                                            position_id,
                                            str(rec["hypothesis_id"]),
                                        )
                            if event.get("is_exit"):
                                from aegis.intel.outcome_log import append_outcome
                                close_facts = broker_close_evidence(
                                    deal_rows, ticket=position_id
                                )
                                if close_facts.get("status") == "BROKER_CONFIRMED":
                                    net_pnl = float(close_facts["realized_net_usd"])
                                    firehose_turnover.record_realized(
                                        position_id,
                                        net_pnl_usd=net_pnl,
                                        cost_usd=float(close_facts["cost_usd"]),
                                        closed_at=(
                                            float(event["time_msc"]) / 1000.0
                                            if event.get("time_msc") else None
                                        ),
                                        exit_reason=str(event.get("close_reason") or "broker_reconciled"),
                                    )
                                    append_outcome({
                                        **event,
                                        **close_facts,
                                        "event_type": "position_exit",
                                        "source": "reconcile",
                                        "pnl": net_pnl,
                                        "evidence_status": "BROKER_CONFIRMED",
                                    })
                                    outcome_memory = getattr(
                                        intelligent_brain, "outcome_memory", None
                                    ) if intelligent_brain is not None else None
                                    if (
                                        outcome_memory is not None
                                        and position_id not in memory_recorded_positions
                                    ):
                                        try:
                                            lifecycle_detail = (
                                                firehose_turnover.close_detail(position_id)
                                                or {}
                                            )
                                            lifecycle_meta = ticket_metadata_store.get(position_id)
                                            _memory_result = record_broker_confirmed_outcome_learning(
                                                outcome_memory=outcome_memory,
                                                outcome_id=position_id,
                                                close_facts=close_facts,
                                                metadata=lifecycle_meta,
                                                lifecycle_detail=lifecycle_detail,
                                                quote_buffer=quote_buffer,
                                                event=event,
                                                usd_per_price_unit=broker_replay_usd_per_price_unit(
                                                    eng,
                                                    symbol=str(event.get("symbol") or ""),
                                                    close_facts=close_facts,
                                                ),
                                            )
                                            append_journal(
                                                journal,
                                                {
                                                    "event": "outcome_learning",
                                                    "ticket": position_id,
                                                    "status": _memory_result.get("status", "RECORDED"),
                                                    "evidence_status": _memory_result.get("evidence_status"),
                                                    "classification": _memory_result.get("classification"),
                                                    "speed_label": _memory_result.get("speed_label"),
                                                },
                                            )
                                            memory_recorded_positions.add(position_id)
                                        except Exception as exc:
                                            logger.error(
                                                "outcome memory update failed position=%s: %s",
                                                position_id, exc, exc_info=True,
                                            )
                                    if exp_store is not None and position_id not in learned_positions:
                                        hyp_id = exp_store.hypothesis_for_position(position_id)
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
                                                    pnl=net_pnl,
                                                    session="",
                                                    regime="",
                                                )
                                                learned_positions.add(position_id)
                                            except Exception:
                                                pass
                                else:
                                    append_outcome({
                                        **event,
                                        **close_facts,
                                        "event_type": "position_exit",
                                        "source": "reconcile",
                                        "evidence_status": "INCOMPLETE_BROKER_EVIDENCE",
                                    })
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
                _turnover = firehose_turnover.snapshot(time.time())
                _brain_counts = extra_hb.get("counts") or {}
                _funnel = extra_hb.get("funnel") or {}
                extra_hb["firehose_telemetry"] = {
                    "FIREHOSE_ACTIVE": bool(_funnel.get("FIREHOSE_ACTIVE", True)),
                    "SCANS": int(_funnel.get("SCANS", _brain_counts.get("scans", 0)) or 0),
                    "RAW_SIGNALS": int(_brain_counts.get("raw_signals", 0) or 0),
                    "ML_ELIGIBLE": int(_brain_counts.get("ml_eligible", 0) or 0),
                    "HIGH_CONFIDENCE": int(_brain_counts.get("high_confidence", 0) or 0),
                    "COST_REJECT": int(
                        (_funnel.get("SPREAD_REJECT", 0) or 0)
                        + (_funnel.get("ECONOMICS_REJECT", 0) or 0)
                    ),
                    "MICRO_CANDIDATES": int(
                        _funnel.get("MICRO_CANDIDATES", 0) or 0
                    ),
                    "VALIDATED_CANDIDATES": int(
                        _funnel.get("VALIDATED_CANDIDATES", _funnel.get("VALIDATED_MATCH", 0)) or 0
                    ),
                    "EXPLORATION_CANDIDATES": int(
                        _funnel.get("EXPLORATION_CANDIDATES", 0) or 0
                    ),
                    "EXPLORATION_ELIGIBLE": int(
                        _funnel.get("EXPLORATION_ELIGIBLE", 0) or 0
                    ),
                    "CANDIDATES_GENERATED": int(
                        _funnel.get("CANDIDATES_GENERATED", 0) or 0
                    ),
                    "SEARCH_CANDIDATES": int(
                        _funnel.get("SEARCH_CANDIDATES", _funnel.get("CANDIDATES_GENERATED", 0)) or 0
                    ),
                    "BUY_VARIANTS_TESTED": int(
                        _funnel.get("BUY_VARIANTS_TESTED", 0) or 0
                    ),
                    "SELL_VARIANTS_TESTED": int(
                        _funnel.get("SELL_VARIANTS_TESTED", 0) or 0
                    ),
                    "HORIZONS_TESTED": int(
                        _funnel.get("HORIZONS_TESTED", 0) or 0
                    ),
                    "MECHANISMS_TESTED": int(
                        _funnel.get("MECHANISMS_TESTED", 0) or 0
                    ),
                    "MECHANISMS_AVAILABLE": int(
                        _funnel.get("MECHANISMS_AVAILABLE", 0) or 0
                    ),
                    "MECHANISMS_ACTUALLY_GENERATING_CANDIDATES": int(
                        _funnel.get("MECHANISMS_ACTUALLY_GENERATING_CANDIDATES", 0) or 0
                    ),
                    "BEST_BUY_SCORE": _funnel.get("BEST_BUY_SCORE"),
                    "BEST_SELL_SCORE": _funnel.get("BEST_SELL_SCORE"),
                    "BEST_AVAILABLE_SYMBOL": _funnel.get("BEST_AVAILABLE_SYMBOL"),
                    "BEST_AVAILABLE_SIDE": _funnel.get("BEST_AVAILABLE_SIDE"),
                    "BEST_AVAILABLE_HORIZON": _funnel.get("BEST_AVAILABLE_HORIZON"),
                    "BEST_AVAILABLE_MECHANISM": _funnel.get("BEST_AVAILABLE_MECHANISM"),
                    "WHY_NO_ORDER": _funnel.get("WHY_NO_ORDER"),
                    "SPREAD_FAIL": int(_funnel.get("SPREAD_FAIL", 0) or 0),
                    "GEOMETRY_FAIL": int(_funnel.get("GEOMETRY_FAIL", 0) or 0),
                    "RISK_FAIL": int(_funnel.get("RISK_FAIL", 0) or 0),
                    "NET_EV_FAIL": int(_funnel.get("NET_EV_FAIL", 0) or 0),
                    "MULTI_GATE_FAIL": int(_funnel.get("MULTI_GATE_FAIL", 0) or 0),
                    "NEAR_ELIGIBLE": int(_funnel.get("NEAR_ELIGIBLE", 0) or 0),
                    "BEST_REJECTED_CANDIDATE_EV": _funnel.get(
                        "BEST_REJECTED_CANDIDATE_EV"
                    ),
                    "BEST_REJECTED_CANDIDATE_P_GREEN": _funnel.get(
                        "BEST_REJECTED_CANDIDATE_P_GREEN"
                    ),
                    "BEST_REJECTED_REASON": _funnel.get("BEST_REJECTED_REASON"),
                    "UNCERTAINTY_REJECT": int(_brain_counts.get("uncertainty_reject", 0) or 0),
                    "MODEL_DISAGREEMENT": int(_brain_counts.get("model_disagreement", 0) or 0),
                    "MODEL_PROBABILITY_REJECT": int(
                        _brain_counts.get("short_horizon_probability_reject", 0) or 0
                    ),
                    "MODEL_EXPECTED_VALUE_REJECT": int(
                        _brain_counts.get("short_horizon_expected_value_reject", 0) or 0
                    ),
                    "MODEL_MISSING_REJECT": int(
                        _brain_counts.get("short_horizon_missing", 0) or 0
                    ),
                    "SHADOW_REJECT_VALIDATED": int(
                        _brain_counts.get("shadow_reject_validated", 0) or 0
                    ),
                    "SHADOW_REJECT_EXPLORATION": int(
                        _brain_counts.get("shadow_reject_exploration", 0) or 0
                    ),
                    "SHORT_HORIZON_ABSTAIN_REASONS": dict(
                        _brain_counts.get("short_horizon_abstain_reasons") or {}
                    ),
                    "TAIL_REJECT": int(_brain_counts.get("tail_reject", 0) or 0),
                    "STALE_REJECT": int(_funnel.get("STALE_REJECT", 0) or 0),
                    "RISK_REJECT": int(_funnel.get("RISK_REJECT", 0) or 0),
                    "BRAIN_INTENTS": int(_brain_counts.get("fire", 0) or 0),
                    "FIRES": int(submitted_count),
                    "SUBMITTED": int(submitted_count),
                    "FILLS": int(fill_count),
                    "FRESH_REVALIDATION_ATTEMPTS": int(
                        global_opportunity_counts.get("GLOBAL_REVALIDATED", 0) or 0
                    ),
                    "VIRTUAL_GEOMETRY_REJECTS": int(
                        quote_refresh_counts.get("virtual_geometry_reject", 0) or 0
                    ),
                    "BROKER_GEOMETRY_REJECTS": int(
                        quote_refresh_counts.get("broker_geometry_reject", 0) or 0
                    ),
                    "STALE_BEFORE_REFRESH": int(
                        quote_refresh_counts.get("stale_observed_at_send", 0) or 0
                    ),
                    "FRESH_QUOTES_RECOVERED": int(
                        quote_refresh_counts.get("fresh_quote_recovered", 0) or 0
                    ),
                    "RISK_RESIZED": int(
                        quote_refresh_counts.get("risk_resized", 0) or 0
                    ),
                    "RISK_HARD_BLOCKED": int(
                        quote_refresh_counts.get("risk_budget_precheck_skip", 0) or 0
                    ),
                    "OMS_REJECTS_BY_REASON": dict(oms_reject_reasons),
                    "CANDIDATE_DISCOVERY_TO_SEND_P50_MS": (
                        extra_hb["hot_path"]["candidate_discovery_to_send_p50_ms"]
                    ),
                    "CANDIDATE_DISCOVERY_TO_SEND_P95_MS": (
                        extra_hb["hot_path"]["candidate_discovery_to_send_p95_ms"]
                    ),
                    "OPEN_TICKETS": len(eng.positions()),
                    **global_opportunity_counts,
                    "GREEN_WITHIN_3S": int(_turnover.get("green_within_3s", 0) or 0),
                    "GREEN_WITHIN_5S": int(_turnover.get("green_within_5s", 0) or 0),
                    "GREEN_WITHIN_10S": int(_turnover.get("green_within_10s", 0) or 0),
                    "SCRATCHES": int(_turnover.get("scratches", 0) or 0),
                    "WIN_EXITS": int(_turnover.get("win_exits", 0) or 0),
                    "LOSS_EXITS": int(_turnover.get("loss_exits", 0) or 0),
                    "COMPLETED_TRADES": int(_turnover.get("completed_trades", 0) or 0),
                    "MEDIAN_HOLD_S": _turnover.get("median_hold_seconds"),
                    "WR": _turnover.get("win_rate"),
                    "EXPECTANCY": _turnover.get("expectancy"),
                    "PF": _turnover.get("profit_factor"),
                    "DAILY_NET": _turnover.get("daily_net"),
                    "OUTCOME_EVIDENCE": _turnover.get("outcome_evidence", "NO_EVIDENCE"),
                }
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
                                    "entry_ev": _ticket_meta.entry_ev,
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
                                if str(cfg.get("fast_firehose_remaining_ev_policy") or "") == REMAINING_EV_EXIT_POLICY_ID:
                                    _rem_ev, _rem_status = estimate_remaining_ev(
                                        side=str(_track.side),
                                        entry_price=_px,
                                        current_mark=_cur,
                                        invalidation=_inv,
                                        target=_tgt,
                                        entry_ev=_track.entry_ev_at_open,
                                    )
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
                            fast_verdict = {
                                "action": "HOLD",
                                "reason": "fast_exit_not_evaluated",
                                "why": "fast exit evidence not yet available",
                                "policy": "safety_noop",
                            }
                            trace: dict[str, Any] | None = None
                            # Fast exit state machine governs FAST tickets.
                            _is_fast = bool(video_style_mode)
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
                                    _fast_now_ts = time.time()
                                    _fast_quantity = float(getattr(pos, "quantity", 0) or 0)
                                    try:
                                        _fast_engine_spec = eng.symbol_spec(_sym) if hasattr(eng, "symbol_spec") else None
                                    except (AttributeError, OSError, TypeError, ValueError):
                                        _fast_engine_spec = None
                                    try:
                                        _current_short_prediction = short_horizon_predictor.predict(
                                            symbol=_sym,
                                            quote_buffer=quote_buffer,
                                            now_ts=_fast_now_ts,
                                            side=_side_l,
                                            broker_spec=_fast_engine_spec,
                                            quantity=_fast_quantity,
                                            horizon_s=(
                                                _ticket_meta.selected_horizon_s
                                                if _ticket_meta is not None
                                                else None
                                            ),
                                            mechanism=(
                                                _ticket_meta.expected_mechanism
                                                if _ticket_meta is not None
                                                else None
                                            ),
                                        )
                                    except Exception as exc:
                                        logger.debug(
                                            "short-horizon exit refresh skipped symbol=%s ticket=%s error=%s",
                                            _sym, tk, type(exc).__name__,
                                        )
                                        _current_short_prediction = None
                                    # Build context for production FastExit helper
                                    from aegis.intel.fast_exit_runner import FastExitContext, evaluate_fast_exit, MissingLiquidationMarkError
                                    from aegis.intel.broker_math import BrokerSymbolSpec
                                    _pip_sz = pip_size_for(_sym, cfg) if _sym else 0.0001
                                    _entry_px = float(getattr(pos, "avg_price", 0) or 0)
                                    _cur_bid = live_marks.get(_sym, {}).get("bid")
                                    _cur_ask = live_marks.get(_sym, {}).get("ask")
                                    # Spread is observed at the current executable
                                    # quote. Slippage/commission remain unavailable
                                    # unless the broker supplies them, preserving the
                                    # harvester's fail-closed evidence requirement.
                                    _spread_r = None
                                    _spread_normal = None
                                    try:
                                        _cost_entry = (
                                            _ticket_meta.entry_price if _ticket_meta is not None else _entry_px
                                        )
                                        _cost_stop = (
                                            _ticket_meta.stop_loss if _ticket_meta is not None
                                            else float(getattr(pos, "stop_loss", 0) or 0)
                                        )
                                        _spread_r = spread_r_from_geometry(
                                            _cost_entry, _cost_stop,
                                            float(getattr(pos, "quantity", 0) or 0),
                                            _cur_bid, _cur_ask,
                                            _fast_engine_spec,
                                        )
                                        _spread_limit = max_spread_for(_sym, cfg)
                                        if _spread_limit > 0 and _cur_bid is not None and _cur_ask is not None:
                                            _spread_normal = (
                                                float(_cur_ask) - float(_cur_bid)
                                            ) <= float(_spread_limit)
                                    except (TypeError, ValueError):
                                        pass
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
                                        regime_at_entry=_track.regime_at_open,
                                        track_target=_track.target if _track else 0.0,
                                        track_invalidation=_track.invalidation if _track else 0.0,
                                        track_entry_ev=float(_track.entry_ev_at_open or 0.0),
                                        track_side=_side_l,
                                        ticket_meta=_ticket_meta,
                                        engine_spec=_fast_engine_spec,
                                        config=cfg,
                                        live_marks=live_marks,
                                        intelligent_brain=intelligent_brain,
                                        profit_manager=profit_manager,
                                        now_ts=_fast_now_ts,
                                        legacy_hypothesis_id=_legacy_hyp_id,
                                        quote_buffer=quote_buffer,
                                        remaining_ev=_rem_ev,
                                        remaining_ev_status=_rem_status,
                                        observed_spread_r=_spread_r,
                                        spread_normal=_spread_normal,
                                        harvest_policy=harvest_policy,
                                        short_horizon_prediction=_current_short_prediction,
                                    )
                                    try:
                                        fast_verdict = evaluate_fast_exit(fast_exit_ctx)
                                    except MissingLiquidationMarkError:
                                        fast_exit_error_count += 1
                                        append_journal(
                                            journal,
                                            fast_exit_error_event(
                                                ticket=tk,
                                                symbol=_sym,
                                                error_type="MissingLiquidationMarkError",
                                                message=f"Missing liquidation mark for {_side_l.upper()}",
                                                observed_at=datetime.now(timezone.utc).isoformat(),
                                            ),
                                        )
                                        continue
                                    trace = firehose_exit_trace(fast_exit_ctx, fast_verdict)
                                    trace["timestamp"] = datetime.now(timezone.utc).isoformat()
                                    trace["pnl_usd"] = _track.last_pnl if _track is not None else None
                                    trace["mfe_usd"] = _track.mfe_usd if _track is not None else None
                                    trace["cost_usd"] = None
                                    trace["liquidation_bid"] = _cur_bid
                                    trace["liquidation_ask"] = _cur_ask
                                    if _ticket_meta is not None and _ticket_meta.basket_id:
                                        evidence = build_runtime_snapshot(
                                            ticket={
                                                "ticket_id": tk,
                                                "basket_id": _ticket_meta.basket_id,
                                                "side": _ticket_meta.side,
                                                "entry_price": _ticket_meta.entry_price,
                                                "initial_risk_usd": _ticket_meta.initial_risk,
                                            },
                                            basket={
                                                "basket_id": _ticket_meta.basket_id,
                                                "hypothesis_id": _ticket_meta.hypothesis_id,
                                                "family": _ticket_meta.strategy_family,
                                                "symbol": _ticket_meta.symbol,
                                            },
                                            marks=live_marks.get(_sym, {}),
                                            observed_at=fast_exit_ctx.now_ts,
                                            costs=_ticket_meta.cost_evidence or {},
                                            momentum={},
                                            remaining_ev={"value": _rem_ev, "observed_at": fast_exit_ctx.now_ts},
                                        )
                                    else:
                                        evidence = {"status": "NO_EVIDENCE", "reason": "missing_exact_basket_ownership"}
                                    trace = attach_runtime_evidence(trace, evidence)
                                    fast_verdict = {
                                        **dict(fast_verdict),
                                        "evidence_snapshot": dict(trace),
                                        "remaining_ev": _rem_ev,
                                    }
                                    firehose_turnover.record_exit_trace(
                                        tk,
                                        observed_at=fast_exit_ctx.now_ts,
                                        mfe_usd=trace["mfe_usd"],
                                        pnl_usd=trace.get("pnl_usd"),
                                    )
                                except Exception as fast_exc:
                                    fast_exit_error_count += 1
                                    append_journal(
                                        journal,
                                        fast_exit_error_event(
                                            ticket=tk,
                                            symbol=str(getattr(pos, "symbol", "")),
                                            error_type=type(fast_exc).__name__,
                                            message=str(fast_exc)[:200],
                                            observed_at=datetime.now(timezone.utc).isoformat(),
                                        ),
                                    )
                            verdict = trade_controller.decide(
                                verdict,
                                fast_verdict,
                                ticket=tk,
                                remaining_ev=_rem_ev,
                                profit_floor_r=fast_verdict.get("profit_floor_r"),
                                evidence_snapshot=(
                                    fast_verdict.get("evidence_snapshot")
                                    if isinstance(fast_verdict, Mapping) else None
                                ),
                            )
                            if trace is not None:
                                trace["exit_action"] = verdict["action"]
                                trace["exit_reason"] = verdict["reason"]
                                trace["profit_floor_r"] = verdict.get("profit_floor_r")
                                trace["profit_floor_source"] = fast_verdict.get(
                                    "profit_floor_source"
                                )
                                trace["EXIT_ACTION"] = verdict["action"]
                                trace["EXIT_REASON"] = verdict["reason"]
                                trace["exit_owner"] = verdict.get("source")
                                append_journal(journal, trace)
                            if verdict["action"] in {"HARVEST", "SCRATCH", "ABORT"} and hasattr(eng, "close_ticket"):
                                res_close = eng.close_ticket(tk)
                                try:
                                    close_facts = broker_close_evidence(
                                        eng.history_deals(1), ticket=tk
                                    )
                                except Exception:
                                    close_facts = {
                                        "status": "INCOMPLETE_BROKER_EVIDENCE",
                                        "reason": "deal_history_unavailable",
                                    }
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
                                # MT5 may acknowledge a placed/partial close as OK. Re-fetch
                                # positions before releasing any local lifecycle state.
                                close_confirmed = False
                                if res_close.ok:
                                    try:
                                        close_confirmed = close_ticket_confirmed(eng.positions(), tk)
                                    except Exception:
                                        close_confirmed = False
                                if close_confirmed:
                                    trade_controller.release_ticket(tk)
                                    closed_at = time.time()
                                    broker_confirmed = (
                                        close_facts.get("status") == "BROKER_CONFIRMED"
                                    )
                                    firehose_turnover.record_close(
                                        tk,
                                        closed_at=closed_at,
                                        gross_pnl_usd=(
                                            float(close_facts["gross_realized_pnl_usd"])
                                            if broker_confirmed else None
                                        ),
                                        net_pnl_usd=(
                                            float(close_facts["realized_net_usd"])
                                            if broker_confirmed else None
                                        ),
                                        cost_usd=(
                                            float(close_facts["cost_usd"])
                                            if broker_confirmed else None
                                        ),
                                        confirmed=True,
                                        exit_reason=str(verdict.get("reason") or "unknown"),
                                    )
                                    outcome_memory = getattr(
                                        intelligent_brain, "outcome_memory", None
                                    ) if intelligent_brain is not None else None
                                    if outcome_memory is not None:
                                        try:
                                            replay_unit = broker_replay_usd_per_price_unit(
                                                eng,
                                                symbol=str(getattr(pos, "symbol", "")),
                                                close_facts=close_facts,
                                            )
                                            learning_result = record_broker_confirmed_outcome_learning(
                                                outcome_memory=outcome_memory,
                                                outcome_id=tk,
                                                close_facts=close_facts,
                                                metadata=_ticket_meta,
                                                lifecycle_detail=firehose_turnover.close_detail(tk),
                                                quote_buffer=quote_buffer,
                                                usd_per_price_unit=replay_unit,
                                            )
                                            append_journal(
                                                journal,
                                                {
                                                    "event": "outcome_learning",
                                                    "ticket": tk,
                                                    "status": learning_result.get("status", "RECORDED"),
                                                    "evidence_status": learning_result.get("evidence_status"),
                                                    "classification": learning_result.get("classification"),
                                                    "speed_label": learning_result.get("speed_label"),
                                                },
                                            )
                                        except Exception as learning_exc:
                                            logger.error(
                                                "outcome learning update failed position=%s: %s",
                                                tk, learning_exc, exc_info=True,
                                            )
                                    append_journal(
                                        journal,
                                        {
                                            "event": "firehose_close",
                                            "ticket": tk,
                                            "timestamp": datetime.now(timezone.utc).isoformat(),
                                            "confirmed": True,
                                            "symbol": str(getattr(pos, "symbol", "")),
                                            "realized_net_usd": (
                                                close_facts.get("realized_net_usd")
                                                if broker_confirmed else None
                                            ),
                                            "gross_pnl_usd": (
                                                close_facts.get("gross_realized_pnl_usd")
                                                if broker_confirmed else None
                                            ),
                                            "cost_usd": (
                                                close_facts.get("cost_usd")
                                                if broker_confirmed else None
                                            ),
                                            "evidence_status": (
                                                "BROKER_CONFIRMED"
                                                if broker_confirmed
                                                else "INCOMPLETE_BROKER_EVIDENCE"
                                            ),
                                            "broker_close_facts": close_facts,
                                            **firehose_lifecycle_identity(_ticket_meta),
                                        },
                                    )
                                    _marks_close = live_marks.get(
                                        str(getattr(pos, "symbol", "")), {}
                                    )
                                    if _marks_close.get("bid") is not None and _marks_close.get("ask") is not None:
                                        _fingerprint = quote_fingerprint(
                                            str(getattr(pos, "symbol", "")),
                                            str(getattr(pos, "side", "")),
                                            _marks_close["bid"], _marks_close["ask"],
                                        )
                                    else:
                                        _fingerprint = None
                                    basket_contract = None
                                    if _ticket_meta is not None and _ticket_meta.basket_id:
                                        try:
                                            basket_contract = eng.symbol_spec(_ticket_meta.symbol)
                                        except (AttributeError, OSError, TypeError, ValueError):
                                            pass
                                    cleanup_result = remove_confirmed_firehose_basket_then_cleanup(
                                        root=ROOT,
                                        metadata_store=ticket_metadata_store,
                                        guard=firehose_reentry_guard,
                                        ticket_id=tk,
                                        quote_fingerprint=_fingerprint,
                                        closed_at=closed_at,
                                        contract=basket_contract,
                                    )
                                    basket_removal = cleanup_result.get(
                                        "basket_removal", cleanup_result,
                                    )
                                    close_cleanup = cleanup_result.get("close_cleanup")
                                    peak = (summary or {}).get("mfe_before_close")
                                    basket_trace = basket_lifecycle_trace(
                                        _ticket_meta,
                                        event="firehose_basket_close",
                                        timestamp=datetime.now(timezone.utc).isoformat(),
                                        confirmed=True,
                                        observation={
                                            "mfe_usd": peak,
                                            "mae_usd": (summary or {}).get("mae_before_close"),
                                            "peak_net_profit_usd": peak,
                                            "realized_net_usd": (
                                                close_facts.get("realized_net_usd")
                                                if broker_confirmed else None
                                            ),
                                            "capture_ratio": None,
                                            "age_seconds": (summary or {}).get("duration_s"),
                                            "clips": (
                                                _ticket_meta.clip_sequence
                                                if _ticket_meta is not None else None
                                            ),
                                            "decision_reasons": [str(verdict.get("reason") or "unknown")],
                                            "ev": _rem_ev,
                                            "cost_usd": (
                                                close_facts.get("cost_usd")
                                                if broker_confirmed else None
                                            ),
                                            "broker_close_facts": close_facts,
                                            "turnover": 1.0,
                                            "basket_removal_status": basket_removal.get("status"),
                                        },
                                        slot_released=bool(close_cleanup and close_cleanup.slot_released),
                                        basket_closed=bool(close_cleanup and close_cleanup.basket_closed),
                                    )
                                    if basket_trace is not None:
                                        append_journal(journal, basket_trace)
                                elif res_close.ok:
                                    append_journal(
                                        journal,
                                        {
                                            "event": "firehose_close_unconfirmed",
                                            "ticket": tk,
                                            "timestamp": datetime.now(timezone.utc).isoformat(),
                                            "symbol": str(getattr(pos, "symbol", "")),
                                            "ok": True,
                                        },
                                    )
                                # Exploration learning is performed only by
                                # reconciliation from broker-confirmed deal
                                # facts. The PM summary intentionally contains
                                # floating-at-close diagnostics, never a
                                # training source of truth.
                            elif verdict["action"] == "LOCK":
                                # 0.01-lot reality: protective STOP ADJUSTMENT
                                # only - never pretend partial close exists.
                                lock_sl = None
                                side_l = str(getattr(pos, "side", "")).lower()
                                px = float(getattr(pos, "avg_price", 0) or 0)
                                buffer_usd = float(
                                    cfg.get("pm_breakeven_buffer_usd", 0.05) or 0.05
                                )
                                floor_r = verdict.get("profit_floor_r")
                                if floor_r is not None:
                                    try:
                                        risk_for_floor = (
                                            float(_ticket_meta.initial_risk)
                                            if _ticket_meta is not None
                                            and _ticket_meta.initial_risk is not None
                                            else 0.0
                                        )
                                        if risk_for_floor > 0 and math.isfinite(float(floor_r)):
                                            buffer_usd = max(
                                                buffer_usd,
                                                float(floor_r) * risk_for_floor,
                                            )
                                    except (TypeError, ValueError, OverflowError):
                                        pass
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
                            elif legacy_normal_exit_enabled(intelligent_mode) and max_hold > 0 and held >= max_hold:
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
                            last_entry_at.pop(sym, None)
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
                        maybe_enter(
                            sym,
                            equity,
                            len(eng.positions()),
                            collect_only=bool(cfg.get("intelligent_firehose", False)),
                        )
                    except Exception:
                        logger.exception("Symbol loop error %s", sym)

                if bool(cfg.get("intelligent_firehose", False)) and deferred_opportunities:
                    _open_for_allocation = len(eng.positions())
                    _remaining_capacity = max(0, int(max_positions) - _open_for_allocation)
                    _per_trade_budget = float(
                        cfg.get("exploration_max_risk_per_trade_usd", 0.0) or 0.0
                    )
                    global_rank_started_at = time.time()
                    ranked_opportunities, selected_opportunities = rank_and_allocate(
                        deferred_opportunities,
                        max_positions=_remaining_capacity,
                        max_total_risk_usd=(
                            _per_trade_budget * _remaining_capacity
                            if _per_trade_budget > 0 else None
                        ),
                        occupied_theses=(
                            key for key, mem in intelligent_brain.memory.theses.items()
                            if mem.tickets
                        ) if intelligent_brain is not None else (),
                    )
                    global_rank_finished_at = time.time()
                    selected_opportunities = [
                        freeze_opportunity({
                            **row.to_dict(),
                            "global_rank_started_at": global_rank_started_at,
                            "global_rank_finished_at": global_rank_finished_at,
                        })
                        for row in selected_opportunities
                    ]
                    global_opportunity_counts["GLOBAL_RANKED"] += len(ranked_opportunities)
                    global_opportunity_counts["GLOBAL_SELECTED"] += len(selected_opportunities)
                    append_journal(
                        journal,
                        {
                            "event": "global_opportunity_allocation",
                            "candidates": len(deferred_opportunities),
                            "ranked": len(ranked_opportunities),
                            "selected": len(selected_opportunities),
                            "selected_ids": [
                            row.get("candidate_id") for row in selected_opportunities
                            ],
                        },
                    )
                    for opportunity in selected_opportunities:
                        maybe_enter(
                            str(opportunity["symbol"]),
                            equity,
                            len(eng.positions()),
                            selected_execution=True,
                            frozen_opportunity=opportunity,
                        )

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
