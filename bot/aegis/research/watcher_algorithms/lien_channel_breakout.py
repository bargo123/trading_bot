"""Kathy Lien's narrow-channel breakout checklist."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, side, values, with_direction

ALGORITHM_ID = "lien_channel_breakout"
SOURCES = ("Kathy Lien — Day Trading and Swing Trading the Currency Market",)
KEYS = (
    "lien_channel_narrow",
    "lien_channel_width_pips",
    "lien_channel_break_direction",
    "lien_channel_break_confirmed",
    "lien_stop_distance_pips",
    "lien_target_range_multiple",
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
    if first(state, "lien_channel_narrow") is not True:
        result["reasons"] = ["price is not contained in an observed narrow channel"]
        return result
    width = number(first(state, "lien_channel_width_pips"))
    stop_distance = number(first(state, "lien_stop_distance_pips"))
    target_multiple = number(first(state, "lien_target_range_multiple"))
    if width is None or width <= 0 or stop_distance is None or stop_distance <= 0:
        result["reasons"] = ["channel width and stop placement must be positive observations"]
        return result
    if target_multiple is None or target_multiple < 2:
        result["reasons"] = ["the channel plan targets at least double the channel range"]
        return result
    if first(state, "lien_channel_break_confirmed") is not True:
        result["reasons"] = ["the channel-line break is not confirmed"]
        return result
    signal = normalized_status(first(state, "lien_channel_break_direction")).upper()
    if signal not in {"BUY", "SELL"}:
        result["reasons"] = ["channel break direction is not observed"]
        return result
    result["lien_channel_width_pips"] = width
    return with_direction(result, state, signal, "narrow channel break has an inside-line stop and double-range objective")
