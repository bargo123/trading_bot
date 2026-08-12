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


def test_mt5_stub_raises_on_connect():
    eng = create_engine({"engine": "mt5"})
    assert isinstance(eng, MT5Engine)
    try:
        eng.connect()
        raise AssertionError("expected NotImplementedError")
    except NotImplementedError:
        pass


if __name__ == "__main__":
    test_factory_ibkr()
    test_factory_rejects_live_port_without_flag()
    test_mt5_stub_raises_on_connect()
    print("OK")
