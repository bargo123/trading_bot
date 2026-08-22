"""Broker-native money/lock math utilities.

Uses CURRENT ticket symbol's broker-native:
- trade_tick_value
- trade_tick_size
- quantity

for USD <-> price/pip conversions. Single source of truth for MFE/MAE/LOCK.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass
class BrokerSymbolSpec:
    """Broker-native symbol specification for money math."""
    trade_tick_value: float  # USD per tick per lot
    trade_tick_size: float   # price units per tick
    volume_min: float        # minimum lot size
    trade_contract_size: float = 100000.0

    @classmethod
    def from_mapping(cls, spec: Mapping[str, Any] | None) -> "BrokerSymbolSpec":
        """Create from broker symbol_info mapping."""
        if spec is None:
            return cls(trade_tick_value=1.0, trade_tick_size=0.00001,
                       volume_min=0.01, trade_contract_size=100000.0)
        tick_val = float(spec.get("trade_tick_value") or 1.0)
        tick_sz = float(spec.get("trade_tick_size") or 0.00001)
        vol_min = float(spec.get("volume_min") or 0.01)
        contract = float(spec.get("trade_contract_size") or 100000.0)
        return cls(trade_tick_value=tick_val, trade_tick_size=tick_sz,
                   volume_min=vol_min, trade_contract_size=contract)

    def usd_per_price_unit_per_lot(self) -> float:
        """USD per price unit per 1.0 lot."""
        if self.trade_tick_size <= 0:
            return self.trade_contract_size
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