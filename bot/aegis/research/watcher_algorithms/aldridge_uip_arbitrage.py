"""Aldridge uncovered-interest-parity arbitrage perspective."""
from __future__ import annotations

from ._aldridge_arbitrage_common import dislocation

ALGORITHM_ID = "aldridge_uip_arbitrage"
SOURCES = ("Irene Aldridge — High-Frequency Trading",)
KEYS = ("aldridge_uip_residual", "aldridge_uip_threshold", "aldridge_uip_net_edge_after_cost", "aldridge_uip_direction", "aldridge_uip_rates_aligned", "aldridge_uip_data_provenance")


def evaluate(state):
    return dislocation(state, algorithm_id=ALGORITHM_ID, keys=KEYS, residual_key="aldridge_uip_residual", threshold_key="aldridge_uip_threshold", edge_key="aldridge_uip_net_edge_after_cost", direction_key="aldridge_uip_direction", provenance_key="aldridge_uip_data_provenance", synchronization_key="aldridge_uip_rates_aligned", output_prefix="aldridge_uip", warning="UIP is a research relationship and requires timestamp-aligned rates")
