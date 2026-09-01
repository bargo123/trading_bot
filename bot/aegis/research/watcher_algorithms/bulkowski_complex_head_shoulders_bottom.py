"""Bulkowski complex head-and-shoulders bottom perspective."""
from .bulkowski_hs_common import KEYS as HS_KEYS, evaluate_hs

ALGORITHM_ID = "bulkowski_complex_head_shoulders_bottom"
SOURCES = ("Thomas N. Bulkowski — Encyclopedia of Chart Patterns",)
KEYS = HS_KEYS


def evaluate(state):
    return evaluate_hs(state, ALGORITHM_ID, bottom=True, complex_pattern=True, source_pages="390-394")
