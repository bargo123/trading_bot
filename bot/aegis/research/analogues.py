"""Point-in-time historical analogue index. Research builds; runtime loads via intel."""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from statistics import mean, pstdev
from typing import Any, Mapping, Sequence

import pandas as pd

from aegis.intel.expected_value import payoff_metrics
from aegis.research.market_state import build_market_state
from aegis.research.market_state_history import current_state_signature
from aegis.research.regime import classify_regime
from aegis.research.structure import structure_event
from aegis.research.dataplane import session_label


@dataclass(frozen=True)
class AnalogueRecord:
    bar_time: str
    symbol: str
    side: str
    setup: str
    regime: str
    structure: str
    volatility: str
    session: str
    h1_direction: str
    m5_direction: str
    outcome: float
    label: str = "research_proxy"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AnalogueEvidence:
    analogue_n: int
    analogue_n_losses: int
    outcomes: tuple[float, ...]
    win_probability: float | None
    avg_win: float | None
    avg_loss: float | None
    expectancy: float | None
    profit_factor: float | None
    payoff_ratio: float | None
    tail_loss: float | None
    wins_erased_by_average_loss: float | None
    mean_lower_95: float | None
    uncertainty: str
    eligible: bool
    similarity_score: float
    label: str = "research_proxy"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def signature_from_state(state: Mapping[str, Any], *, side: str, setup: str) -> dict[str, str]:
    mtf = state.get("multi_timeframe") if isinstance(state.get("multi_timeframe"), Mapping) else {}
    structure = state.get("structure") if isinstance(state.get("structure"), Mapping) else {}
    m15 = structure.get("M15") if isinstance(structure.get("M15"), Mapping) else {}
    regime = state.get("regime") if isinstance(state.get("regime"), Mapping) else {}
    vol = state.get("volatility") if isinstance(state.get("volatility"), Mapping) else {}
    return {
        "side": str(side).lower(),
        "setup": str(setup or "unknown"),
        "regime": str(regime.get("label") or "unknown"),
        "structure": str(m15.get("kind") or "none"),
        "volatility": str(vol.get("phase") or "unknown"),
        "session": str(state.get("session") or "unknown"),
        "h1_direction": str((mtf.get("H1") or {}).get("direction") or "unavailable"),
        "m5_direction": str((mtf.get("M5") or {}).get("direction") or "unavailable"),
    }


def _similarity(query: Mapping[str, str], row: Mapping[str, str]) -> float:
    keys = ("side", "regime", "structure", "volatility", "session", "h1_direction", "m5_direction")
    hits = sum(1 for key in keys if str(query.get(key)) == str(row.get(key)))
    setup_match = 1.0 if str(query.get("setup")) == str(row.get("setup")) else 0.0
    return (hits + setup_match) / (len(keys) + 1)


def _lower_bound(values: Sequence[float]) -> float | None:
    items = [float(v) for v in values]
    n = len(items)
    if n < 2:
        return None
    avg = mean(items)
    sigma = pstdev(items)
    se = sigma / math.sqrt(n)
    return avg - 1.96 * se


def query_analogues(
    records: Sequence[Mapping[str, Any]],
    *,
    signature: Mapping[str, str],
    before_time: str | pd.Timestamp,
    min_n: int = 20,
    min_similarity: float = 0.55,
) -> AnalogueEvidence:
    """Return only records strictly before the observation timestamp."""
    cutoff = pd.Timestamp(before_time)
    if cutoff.tzinfo is None:
        cutoff = cutoff.tz_localize("UTC")
    else:
        cutoff = cutoff.tz_convert("UTC")
    matched: list[tuple[float, float]] = []
    symbol = str(signature.get("symbol") or "").upper()
    for row in records:
        if symbol and str(row.get("symbol") or "").upper() != symbol:
            continue
        try:
            ts = pd.Timestamp(row["bar_time"])
            if ts.tzinfo is None:
                ts = ts.tz_localize("UTC")
            else:
                ts = ts.tz_convert("UTC")
        except (KeyError, TypeError, ValueError):
            continue
        if ts >= cutoff:
            continue
        sim = _similarity(signature, row)
        if sim < min_similarity:
            continue
        try:
            matched.append((sim, float(row["outcome"])))
        except (KeyError, TypeError, ValueError):
            continue
    if not matched:
        return AnalogueEvidence(
            0,
            0,
            (),
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            "no_observations",
            False,
            0.0,
        )
    matched.sort(key=lambda item: item[0], reverse=True)
    outcomes = tuple(value for _, value in matched)
    stats = payoff_metrics(outcomes)
    lower = _lower_bound(outcomes)
    eligible = (
        int(stats["n"]) >= min_n
        and stats.get("expectancy") is not None
        and float(stats["expectancy"]) > 0
        and lower is not None
        and lower > 0
        and not bool(stats.get("cosmetic_win_rate"))
    )
    uncertainty = (
        "insufficient_sample"
        if int(stats["n"]) < min_n
        else "mean_not_positive_with_95_confidence"
        if not eligible
        else "calibrated"
    )
    return AnalogueEvidence(
        int(stats["n"]),
        int(stats["n_losses"]),
        outcomes,
        stats.get("win_rate"),
        stats.get("avg_win"),
        stats.get("avg_loss"),
        stats.get("expectancy"),
        stats.get("profit_factor"),
        stats.get("payoff_ratio"),
        stats.get("tail_loss"),
        stats.get("wins_erased_by_average_loss"),
        lower,
        uncertainty,
        eligible,
        float(matched[0][0]),
    )


