"""Size a thesis clip from validated edge and invalidation distance.

The Intelligent Firehose previously sent a fixed ``order_quantity`` for every fire,
so a trade with a 3-pip invalidation risked a tenth of what a trade with a 30-pip
invalidation risked, and neither had anything to do with the strength of the
evidence. Risk per clip is the quantity that should be controlled; lots are the
consequence.

Sizing derives from:
  * the validated risk fraction of the promoted strategy model,
  * how much of the thesis budget is already deployed,
  * the structural invalidation distance,
  * the broker's real contract value,
  * a confidence haircut from the width of the evidence.

Weak evidence produces no position rather than a small gamble: when the computed
size rounds below the broker minimum, the trade is refused instead of being padded
up to a lot size the edge does not justify.

Deterministic, no research imports - the paper runner imports this directly.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Mapping

from aegis.intel.trade_economics import usd_per_price_unit

# Never let one clip carry the whole thesis budget regardless of configuration.
DEFAULT_MAX_CLIPS = 5


@dataclass(frozen=True)
class SizingPlan:
    allowed: bool
    reason: str
    lots: float
    risk_usd: float
    risk_budget_usd: float
    clip_budget_usd: float
    invalidation_distance: float | None
    usd_per_price_per_lot: float | None
    confidence: float

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def journal(self) -> dict[str, Any]:
        return {
            "size_ok": self.allowed,
            "size_reason": self.reason,
            "size_lots": self.lots,
            "size_risk_usd": self.risk_usd,
            "size_clip_budget_usd": self.clip_budget_usd,
            "size_confidence": self.confidence,
        }


def _reject(reason: str, **kwargs: Any) -> SizingPlan:
    base: dict[str, Any] = {
        "lots": 0.0,
        "risk_usd": 0.0,
        "risk_budget_usd": 0.0,
        "clip_budget_usd": 0.0,
        "invalidation_distance": None,
        "usd_per_price_per_lot": None,
        "confidence": 0.0,
    }
    base.update(kwargs)
    return SizingPlan(allowed=False, reason=reason, **base)


def evidence_confidence(*, analogue_n: int, min_n: int = 20, uncertainty: str = "calibrated") -> float:
    """Haircut in (0, 1] reflecting how much the evidence actually supports.

    A sample at exactly the minimum earns a materially smaller position than a deep
    one. Anything not calibrated earns nothing.
    """
    if str(uncertainty) != "calibrated":
        return 0.0
    n = int(analogue_n)
    floor = max(int(min_n), 1)
    if n < floor:
        return 0.0
    # sqrt growth, saturating at 4x the minimum sample.
    ratio = min(float(n) / float(floor), 4.0)
    return max(0.25, min(1.0, math.sqrt(ratio) / 2.0))


def _round_down_to_step(value: float, step: float) -> float:
    if step <= 0:
        return value
    steps = math.floor((value + 1e-12) / step)
    return max(0.0, steps * step)


def size_thesis_clip(
    *,
    entry: float,
    invalidation: float | None,
    spec: Mapping[str, Any] | None,
    risk_budget_usd: float,
    validated_risk_fraction: float | None,
    current_risk_usd: float = 0.0,
    max_clips: int = DEFAULT_MAX_CLIPS,
    confidence: float = 1.0,
    hard_max_lots: float | None = None,
) -> SizingPlan:
    """Lots for one clip of a thesis, or a refusal with a reason."""
    if invalidation is None:
        return _reject("no_structural_invalidation")
    try:
        distance = abs(float(entry) - float(invalidation))
    except (TypeError, ValueError):
        return _reject("bad_geometry")
    if not math.isfinite(distance) or distance <= 0:
        return _reject("no_invalidation_distance")

    if validated_risk_fraction is None:
        return _reject("no_validated_risk_fraction")
    fraction = float(validated_risk_fraction)
    if not (0.0 < fraction <= 1.0):
        return _reject("no_validated_risk_fraction")

    budget = float(risk_budget_usd) * fraction
    if not math.isfinite(budget) or budget <= 0:
        return _reject("no_risk_budget", risk_budget_usd=max(0.0, budget))

    haircut = max(0.0, min(1.0, float(confidence)))
    if haircut <= 0:
        return _reject("no_evidence_confidence", risk_budget_usd=budget, confidence=haircut)

    # Room left in the thesis before this clip.
    remaining = budget - max(0.0, float(current_risk_usd))
    if remaining <= 0:
        return _reject(
            "thesis_at_target_exposure",
            risk_budget_usd=budget,
            confidence=haircut,
            invalidation_distance=distance,
        )

    clips = max(1, int(max_clips or DEFAULT_MAX_CLIPS))
    clip_budget = min(budget / clips, remaining) * haircut
    if clip_budget <= 0:
        return _reject(
            "no_clip_budget",
            risk_budget_usd=budget,
            confidence=haircut,
            invalidation_distance=distance,
        )

    per_lot = usd_per_price_unit(spec, lots=1.0)
    if per_lot is None or per_lot <= 0:
        return _reject(
            "contract_value_unavailable",
            risk_budget_usd=budget,
            clip_budget_usd=clip_budget,
            confidence=haircut,
            invalidation_distance=distance,
        )

    loss_per_lot = distance * per_lot
    if loss_per_lot <= 0:
        return _reject(
            "no_loss_per_lot",
            risk_budget_usd=budget,
            clip_budget_usd=clip_budget,
            confidence=haircut,
            invalidation_distance=distance,
            usd_per_price_per_lot=per_lot,
        )

    def _num(key: str, default: float) -> float:
        value = (spec or {}).get(key)
        try:
            number = float(value)
        except (TypeError, ValueError):
            return default
        return number if math.isfinite(number) and number > 0 else default

    volume_min = _num("volume_min", 0.01)
    volume_step = _num("volume_step", 0.01)
    volume_max = _num("volume_max", 100.0)
    if hard_max_lots is not None and float(hard_max_lots) > 0:
        volume_max = min(volume_max, float(hard_max_lots))

    raw_lots = clip_budget / loss_per_lot
    lots = _round_down_to_step(min(raw_lots, volume_max), volume_step)

    fields = {
        "risk_budget_usd": budget,
        "clip_budget_usd": clip_budget,
        "invalidation_distance": distance,
        "usd_per_price_per_lot": per_lot,
        "confidence": haircut,
    }

    if lots + 1e-12 < volume_min:
        # Padding up to the broker minimum would risk more than the edge earns.
        return SizingPlan(
            allowed=False,
            reason="minimum_lot_exceeds_clip_budget",
            lots=0.0,
            risk_usd=0.0,
            **fields,
        )

    risk_usd = lots * loss_per_lot
    return SizingPlan(allowed=True, reason="sized_from_validated_risk", lots=lots, risk_usd=risk_usd, **fields)
