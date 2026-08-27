"""Production FastExit evaluation helper for runner.

This module extracts the FastExit evaluation logic from run_broker_paper.py
so it can be tested deterministically without running the full runner loop.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Mapping, Optional

from aegis.intel.broker_math import BrokerSymbolSpec, mfe_mae_from_usd
from aegis.intel.fast_firehose import FastExitConfig, FastExitStateMachine
from aegis.intel.profit_harvester import HarvestInput, HarvestPolicy
from aegis.intel.quote_buffer import QuoteBuffer
from aegis.intel.ticket_metadata import TicketMetadata, firehose_lifecycle_identity


# This is a separately validated point-in-time rule, not a fabricated harvest
# policy. It uses only the current executable liquidation mark, current spread,
# the ticket's entry geometry, and the runner's current EV estimate.
REMAINING_EV_EXIT_POLICY_ID = "fast_firehose_remaining_ev_v1"


@dataclass
class FastExitContext:
    """All inputs needed for FastExit evaluation."""
    symbol: str
    ticket: str
    side: str
    entry_price: float
    current_bid: float
    current_ask: float
    avg_price: float
    stop_loss: float
    quantity: float
    mfe_usd: float
    mae_usd: float
    opened_ts: float
    regime_at_entry: str
    track_target: float
    track_invalidation: float
    track_entry_ev: float
    track_side: str
    ticket_meta: Optional[TicketMetadata]
    engine_spec: Optional[Mapping[str, Any]]
    config: Mapping[str, Any]
    live_marks: Mapping[str, Mapping[str, float]]
    intelligent_brain: Any
    profit_manager: Any
    now_ts: float
    # Legacy hypothesis ID for experiment fallback (only when exact ticket metadata absent)
    legacy_hypothesis_id: Optional[str] = None
    quote_buffer: Optional[QuoteBuffer] = None
    remaining_ev: Optional[float] = None
    remaining_ev_status: str = "UNKNOWN"
    observed_spread_r: Optional[float] = None
    observed_slippage_r: Optional[float] = None
    observed_commission_r: Optional[float] = None
    spread_normal: Optional[bool] = None
    harvest_policy: Optional[HarvestPolicy] = None
    short_horizon_prediction: Optional[Mapping[str, Any]] = None


class MissingLiquidationMarkError(Exception):
    """Raised when required liquidation mark (BID for BUY, ASK for SELL) is unavailable."""
    def __init__(self, side: str, symbol: str):
        self.side = side
        self.symbol = symbol
        super().__init__(f"Missing liquidation mark for {side.upper()} on {symbol}: required {'BID' if side == 'buy' else 'ASK'} unavailable")


_FAST_EXIT_TO_CONTROLLER_ACTION = {
    "TAKE": "EXIT",
    "QUICK_TAKE": "EXIT",
    "SCRATCH": "EXIT",
    "ABORT": "EXIT",
    "TIME_EXIT": "EXIT",
}


def unified_trade_controller_decision(
    profit_manager_verdict: Mapping[str, Any],
    fast_verdict: Mapping[str, Any],
) -> dict[str, Any]:
    """Select one canonical per-ticket action from the two evidence adapters.

    ProfitManager and FastExit provide independent evidence, but the runner must
    have one decision owner. Any explicit PM exit is preserved; otherwise a
    terminal FastExit action becomes the canonical EXIT. Non-terminal LOCK/HOLD
    decisions are retained with both explanations so a HOLD is auditable.
    """
    pm = dict(profit_manager_verdict or {})
    fast = dict(fast_verdict or {})
    pm_action = str(pm.get("action") or "HOLD").upper()
    fast_action = str(fast.get("action") or "HOLD").upper()

    if pm_action == "EXIT":
        return pm
    if fast_action in _FAST_EXIT_TO_CONTROLLER_ACTION:
        return {
            "action": "EXIT",
            "reason": f"fast_{fast_action.lower()}:{fast.get('reason') or 'requested'}",
            "why": str(fast.get("why") or "fast exit evidence"),
            "policy": f"fast_{fast.get('policy') or fast.get('reason') or fast_action.lower()}",
        }
    if pm_action != "HOLD":
        return pm
    if fast_action != "HOLD":
        return fast
    return {
        "action": "HOLD",
        "reason": pm.get("reason") or fast.get("reason") or "controller_hold",
        "why": "; ".join(
            value for value in (pm.get("why"), fast.get("why")) if value
        ) or "no exit evidence",
        "policy": pm.get("policy") or fast.get("policy"),
    }


def combine_existing_exit_with_policy(
    existing: Mapping[str, Any], policy: Mapping[str, Any],
) -> dict[str, Any]:
    """Expose policy evidence without allowing it to replace an existing exit decision."""
    result = dict(existing)
    result["policy_action"] = policy.get("action")
    result["policy_reason"] = policy.get("reason")
    return result


def evaluate_fast_exit(ctx: FastExitContext) -> dict[str, Any]:
    """Evaluate FastExit for a single ticket using production logic.

    This is the exact logic from run_broker_paper.py, extracted for testability.

    Returns the fast_verdict dict with action, reason, why, policy.
    
    Raises:
        MissingLiquidationMarkError: If required liquidation mark (BID for BUY, ASK for SELL) is unavailable.
    """
    tk = ctx.ticket
    pos_symbol = ctx.symbol
    pos_side = ctx.side.lower()

    # Get current symbol's marks
    _marks = ctx.live_marks.get(pos_symbol, {})

    # Get pip size for current symbol
    _pip_sz = pip_size_for(pos_symbol, ctx.config)

    # Fresh liquidation mark for current position's side - NO FALLBACKS
    if pos_side == "buy":
        _mark = _marks.get("bid")
        if _mark is None:
            raise MissingLiquidationMarkError("buy", pos_symbol)
    else:
        _mark = _marks.get("ask")
        if _mark is None:
            raise MissingLiquidationMarkError("sell", pos_symbol)

    # Exact ticket metadata is authoritative for fresh tickets.
    _ticket_meta = ctx.ticket_meta
    _entry_px = float(_ticket_meta.entry_price if _ticket_meta else ctx.avg_price or 0)
    _state_entry_px = _ticket_meta.entry_price if _ticket_meta else ctx.entry_price

    # PnL in pips using liquidation mark
    _pnl_pips = ((_mark - _entry_px) / max(_pip_sz, 1e-10)) * (1 if pos_side == "buy" else -1)

    # Broker-native spec for current symbol
    try:
        _spec_fast = BrokerSymbolSpec.from_mapping(ctx.engine_spec)
    except ValueError:
        return {
            "action": "HOLD",
            "reason": "broker_spec_unavailable",
            "why": "Broker-native tick value, tick size, and volume evidence are required",
            "policy": "safety_noop",
        }
    _lot_sz = float(ctx.quantity)

    # Convert MFE/MAE from USD to pips using broker-native math
    _mfe_pips, _mae_pips = mfe_mae_from_usd(
        float(ctx.mfe_usd or 0),
        float(ctx.mae_usd or 0),
        _spec_fast, _lot_sz, _pip_sz
    )

    _stop_loss = _ticket_meta.stop_loss if _ticket_meta else ctx.stop_loss
    _opened_ts = _ticket_meta.opened_ts if _ticket_meta else ctx.opened_ts

    # Stop distance in pips
    _stop_dist_pips = abs(
        _entry_px - float(_stop_loss or 0)
    ) / max(_pip_sz, 1e-10) if _stop_loss else 10.0

    # Use exact ticket metadata for target and max_hold_s (first priority)
    _tgt_px = _ticket_meta.target_price if _ticket_meta else None
    _video_fallback = int(ctx.config.get("_video_style_max_hold_s") or 0)
    if _ticket_meta:
        # Fresh ticket metadata carries the selected search horizon.  Video
        # mode must not replace a 5/8/10s decision with an arbitrary blanket
        # cap after the fill.
        _max_hold_s = int(_ticket_meta.max_hold_s)
    else:
        _max_hold_s = _video_fallback or 120

    # Fallback to experiment scan for legacy tickets ONLY when exact metadata absent
    if _ticket_meta is None and _tgt_px is None and ctx.intelligent_brain is not None:
        # Use explicit legacy_hypothesis_id for lookup, NOT track_target (which is a price)
        _legacy_hyp_id = ctx.legacy_hypothesis_id
        if _legacy_hyp_id:
            for _exp in ctx.intelligent_brain.experiments.data.get("experiments", {}).values():
                if str(_exp.get("hypothesis_id")) == str(_legacy_hyp_id):
                    _tgt_px = _exp.get("target_price")
                    _max_hold_s = int(_exp.get("max_hold_s") or (_video_fallback or 120))
                    break

    # Create FastExit state machine with ticket's max_hold_s
    fast_exit_sm = FastExitStateMachine(FastExitConfig(time_exit_s=_max_hold_s))

    # The remaining-EV rule is independently governed and point-in-time. A
    # harvest policy is optional additional evidence and is never fabricated.
    harvest_input = build_harvest_input(ctx)
    remaining_ev_active = (
        str(ctx.config.get("fast_firehose_remaining_ev_policy") or "")
        == REMAINING_EV_EXIT_POLICY_ID
        and ctx.remaining_ev_status == "ESTIMATED"
        and _finite(ctx.remaining_ev)
    )

    # Evaluate. Remaining EV is observed and traced regardless; this separately
    # governed rule is active only when the runner config names its policy ID.
    fast_verdict = fast_exit_sm.evaluate(
        side=pos_side,
        entry_price=_state_entry_px,
        current_mark=_mark,
        stop_loss=float(_stop_loss or 0),
        target=_tgt_px or _entry_px + _pip_sz * 10 * (1 if pos_side == "buy" else -1),
        opened_ts=_opened_ts,
        now=ctx.now_ts,
        pnl_pips=_pnl_pips,
        mfe_pips=_mfe_pips,
        mae_pips=_mae_pips,
        stop_pips=max(_stop_dist_pips, 1.0),
        pip=_pip_sz,
        regime_now=str(ctx.intelligent_brain.regime_by_symbol.get(pos_symbol, "") if ctx.intelligent_brain else ""),
        regime_at_entry=ctx.regime_at_entry,
        remaining_ev=ctx.remaining_ev if remaining_ev_active else None,
        remaining_ev_status=ctx.remaining_ev_status if remaining_ev_active else "UNKNOWN",
        harvest_policy=ctx.harvest_policy,
        harvest_input=harvest_input,
    )

    # Current calibrated model support may replace only the default HOLD, and
    # only while the ticket is non-profitable. Existing target, scratch,
    # giveback, regime, EV, and lock decisions keep priority.
    if (
        fast_verdict.get("action") == "HOLD"
        and _pnl_pips <= 0
        and short_horizon_support_revoked(ctx.short_horizon_prediction)
    ):
        prediction = ctx.short_horizon_prediction or {}
        return {
            "action": "ABORT",
            "reason": "short_horizon_support_revoked",
            "why": (
                "current calibrated short-horizon support was revoked "
                f"(probability={float(prediction.get('probability', 0.0)):.3f}, "
                f"threshold={float(prediction.get('threshold', 0.5)):.3f}, "
                f"decision={bool(prediction.get('decision', False))}) while pnl is non-positive"
            ),
            "policy": "short_horizon_support_revoked",
        }

    return fast_verdict


def build_harvest_input(ctx: FastExitContext) -> HarvestInput | None:
    """Build costed, normalized harvester evidence without fabricating inputs."""
    meta = ctx.ticket_meta
    if meta is None or ctx.quote_buffer is None:
        return None
    side = ctx.side.lower()
    if side not in {"buy", "sell"}:
        return None
    mark = ctx.current_bid if side == "buy" else ctx.current_ask
    entry = meta.entry_price
    stop = meta.stop_loss
    if not _finite_positive(mark) or not _finite_positive(entry) or not _finite_positive(stop):
        return None
    try:
        spec = BrokerSymbolSpec.from_mapping(ctx.engine_spec)
    except ValueError:
        return None
    lots = float(ctx.quantity)
    if not _finite_positive(lots):
        return None
    risk_usd = abs(entry - stop) * spec.usd_per_price_unit_per_lot() * lots
    if not _finite_positive(risk_usd):
        return None
    returns = (
        ctx.quote_buffer.return_5s(ctx.symbol, side, ctx.now_ts),
        ctx.quote_buffer.return_15s(ctx.symbol, side, ctx.now_ts),
        ctx.quote_buffer.return_30s(ctx.symbol, side, ctx.now_ts),
    )
    if not all(_finite(value) for value in returns):
        return None
    direction = 1.0 if side == "buy" else -1.0
    price_to_r = spec.usd_per_price_unit_per_lot() * lots / risk_usd
    return HarvestInput(
        ticket=ctx.ticket,
        side=side,
        gross_pnl_r=(mark - entry) * direction * price_to_r,
        gross_mfe_r=float(ctx.mfe_usd) / risk_usd if _finite(ctx.mfe_usd) else None,
        age_s=ctx.now_ts - meta.opened_ts if _finite(ctx.now_ts) and _finite(meta.opened_ts) else None,
        gross_return_5s_r=returns[0] * direction * price_to_r,
        gross_return_15s_r=returns[1] * direction * price_to_r,
        gross_return_30s_r=returns[2] * direction * price_to_r,
        remaining_ev=ctx.remaining_ev,
        remaining_ev_status=ctx.remaining_ev_status,
        spread_normal=ctx.spread_normal,
        observed_spread_r=ctx.observed_spread_r,
        observed_slippage_r=ctx.observed_slippage_r,
        observed_commission_r=ctx.observed_commission_r,
        liquidation_mark=mark,
        opened_ts=meta.opened_ts,
        stop_loss=stop,
        target_price=meta.target_price,
    )


def firehose_exit_trace(ctx: FastExitContext, verdict: Mapping[str, Any]) -> dict[str, Any]:
    """Return observed exit evidence; unavailable measurements remain null."""
    harvest = build_harvest_input(ctx)
    meta = ctx.ticket_meta
    pnl_r = harvest.net_pnl_r if harvest is not None else None
    mfe_r = harvest.mfe_r if harvest is not None else None
    floor_r = None
    if harvest is not None and ctx.harvest_policy is not None and mfe_r is not None:
        floor_r = mfe_r * ctx.harvest_policy.protected_mfe_fraction
    return {
        "event": "firehose_exit_trace",
        "ticket": ctx.ticket,
        "symbol": ctx.symbol,
        "side": ctx.side.lower(),
        "liquidation_mark": (harvest.liquidation_mark if harvest else None),
        "pnl_r": pnl_r,
        "mfe_r": mfe_r,
        "mae_r": (float(ctx.mae_usd) / _risk_usd(ctx, meta) if meta and _risk_usd(ctx, meta) else None),
        "giveback_r": (mfe_r - pnl_r if mfe_r is not None and pnl_r is not None else None),
        "profit_floor_r": floor_r,
        "return_5s_r": (harvest.return_5s_r if harvest else None),
        "return_15s_r": (harvest.return_15s_r if harvest else None),
        "return_30s_r": (harvest.return_30s_r if harvest else None),
        "observed_spread_r": (harvest.observed_spread_r if harvest else ctx.observed_spread_r),
        "observed_slippage_r": (harvest.observed_slippage_r if harvest else ctx.observed_slippage_r),
        "observed_commission_r": (harvest.observed_commission_r if harvest else ctx.observed_commission_r),
        "spread_normal": (harvest.spread_normal if harvest else ctx.spread_normal),
        "remaining_ev": ctx.remaining_ev,
        "remaining_ev_status": ctx.remaining_ev_status,
        "target_price": (meta.target_price if meta else None),
        "action": verdict.get("action"),
        "reason": verdict.get("reason"),
        **firehose_lifecycle_identity(meta),
    }


def confirmed_close_event(close: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize broker-confirmed close facts; missing facts stay fail-closed."""
    if close.get("confirmed") is not True:
        return {"status": "NO_EVIDENCE", "reason": "close_not_confirmed"}
    required = ("cost_usd", "realized_net_usd", "mfe_usd", "mae_usd")
    if any(not _finite(close.get(field)) for field in required):
        return {"status": "NO_EVIDENCE", "reason": "numeric_close_facts_required"}
    return {
        **dict(close),
        "status": "OK",
        **{field: float(close[field]) for field in required},
    }


