"""AEGIS Research Factory - Main Entry Point."""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from aegis.research_factory.core import ResearchFactory, main

if __name__ == "__main__":
    main()