from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]


def load_config(path: Path | str | None = None) -> dict[str, Any]:
    cfg_path = Path(path) if path else ROOT / "config.yaml"
    with cfg_path.open(encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    required = ["symbol", "timeframe", "mode"]
    missing = [k for k in required if k not in cfg]
    if missing:
        raise ValueError(f"Missing config keys: {missing}")
    return cfg


def dump_config(cfg: dict[str, Any], path: Path | str) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, sort_keys=False, allow_unicode=True)


def configured_symbols(cfg: dict[str, Any]) -> list[str]:
    raw = cfg.get("symbols")
    if isinstance(raw, str) and raw.strip():
        return [raw.strip()]
    if isinstance(raw, (list, tuple)):
        out = [str(s).strip() for s in raw if str(s).strip()]
        if out:
            return out
    return [str(cfg["symbol"]).strip()]


def pip_size_for(symbol: str, cfg: dict[str, Any]) -> float:
    table = cfg.get("pip_size_by_symbol") or {}
    if symbol in table:
        return float(table[symbol])
    upper = symbol.upper()
    if "JPY" in upper:
        return float(cfg.get("jpy_pip_size", 0.01))
    if upper.startswith("XAU") or upper.startswith("GOLD"):
        return float(cfg.get("xau_pip_size", 0.1))
    return float(cfg.get("firehose_pip_size", cfg.get("volman_pip_size", 0.0001)))


def max_spread_for(symbol: str, cfg: dict[str, Any]) -> float:
    pips = float(cfg.get("max_spread_pips", 0) or 0)
    if pips > 0:
        return pips * pip_size_for(symbol, cfg)
    return float(cfg.get("max_spread_price", 0) or 0)
