"""Andrew Aziz's relative-volume and market/sector independence check."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, normalized_status, number, values

ALGORITHM_ID = "aziz_relative_volume_independence"
SOURCES = ("Andrew Aziz — How to Day Trade for a Living",)
KEYS = (
    "aziz_asset_class",
    "aziz_relative_volume",
    "aziz_market_independence",
    "aziz_sector_independence",
    "aziz_stock_scanner_data_provenance",
)


def _observed_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return normalized_status(value) in {"true", "yes", "confirmed", "observed", "independent"}


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(
        first(state, "aziz_stock_scanner_data_provenance"),
        accepted=("observed", "measured", "historical", "timestamped"),
    ):
        missing.append("aziz_stock_scanner_data_provenance")
    missing = list(dict.fromkeys(missing))
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    asset_class = normalized_status(first(state, "aziz_asset_class"))
    if asset_class not in {"equity", "equities", "stock", "stocks"}:
        result["applicability"] = "NOT_APPLICABLE"
        result["view"] = "WAIT"
        result["aziz_independence_assessment"] = "EQUITY_ONLY"
        result["reasons"] = ["the source Stock-in-Play independence rule is defined for equities"]
        return result

    relative_volume = number(first(state, "aziz_relative_volume"))
    result["view"] = "WAIT"
    result["aziz_independence_thresholds"] = {
        "relative_volume_min": 1.5,
        "market_independence_required": True,
        "sector_independence_required": True,
    }
    if relative_volume is None:
        result["aziz_independence_assessment"] = "RELATIVE_VOLUME_INVALID"
        result["aziz_independence_failures"] = ["relative_volume_invalid"]
        result["reasons"] = ["relative volume must be a finite observed number"]
        return result

    failures = []
    if relative_volume < 1.5:
        failures.append("relative_volume_below_1_5")
    if not _observed_bool(first(state, "aziz_market_independence")):
        failures.append("market_not_independent")
    if not _observed_bool(first(state, "aziz_sector_independence")):
        failures.append("sector_not_independent")
    result["aziz_independence_failures"] = failures
    if relative_volume < 1.5:
        assessment = "RELATIVE_VOLUME_LOW"
    elif failures:
        assessment = "NOT_INDEPENDENT"
    else:
        assessment = "STOCK_IN_PLAY"
    result["aziz_independence_assessment"] = assessment
    return result
