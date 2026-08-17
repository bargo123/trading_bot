"""Readonly Intelligent Firehose observer. Never places orders.

Decision timestamps follow the Old Firehose convention: prepare the full
broker frame, then act on the last completed bar (`iloc[-2]`).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

import pandas as pd

from aegis.intel.expected_value import payoff_metrics
from aegis.intel.strategy_model import ValidatedStrategyModel
from aegis.intel.thesis_fire import ThesisFireDecision, evaluate_thesis_action, evaluate_thesis_fire
from aegis.portfolio_risk import portfolio_pretrade_decision
from aegis.research.exit_hypotheses import (
    thesis_geometry,
    thesis_invalidated,
    thesis_target_reached,
)
from aegis.research.knowledge import select_knowledge_for_state
from aegis.research.market_state import MarketState, MarketStateCache, build_market_state
from aegis.research.thesis import CalibratedEvidence, Thesis, target_thesis_exposure, thesis_information_id


def bars_to_frame(bars: Sequence[Any]) -> pd.DataFrame:
    rows = [
        {
            "time": pd.Timestamp(getattr(bar, "time", bar["time"] if isinstance(bar, Mapping) else None)),
            "open": float(getattr(bar, "open", bar["open"] if isinstance(bar, Mapping) else 0.0)),
            "high": float(getattr(bar, "high", bar["high"] if isinstance(bar, Mapping) else 0.0)),
            "low": float(getattr(bar, "low", bar["low"] if isinstance(bar, Mapping) else 0.0)),
            "close": float(getattr(bar, "close", bar["close"] if isinstance(bar, Mapping) else 0.0)),
            "volume": float(getattr(bar, "volume", bar["volume"] if isinstance(bar, Mapping) else 0.0) or 0.0),
        }
        for bar in bars
    ]
    return pd.DataFrame(rows)


def old_firehose_decision(row: pd.Series, cfg: Mapping[str, Any]) -> dict[str, Any]:
    """Replay CORE firehose on the same completed row. Does not send an order."""
    from aegis.strategy import signal_from_row

    sig = signal_from_row(row, dict(cfg))
    if sig is None:
        return {
            "action": "skip",
            "reason": "no_signal",
            "side": None,
            "tp": None,
            "sl": None,
            "entry": None,
        }
    return {
        "action": sig.side,
        "reason": sig.reason,
        "side": sig.side,
        "tp": None if sig.tp is None else float(sig.tp),
        "sl": float(sig.sl),
        "entry": float(sig.entry),
    }


def infer_thesis_side(state: MarketState, close: float) -> str | None:
    m15 = state.structure.get("M15") or {}
    kind = str(m15.get("kind") or "none")
    support = m15.get("support")
    resistance = m15.get("resistance")
    if kind == "breakout":
        if resistance is not None and close > float(resistance):
            return "buy"
        if support is not None and close < float(support):
            return "sell"
    if kind == "failure":
        if resistance is not None and close < float(resistance):
            return "sell"
        if support is not None and close > float(support):
            return "buy"
    if kind == "retest":
        if support is not None and (
            resistance is None or abs(close - float(support)) <= abs(close - float(resistance))
        ):
            return "buy"
        if resistance is not None:
            return "sell"
    return None


@dataclass
class ShadowThesisState:
    symbol: str
    side: str | None = None
    information_id: str | None = None
    thesis_id: str | None = None
    current_risk_usd: float = 0.0


@dataclass
class ShadowBook:
    """Virtual Intelligent Firehose book. It never maps onto MT5 tickets."""

    _by_symbol: dict[str, ShadowThesisState] = field(default_factory=dict)

    def open_states(self) -> list[ShadowThesisState]:
        return [state for state in self._by_symbol.values() if state.current_risk_usd > 0]

    def get(self, symbol: str) -> ShadowThesisState:
        key = str(symbol).upper()
        return self._by_symbol.setdefault(key, ShadowThesisState(symbol=key))

    def apply(
        self,
        symbol: str,
        action: str,
        *,
        side: str | None,
        information_id: str | None,
        thesis_id: str | None,
        target_risk_usd: float,
    ) -> ShadowThesisState:
        state = self.get(symbol)
        if action == "exit":
            state.current_risk_usd = 0.0
            state.information_id = None
            state.side = None
            state.thesis_id = None
            return state
        if action in {"fire", "scale"}:
            state.side = side
            state.information_id = information_id
            state.thesis_id = thesis_id
            state.current_risk_usd = max(0.0, float(target_risk_usd))
        elif action == "reduce":
            state.current_risk_usd = max(0.0, float(target_risk_usd))
            if state.current_risk_usd <= 0:
                state.information_id = None
                state.side = None
                state.thesis_id = None
        return state


def observe_completed_bar(
    *,
    symbol: str,
    bar_time: str,
    completed_m1: pd.DataFrame,
    close: float,
    old: Mapping[str, Any],
    knowledge_rows: Sequence[Mapping[str, Any]] = (),
    strategy: ValidatedStrategyModel | None = None,
    memory: ShadowThesisState | None = None,
    analogue_outcomes: Sequence[float] = (),
    total_risk_budget_usd: float = 0.0,
    correlated_risk_usd: float = 0.0,
    buffer: float = 0.0,
    portfolio_ok: bool = True,
    portfolio_reason: str = "",
    state: MarketState | None = None,
) -> dict[str, Any]:
    """One completed-bar comparison row. placed_orders is always false."""
    held = memory or ShadowThesisState(symbol=str(symbol).upper())
    market = state or build_market_state(
        symbol=symbol,
        m1=completed_m1,
        provenance={"cycle": "intelligent_firehose_shadow.v1"},
    )
    regime = str(market.regime.get("label") or "unknown")
    m15 = market.structure.get("M15") or {}
    structure_kind = str(m15.get("kind") or "none")
    side = infer_thesis_side(market, float(close))
    books = select_knowledge_for_state(
        knowledge_rows,
        regime=regime,
        structure_kind=structure_kind,
    )
    setup = structure_kind if structure_kind not in {"none", "unavailable"} else "unvalidated_state_scan"
    if books:
        setup = str(books[0].get("setup") or books[0].get("filename") or setup)
    geometry = None
    if side in {"buy", "sell"}:
        geometry = thesis_geometry(
            side=side,
            support=None if m15.get("support") is None else float(m15["support"]),
            resistance=None if m15.get("resistance") is None else float(m15["resistance"]),
            buffer=float(buffer),
        )
    invalidation = (
        "no completed swing for structural invalidation"
        if geometry is None
        else f"completed close beyond {geometry.invalidation_price}"
    )
    info_id = thesis_information_id(
        symbol=symbol,
        side=side or "none",
        setup=setup,
        invalidation=invalidation,
        htf_bucket=str((market.multi_timeframe.get("H1") or {}).get("time") or ""),
        session=str(market.session or ""),
    )
    payoff = payoff_metrics(analogue_outcomes)
    analogue_n = int(payoff["n"])
    analogue_n_losses = int(payoff["n_losses"])
    state_ev = payoff["expectancy"] if analogue_n else None
    eligible = analogue_n >= 20 and payoff.get("expectancy") is not None and float(payoff["expectancy"]) > 0
    uncertainty = "calibrated" if eligible else (
        "insufficient_sample" if analogue_n < 20 else "mean_not_positive_with_95_confidence"
    )
    fire = evaluate_thesis_fire(
        strategy=strategy,
        state_expected_net_value=state_ev if eligible else None,
        analogue_n=analogue_n,
        analogue_n_losses=analogue_n_losses,
        uncertainty=uncertainty,
        eligible=eligible,
        portfolio_ok=portfolio_ok,
        portfolio_reason=portfolio_reason,
    )
    if fire.action == "fire":
        if side not in {"buy", "sell"}:
            fire = ThesisFireDecision("skip", "no_structural_side", fire.expected_net_value)
        elif geometry is None:
            fire = ThesisFireDecision("skip", "no_structural_invalidation", fire.expected_net_value)

    evidence = CalibratedEvidence(
        n=analogue_n,
        expected_return=state_ev,
        mean_lower_95=state_ev if eligible else None,
        favorable_probability=payoff.get("win_rate"),
        probability_lower_95=None,
        downside_std=None,
        uncertainty=uncertainty,
        eligible=eligible,
    )
    thesis = Thesis(
        thesis_id=f"{str(symbol).upper()}_{side or 'FLAT'}_{info_id}",
        symbol=str(symbol).upper(),
        side=side or "none",
        setup=setup,
        market_state=market.as_dict(),
        supporting_evidence=(),
        contradicting_evidence=(),
        invalidation=invalidation,
        expected_duration="M15",
        calibrated_evidence=evidence,
        book_provenance=tuple(
            {"filename": row.get("filename"), "file_hash": row.get("file_hash")}
            for row in books
        ),
    )
    exposure = target_thesis_exposure(
        thesis=thesis,
        current_risk_usd=held.current_risk_usd,
        correlated_risk_usd=correlated_risk_usd,
        total_risk_budget_usd=total_risk_budget_usd,
        validated_risk_fraction=None if strategy is None else strategy.validated_risk_fraction,
    )
    invalidated = bool(
        side
        and geometry is not None
        and thesis_invalidated(
            side=side,
            close=float(close),
            invalidation_price=geometry.invalidation_price,
        )
    )
    target_hit = bool(
        side
        and geometry is not None
        and thesis_target_reached(
            side=side,
            close=float(close),
            target_price=geometry.target_price,
        )
    )
    opposite = bool(held.current_risk_usd > 0 and held.side and side and held.side != side)
    action = evaluate_thesis_action(
        fire_decision=fire,
        information_id=info_id,
        last_information_id=held.information_id,
        current_risk_usd=held.current_risk_usd,
        target_risk_usd=exposure.target_risk_usd,
        invalidated=invalidated,
        target_reached=target_hit,
        opposite_side=opposite,
    )
    return {
        "schema": "firehose_vs_firehose.v1",
        "placed_orders": False,
        "symbol": str(symbol).upper(),
        "bar_time": str(bar_time),
        "old": dict(old),
        "new": {
            "action": action.action,
            "reason": action.reason,
            "expected_net_value": action.expected_net_value,
            "side": side,
            "setup": setup,
            "information_id": info_id,
            "thesis_id": thesis.thesis_id,
            "current_risk_usd": held.current_risk_usd,
            "target_risk_usd": exposure.target_risk_usd,
            "invalidation_price": None if geometry is None else geometry.invalidation_price,
            "target_price": None if geometry is None else geometry.target_price,
            "regime": regime,
            "structure": structure_kind,
            "book_hashes": [row.get("file_hash") for row in books],
            "inherited_strategy": None if strategy is None else strategy.strategy_id,
        },
    }


def scan_symbol(
    *,
    engine: Any,
    symbol: str,
    cfg: Mapping[str, Any],
    last_bar_time: pd.Timestamp | None,
    knowledge_rows: Sequence[Mapping[str, Any]],
    strategy: ValidatedStrategyModel | None,
    book: ShadowBook,
    cache: MarketStateCache,
    analogue_outcomes: Sequence[float] = (),
    total_risk_budget_usd: float = 0.0,
) -> dict[str, Any] | None:
    """Fetch the same timeframe bars as Old Firehose and compare one new completed bar."""
    timeframe = str(cfg.get("timeframe") or "1m")
    lookback = int(cfg.get("lookback_days", 1) or 1)
    bars = engine.bars(symbol, timeframe, lookback)
    if len(bars) < 50:
        return None
    raw = bars_to_frame(bars)
    from aegis.config import pip_size_for
    from aegis.strategy import prepare

    loop_cfg = dict(cfg)
    pip = pip_size_for(symbol, loop_cfg)
    loop_cfg["firehose_pip_size"] = pip
    loop_cfg["volman_pip_size"] = pip
    if hasattr(engine, "quote"):
        try:
            quote = engine.quote(symbol)
            spread = max(0.0, float(quote.ask) - float(quote.bid))
            mid = (float(quote.bid) + float(quote.ask)) / 2.0 if quote.bid and quote.ask else 0.0
            live_bps = (spread / mid * 10000.0) if mid > 0 else 0.0
            loop_cfg["spread_bps"] = max(live_bps, float(cfg.get("spread_bps_floor", 0.2) or 0.0))
        except Exception:
            pass
    frame = prepare(raw, loop_cfg)
    if len(frame) < 3:
        return None
    row = frame.iloc[-2]
    bar_time = pd.Timestamp(row["time"])
    if last_bar_time is not None and bar_time <= last_bar_time:
        return None
    completed = raw.iloc[:-1].copy() if len(raw) >= 2 else raw
    state, _changed = cache.update(
        symbol=symbol,
        m1=completed,
        provenance={"cycle": "intelligent_firehose_shadow.v1", "bar_time": str(bar_time)},
    )
    old = old_firehose_decision(row, loop_cfg)
    memory = book.get(symbol)
    portfolio_ok, portfolio_reason = True, ""
    side_guess = infer_thesis_side(state, float(row["close"]))
    if side_guess in {"buy", "sell"}:
        from aegis.engines import PositionSnapshot

        virtual = []
        for held in book.open_states():
            if held.side in {"buy", "sell"}:
                virtual.append(
                    PositionSnapshot(
                        symbol=held.symbol,
                        side=held.side,
                        quantity=0.01,
                        avg_price=float(row["close"]),
                    )
                )
        portfolio_ok, portfolio_reason, _event = portfolio_pretrade_decision(
            positions=virtual,
            symbol=str(symbol).upper(),
            side=side_guess,
            quantity=0.01,
            avg_price=float(row["close"]),
            cfg={
                "max_positions": int(cfg.get("max_positions", 40) or 40),
                "max_currency_direction_positions": int(
                    cfg.get("max_currency_direction_positions", 0) or 0
                ),
                "max_per_symbol": 1,
            },
        )
    observed = observe_completed_bar(
        symbol=symbol,
        bar_time=str(bar_time),
        completed_m1=completed,
        close=float(row["close"]),
        old=old,
        knowledge_rows=knowledge_rows,
        strategy=strategy,
        memory=memory,
        analogue_outcomes=analogue_outcomes,
        total_risk_budget_usd=total_risk_budget_usd,
        buffer=pip,
        portfolio_ok=portfolio_ok,
        portfolio_reason=portfolio_reason,
        state=state,
    )
    new = observed["new"]
    book.apply(
        symbol,
        new["action"],
        side=new.get("side"),
        information_id=new.get("information_id"),
        thesis_id=new.get("thesis_id"),
        target_risk_usd=float(new.get("target_risk_usd") or 0.0),
    )
    observed["bar_time"] = str(bar_time)
    return observed
