"""Evidence-derived capture authorization for the executable Firehose lane.

The required capture probability belongs to the candidate's actual executable
payoff/cost geometry.  This module deliberately has no universal probability
floor: a candidate is authorized only when measured, point-in-time evidence has
enough support for its own breakeven probability.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any

from aegis.intel.analogue_store import is_executable_capture_provenance
from aegis.intel.trade_economics import wilson_lower_bound


@dataclass(frozen=True)
class CaptureAuthorization:
    authorized: bool
    reason: str
    probability: float | None
    lower_95: float | None
    required_probability: float | None
    observations: int
    successes: int
    evidence_source: str
    provenance: str
    distance_to_pass: float | None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def authorize_capture_probability(
    *,
    successes: int,
    observations: int,
    breakeven_probability: float | None,
    evidence_source: str,
    provenance: str,
    min_observations: int = 20,
) -> CaptureAuthorization:
    """Authorize a candidate using its measured capture evidence.

    ``breakeven_probability`` must come from the candidate's executable
    geometry, including spread, slippage, commission and the chosen exit
    policy.  The Wilson lower bound is compared with that value; the point
    estimate alone can never authorize a thin sample.
    """
    n = int(observations) if isinstance(observations, int) else -1
    wins = int(successes) if isinstance(successes, int) else -1
    source = str(evidence_source or "unknown")
    origin = str(provenance or "unknown")
    required = None
    if breakeven_probability is not None:
        try:
            required = float(breakeven_probability)
        except (TypeError, ValueError, OverflowError):
            required = None
    if required is None or not math.isfinite(required) or not 0.0 <= required < 1.0:
        return CaptureAuthorization(
            False, "capture_breakeven_unavailable", None, None, None,
            max(n, 0), max(wins, 0), source, origin, None,
        )
    if n <= 0 or wins < 0 or wins > n:
        return CaptureAuthorization(
            False, "capture_evidence_invalid", None, None, required,
            max(n, 0), max(wins, 0), source, origin, None,
        )
    probability = wins / n
    lower = wilson_lower_bound(wins=wins, n=n)
    distance = None if lower is None else max(0.0, required - lower)
    if not is_executable_capture_provenance(origin):
        return CaptureAuthorization(
            False, "capture_evidence_not_measured", probability, lower, required,
            n, wins, source, origin, distance,
        )
    if n < max(int(min_observations), 1):
        return CaptureAuthorization(
            False, "capture_evidence_insufficient", probability, lower, required,
            n, wins, source, origin, distance,
        )
    if lower is None or lower + 1e-12 < required:
        return CaptureAuthorization(
            False, "capture_probability_lcb_below_breakeven", probability, lower,
            required, n, wins, source, origin, distance,
        )
    return CaptureAuthorization(
        True, "capture_probability_authorized", probability, lower, required,
        n, wins, source, origin, 0.0,
    )
