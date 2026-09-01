"""Andrew Aziz's equity-only premarket Stock-in-Play scanner."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, explicitly_observed, values

ALGORITHM_ID = "aziz_premarket_gapper_scanner"
SOURCES = ("Andrew Aziz — How to Day Trade for a Living",)
KEYS = (
    "aziz_asset_class",
    "aziz_gap_percent",
    "aziz_premarket_volume",
    "aziz_average_daily_volume",
    "aziz_atr_usd",
    "aziz_fundamental_catalyst",
    "aziz_short_interest_percent",
    "aziz_stock_scanner_data_provenance",
)


def _catalyst_present(value) -> bool:
    if value is True:
        return True
    status = normalized_status(value)
    return bool(status) and status not in {
        "false",
        "no",
        "none",
        "unknown",
        "unavailable",
        "not present",
        "not observed",
    }


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
        result["aziz_premarket_scanner_assessment"] = "EQUITY_ONLY"
        result["reasons"] = ["the source premarket scanner is defined for equities, not this asset class"]
        return result

    gap = number(first(state, "aziz_gap_percent"))
    premarket_volume = number(first(state, "aziz_premarket_volume"))
    average_volume = number(first(state, "aziz_average_daily_volume"))
    atr = number(first(state, "aziz_atr_usd"))
    short_interest = number(first(state, "aziz_short_interest_percent"))
    result["view"] = "WAIT"
    result["aziz_premarket_gap_direction"] = "UP" if gap is not None and gap > 0 else "DOWN" if gap is not None and gap < 0 else None
    result["aziz_premarket_scanner_thresholds"] = {
        "absolute_gap_percent_min": 2.0,
        "premarket_volume_min": 50_000,
        "average_daily_volume_min": 500_000,
        "atr_usd_min": 0.50,
        "short_interest_percent_max": 30.0,
    }
    if any(value is None for value in (gap, premarket_volume, average_volume, atr, short_interest)):
        result["aziz_premarket_scanner_assessment"] = "SCANNER_INPUT_INVALID"
        result["reasons"] = ["all premarket scanner measurements must be finite numbers"]
        return result

    failures = []
    if abs(gap) < 2.0:
        failures.append("gap_below_two_percent")
    if premarket_volume < 50_000:
        failures.append("premarket_volume_below_50000")
    if average_volume < 500_000:
        failures.append("average_volume_below_500000")
    if atr < 0.50:
        failures.append("atr_below_fifty_cents")
    if not _catalyst_present(first(state, "aziz_fundamental_catalyst")):
        failures.append("fundamental_catalyst_missing")
    if short_interest < 0:
        failures.append("short_interest_invalid")
    elif short_interest > 30.0:
        failures.append("short_interest_above_thirty_percent")

    result["aziz_premarket_scanner_failures"] = failures
    result["aziz_premarket_scanner_assessment"] = "STOCK_IN_PLAY" if not failures else "SCANNER_FILTER_FAILED"
    return result
