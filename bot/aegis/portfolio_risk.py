"""Fail-closed portfolio and currency-factor exposure gates.

Library only. The live paper runner is not wired to this module until a later
authorized integration. Shadow intelligence may call it.
"""
from __future__ import annotations

import re
from collections import Counter
from math import isfinite
from typing import Any, Mapping, Sequence

from aegis.engines import PositionSnapshot


FX_SYMBOL_RE = re.compile(r"^([A-Z]{3})([A-Z]{3})$")
SUPPORTED_FX_SYMBOLS = frozenset(
    {
        "AUDCAD",
        "AUDCHF",
        "AUDJPY",
        "AUDNZD",
        "AUDSGD",
        "AUDUSD",
        "CADCHF",
        "CADJPY",
        "EURAUD",
        "EURCAD",
        "EURCHF",
        "EURGBP",
        "EURJPY",
        "EURNZD",
        "EURUSD",
        "GBPAUD",
        "GBPCAD",
        "GBPCHF",
        "GBPJPY",
        "GBPNZD",
        "GBPUSD",
        "NZDJPY",
        "NZDUSD",
        "USDCAD",
        "USDCHF",
        "USDJPY",
    }
)
SUPPORTED_NON_FX_SYMBOLS = frozenset({"MGC"})
_MISSING = object()


def _symbol_kind(symbol: object) -> tuple[str, str]:
    if not isinstance(symbol, str) or not symbol or symbol != symbol.strip():
        return "", ""
    normalized = symbol.upper()
    if normalized in SUPPORTED_FX_SYMBOLS:
        return "fx", normalized
    if normalized in SUPPORTED_NON_FX_SYMBOLS:
        return "non_fx", normalized
    return "", ""


def _valid_side(side: object) -> str:
    if not isinstance(side, str):
        return ""
    normalized = side.lower()
    return normalized if side == side.strip() and normalized in {"buy", "sell"} else ""


def _valid_quantity(quantity: object) -> float | None:
    if isinstance(quantity, bool):
        return None
    try:
        value = float(quantity)
    except (TypeError, ValueError, OverflowError):
        return None
    return value if isfinite(value) and value > 0 else None


def _position_error(position: PositionSnapshot) -> str:
    if not _symbol_kind(position.symbol)[0]:
        return "symbol"
    if not _valid_side(position.side):
        return "side"
    if _valid_quantity(position.quantity) is None:
        return "quantity"
    return ""


def _configured_cap(
    cfg: Mapping[str, Any], name: str, *, default: int
) -> tuple[int | None, str]:
    raw = cfg.get(name, _MISSING)
    if raw is _MISSING:
        return default, ""
    if raw is None:
        return None, f"invalid_config:{name}"
    if isinstance(raw, bool):
        return None, f"invalid_config:{name}"
    try:
        numeric = float(raw)
    except (TypeError, ValueError, OverflowError):
        return None, f"invalid_config:{name}"
    if not isfinite(numeric) or numeric < 0 or not numeric.is_integer():
        return None, f"invalid_config:{name}"
    value = int(numeric)
    if name == "max_per_symbol" and value == 0:
        value = default
    return value, ""


def fx_legs(symbol: str, side: str, lots: float) -> dict[str, int]:
    """Return one directional clip for each leg of a supported FX pair."""
    kind, normalized_symbol = _symbol_kind(symbol)
    normalized_side = _valid_side(side)
    if kind != "fx" or not normalized_side or _valid_quantity(lots) is None:
        return {}
    match = FX_SYMBOL_RE.fullmatch(normalized_symbol)
    if match is None:  # pragma: no cover - guaranteed by _symbol_kind
        return {}
    base, quote = match.groups()
    sign = 1 if normalized_side == "buy" else -1
    return {base: sign, quote: -sign}


def portfolio_exposure(positions: Sequence[PositionSnapshot]) -> dict[str, int]:
    """Aggregate directional FX clips, rejecting malformed position snapshots."""
    exposure: Counter[str] = Counter()
    for index, position in enumerate(positions):
        error = _position_error(position)
        if error:
            raise ValueError(f"invalid_position:{index}:{error}")
        exposure.update(fx_legs(position.symbol, position.side, position.quantity))
    return dict(exposure)


def portfolio_allows(
    positions: Sequence[PositionSnapshot],
    candidate: PositionSnapshot,
    cfg: Mapping[str, Any],
) -> tuple[bool, str]:
    """Apply position, symbol, and signed currency-factor caps to a proposed trade."""
    candidate_error = _position_error(candidate)
    if candidate_error:
        return False, f"invalid_candidate:{candidate_error}"
    for index, position in enumerate(positions):
        position_error = _position_error(position)
        if position_error:
            return False, f"invalid_position:{index}:{position_error}"

    max_positions, config_error = _configured_cap(cfg, "max_positions", default=0)
    if config_error:
        return False, config_error
    assert max_positions is not None
    if max_positions > 0 and len(positions) >= max_positions:
        return False, "max_positions"

    max_per_symbol, config_error = _configured_cap(cfg, "max_per_symbol", default=1)
    if config_error:
        return False, config_error
    assert max_per_symbol is not None
    candidate_symbol = _symbol_kind(candidate.symbol)[1]
    same_symbol = sum(
        _symbol_kind(position.symbol)[1] == candidate_symbol for position in positions
    )
    if same_symbol >= max_per_symbol:
        return False, "max_per_symbol"

    limit, config_error = _configured_cap(
        cfg, "max_currency_direction_positions", default=0
    )
    if config_error:
        return False, config_error
    assert limit is not None
    exposure = Counter(portfolio_exposure(positions))
    exposure.update(fx_legs(candidate.symbol, candidate.side, candidate.quantity))
    if limit > 0:
        for currency, signed_count in sorted(exposure.items()):
            if abs(signed_count) > limit:
                direction = "long" if signed_count > 0 else "short"
                return False, f"currency_factor:{currency}:{direction}"
    return True, ""


def portfolio_pretrade_decision(
    *,
    positions: Sequence[PositionSnapshot],
    symbol: str,
    side: str,
    quantity: float,
    avg_price: float,
    cfg: Mapping[str, Any],
) -> tuple[bool, str, dict[str, Any] | None]:
    """Build a candidate and return journal-ready rejection evidence. Does not place orders."""
    held = list(positions)
    gate_cfg = dict(cfg)
    gate_cfg["max_per_symbol"] = cfg.get(
        "max_per_symbol", cfg.get("firehose_max_per_symbol", 1)
    )
    candidate = PositionSnapshot(
        symbol=symbol,
        side=side,  # type: ignore[arg-type]
        quantity=quantity,
        avg_price=avg_price,
    )
    allowed, reason = portfolio_allows(held, candidate, gate_cfg)
    if allowed:
        return True, "", None

    cap_names = {
        "max_positions": "max_positions",
        "max_per_symbol": "max_per_symbol",
    }
    cap_name = cap_names.get(reason)
    if reason.startswith("currency_factor:"):
        cap_name = "max_currency_direction_positions"
    cap = None
    if cap_name is not None:
        raw_cap = gate_cfg.get(cap_name, 1 if cap_name == "max_per_symbol" else 0)
        effective_cap = int(float(raw_cap or (1 if cap_name == "max_per_symbol" else 0)))
        cap = {"name": cap_name, "value": effective_cap}
    try:
        exposure = portfolio_exposure([*held, candidate])
    except ValueError:
        exposure = {}
    event = {
        "event": "portfolio_reject",
        "symbol": symbol,
        "side": side,
        "qty": quantity,
        "reason": reason,
        "cap": cap,
        "exposure": exposure,
    }
    return False, reason, event
