"""Kathy Lien's London-open stop-hunt and real-deal continuation checklist."""
from __future__ import annotations

import re

from ._common import absent, base, first, normalized_status, number, side, values, with_direction

ALGORITHM_ID = "lien_wait_for_real_deal"
SOURCES = ("Kathy Lien — Day Trading and Swing Trading the Currency Market",)
KEYS = (
    "symbol",
    "lien_session",
    "lien_open_range_width_pips",
    "lien_early_excursion",
    "lien_opposite_range_penetrated",
    "lien_noise_settled",
    "lien_entry_offset_pips",
    "lien_stop_pips",
    "lien_data_provenance",
)


def _provenance_ok(value) -> bool:
    provenance = normalized_status(value)
    return bool(provenance) and not any(
        token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")
    )


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    if not _provenance_ok(first(state, "lien_data_provenance")):
        missing.append("lien_data_provenance")
    missing = list(dict.fromkeys(missing))
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    symbol = re.sub(r"[^a-z]", "", normalized_status(first(state, "symbol")))
    session = normalized_status(first(state, "lien_session"))
    if not symbol.startswith("gbpusd"):
        result["reasons"] = ["the published real-deal example is specific to GBP/USD"]
        return result
    if "london" not in session or "open" not in session:
        result["reasons"] = ["the setup requires the Frankfurt/London opening range"]
        return result
    width = number(first(state, "lien_open_range_width_pips"))
    entry_offset = number(first(state, "lien_entry_offset_pips"))
    stop_pips = number(first(state, "lien_stop_pips"))
    if width is None or width < 25:
        result["reasons"] = ["the early opening-range excursion is less than 25 pips"]
        return result
    if first(state, "lien_opposite_range_penetrated") is not True:
        result["reasons"] = ["the early move has not penetrated the opposite side of the range"]
        return result
    if first(state, "lien_noise_settled") is not True:
        result["reasons"] = ["the post-stop-hunt price action has not settled"]
        return result
    if entry_offset is None or entry_offset < 10 or stop_pips is None or not 0 < stop_pips <= 20:
        result["reasons"] = ["the entry offset and protective stop do not match the source geometry"]
        return result
    candidate_side = side(state)
    excursion = normalized_status(first(state, "lien_early_excursion"))
    signal = "BUY" if excursion == "below range" else "SELL" if excursion == "above range" else None
    if signal is None:
        result["reasons"] = ["the early excursion side is not an observed range stop-hunt"]
        return result
    result["lien_open_range_width_pips"] = width
    return with_direction(result, state, signal, "London opening stop-hunt reversed after the range was cleared")
