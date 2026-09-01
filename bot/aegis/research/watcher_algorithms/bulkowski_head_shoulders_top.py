"""Bulkowski normal head-and-shoulders top perspective."""
from .bulkowski_hs_common import KEYS as HS_KEYS, evaluate_hs

ALGORITHM_ID = "bulkowski_head_shoulders_top"
SOURCES = ("Thomas N. Bulkowski — Encyclopedia of Chart Patterns",)
KEYS = HS_KEYS


def evaluate(state):
    return evaluate_hs(state, ALGORITHM_ID, bottom=False, complex_pattern=False, source_pages="405-408")
