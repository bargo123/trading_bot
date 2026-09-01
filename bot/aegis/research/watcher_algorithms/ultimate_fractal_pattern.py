"""Anna Coulling's early-stage, self-repeating fractal chart study."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "ultimate_fractal_pattern"
SOURCES = ("Anna Coulling — The Ultimate Forex Trading System",)
KEYS = (
    "ultimate_fractal_shape",
    "ultimate_fractal_stage",
    "ultimate_fractal_direction",
    "ultimate_fractal_scale_count",
    "ultimate_fractal_observed",
    "ultimate_data_provenance",
)


def _truthy(value):
    return value is True or normalized_status(value) in {
        "true", "yes", "confirmed", "observed", "valid",
    }


def _direction(value):
    normalized = normalized_status(value)
    if normalized in {"up", "upward", "bull", "bullish", "buy", "long"}:
        return "BUY"
    if normalized in {"down", "downward", "bear", "bearish", "sell", "short"}:
        return "SELL"
    return None


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    provenance = normalized_status(first(state, "ultimate_data_provenance"))
    if not provenance or any(token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")):
        missing.append("ultimate_data_provenance")
    missing = list(dict.fromkeys(missing))
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    shape = normalized_status(first(state, "ultimate_fractal_shape"))
    stage = normalized_status(first(state, "ultimate_fractal_stage"))
    direction = _direction(first(state, "ultimate_fractal_direction"))
    scale_count = number(first(state, "ultimate_fractal_scale_count"))
    if not shape or not any(token in shape for token in ("fractal", "symmetric", "repeating")):
        result["view"] = "WAIT"
        result["ultimate_fractal_assessment"] = "SHAPE_NOT_IDENTIFIED"
        result["reasons"] = ["the observed shape is not identified as a self-repeating fractal"]
        return result
    if stage not in {"first", "second", "early", "early stage"}:
        result["view"] = "WAIT"
        result["ultimate_fractal_assessment"] = "EARLY_STAGE_REQUIRED"
        result["reasons"] = ["the source only treats a first or second observed fractal as an early opportunity"]
        return result
    if scale_count is None or scale_count < 2 or not _truthy(first(state, "ultimate_fractal_observed")):
        result["view"] = "WAIT"
        result["ultimate_fractal_assessment"] = "FRACTAL_OBSERVATION_INVALID"
        result["reasons"] = ["at least two observed scales and an explicit observation are required"]
        return result
    if direction is None:
        result["view"] = "WAIT"
        result["ultimate_fractal_assessment"] = "DIRECTION_UNRESOLVED"
        result["reasons"] = ["the early fractal has no explicit directional interpretation"]
        return result
    result["ultimate_fractal_assessment"] = "EARLY_STAGE_SIGNAL"
    result["ultimate_fractal_scale_count"] = int(scale_count)
    return with_direction(result, state, direction, "the observed self-repeating fractal is still in an early stage")
