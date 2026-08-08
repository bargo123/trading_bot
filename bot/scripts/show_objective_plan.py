#!/usr/bin/env python3
"""Print the book-aligned path to a daily dollar objective."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
md = ROOT / "reports" / "ACHIEVABLE_50DAY.md"
cfg = ROOT / "config_objective_50day.yaml"
print(md.read_text(encoding="utf-8") if md.exists() else "Run optimization first.")
print(f"\nConfig: {cfg}")
