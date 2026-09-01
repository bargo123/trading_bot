"""Measured per-symbol/session spread limits for safe runtime authorization."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class MeasuredSpreadLimit:
    symbol: str
    session: str
    max_spread_pips: float
    slippage_pips: float
    commission_pips: float
    observations: int

    def allows(self, spread_pips: float) -> bool:
        try:
            observed = float(spread_pips)
        except (TypeError, ValueError):
            return False
        return math.isfinite(observed) and observed >= 0 and observed <= self.max_spread_pips


def measured_spread_limit_pips(
    profile: Mapping[str, Any], *, symbol: str, session: str
) -> MeasuredSpreadLimit | None:
    """Return the measured p90 limit only for sufficient symbol/session evidence."""
    symbols = profile.get("symbols") if isinstance(profile, Mapping) else None
    symbol_profile = symbols.get(str(symbol).upper()) if isinstance(symbols, Mapping) else None
    sessions = symbol_profile.get("sessions") if isinstance(symbol_profile, Mapping) else None
    evidence = sessions.get(str(session).lower()) if isinstance(sessions, Mapping) else None
    if not isinstance(evidence, Mapping) or not bool(evidence.get("evidence_sufficient")):
        return None
    try:
        p90 = float(evidence["spread_p90"])
        slippage = float(evidence.get("slippage_pips", 0.0) or 0.0)
        commission = float(evidence.get("commission_pips", 0.0) or 0.0)
        observations = int(evidence.get("observations", 0) or 0)
    except (KeyError, TypeError, ValueError):
        return None
    if not math.isfinite(p90) or p90 < 0 or not math.isfinite(slippage) or slippage < 0:
        return None
    if not math.isfinite(commission) or commission < 0 or observations <= 0:
        return None
    return MeasuredSpreadLimit(
        symbol=str(symbol).upper(),
        session=str(session).lower(),
        max_spread_pips=p90,
        slippage_pips=slippage,
        commission_pips=commission,
        observations=observations,
    )
