"""Clenow's warning against stacking the same currency exposure."""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence

from ._common import absent, base, explicitly_observed, first, number, side, values

ALGORITHM_ID = "clenow_currency_exposure"
SOURCES = ("Following the Trend — Diversified Managed Futures Trading",)
KEYS = (
    "clenow_candidate_base_currency",
    "clenow_candidate_quote_currency",
    "clenow_candidate_risk_usd",
    "clenow_existing_positions",
    "clenow_currency_exposure_limit_usd",
    "clenow_exposure_data_provenance",
)


def _currency(value):
    text = str(value or "").strip().upper()
    return text if len(text) == 3 and text.isalpha() else None


def _add(exposure, base_currency, quote_currency, position_side, risk):
    if position_side == "BUY":
        exposure[base_currency] += risk
        exposure[quote_currency] -= risk
    else:
        exposure[base_currency] -= risk
        exposure[quote_currency] += risk


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(
        first(state, "clenow_exposure_data_provenance"),
        accepted=("observed", "timestamped"),
    ):
        missing.append("clenow_exposure_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    candidate_base = _currency(first(state, "clenow_candidate_base_currency"))
    candidate_quote = _currency(first(state, "clenow_candidate_quote_currency"))
    candidate_risk = number(first(state, "clenow_candidate_risk_usd"))
    limit = number(first(state, "clenow_currency_exposure_limit_usd"))
    positions = first(state, "clenow_existing_positions")
    if (
        candidate_base is None
        or candidate_quote is None
        or candidate_base == candidate_quote
        or candidate_risk is None
        or candidate_risk <= 0
        or limit is None
        or limit <= 0
        or not isinstance(positions, Sequence)
        or isinstance(positions, (str, bytes, bytearray))
    ):
        result["clenow_exposure_assessment"] = "INVALID_EXPOSURE_INPUT"
        result["view"] = "WAIT"
        result["reasons"] = ["currency pair, risk, limit, and existing positions must be explicit and valid"]
        return result

    exposure = defaultdict(float)
    existing_currencies = set()
    for position in positions:
        if not isinstance(position, Mapping):
            result["clenow_exposure_assessment"] = "INVALID_EXPOSURE_INPUT"
            result["view"] = "WAIT"
            result["reasons"] = ["each existing position must be a mapping"]
            return result
        position_base = _currency(position.get("base_currency"))
        position_quote = _currency(position.get("quote_currency"))
        position_side = str(position.get("side") or "").strip().upper()
        risk = number(position.get("risk_usd"))
        if (
            position_base is None
            or position_quote is None
            or position_base == position_quote
            or position_side not in {"BUY", "SELL"}
            or risk is None
            or risk < 0
        ):
            result["clenow_exposure_assessment"] = "INVALID_EXPOSURE_INPUT"
            result["view"] = "WAIT"
            result["reasons"] = ["existing currency exposure contains an invalid position"]
            return result
        existing_currencies.update((position_base, position_quote))
        _add(exposure, position_base, position_quote, position_side, risk)

    candidate_side = side(state)
    if candidate_side not in {"BUY", "SELL"}:
        result["clenow_exposure_assessment"] = "INVALID_EXPOSURE_INPUT"
        result["view"] = "WAIT"
        result["reasons"] = ["candidate side must be BUY or SELL"]
        return result
    _add(exposure, candidate_base, candidate_quote, candidate_side, candidate_risk)

    projected = {currency: round(value, 12) for currency, value in sorted(exposure.items()) if abs(value) > 1e-12}
    overlap = sorted({candidate_base, candidate_quote} & existing_currencies)
    exceeds_limit = any(abs(value) > limit for value in projected.values())
    concentrated = bool(overlap) or exceeds_limit
    result["clenow_projected_currency_exposure_usd"] = projected
    result["clenow_shared_currencies"] = overlap
    result["clenow_currency_limit_usd"] = limit
    result["clenow_exposure_assessment"] = (
        "CONCENTRATED_CURRENCY_RISK" if concentrated else "DIVERSIFIED_CURRENCY_EXPOSURE"
    )
    result["view"] = "WAIT"
    result["reasons"] = [
        "candidate is evaluated against existing base/quote currency exposures; this is a research warning, not an order block"
    ]
    return result
