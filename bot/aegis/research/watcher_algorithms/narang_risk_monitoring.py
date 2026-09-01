"""Narang's exposure, P&L, execution, and system monitoring perspective (ch. 10)."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, normalized_status, number, values


ALGORITHM_ID = "narang_risk_monitoring"
SOURCES = ("Rishi K. Narang — Inside the Black Box",)
KEYS = (
    "narang_exposure_observed",
    "narang_exposure_limit",
    "narang_pnl_observed",
    "narang_pnl_expected",
    "narang_pnl_deviation_limit",
    "narang_execution_latency_ms",
    "narang_execution_latency_limit_ms",
    "narang_system_health",
    "narang_risk_monitor_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    provenance = first(state, "narang_risk_monitor_data_provenance")
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(provenance, accepted=("observed", "measured", "historical", "runtime")):
        missing.append("narang_risk_monitor_data_provenance")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    exposure = number(first(state, "narang_exposure_observed"))
    exposure_limit = number(first(state, "narang_exposure_limit"))
    pnl = number(first(state, "narang_pnl_observed"))
    expected_pnl = number(first(state, "narang_pnl_expected"))
    pnl_limit = number(first(state, "narang_pnl_deviation_limit"))
    latency = number(first(state, "narang_execution_latency_ms"))
    latency_limit = number(first(state, "narang_execution_latency_limit_ms"))
    health = normalized_status(first(state, "narang_system_health"))
    if (
        any(value is None for value in (exposure, exposure_limit, pnl, expected_pnl, pnl_limit, latency, latency_limit))
        or exposure < 0.0
        or exposure_limit <= 0.0
        or pnl_limit < 0.0
        or latency < 0.0
        or latency_limit <= 0.0
        or not health
    ):
        result["narang_risk_monitor_assessment"] = "MONITOR_INVALID_INPUT"
        result["reasons"] = ["monitor observations and explicit limits must be finite and valid"]
        return result

    checks = {
        "exposure": "CLEAR" if exposure <= exposure_limit else "ALERT",
        "pnl": "CLEAR" if abs(pnl - expected_pnl) <= pnl_limit else "ALERT",
        "execution": "CLEAR" if latency <= latency_limit else "ALERT",
        "system": "CLEAR" if health in {"healthy", "ok", "nominal", "clear"} else "ALERT",
    }
    result["narang_monitor_checks"] = checks
    result["narang_monitor_alerts"] = [name for name, status in checks.items() if status == "ALERT"]
    result["directional_claim"] = False
    if result["narang_monitor_alerts"]:
        result["narang_risk_monitor_assessment"] = "MONITOR_ALERT"
        result["reasons"] = ["one or more observed risk/system monitors exceeded their explicit limits"]
    else:
        result["narang_risk_monitor_assessment"] = "MONITOR_CLEAR"
        result["reasons"] = ["exposure, P&L, execution latency, and system health are within observed limits"]
    return result