def _risk_usd(ctx: FastExitContext, meta: TicketMetadata | None) -> float | None:
    if meta is None:
        return None
    try:
        spec = BrokerSymbolSpec.from_mapping(ctx.engine_spec)
        risk = abs(meta.entry_price - meta.stop_loss) * spec.usd_per_price_unit_per_lot() * float(ctx.quantity)
        return risk if _finite_positive(risk) else None
    except (TypeError, ValueError):
        return None


def spread_r_from_geometry(
    entry_price: float,
    stop_loss: float,
    quantity: float,
    bid: float,
    ask: float,
    engine_spec: Mapping[str, Any] | None,
) -> float | None:
    """Normalize observed spread against immutable ticket risk geometry."""
    try:
        spec = BrokerSymbolSpec.from_mapping(engine_spec)
        entry = float(entry_price)
        stop = float(stop_loss)
        lots = float(quantity)
        current_bid = float(bid)
        current_ask = float(ask)
        risk_usd = abs(entry - stop) * spec.usd_per_price_unit_per_lot() * lots
        spread_usd = (current_ask - current_bid) * spec.usd_per_price_unit_per_lot() * lots
        if not _finite_positive(risk_usd) or not _finite(spread_usd) or spread_usd < 0:
            return None
        return spread_usd / risk_usd
    except (TypeError, ValueError):
        return None


