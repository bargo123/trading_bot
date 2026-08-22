"""FAST_TURNOVER_FIREHOSE_V1 — micro-edge family definitions + fast exit.

Two-timescale architecture:
  CONTEXT: M15/M5 regime, structure, S/R, compression
  EXECUTION: M1/tick trigger, spread condition, micro momentum

Multiple independent families, each with its own:
  hypothesis_id, mechanism, side logic, entry, confirmation,
  invalidation, target, max hold, required state, falsification

Two lanes:
  SHADOW_MICRO: research throughput when broker lot granularity blocks
  BROKER_MICRO: real MT5 DEMO orders when geometry fits

The fast exit state machine manages each ticket through:
  HOLD / LOCK / TAKE / SCRATCH / ABORT / TRAIL / STOP / TIME_EXIT
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class ExitAction(str, Enum):
    HOLD = "HOLD"
    LOCK = "LOCK"
    TAKE = "TAKE"
    SCRATCH = "SCRATCH"
    ABORT = "ABORT"
    TRAIL = "TRAIL"
    STOP = "STOP"
    TIME_EXIT = "TIME_EXIT"


class FirehoseLane(str, Enum):
    SHADOW_MICRO = "SHADOW_RESEARCH_FIREHOSE"
    BROKER_MICRO = "DEMO_FAST_TURNOVER_FIREHOSE"


def firehose_hypothesis_id(*, family: str, symbol: str, side: str,
                           regime: str, session: str) -> str:
    blob = f"ftf|{family}|{symbol}|{side}|{regime}|{session}"
    return "ftf_" + hashlib.sha256(blob.encode()).hexdigest()[:16]


class Direction(str, Enum):
    UP = "up"
    DOWN = "down"
    FLAT = "flat"
    UNKNOWN = "unknown"


@dataclass
class FastMarketContext:
    """Point-in-time market data for fast-turnover decisions.
    All fields are None if unavailable. NO fabricated defaults.

    Sub-minute returns are side-specific (liquidation-side semantics):
    BUY -> BID (closing a long), SELL -> ASK (closing a short).
    """
    symbol: str
    timestamp: str = ""
    bid: float | None = None
    ask: float | None = None
    spread_pips: float | None = None
    # Completed M1
    m1_open: float | None = None
    m1_high: float | None = None
    m1_low: float | None = None
    m1_close: float | None = None
    m1_prev_close: float | None = None
    m1_atr: float | None = None
    m1_range: float | None = None
    m1_body: float | None = None
    m1_volume: float | None = None
    # Completed M5
    m5_direction: str | None = None  # up/down/flat/unknown
    m5_structure: str | None = None
    m5_support: float | None = None
    m5_resistance: float | None = None
    m5_atr: float | None = None
    m5_compression: float | None = None
    # Completed M15
    m15_direction: str | None = None
    m15_structure: str | None = None
    m15_support: float | None = None
    m15_resistance: float | None = None
    m15_range_mid: float | None = None
    m15_range_half_width: float | None = None
    # Recent tick/quote buffer - side-specific returns
    return_5s_buy: float | None = None
    return_5s_sell: float | None = None
    return_15s_buy: float | None = None
    return_15s_sell: float | None = None
    return_30s_buy: float | None = None
    return_30s_sell: float | None = None
    return_60s_buy: float | None = None
    return_60s_sell: float | None = None
    tick_rate_per_min: float | None = None
    quote_change_rate: float | None = None
    short_volatility: float | None = None
    signed_tick_imbalance: float | None = None
    # Session/regime
    session: str | None = None
    regime: str | None = None

    def get_return(self, window_s: int, side: str) -> float | None:
        """Get return for window and side (buy/sell)."""
        if window_s == 5:
            return self.return_5s_buy if side == "buy" else self.return_5s_sell
        if window_s == 15:
            return self.return_15s_buy if side == "buy" else self.return_15s_sell
        if window_s == 30:
            return self.return_30s_buy if side == "buy" else self.return_30s_sell
        if window_s == 60:
            return self.return_60s_buy if side == "buy" else self.return_60s_sell
        return None

    @property
    def has_micro_geometry(self) -> bool:
        return all(v is not None for v in (
            self.bid, self.ask, self.m1_close, self.m1_atr,
            self.m1_low, self.m1_high))


@dataclass
class MicroCandidate:
    """One fast-turnover trade candidate from a specific family."""
    hypothesis_id: str
    family: str
    symbol: str
    side: str  # buy | sell
    entry_price: float          # ask for buy, bid for sell
    invalidation: float         # protective stop level (micro structure)
    target: float               # profit target
    max_hold_s: int             # expected horizon
    required_regime: str        # trend/range/compression/expansion
    required_session: str       # asia/london/newyork
    spread_pips: float          # current spread at evaluation
    stop_pips: float            # structural invalidation distance
    target_pips: float          # target distance
    risk_usd_min_lot: float     # actual risk at broker volume_min
    lane: FirehoseLane          # SHADOW or BROKER
    mechanism: str = ""         # why this edge exists
    book_source_hash: str = ""  # passage hash if book-derived
    book_family: str = ""       # source strategy family label
    falsification: str = ""     # what proves this wrong

    @property
    def payoff(self) -> float:
        return self.target_pips / max(self.stop_pips, 1e-9)

    @property
    def net_target_pips(self) -> float:
        return self.target_pips - self.spread_pips

    @property
    def economics_viable(self) -> bool:
        """Target must clear round-trip cost with room."""
        return self.net_target_pips > 0.1 and self.payoff >= 0.5


# ---------------------------------------------------------------------------
# Micro-firehose families (Phase 5)
# Each returns a MicroCandidate or None if conditions don't match.
# ---------------------------------------------------------------------------


def _micro_invalidation(*, side: str, entry: float, m1_low: float,
                        m1_high: float, atr_m1: float, buffer_mult: float = 0.3) -> float | None:
    """Micro-structure stop: recent M1 swing +/- ATR buffer. NOT the old
    wide M15 structural level. Must produce a TECHNICALLY VALID tight stop."""
    buffer = atr_m1 * buffer_mult
    if side == "buy":
        level = min(m1_low, entry - atr_m1 * 0.5)
        return level - buffer
    elif side == "sell":
        level = max(m1_high, entry + atr_m1 * 0.5)
        return level + buffer
    return None


def micro_momentum_burst(ctx: FastMarketContext) -> MicroCandidate | None:
    """A. MICRO MOMENTUM BURST: compression → clean impulse → M15/M5 aligned."""
    if None in (ctx.m1_atr, ctx.bid, ctx.ask,
                ctx.m1_low, ctx.m1_high,
                ctx.m15_direction, ctx.m5_direction):
        return None
    # Use side-specific 30s return once direction is known.
    # First check both sides to determine direction.
    ret_30s_buy = ctx.get_return(30, "buy")
    ret_30s_sell = ctx.get_return(30, "sell")
    if ret_30s_buy is None and ret_30s_sell is None:
        return None  # required feature unavailable → SKIP
    # Determine direction from returns
    if ret_30s_buy is not None and abs(ret_30s_buy) >= abs(ret_30s_sell or 0):
        direction = "buy" if ret_30s_buy > 0 else "sell"
        m1_ret = ret_30s_buy if direction == "buy" else -abs(ret_30s_buy)
    else:
        direction = "sell" if ret_30s_sell < 0 else "buy"
        m1_ret = ret_30s_sell if direction == "sell" else abs(ret_30s_sell or 0)
    atr = ctx.m1_atr
    compression = ctx.m5_compression
    if compression is None:
        return None  # required feature unavailable → SKIP
    if abs(m1_ret) < atr * 0.3:
        return None
    if compression > 0.8:
        return None
    direction = "buy" if m1_ret > 0 else "sell"
    m15d = ctx.m15_direction or ""
    m5d = ctx.m5_direction or ""
    # BOTH M15 and M5 must align with the intended momentum direction.
    if direction == "buy" and (m15d != "up" or m5d != "up"):
        return None
    if direction == "sell" and (m15d != "down" or m5d != "down"):
        return None
    entry = ctx.ask if direction == "buy" else ctx.bid
    inv = _micro_invalidation(side=direction, entry=entry,
                              m1_low=ctx.m1_low, m1_high=ctx.m1_high, atr_m1=atr)
    pip = pip_value(symbol := ctx.symbol)
    if inv is None or abs(entry - inv) < pip * 1.5:
        return None
    stop_pips = abs(entry - inv) / pip
    target_pips = stop_pips * 1.2
    sign = 1.0 if direction == "buy" else -1.0
    tgt = entry + sign * target_pips * pip
    spread_pips = ctx.spread_pips or 0.0
    hyp = firehose_hypothesis_id(family="micro_momentum_burst", symbol=symbol,
                                 side=direction, regime=ctx.regime or "",
                                 session=ctx.session or "")
    return MicroCandidate(
        hypothesis_id=hyp, family="micro_momentum_burst", symbol=symbol,
        side=direction, entry_price=entry, invalidation=inv, target=tgt,
        max_hold_s=120, required_regime=ctx.regime or "",
        required_session=ctx.session or "",
        spread_pips=spread_pips, stop_pips=round(stop_pips, 1),
        target_pips=round(target_pips, 1), risk_usd_min_lot=0.0,
        lane=FirehoseLane.SHADOW_MICRO,
        mechanism=f"compression→impulse continuation {symbol} {m15d}",
        falsification="OOS negative expectancy after costs",
    )


def failed_breakout_fade(ctx: FastMarketContext) -> MicroCandidate | None:
    """B. FAILED BREAKOUT FADE: pierce level → fail → fade back inside."""
    if None in (ctx.m15_resistance, ctx.m15_support, ctx.m1_close,
                ctx.bid, ctx.ask, ctx.m1_atr, ctx.m1_low, ctx.m1_high):
        return None
    res, sup = ctx.m15_resistance, ctx.m15_support
    close, prev_close = ctx.m1_close, ctx.m1_prev_close
    if prev_close is None:
        return None
    atr = ctx.m1_atr
    if prev_close > res and close < res:
        direction = "sell"
        entry = ctx.bid
        inv = max(ctx.m1_high, res) + atr * 0.2
        tgt = sup if sup < entry else entry - atr * 2
    elif prev_close < sup and close > sup:
        direction = "buy"
        entry = ctx.ask
        inv = min(ctx.m1_low, sup) - atr * 0.2
        tgt = res if res > entry else entry + atr * 2
    else:
        return None
    pip = pip_value(symbol := ctx.symbol)
    stop_pips = abs(entry - inv) / pip
    target_pips = abs(entry - tgt) / pip
    if stop_pips < 1.0 or target_pips < 1.0:
        return None
    spread_pips = ctx.spread_pips or 0.0
    hyp = firehose_hypothesis_id(family="failed_breakout_fade", symbol=symbol,
                                 side=direction, regime=ctx.regime or "",
                                 session=ctx.session or "")
    return MicroCandidate(
        hypothesis_id=hyp, family="failed_breakout_fade", symbol=symbol,
        side=direction, entry_price=entry, invalidation=inv, target=tgt,
        max_hold_s=180, required_regime=ctx.regime or "",
        required_session=ctx.session or "",
        spread_pips=spread_pips, stop_pips=round(stop_pips, 1),
        target_pips=round(target_pips, 1), risk_usd_min_lot=0.0,
        lane=FirehoseLane.SHADOW_MICRO,
        mechanism=f"failed breakout trap fade {symbol}",
        book_family="failed_breakout_fade",
        falsification="fade trades show negative expectancy after costs",
    )


def fair_value_snapback(ctx: FastMarketContext) -> MicroCandidate | None:
    """C. FAIR-VALUE SNAPBACK: price reaches value edge → rejection → snapback."""
    mid = ctx.m15_range_mid
    hw = ctx.m15_range_half_width
    if None in (mid, hw, ctx.m1_close, ctx.bid, ctx.ask, ctx.m1_atr):
        return None
    if hw <= 0:
        return None
    edge_upper = mid + hw
    edge_lower = mid - hw
    close = ctx.m1_close
    atr = ctx.m1_atr
    if close > edge_upper:
        direction = "sell"
        entry = ctx.bid
        inv = close + atr * 0.4
        tgt = mid
    elif close < edge_lower:
        direction = "buy"
        entry = ctx.ask
        inv = close - atr * 0.4
        tgt = mid
    else:
        return None
    pip = pip_value(symbol := ctx.symbol)
    stop_pips = abs(entry - inv) / pip
    target_pips = abs(entry - tgt) / pip
    if stop_pips < 1.0 or target_pips < 0.8:
        return None
    spread_pips = ctx.spread_pips or 0.0
    hyp = firehose_hypothesis_id(family="fair_value_snapback", symbol=symbol,
                                 side=direction, regime="range",
                                 session=ctx.session or "")
    return MicroCandidate(
        hypothesis_id=hyp, family="fair_value_snapback", symbol=symbol,
        side=direction, entry_price=entry, invalidation=inv, target=tgt,
        max_hold_s=300, required_regime="range",
        required_session=ctx.session or "",
        spread_pips=spread_pips, stop_pips=round(stop_pips, 1),
        target_pips=round(target_pips, 1), risk_usd_min_lot=0.0,
        lane=FirehoseLane.SHADOW_MICRO,
        mechanism=f"fair-value snapback from {ctx.session or ''} range edge",
        book_family="mean_reversion_completion",
        falsification="snapback trades show negative expectancy after costs",
    )


def pip_value(symbol: str) -> float:
    """Pip size per symbol. JPY pairs have different pip conventions."""
    upper = symbol.upper()
    if "JPY" in upper:
        return 0.01
    if "XAU" in upper or "GOLD" in upper:
        return 0.1
    return 0.0001


def generate_micro_candidates(ctx: FastMarketContext) -> list[MicroCandidate]:
    """Generate candidates from ALL independent micro-firehose families.

    Each family independently evaluates the context. No array-order bias:
    all candidates are returned and the caller must evaluate economics
    for each before selecting.
    """
    candidates = []
    for fn in (micro_momentum_burst, failed_breakout_fade, fair_value_snapback):
        try:
            c = fn(ctx)
            if c is not None:
                candidates.append(c)
        except Exception:
            pass
    return candidates


# ---------------------------------------------------------------------------
# Entry economics pre-check (Phase 8)
# ---------------------------------------------------------------------------


def check_entry_economics(candidate: MicroCandidate, *,
                          max_risk_usd: float,
                          volume_min: float = 0.01,
                          contract_size: float = 100000.0,
                          tick_value: float | None = None,
                          tick_size: float | None = None,
                          commission_rt_usd: float = 0.0,
                          slippage_pips: float = 0.3,
                          measured_spread_percentile: float | None = None,
                          spread_p90: float | None = None) -> dict[str, Any]:
    """Broker-native pre-entry economics. Uses tick_value/tick_size when
    available for correct JPY/cross pricing; falls back to contract*pip."""
    rejections = []
    pip = pip_value(candidate.symbol)
    stop_dist_price = abs(candidate.entry_price - candidate.invalidation)
    if tick_value and tick_size and tick_size > 0:
        usd_per_price_unit_per_lot = float(tick_value) / float(tick_size)
    else:
        usd_per_price_unit_per_lot = contract_size
    min_lot_risk = stop_dist_price * usd_per_price_unit_per_lot * volume_min
    budget = max_risk_usd
    if min_lot_risk > budget:
        rejections.append("RISK_GRANULARITY_BLOCKED")
    total_cost_pips = candidate.spread_pips + slippage_pips + \
        (commission_rt_usd / (usd_per_price_unit_per_lot * pip * volume_min)
         if volume_min > 0 else 0)
    net_target = candidate.target_pips - total_cost_pips
    if net_target <= 0:
        rejections.append("NEGATIVE_EXPECTED_NET_AFTER_COST")
    if candidate.spread_pips > candidate.target_pips * 0.5:
        rejections.append("SPREAD_FAILURE")
    if candidate.stop_pips < 0.5:
        rejections.append("INVALID_GEOMETRY")
    if candidate.stop_pips > 20:
        rejections.append("TAIL_RISK_FAILURE")
    if measured_spread_percentile is not None and spread_p90 is not None \
            and candidate.spread_pips > spread_p90:
        rejections.append("SPREAD_ABNORMAL_PERCENTILE")

    return {
        "allowed": len(rejections) == 0,
        "rejections": rejections,
        "min_lot_risk_usd": round(min_lot_risk, 4),
        "risk_budget_usd": budget,
        "total_cost_pips": round(total_cost_pips, 2),
        "net_target_pips": round(net_target, 2),
        "payoff_net": round(net_target / max(stop_dist_price / pip, 0.1), 3),
    }


# ---------------------------------------------------------------------------
# Fast exit state machine (Phase 9)
# ---------------------------------------------------------------------------


@dataclass
class FastExitConfig:
    """Research grid parameters. These are CANDIDATES, not final values.
    The sealed walk-forward must validate which combination works."""

    mfe_arm_r: float = 0.5           # arm protection at 0.5R MFE
    giveback_frac: float = 0.40      # max 40% of peak MFE given back
    breakeven_buffer_r: float = 0.05  # lock at entry+costs+5% of R
    time_exit_s: int = 180           # scratch after 3 min without progress
    progress_frac: float = 0.25      # pnl must be >= 25% of MFE to count as progress
    min_scratch_loss_frac: float = 0.30  # scratch if losing > 30% of stop distance


class FastExitStateMachine:
    """Per-ticket state machine producing fast, explained decisions."""

    def __init__(self, cfg: FastExitConfig | None = None):
        self.cfg = cfg or FastExitConfig()

    def evaluate(
        self,
        *,
        side: str,
        entry_price: float,
        current_mark: float,
        stop_loss: float,
        target: float,
        opened_ts: float,
        now: float,
        pnl_pips: float,
        mfe_pips: float,
        mae_pips: float,
        stop_pips: float,
        pip: float,
        regime_now: str = "",
        regime_at_entry: str = "",
        remaining_ev: float | None = None,
        remaining_ev_status: str = "UNKNOWN",
    ) -> dict[str, Any]:
        R = max(stop_pips, 0.1)
        age = now - opened_ts
        giveback_pips = max(0.0, mfe_pips - pnl_pips)

        # 1. Structural target reached (within 0.2 pips)
        dist_to_target = abs(target - current_mark) / max(pip, 1e-9)
        if dist_to_target <= 0.2:
            return self._decide(ExitAction.TAKE, "target_reached",
                                f"price within {dist_to_target:.1f} pips of target")

        # 2. Regime change with loss
        if regime_now and regime_at_entry and regime_now != regime_at_entry and pnl_pips < 0:
            return self._decide(ExitAction.ABORT, "regime_change",
                                f"regime {regime_at_entry}->{regime_now}, losing")

        # 3. Time decay without progress
        if age > self.cfg.time_exit_s and not (
            mfe_pips >= self.cfg.mfe_arm_r * R
            and pnl_pips >= self.cfg.progress_frac * mfe_pips
        ):
            return self._decide(ExitAction.SCRATCH, "time_decay_no_progress",
                                f"{int(age)}s held, pnl {pnl_pips:.1f} vs mfe {mfe_pips:.1f}")

        # 4. MFE giveback (armed only after meaningful MFE)
        mfe_r = mfe_pips / R
        if mfe_r >= self.cfg.mfe_arm_r:
            max_giveback = self.cfg.giveback_frac * mfe_pips
            if giveback_pips > max_giveback:
                return self._decide(ExitAction.TAKE, "mfe_giveback_limit",
                                    f"gave back {giveback_pips:.1f} of mfe {mfe_pips:.1f} "
                                    f"(max {max_giveback:.1f})")
            # 5. Breakeven/cost-plus lock via stop adjustment
            if pnl_pips > self.cfg.breakeven_buffer_r * R:
                return self._decide(ExitAction.LOCK, "breakeven_lock_armed",
                                    f"mfe {mfe_r:.1f}R armed cost-plus lock at "
                                    f"+{self.cfg.breakeven_buffer_r * R:.1f} pips")

        # 6. Current EV exit (if estimable)
        if remaining_ev_status == "ESTIMATED" and remaining_ev is not None and remaining_ev <= 0:
            return self._decide(ExitAction.ABORT, "remaining_ev_negative",
                                f"remaining costed EV={remaining_ev:.4f} <= 0")

        # Default: HOLD with explanation
        hold_reasons = []
        if mfe_r >= self.cfg.mfe_arm_r:
            pct_given = 100.0 * giveback_pips / max(mfe_pips, 1e-9)
            hold_reasons.append(f"only {pct_given:.0f}% of mfe {mfe_pips:.1f} given back")
        else:
            hold_reasons.append(f"mfe {mfe_pips:.1f} below arm threshold; "
                                "protective stop owns downside")
        if remaining_ev_status == "ESTIMATED" and remaining_ev is not None and remaining_ev > 0:
            hold_reasons.append(f"remaining costed EV positive ({remaining_ev:.4f})")
        return self._decide(ExitAction.HOLD, "fast_hold_justified",
                            "; ".join(hold_reasons))

    def _decide(self, action: ExitAction, reason: str, why: str) -> dict[str, Any]:
        return {"action": action.value, "reason": reason, "why": why,
                "policy": reason}


# ---------------------------------------------------------------------------

def classify_firehose_mode(*, broker_round_trips: int, shadow_trades: int) -> str:
    if broker_round_trips > 0:
        return FirehoseLane.BROKER_MICRO.value
    if shadow_trades > 0:
        return FirehoseLane.SHADOW_MICRO.value
    return "RESEARCH_CANDIDATES_ONLY"
