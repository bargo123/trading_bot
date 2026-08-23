"""Broker-native money/lock math utilities.

Uses CURRENT ticket symbol's broker-native:
- trade_tick_value
- trade_tick_size
- quantity

for USD <-> price/pip conversions. Single source of truth for MFE/MAE/LOCK.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping


@dataclass
class BrokerSymbolSpec:
    """Broker-native symbol specification for money math."""
    trade_tick_value: float  # USD per tick per lot
    trade_tick_size: float   # price units per tick
    volume_min: float        # minimum lot size
    trade_contract_size: float | None = None

    @classmethod
    def from_mapping(cls, spec: Mapping[str, Any] | None) -> "BrokerSymbolSpec":
        """Create from complete broker evidence without inferred defaults."""
        if spec is None:
            raise ValueError("broker symbol specification is required")
        try:
            raw_values = (
                spec["trade_tick_value"],
                spec["trade_tick_size"],
                spec["volume_min"],
            )
            if any(isinstance(value, bool) for value in raw_values):
                raise ValueError
            tick_val, tick_sz, vol_min = (float(value) for value in raw_values)
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("positive tick value, tick size, and volume minimum are required") from exc
        if not all(math.isfinite(value) and value > 0 for value in (tick_val, tick_sz, vol_min)):
            raise ValueError("positive tick value, tick size, and volume minimum are required")

        contract_raw = spec.get("trade_contract_size")
        try:
            contract = None if contract_raw is None else float(contract_raw)
        except (TypeError, ValueError) as exc:
            raise ValueError("trade contract size must be numeric when provided") from exc
        return cls(trade_tick_value=tick_val, trade_tick_size=tick_sz,
                    volume_min=vol_min, trade_contract_size=contract)

    def usd_per_price_unit_per_lot(self) -> float:
        """USD per price unit per 1.0 lot."""
        if self.trade_tick_size <= 0:
            raise ValueError("trade_tick_size must be positive")
        return self.trade_tick_value / self.trade_tick_size

    def usd_per_pip_per_lot(self, pip_size: float) -> float:
        """USD per pip per 1.0 lot."""
        return self.usd_per_price_unit_per_lot() * pip_size

    def price_units_per_pip(self, pip_size: float) -> float:
        """Price units per pip."""
        return pip_size

    def price_units_to_usd(self, price_units: float, lots: float) -> float:
        """Convert price units to USD for given lot size."""
        return price_units * self.usd_per_price_unit_per_lot() * lots

    def usd_to_price_units(self, usd: float, lots: float) -> float:
        """Convert USD to price units for given lot size."""
        uppl = self.usd_per_price_unit_per_lot()
        if uppl <= 0 or lots <= 0:
            return 0.0
        return usd / (uppl * lots)

    def pips_to_usd(self, pips: float, lots: float, pip_size: float) -> float:
        """Convert pips to USD for given lot size."""
        return pips * self.usd_per_pip_per_lot(pip_size) * lots

    def usd_to_pips(self, usd: float, lots: float, pip_size: float) -> float:
        """Convert USD to pips for given lot size."""
        uppl = self.usd_per_pip_per_lot(pip_size)
        if uppl <= 0 or lots <= 0:
            return 0.0
        return usd / (uppl * lots)

    def min_lot_risk_usd(self, stop_dist_price: float) -> float:
        """Minimum risk at broker volume_min for given stop distance."""
        return stop_dist_price * self.usd_per_price_unit_per_lot() * self.volume_min


def mfe_mae_from_usd(
    mfe_usd: float,
    mae_usd: float,
    spec: BrokerSymbolSpec,
    lots: float,
    pip_size: float
) -> tuple[float, float]:
    """Convert MFE/MAE from USD to pips using broker-native spec."""
    mfe_pips = spec.usd_to_pips(mfe_usd, lots, pip_size)
    mae_pips = spec.usd_to_pips(mae_usd, lots, pip_size)
    return mfe_pips, mae_pips


def lock_buffer_price(
    buffer_usd: float,
    spec: BrokerSymbolSpec,
    lots: float
) -> float:
    """Convert breakeven buffer USD to price units for stop adjustment."""
    return spec.usd_to_price_units(buffer_usd, lots)


def usd_from_price_change(
    price_change: float,
    spec: BrokerSymbolSpec,
    lots: float
) -> float:
    """Convert price change to USD using broker-native spec."""
    return spec.price_units_to_usd(price_change, lots)