def estimate_remaining_ev(
    *,
    side: str,
    entry_price: object,
    current_mark: object,
    invalidation: object,
    target: object,
    entry_ev: object,
) -> tuple[float | None, str]:
    """Estimate remaining costed EV from current executable geometry.

    This is the explicitly configured ``fast_firehose_remaining_ev_v1`` rule.
    It scales the already-costed entry EV by the remaining reward/risk ratio;
    it does not invent EV when the entry economics or directional geometry are
    unavailable. ``UNKNOWN`` is fail-closed and never activates an exit.
    """
    normalized_side = str(side or "").strip().lower()
    if normalized_side not in {"buy", "sell"}:
        return None, "UNKNOWN"
    values = (entry_price, current_mark, invalidation, target, entry_ev)
    if not all(_finite(value) for value in values):
        return None, "UNKNOWN"
    entry = float(entry_price)
    current = float(current_mark)
    invalid = float(invalidation)
    target_price = float(target)
    base_ev = float(entry_ev)
    if entry <= 0.0 or current <= 0.0 or base_ev <= 0.0:
        return None, "UNKNOWN"
    sign = 1.0 if normalized_side == "buy" else -1.0
    initial_reward = (target_price - entry) * sign
    initial_risk = (entry - invalid) * sign
    if initial_reward <= 0.0 or initial_risk <= 0.0:
        return None, "UNKNOWN"
    remaining_reward = (target_price - current) * sign
    remaining_risk = abs(current - invalid)
    if remaining_risk <= 0.0:
        return None, "UNKNOWN"
    initial_rr = initial_reward / initial_risk
    remaining_rr = remaining_reward / remaining_risk
    if not (_finite(initial_rr) and _finite(remaining_rr)):
        return None, "UNKNOWN"
    ratio = max(0.0, min(2.0, remaining_rr / initial_rr))
    return float(base_ev * ratio), "ESTIMATED"


def short_horizon_support_revoked(prediction: Mapping[str, Any] | None) -> bool:
    """Return True only for current, calibrated, non-abstaining negative support."""
    if not isinstance(prediction, Mapping):
        return False
    if str(prediction.get("calibration_status") or "") != "calibrated":
        return False
    if bool(prediction.get("abstain", True)):
        return False
    try:
        probability = float(prediction["probability"])
        threshold = float(prediction.get("threshold", 0.5))
    except (KeyError, TypeError, ValueError):
        return False
    if not (math.isfinite(probability) and math.isfinite(threshold)):
        return False
    if not 0.0 <= probability <= 1.0 or not 0.0 < threshold < 1.0:
        return False
    return probability < threshold or (
        "decision" in prediction and not bool(prediction.get("decision"))
    )


def _finite(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _finite_positive(value: object) -> bool:
    return _finite(value) and value > 0


def pip_size_for(symbol: str, config: Mapping[str, Any]) -> float:
    """Get pip size from config or use standard defaults."""
    sym = str(symbol).upper()
    if "JPY" in sym:
        return 0.01
    if "XAU" in sym or "GOLD" in sym:
        return 0.1
    return 0.0001
