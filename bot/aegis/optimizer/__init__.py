"""File-backed research loop beside the live MT5 paper runner.

Does not place orders. Never calls mt5.shutdown(). YAML-first experiments.
"""
from __future__ import annotations

__all__ = ["OPTIMIZER_DIR"]

from aegis.optimizer.paths import OPTIMIZER_DIR
