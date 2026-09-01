"""Bulkowski normal head-and-shoulders bottom perspective."""
from .bulkowski_hs_common import KEYS as HS_KEYS, evaluate_hs

ALGORITHM_ID = "bulkowski_head_shoulders_bottom"
SOURCES = ("Thomas N. Bulkowski — Encyclopedia of Chart Patterns",)
KEYS = HS_KEYS


def evaluate(state):
    return evaluate_hs(state, ALGORITHM_ID, bottom=True, complex_pattern=False, source_pages="374-378")
