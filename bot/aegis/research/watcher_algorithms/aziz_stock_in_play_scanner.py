"""Andrew Aziz's equity-only Stock-in-Play scanner."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values

ALGORITHM_ID = "aziz_stock_in_play_scanner"
SOURCES = ("Andrew Aziz — How to Day Trade for a Living",)
KEYS = (
    "aziz_asset_class",
    "aziz_gap_usd",
    "aziz_atr_usd",
    "aziz_relative_volume",
    "aziz_average_daily_volume",
    "aziz_stock_scanner_data_provenance",
)


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    provenance = normalized_status(first(state, "aziz_stock_scanner_data_provenance"))
    if not provenance or any(token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")):
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
        result["aziz_stock_scanner_assessment"] = "EQUITY_ONLY"
        result["reasons"] = ["the source scanner is defined for US equities, not this asset class"]
        return result
    gap = number(first(state, "aziz_gap_usd"))
    atr = number(first(state, "aziz_atr_usd"))
    relative_volume = number(first(state, "aziz_relative_volume"))
    average_volume = number(first(state, "aziz_average_daily_volume"))
    if any(value is None for value in (gap, atr, relative_volume, average_volume)):
        result["view"] = "WAIT"
        result["aziz_stock_scanner_assessment"] = "SCANNER_INPUT_INVALID"
        result["reasons"] = ["all four scanner measurements must be finite numbers"]
        return result
    failures = []
    if gap < 1.0:
        failures.append("gap_below_one_dollar")
    if atr <= 0.50:
        failures.append("atr_not_above_fifty_cents")
    if relative_volume < 1.5:
        failures.append("relative_volume_below_1_5")
    if average_volume < 500000:
        failures.append("average_volume_below_500000")
    result["aziz_stock_scanner_assessment"] = "STOCK_IN_PLAY" if not failures else "SCANNER_FILTER_FAILED"
    result["aziz_stock_scanner_failures"] = failures
    result["view"] = "WAIT"
    result["aziz_stock_scanner_thresholds"] = {
        "gap_usd_min": 1.0,
        "atr_usd_min_exclusive": 0.50,
        "relative_volume_min": 1.5,
        "average_daily_volume_min": 500000,
    }
    return result
