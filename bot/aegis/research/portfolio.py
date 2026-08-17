"""Research-only portfolio context. It calculates exposure; it never mutates it."""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable, Mapping


def _value(position: Mapping[str, Any], name: str, default: Any = None) -> Any:
    return position.get(name, default)


def portfolio_state(positions: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Summarize FX base/quote exposure and existing thesis concentration."""
    currencies: dict[str, float] = defaultdict(float)
    symbols: dict[str, float] = defaultdict(float)
    theses: dict[str, float] = defaultdict(float)
    unknown: list[str] = []
    count = 0
    for position in positions:
        symbol = str(_value(position, "symbol", "")).upper()
        side = str(_value(position, "side", "")).lower()
        try:
            quantity = abs(float(_value(position, "quantity", _value(position, "qty", 0.0))))
        except (TypeError, ValueError):
            continue
        if len(symbol) < 6 or side not in {"buy", "sell"}:
            unknown.append(symbol or "unknown")
            continue
        sign = 1.0 if side == "buy" else -1.0
        base, quote = symbol[:3], symbol[3:6]
        currencies[base] += sign * quantity
        currencies[quote] -= sign * quantity
        symbols[symbol] += sign * quantity
        thesis_id = str(_value(position, "thesis_id", "unattributed"))
        theses[thesis_id] += sign * quantity
        count += 1
    return {
        "schema": "portfolio_state.v1",
        "positions": count,
        "currency_exposure": dict(sorted(currencies.items())),
        "symbol_exposure": dict(sorted(symbols.items())),
        "thesis_exposure": dict(sorted(theses.items())),
        "unknown_positions": unknown,
        "label": "research_proxy",
    }
