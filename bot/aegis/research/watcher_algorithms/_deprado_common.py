"""Private statistical helpers for De Prado research diagnostics."""
from __future__ import annotations

import math
from statistics import NormalDist
from typing import Any, Mapping


def finite_series(state: Mapping[str, Any], key: str) -> list[float] | None:
    value = state.get(key)
    if not isinstance(value, (list, tuple)) or isinstance(value, (str, bytes)):
        return None
    result: list[float] = []
    for item in value:
        try:
            number = float(item)
        except (TypeError, ValueError, OverflowError):
            return None
        if not math.isfinite(number):
            return None
        result.append(number)
    return result


def moments(values: list[float]) -> tuple[float, float, float, float] | None:
    if len(values) < 3:
        return None
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    if variance <= 0:
        return None
    standard_deviation = math.sqrt(variance)
    skewness = sum((value - mean) ** 3 for value in values) / len(values) / standard_deviation**3
    kurtosis = sum((value - mean) ** 4 for value in values) / len(values) / variance**2
    return mean, standard_deviation, skewness, kurtosis


def psr(observed_sharpe: float, target_sharpe: float, sample_n: int, skewness: float, kurtosis: float) -> float | None:
    if sample_n < 3:
        return None
    correction = 1.0 - skewness * observed_sharpe + ((kurtosis - 1.0) / 4.0) * observed_sharpe**2
    if correction <= 0:
        return None
    z = (observed_sharpe - target_sharpe) * math.sqrt(sample_n - 1.0) / math.sqrt(correction)
    return NormalDist().cdf(z)


def provenance_ok(value: Any) -> bool:
    normalized = str(value or "").strip().lower().replace("-", "_")
    return bool(normalized) and not any(
        marker in normalized
        for marker in ("synthetic", "proxy", "missing", "unavailable", "unverified")
    ) and any(marker in normalized for marker in ("observed", "measured", "replay"))
