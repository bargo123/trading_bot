from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any


@dataclass
class RiskState:
    day: date | None = None
    day_start_equity: float | None = None
    peak_equity: float | None = None
    halted: bool = False
    reason: str = ""


@dataclass
class RiskEngine:
    risk_percent: float
    max_daily_loss_percent: float
    max_total_drawdown_percent: float
    max_positions: int
    kill_switch: bool = False
    state: RiskState = field(default_factory=RiskState)

    @classmethod
    def from_config(cls, cfg: dict[str, Any]) -> "RiskEngine":
        return cls(
            risk_percent=float(cfg.get("risk_percent", 0.75)),
            max_daily_loss_percent=float(cfg.get("max_daily_loss_percent", 3.0)),
            max_total_drawdown_percent=float(cfg.get("max_total_drawdown_percent", 12.0)),
            max_positions=int(cfg.get("max_positions", 1)),
            kill_switch=bool(cfg.get("kill_switch", False)),
        )

    def update(self, equity: float, now: datetime | None = None) -> None:
        now = now or datetime.now(timezone.utc)
        today = now.date()
        if self.state.day != today:
            self.state.day = today
            self.state.day_start_equity = equity
            self.state.halted = False
            self.state.reason = ""
        if self.state.peak_equity is None or equity > self.state.peak_equity:
            self.state.peak_equity = equity

    def allow(self, equity: float, open_positions: int) -> tuple[bool, str]:
        if self.kill_switch:
            return False, "kill_switch"
        self.update(equity)
        if self.state.halted:
            return False, self.state.reason or "halted"
        if open_positions >= self.max_positions:
            return False, "max_positions"

        if self.state.day_start_equity and self.state.day_start_equity > 0:
            day_dd = (self.state.day_start_equity - equity) / self.state.day_start_equity * 100
            if day_dd >= self.max_daily_loss_percent:
                self.state.halted = True
                self.state.reason = f"daily_loss {day_dd:.2f}%"
                return False, self.state.reason

        if self.state.peak_equity and self.state.peak_equity > 0:
            tot_dd = (self.state.peak_equity - equity) / self.state.peak_equity * 100
            if tot_dd >= self.max_total_drawdown_percent:
                self.state.halted = True
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
