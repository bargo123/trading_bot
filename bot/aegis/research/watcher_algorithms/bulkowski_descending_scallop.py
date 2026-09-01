"""Bulkowski descending scallop: reverse-J continuation in a declining trend."""
from __future__ import annotations

from .bulkowski_scallop_common import KEYS as SCALLOP_KEYS, evaluate_scallop

ALGORITHM_ID = "bulkowski_descending_scallop"
SOURCES = ("Thomas N. Bulkowski — Encyclopedia of Chart Patterns",)
KEYS = SCALLOP_KEYS


def evaluate(state):
    return evaluate_scallop(
        ALGORITHM_ID,
        state,
        expected_type="descending",
        expected_trend="down",
        source_pages="654-661",
        allow_breakout=("UP", "DOWN"),
        require_retrace=True,
    )
