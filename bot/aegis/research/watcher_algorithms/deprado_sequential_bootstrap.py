"""López de Prado sequential-bootstrap next-draw probabilities."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, values

ALGORITHM_ID = "deprado_sequential_bootstrap"
SOURCES = ("Marcos López de Prado — Advances in Financial Machine Learning",)
KEYS = (
    "deprado_indicator_matrix",
    "deprado_selected_indices",
    "deprado_sequential_bootstrap_data_provenance",
)


def evaluate(state):
    matrix = first(state, "deprado_indicator_matrix")
    selected = first(state, "deprado_selected_indices")
    found = values(state, *KEYS)
    missing = []
    if not isinstance(matrix, (list, tuple)) or not matrix:
        missing.append("deprado_indicator_matrix")
    if not isinstance(selected, (list, tuple)):
        missing.append("deprado_selected_indices")
    if not explicitly_observed(
        first(state, "deprado_sequential_bootstrap_data_provenance"),
        accepted=("observed", "measured", "replay"),
    ):
        missing.append("deprado_sequential_bootstrap_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    try:
        rows = [[float(value) for value in row] for row in matrix]
        width = len(rows[0])
        selected_indices = [int(value) for value in selected]
    except (TypeError, ValueError, OverflowError, IndexError):
        rows, width, selected_indices = [], 0, []
    if not rows or width < 1 or any(len(row) != width for row in rows) or any(
        value not in {0.0, 1.0} for row in rows for value in row
    ):
        result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="MISSING_DATA")
        result["reasons"] = ["indicator matrix must be rectangular and binary"]
        return result
    if any(index < 0 or index >= width for index in selected_indices):
        result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="MISSING_DATA")
        result["reasons"] = ["selected bootstrap indices must reference matrix columns"]
        return result

    scores: list[float] = []
    for candidate in range(width):
        active_rows = [row for row in rows if row[candidate] == 1.0]
        if not active_rows:
            scores.append(0.0)
            continue
        uniqueness = []
        for row in active_rows:
            concurrency = sum(row[index] for index in selected_indices) + 1.0
            uniqueness.append(1.0 / concurrency)
        scores.append(sum(uniqueness) / len(uniqueness))
    total = sum(scores)
    if total <= 0:
        result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="MISSING_DATA")
        result["reasons"] = ["indicator matrix contains no observable candidate lifespan"]
        return result

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    result["directional_claim"] = False
    result["deprado_next_draw_probabilities"] = [score / total for score in scores]
    result["deprado_selected_indices"] = selected_indices
    result["deprado_sequential_bootstrap_assessment"] = "UNIQUENESS_WEIGHTED_DRAW"
    result["warnings"] = ["probabilities describe the next validation resample, not market direction"]
    return result
