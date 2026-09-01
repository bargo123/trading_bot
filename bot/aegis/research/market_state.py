"""Research-only, point-in-time market context for thesis evaluation.

This module intentionally has no broker imports and does not place orders.  A
MarketState describes what was observable at a completed-bar decision point; it
does not assert that any feature is predictive.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping

import pandas as pd

from aegis.research.dataplane import TF_MINUTES, session_label
from aegis.research.mtf import mtf_state, require_htf
from aegis.research.regime import classify_regime
from aegis.research.structure import structure_event
from aegis.state_semantics import direction as _direction
from aegis.state_semantics import volatility as _volatility


@dataclass(frozen=True)
class MarketState:
    schema: str
    symbol: str
    observed_at: str
    regime: Mapping[str, Any]
    structure: Mapping[str, Mapping[str, Any]]
    multi_timeframe: Mapping[str, Mapping[str, Any]]
    volatility: Mapping[str, Any]
    execution: Mapping[str, Any]
    portfolio: Mapping[str, Any]
    provenance: Mapping[str, Any]
    costs: Mapping[str, Any] = field(default_factory=dict)
    session: str | None = None
    htf_ready: bool = False
    lookahead: bool = False
    label: str = "research_proxy"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_market_state(
    *,
    symbol: str,
    m1: pd.DataFrame,
    execution: Mapping[str, Any] | None = None,
    portfolio: Mapping[str, Any] | None = None,
    costs: Mapping[str, Any] | None = None,
    provenance: Mapping[str, Any] | None = None,
    require_tfs: tuple[str, ...] = ("M5", "H1"),
) -> MarketState:
    """Build a serializable state from genuine completed M1→D1 resamples."""
    required = {"time", "open", "high", "low", "close", "volume"}
    missing = sorted(required - set(m1.columns))
    if missing:
        raise ValueError(f"market state missing OHLCV columns: {missing}")
    source = m1.copy()
    source["time"] = pd.to_datetime(source["time"], utc=True)
    source = source.sort_values("time").reset_index(drop=True)
    if source.empty:
        raise ValueError("market state needs at least one completed M1 bar")

    mtf_raw = mtf_state(source)
    frames = mtf_raw.get("frames") or {}
    mtf: dict[str, dict[str, Any]] = {}
    structures: dict[str, dict[str, Any]] = {}
    for tf in TF_MINUTES:
        frame = frames.get(tf)
        empty = frame is None or getattr(frame, "empty", True)
        mtf[tf] = {
            "complete": bool(not empty),
            "bars": 0 if empty else int(len(frame)),
            "time": None if empty else str(frame["time"].iloc[-1]),
            "direction": "unavailable" if empty else _direction(frame),
        }
        structures[tf] = (
            structure_event(frame)
            if not empty and len(frame) >= 3
            else {
                "kind": "unavailable",
                "lookahead": False,
                "support": None,
                "resistance": None,
                "n_pivots": 0,
                "label": "research_proxy",
            }
        )
    observed = str(source["time"].iloc[-1])
    return MarketState(
        schema="market_state.v1",
        symbol=str(symbol),
        observed_at=observed,
        regime=classify_regime(source),
        structure=structures,
        multi_timeframe=mtf,
        volatility=_volatility(source),
        execution=dict(execution or {}),
        portfolio=dict(portfolio or {}),
        provenance={
            "data_source": "completed_ohlcv",
            "timeframes": list(TF_MINUTES),
            "mtf_schema": mtf_raw.get("schema"),
            **dict(provenance or {}),
        },
        costs=dict(costs or {}),
        session=session_label(source["time"].iloc[-1]),
        htf_ready=require_htf(mtf_raw, *require_tfs),
        lookahead=False,
    )


class MarketStateCache:
    """Skip rebuilds when the completed M1 fingerprint is unchanged."""

    def __init__(self) -> None:
        self._states: dict[str, MarketState] = {}
        self._fingerprints: dict[str, tuple[str, int]] = {}

    @staticmethod
    def fingerprint(m1: pd.DataFrame) -> tuple[str, int]:
        if m1.empty:
            raise ValueError("market state cache needs at least one completed M1 bar")
        last = pd.to_datetime(m1["time"].iloc[-1], utc=True)
        return str(last), int(len(m1))

    def update(
        self,
        *,
        symbol: str,
        m1: pd.DataFrame,
        **kwargs: Any,
    ) -> tuple[MarketState, bool]:
        """Return (state, changed). Unchanged fingerprints reuse the cached object."""
        fp = self.fingerprint(m1)
        if self._fingerprints.get(symbol) == fp:
            return self._states[symbol], False
        state = build_market_state(symbol=symbol, m1=m1, **kwargs)
        self._states[symbol] = state
        self._fingerprints[symbol] = fp
        return state, True


def build_market_state_from_ticks(
    *,
    symbol: str,
    ticks: pd.DataFrame,
    broker_tz: str,
    timezone_assumption: str,
    tf: str = "M1",
    **kwargs: Any,
) -> MarketState:
    """Fail closed unless timezone is explicit; never invent L2."""
    from aegis.research.bars import bars_from_ticks

    m1 = bars_from_ticks(
        ticks, tf=tf, broker_tz=broker_tz, timezone_assumption=timezone_assumption
    )
    provenance = dict(kwargs.pop("provenance", {}) or {})
    provenance.setdefault("bar_schema", "bars.v1")
    provenance.setdefault("timezone_assumption", timezone_assumption)
    return build_market_state(symbol=symbol, m1=m1, provenance=provenance, **kwargs)
