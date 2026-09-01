"""Validate the observation-only shadow YAML without changing live load_config."""
from __future__ import annotations

from typing import Any

from aegis.paper_control import paper_execution_enabled


class ShadowConfigError(ValueError):
    pass


def validate_shadow_config(cfg: dict[str, Any]) -> None:
    if cfg.get("allow_live") is True:
        raise ShadowConfigError("allow_live")
    if cfg.get("dry_run") is not True:
        raise ShadowConfigError("dry_run")
    if paper_execution_enabled(cfg) is not False:
        raise ShadowConfigError("paper_execution_enabled")
    if str(cfg.get("position_sizing_mode") or "") != "risk":
        raise ShadowConfigError("position_sizing_mode")
    if float(cfg.get("max_daily_loss_percent") or 0) <= 0:
        raise ShadowConfigError("max_daily_loss_percent")
    if float(cfg.get("max_total_drawdown_percent") or 0) <= 0:
        raise ShadowConfigError("max_total_drawdown_percent")
    if bool(cfg.get("firehose_stack")):
        raise ShadowConfigError("firehose_stack")
    if bool(cfg.get("firehose_every_bar")):
        raise ShadowConfigError("firehose_every_bar")
    if int(cfg.get("max_positions") or 0) > 8:
        raise ShadowConfigError("max_positions")
