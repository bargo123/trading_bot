"""Bulkowski ascending-and-inverted scallop: bullish backward-J recovery."""
from __future__ import annotations

from .bulkowski_scallop_common import KEYS as SCALLOP_KEYS, evaluate_scallop

ALGORITHM_ID = "bulkowski_ascending_inverted_scallop"
SOURCES = ("Thomas N. Bulkowski — Encyclopedia of Chart Patterns",)
KEYS = SCALLOP_KEYS


def evaluate(state):
    return evaluate_scallop(
        ALGORITHM_ID,
        state,
        expected_type="ascending_inverted",
        expected_trend="up",
        source_pages="639-646",
        allow_breakout=("UP",),
        require_retrace=True,
        inverted=True,
    )
