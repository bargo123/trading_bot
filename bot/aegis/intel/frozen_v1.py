"""Load CORE_STRATEGY_V1 params for offline research. Never writes the live YAML."""
from __future__ import annotations

import json
from typing import Any

from aegis.config import load_config
from aegis.intel.paths import BOT_ROOT, FROZEN_V1
from aegis.optimizer.paths import DEFAULT_LIVE_CONFIG


def frozen_payload() -> dict[str, Any]:
    return json.loads(FROZEN_V1.read_text(encoding="utf-8"))


def research_cfg() -> dict[str, Any]:
    """Clone of live firehose + $100 research sizing. intel_enabled stays false here."""
    live = load_config(DEFAULT_LIVE_CONFIG)
    cfg = dict(live)
    frozen = frozen_payload().get("params") or {}
    for key, val in frozen.items():
        cfg[key] = val
    cfg["intel_enabled"] = False
    cfg["starting_equity"] = 100.0
    # 0.01 lot FX ≈ 1000 units of quote in the OHLC backtester.
    cfg["fixed_units"] = 1000.0
    cfg["lookback_days"] = int(cfg.get("lookback_days") or 14)
    cfg["symbol"] = str((cfg.get("symbols") or ["EURUSD"])[0])
    # Observe the full loss distribution. Live YAML still uses 12% DD.
    cfg["max_total_drawdown_percent"] = 80.0
    cfg["max_daily_loss_percent"] = 0.0
    return cfg
