"""López de Prado average uniqueness diagnostic."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, values

ALGORITHM_ID = "deprado_sample_uniqueness"
SOURCES = ("Marcos López de Prado — Advances in Financial Machine Learning",)
KEYS = ("deprado_concurrency_counts", "deprado_uniqueness_data_provenance")


def evaluate(state):
    counts = first(state, "deprado_concurrency_counts")
    found = values(state, *KEYS)
    missing = []
    if not isinstance(counts, (list, tuple)) or not counts:
        missing.append("deprado_concurrency_counts")
    if not explicitly_observed(
        first(state, "deprado_uniqueness_data_provenance"),
        accepted=("observed", "measured", "replay"),
    ):
        missing.append("deprado_uniqueness_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    try:
        numeric_counts = [float(value) for value in counts]
    except (TypeError, ValueError, OverflowError):
        numeric_counts = []
    if not numeric_counts or any(value < 1 or not value.is_integer() for value in numeric_counts):
        result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="MISSING_DATA")
        result["reasons"] = ["concurrency counts must be positive integers"]
        return result

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    result["deprado_average_uniqueness"] = sum(1.0 / value for value in numeric_counts) / len(numeric_counts)
    result["deprado_uniqueness_sample_n"] = len(numeric_counts)
    result["deprado_uniqueness_assessment"] = "UNIQUENESS_MEASURED"
    result["warnings"] = ["sample uniqueness is a validation weight, not a trade direction"]
    return result
