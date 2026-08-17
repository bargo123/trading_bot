"""Thesis invalidation and exit hypotheses. Research-only; 1/30 remains a benchmark."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class ExitHypothesis:
    invalidation_kind: str
    invalidation_detail: str
    invalidation_price: float | None
    target_kind: str
    target_detail: str
    target_price: float | None
    label: str = "research_proxy"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def structural_exit_hypothesis(
    *,
    side: str,
    swing_level: float,
    buffer: float,
    structure_target: float | None,
) -> ExitHypothesis:
    """Stop answers 'the thesis is wrong'; target answers 'what we can realistically capture'."""
    if str(side).lower() not in {"buy", "sell"}:
        raise ValueError("side must be buy or sell")
    if buffer < 0:
        raise ValueError("buffer must be non-negative")
    buy = str(side).lower() == "buy"
    invalidation_price = float(swing_level) - float(buffer) if buy else float(swing_level) + float(buffer)
    return ExitHypothesis(
        invalidation_kind="structural_swing",
        invalidation_detail=(
            "completed close beyond the confirmed swing plus buffer"
        ),
        invalidation_price=invalidation_price,
        target_kind="structure_target" if structure_target is not None else "unspecified",
        target_detail=(
            "prior opposing swing / range boundary"
            if structure_target is not None
            else "no structural target supplied"
        ),
        target_price=None if structure_target is None else float(structure_target),
    )


def thesis_invalidated(*, side: str, close: float, invalidation_price: float | None) -> bool:
    if invalidation_price is None:
        return False
    if str(side).lower() == "buy":
        return float(close) < float(invalidation_price)
    if str(side).lower() == "sell":
        return float(close) > float(invalidation_price)
    return False


def thesis_target_reached(*, side: str, close: float, target_price: float | None) -> bool:
    if target_price is None:
        return False
    if str(side).lower() == "buy":
        return float(close) >= float(target_price)
    if str(side).lower() == "sell":
        return float(close) <= float(target_price)
    return False


def thesis_geometry(
    *,
    side: str,
    support: float | None,
    resistance: float | None,
    buffer: float,
) -> ExitHypothesis | None:
    """Require a completed swing. Do not invent a pip stop when structure is missing."""
    buy = str(side).lower() == "buy"
    swing = support if buy else resistance
    target = resistance if buy else support
    if swing is None:
        return None
    return structural_exit_hypothesis(
        side=side,
        swing_level=float(swing),
        buffer=float(buffer),
        structure_target=None if target is None else float(target),
    )
