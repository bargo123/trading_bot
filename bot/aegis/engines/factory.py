"""Factory: config `engine` → BrokerEngine instance."""
from __future__ import annotations

from typing import Any

from aegis.engines.base import BrokerEngine


def create_engine(cfg: dict[str, Any]) -> BrokerEngine:
    name = str(cfg.get("engine") or cfg.get("broker_engine") or "").lower().strip()
    # Back-compat: mode hints
    mode = str(cfg.get("mode") or "").lower()
    if not name:
        if mode in {"ib_paper", "ibkr", "ib"}:
            name = "ibkr"
        elif mode in {"mt5", "mt5_demo", "mt5_paper"}:
            name = "mt5"
        else:
            raise ValueError(
                "Set config engine: ibkr | mt5 (or mode: ib_paper). "
                "Yahoo paper stays mode: paper without an engine."
            )

    if name in {"ibkr", "ib", "interactive_brokers"}:
        from aegis.engines.ibkr import IBKREngine

        return IBKREngine(cfg)
    if name in {"mt5", "metatrader5"}:
        from aegis.engines.mt5 import MT5Engine

        return MT5Engine(cfg)
    raise ValueError(f"Unknown engine: {name!r}. Supported: ibkr, mt5")
