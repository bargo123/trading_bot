"""Production FastExit evaluation helper for runner.

This module extracts the FastExit evaluation logic from run_broker_paper.py
so it can be tested deterministically without running the full runner loop.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional

from aegis.intel.broker_math import BrokerSymbolSpec, mfe_mae_from_usd
from aegis.intel.fast_firehose import FastExitConfig, FastExitStateMachine
from aegis.intel.ticket_metadata import TicketMetadata


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


class MissingLiquidationMarkError(Exception):
    """Raised when required liquidation mark (BID for BUY, ASK for SELL) is unavailable."""
    def __init__(self, side: str, symbol: str):
        self.side = side
        self.symbol = symbol
        super().__init__(f"Missing liquidation mark for {side.upper()} on {symbol}: required {'BID' if side == 'buy' else 'ASK'} unavailable")


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

    # Entry price from position
    _entry_px = float(ctx.avg_price or 0)

    # PnL in pips using liquidation mark
    _pnl_pips = ((_mark - _entry_px) / max(_pip_sz, 1e-10)) * (1 if pos_side == "buy" else -1)

    # Broker-native spec for current symbol
    _spec_fast = BrokerSymbolSpec.from_mapping(ctx.engine_spec)
    _lot_sz = float(ctx.quantity)

    # Convert MFE/MAE from USD to pips using broker-native math
    _mfe_pips, _mae_pips = mfe_mae_from_usd(
        float(ctx.mfe_usd or 0),
        float(ctx.mae_usd or 0),
        _spec_fast, _lot_sz, _pip_sz
    )

    # Stop distance in pips
    _stop_dist_pips = abs(
        float(ctx.avg_price or 0) - float(ctx.stop_loss or 0)
    ) / max(_pip_sz, 1e-10) if ctx.stop_loss else 10.0

    # Use exact ticket metadata for target and max_hold_s (first priority)
    _ticket_meta = ctx.ticket_meta
    _tgt_px = _ticket_meta.target_price if _ticket_meta else None
    _max_hold_s = int(_ticket_meta.max_hold_s) if _ticket_meta else 120

    # Fallback to experiment scan for legacy tickets ONLY when exact metadata absent
    if _tgt_px is None and ctx.intelligent_brain is not None:
        # Use explicit legacy_hypothesis_id for lookup, NOT track_target (which is a price)
        _legacy_hyp_id = ctx.legacy_hypothesis_id
        if _legacy_hyp_id:
            for _exp in ctx.intelligent_brain.experiments.data.get("experiments", {}).values():
                if str(_exp.get("hypothesis_id")) == str(_legacy_hyp_id):
                    _tgt_px = _exp.get("target_price")
                    _max_hold_s = int(_exp.get("max_hold_s") or 120)
                    break

    # Create FastExit state machine with ticket's max_hold_s
    fast_exit_sm = FastExitStateMachine(FastExitConfig(time_exit_s=_max_hold_s))

    # Evaluate
    fast_verdict = fast_exit_sm.evaluate(
        side=pos_side,
        entry_price=ctx.entry_price,
        current_mark=_mark,
        stop_loss=float(ctx.stop_loss or 0),
        target=_tgt_px or _entry_px + _pip_sz * 10 * (1 if pos_side == "buy" else -1),
        opened_ts=ctx.opened_ts,
        now=ctx.now_ts,
        pnl_pips=_pnl_pips,
        mfe_pips=_mfe_pips,
        mae_pips=_mae_pips,
        stop_pips=max(_stop_dist_pips, 1.0),
        pip=_pip_sz,
        regime_now=str(ctx.intelligent_brain.regime_by_symbol.get(pos_symbol, "") if ctx.intelligent_brain else ""),
        regime_at_entry=ctx.regime_at_entry,
        remaining_ev=None,
        remaining_ev_status="UNKNOWN",
    )

    return fast_verdict


def pip_size_for(symbol: str, config: Mapping[str, Any]) -> float:
    """Get pip size from config or use standard defaults."""
    sym = str(symbol).upper()
    if "JPY" in sym:
        return 0.01
    if "XAU" in sym or "GOLD" in sym:
        return 0.1
    return 0.0001