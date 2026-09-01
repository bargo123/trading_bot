"""Bulkowski ascending scallop: J-shaped continuation in a rising trend."""
from __future__ import annotations

from .bulkowski_scallop_common import KEYS as SCALLOP_KEYS, evaluate_scallop

ALGORITHM_ID = "bulkowski_ascending_scallop"
SOURCES = ("Thomas N. Bulkowski — Encyclopedia of Chart Patterns",)
KEYS = SCALLOP_KEYS


def evaluate(state):
    return evaluate_scallop(
        ALGORITHM_ID,
        state,
        expected_type="ascending",
        expected_trend="up",
        source_pages="624-630",
        allow_breakout=("UP", "DOWN"),
    )
