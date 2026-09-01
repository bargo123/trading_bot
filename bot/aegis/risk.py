from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


def demo_global_loss_halt_disabled(cfg: dict[str, Any]) -> bool:
    """Recognize the explicit unlimited-loss-halt MT5 DEMO policy marker.

    This is deliberately strict: a zero loss setting never disables global
    drawdown protection for live, non-MT5, dry-run, or incompletely governed
    configurations.
    """
    try:
        return (
            str(cfg.get("engine") or "").casefold() == "mt5"
            and str(cfg.get("mode") or "").casefold() == "mt5_demo"
            and cfg.get("allow_live") is False
            and cfg.get("paper_trading_enabled") is True
            and cfg.get("dry_run") is False
            and float(cfg["max_daily_loss_percent"]) == 0.0
            and float(cfg["exploration_max_daily_loss_usd"]) == 0.0
        )
    except (KeyError, TypeError, ValueError):
        return False


@dataclass
class RiskState:
    day: date | None = None
    day_start_equity: float | None = None
    peak_equity: float | None = None
    halted: bool = False
    permanent_halt: bool = False
    reason: str = ""


@dataclass
class RiskEngine:
    risk_percent: float
    max_daily_loss_percent: float
    max_total_drawdown_percent: float
    max_positions: int
    kill_switch: bool = False
    demo_global_loss_halt_disabled: bool = False
    state: RiskState = field(default_factory=RiskState)

    @classmethod
    def from_config(cls, cfg: dict[str, Any]) -> "RiskEngine":
        demo_unlimited = demo_global_loss_halt_disabled(cfg)
        return cls(
            risk_percent=float(cfg.get("risk_percent", 0.75)),
            max_daily_loss_percent=float(cfg.get("max_daily_loss_percent", 3.0)),
            max_total_drawdown_percent=(
                0.0
                if demo_unlimited
                else float(cfg.get("max_total_drawdown_percent", 12.0))
            ),
            max_positions=int(cfg.get("max_positions", 1)),
            kill_switch=bool(cfg.get("kill_switch", False)),
            demo_global_loss_halt_disabled=demo_unlimited,
        )

    def update(self, equity: float, now: datetime | None = None) -> None:
        now = now or datetime.now(timezone.utc)
        today = now.date()
        if self.state.day != today:
            self.state.day = today
            self.state.day_start_equity = equity
            if not self.state.permanent_halt:
                self.state.halted = False
                self.state.reason = ""
        if self.state.peak_equity is None or equity > self.state.peak_equity:
            self.state.peak_equity = equity

    def allow(
        self,
        equity: float,
        open_positions: int,
        now: datetime | None = None,
    ) -> tuple[bool, str]:
        if self.kill_switch:
            return False, "kill_switch"
        self.update(equity, now=now)
        # 0 or negative = no daily-loss / no total-DD budget (demo keep-spraying).
        if self.max_daily_loss_percent <= 0:
            if self.state.halted and str(self.state.reason).startswith("daily_loss"):
                self.state.halted = False
                self.state.reason = ""
        if self.max_total_drawdown_percent <= 0:
            if self.state.halted and str(self.state.reason).startswith("max_drawdown"):
                self.state.halted = False
                self.state.permanent_halt = False
                self.state.reason = ""
        if self.state.halted:
            return False, self.state.reason or "halted"
        if open_positions >= self.max_positions:
            return False, "max_positions"

        if (
            self.max_daily_loss_percent > 0
            and self.state.day_start_equity
            and self.state.day_start_equity > 0
        ):
            day_dd = (self.state.day_start_equity - equity) / self.state.day_start_equity * 100
            if day_dd >= self.max_daily_loss_percent:
                self.state.halted = True
                self.state.reason = f"daily_loss {day_dd:.2f}%"
                return False, self.state.reason

        if (
            self.max_total_drawdown_percent > 0
            and self.state.peak_equity
            and self.state.peak_equity > 0
        ):
            tot_dd = (self.state.peak_equity - equity) / self.state.peak_equity * 100
            if tot_dd >= self.max_total_drawdown_percent:
                self.state.halted = True
                self.state.permanent_halt = True
                self.state.reason = f"max_drawdown {tot_dd:.2f}%"
                return False, self.state.reason
        return True, "ok"

    def size_units(
        self,
        equity: float,
        entry: float,
        sl: float,
        min_stop: float | None = None,
        risk_percent: float | None = None,
    ) -> float:
        """Notional units such that stop distance ≈ risk_percent of equity."""
        stop = abs(entry - sl)
        if min_stop is not None:
            stop = max(stop, min_stop)
        if stop <= 0 or equity <= 0:
            return 0.0
        rp = self.risk_percent if risk_percent is None else float(risk_percent)
        risk_money = equity * (rp / 100.0)
        return risk_money / stop

    def dump(self) -> dict[str, Any]:
        return {
            "day": self.state.day.isoformat() if self.state.day else None,
            "day_start_equity": self.state.day_start_equity,
            "peak_equity": self.state.peak_equity,
            "halted": self.state.halted,
            "permanent_halt": self.state.permanent_halt,
            "reason": self.state.reason,
            "demo_global_loss_halt_disabled": self.demo_global_loss_halt_disabled,
            "max_total_drawdown_percent": self.max_total_drawdown_percent,
        }

    def load_json(self, path: Path) -> bool:
        p = Path(path)
        if not p.exists():
            return False
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        if not isinstance(raw, dict):
            return False
        day_s = raw.get("day")
        try:
            self.state.day = date.fromisoformat(str(day_s)) if day_s else None
        except ValueError:
            self.state.day = None
        self.state.day_start_equity = (
            float(raw["day_start_equity"]) if raw.get("day_start_equity") is not None else None
        )
        self.state.peak_equity = float(raw["peak_equity"]) if raw.get("peak_equity") is not None else None
        self.state.halted = bool(raw.get("halted"))
        self.state.permanent_halt = bool(raw.get("permanent_halt"))
        self.state.reason = str(raw.get("reason") or "")
        return True

    def save_json(self, path: Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.dump(), indent=2), encoding="utf-8")
