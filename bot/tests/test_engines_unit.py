"""Unit tests for engine factory / stubs (no live broker required)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aegis.engines import create_engine
from aegis.engines.ibkr import IBKREngine
from aegis.engines.mt5 import MT5Engine


def test_factory_ibkr():
    eng = create_engine({"engine": "ibkr", "ib_port": 7497, "allow_live": False})
    assert eng.name == "ibkr"
    assert isinstance(eng, IBKREngine)


def test_factory_rejects_live_port_without_flag():
    for port in (7496, 4001):
        try:
            IBKREngine({"ib_port": port, "allow_live": False})
            raise AssertionError(f"expected RuntimeError for live port {port}")
        except RuntimeError as e:
            assert str(port) in str(e) or "live" in str(e).lower()


def test_factory_mt5():
    eng = create_engine({"engine": "mt5", "allow_live": False})
    assert isinstance(eng, MT5Engine)
    assert eng.name == "mt5"


if __name__ == "__main__":
    test_factory_ibkr()
    test_factory_rejects_live_port_without_flag()
    test_factory_mt5()
    print("OK")