def _forward_outcome(
    m1: pd.DataFrame,
    *,
    start_idx: int,
    side: str,
    invalidation: float,
    target: float | None,
    pip: float,
    max_bars: int = 120,
) -> float | None:
    """Simulate structural exit in pips from a completed entry bar. Labels only for index build."""
    if start_idx >= len(m1) - 1:
        return None
    entry = float(m1["close"].iloc[start_idx])
    sign = 1.0 if str(side).lower() == "buy" else -1.0
    for offset in range(1, min(max_bars, len(m1) - start_idx)):
        bar = m1.iloc[start_idx + offset]
        high = float(bar["high"])
        low = float(bar["low"])
        close = float(bar["close"])
        if sign > 0:
            if low <= invalidation:
                return (invalidation - entry) / pip
            if target is not None and high >= target:
                return (target - entry) / pip
        else:
            if high >= invalidation:
                return (entry - invalidation) / pip
            if target is not None and low <= target:
                return (entry - target) / pip
        if offset == max_bars - 1:
            return sign * (close - entry) / pip
    return None


def build_analogues_from_m1(
    frames: Mapping[str, pd.DataFrame],
    *,
    pip_by_symbol: Mapping[str, float],
    min_bars: int = 400,
    step: int = 3,
) -> list[dict[str, Any]]:
    """Walk completed M1 history and label structural outcomes without leaking future into queries."""
    from aegis.research.exit_hypotheses import thesis_geometry

    rows: list[dict[str, Any]] = []
    for symbol, m1 in frames.items():
        frame = m1.copy()
        frame["time"] = pd.to_datetime(frame["time"], utc=True)
        frame = frame.sort_values("time").reset_index(drop=True)
        if len(frame) < min_bars:
            continue
        pip = float(pip_by_symbol.get(symbol, 0.0001))
        for idx in range(min_bars, len(frame) - 5, step):
            hist = frame.iloc[: idx + 1].copy()
            bar_time = hist["time"].iloc[-1]
            try:
                state = build_market_state(symbol=symbol, m1=hist)
            except ValueError:
                continue
            close = float(hist["close"].iloc[-1])
            m15 = state.structure.get("M15") or {}
            structure_kind = str(m15.get("kind") or "none")
            side = "buy" if close >= float(hist["close"].iloc[-2]) else "sell"
            if structure_kind == "breakout":
                resistance = m15.get("resistance")
                support = m15.get("support")
                if resistance is not None and close > float(resistance):
                    side = "buy"
                elif support is not None and close < float(support):
                    side = "sell"
            geometry = thesis_geometry(
                side=side,
                support=None if m15.get("support") is None else float(m15["support"]),
                resistance=None if m15.get("resistance") is None else float(m15["resistance"]),
                buffer=pip,
            )
            if geometry is None or geometry.invalidation_price is None:
                continue
            outcome = _forward_outcome(
                frame,
                start_idx=idx,
                side=side,
                invalidation=float(geometry.invalidation_price),
                target=geometry.target_price,
                pip=pip,
            )
            if outcome is None:
                continue
            sig = signature_from_state(state.as_dict(), side=side, setup=structure_kind)
            rows.append(
                AnalogueRecord(
                    bar_time=str(bar_time),
                    symbol=str(symbol).upper(),
                    side=side,
                    setup=structure_kind,
                    regime=sig["regime"],
                    structure=sig["structure"],
                    volatility=sig["volatility"],
                    session=sig["session"],
                    h1_direction=sig["h1_direction"],
                    m5_direction=sig["m5_direction"],
                    outcome=float(outcome),
                ).as_dict()
            )
    return rows


def save_analogue_index(rows: Sequence[Mapping[str, Any]], path: Path) -> dict[str, Any]:
    payload = {
        "schema": "analogue_index.v1",
        "label": "research_proxy",
        "n": len(rows),
        "records": list(rows),
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def load_analogue_index(path: Path) -> list[dict[str, Any]]:
    target = Path(path)
    if not target.is_file():
        return []
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    rows = payload.get("records") if isinstance(payload, dict) else payload
    return [row for row in rows if isinstance(row, dict)]
