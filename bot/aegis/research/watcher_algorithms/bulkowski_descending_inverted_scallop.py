"""Bulkowski descending-and-inverted scallop: bearish upside-down-J break."""
from __future__ import annotations

from .bulkowski_scallop_common import KEYS as SCALLOP_KEYS, evaluate_scallop

ALGORITHM_ID = "bulkowski_descending_inverted_scallop"
SOURCES = ("Thomas N. Bulkowski — Encyclopedia of Chart Patterns",)
KEYS = SCALLOP_KEYS


def evaluate(state):
    return evaluate_scallop(
        ALGORITHM_ID,
        state,
        expected_type="descending_inverted",
        expected_trend="down",
        source_pages="670-676",
        allow_breakout=("DOWN",),
        require_retrace=True,
        inverted=True,
    )
