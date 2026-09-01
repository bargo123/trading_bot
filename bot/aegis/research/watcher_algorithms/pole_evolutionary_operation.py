"""Andrew Pole evolutionary-operation calibration-drift perspective."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, number, values
from ._deprado_common import finite_series, provenance_ok

ALGORITHM_ID = "pole_evolutionary_operation"
SOURCES = ("Andrew Pole — Statistical Arbitrage",)
KEYS = (
    "pole_current_calibration_edge",
    "pole_neighbor_calibration_edges",
    "pole_observed_persistence_periods",
    "pole_required_persistence_periods",
    "pole_evolution_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    current = number(first(state, "pole_current_calibration_edge"))
    neighbors = finite_series(state, "pole_neighbor_calibration_edges")
    observed_periods = number(first(state, "pole_observed_persistence_periods"))
    required_periods = number(first(state, "pole_required_persistence_periods"))
    missing = []
    if current is None:
        missing.append("pole_current_calibration_edge")
    if neighbors is None or not neighbors:
        missing.append("pole_neighbor_calibration_edges")
    if observed_periods is None:
        missing.append("pole_observed_persistence_periods")
    if required_periods is None:
        missing.append("pole_required_persistence_periods")
    provenance = first(state, "pole_evolution_data_provenance")
    if not explicitly_observed(provenance, accepted=("observed", "measured", "replay")) or not provenance_ok(provenance):
        missing.append("pole_evolution_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    result["directional_claim"] = False
    if observed_periods < 0 or required_periods <= 0 or int(observed_periods) != observed_periods or int(required_periods) != required_periods:
        result["pole_evolution_action"] = "INVALID_PERSISTENCE_INPUT"
        result["reasons"] = ["persistence periods must be non-negative and positive integers"]
        return result
    best_neighbor = max(neighbors)
    delta = best_neighbor - current
    result["analysis_stage"] = "causal_calibration_monitoring"
    result["pole_best_neighbor_edge"] = best_neighbor
    result["pole_best_neighbor_delta"] = delta
    result["pole_observed_persistence_periods"] = int(observed_periods)
    result["pole_required_persistence_periods"] = int(required_periods)
    if delta > 0 and observed_periods >= required_periods:
        result["pole_evolution_action"] = "REVIEW_CALIBRATION_SHIFT"
        result["reasons"] = ["a neighboring calibration has outperformed persistently beyond the noise-review horizon"]
    elif delta > 0:
        result["pole_evolution_action"] = "MONITOR_LOCAL_NOISE"
        result["reasons"] = ["a neighboring calibration leads, but the lead has not persisted long enough to adapt"]
    else:
        result["pole_evolution_action"] = "CURRENT_CALIBRATION_STABLE"
        result["reasons"] = ["no neighboring calibration currently has a positive observed edge over the current model"]
    result["warnings"] = ["evolutionary operation monitors nearby calibrations; it does not authorize automatic live parameter changes"]
    return result
