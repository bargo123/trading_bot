"""
High-risk modes from the trading library — with a safety cage that "solves"
the ruin patterns (Windsor escalate, uncapped Brown recovery/DCA, 80–100% risk).

Modes (books):
- traditional     — Brown/Silvani/DraKoln: fixed small % risk, stops always
- fuller_pyramid  — Fuller: add to winners only; aggregate risk ≤ 1R (backtest flag)
- brown_recovery  — Brown: Fib size 1,3,5,8… after losses (STOPS REQUIRED)
- windsor_escalate— Windsor: raise size after losses (UNSAFE unless capped)
- thomas_compound — Thomas: risk fraction of prior win; reset after loss
- brown_dca_size  — Brown DCA spirit as *next-trade* size-up same direction (still with SL)
- forever_safe    — safest high-risk: tiny seed, then risk HOUSE MONEY only; halt on first loss

Safety cage (default ON — this is the "solved" policy):
- Hard clamp: risk_percent ∈ [risk_min, risk_max_cap]
- Max recovery / escalate steps then reset or halt
- Max consecutive losses → halt new entries
- Equity floor vs start → halt
- Forbid true no-stop grids

Honest limit (Douglas/Tharp/Elder): no system is forever 100% WR.
forever_safe maximizes principal survival + aggressive sizing on profits only.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


# Brown loss-recovery style multipliers (relative to base risk %)
BROWN_FIB = (1, 3, 5, 8, 13)


@dataclass
class HighRiskController:
    mode: str = "traditional"
    base_risk_percent: float = 1.0
    # Safety cage
    safe: bool = True
    risk_min: float = 0.25
    risk_max_cap: float = 5.0  # never risk more than this % when safe
    max_steps: int = 3  # recovery/escalate depth before reset
    max_consecutive_losses: int = 4
    equity_floor_frac: float = 0.50  # halt if equity < 50% of start
    allow_unsafe: bool = False  # must be True to run uncapped windsor/dca
    thomas_win_frac: float = 0.25  # Thomas: risk this fraction of prior win $
    windsor_step_pct: float = 1.0  # add this many risk-% points per loss day/trade
    # forever_safe: protected principal + aggressive risk bankroll
    seed_risk_percent: float = 1.0  # legacy seed % if bankroll mode off
    house_money_frac: float = 0.50  # fraction of risk bankroll to risk per trade
    halt_on_first_loss: bool = False
    risk_bankroll_frac: float = 0.20  # % of start ring-fenced as riskable capital
    use_risk_bankroll: bool = False
    # State
    start_equity: float = 0.0
    step: int = 0
    consec_losses: int = 0
    last_win_pnl: float = 0.0
    halted: bool = False
    halt_reason: str = ""
    peak_equity: float = 0.0
    history: list[dict[str, Any]] = field(default_factory=list)
    trades_taken: int = 0
    risk_bankroll: float = 0.0  # dollars currently allowed to risk
    protected_principal: float = 0.0

    @classmethod
    def from_config(cls, cfg: dict[str, Any], start_equity: float) -> "HighRiskController":
        mode = str(cfg.get("high_risk_mode") or cfg.get("hr_mode") or "traditional").lower()
        safe = bool(cfg.get("high_risk_safe", True))
        allow_unsafe = bool(cfg.get("allow_unsafe_high_risk", False))
        # If user picks dangerous mode without allow_unsafe, force safe cage + remap
        if mode in {"windsor_escalate", "brown_dca_size", "windsor"} and not allow_unsafe:
            safe = True
        forever = mode in {"forever_safe", "principal_safe", "safe_high_risk"}
        if forever:
            safe = True
            allow_unsafe = False
        bankroll_frac = float(cfg.get("hr_risk_bankroll_frac", 0.20 if forever else 0.0))
        use_bankroll = bool(cfg.get("hr_use_risk_bankroll", forever))
        start = float(start_equity)
        bankroll = start * bankroll_frac if use_bankroll and forever else 0.0
        protected = start - bankroll if use_bankroll and forever else start
        return cls(
            mode=mode,
            base_risk_percent=float(cfg.get("risk_percent", 1.0)),
            safe=safe,
            risk_min=float(cfg.get("hr_risk_min", 0.25)),
            risk_max_cap=float(cfg.get("hr_risk_max_cap", 5.0 if not forever else 100.0)),
            max_steps=int(cfg.get("hr_max_steps", 3)),
            max_consecutive_losses=int(
                cfg.get("hr_max_consecutive_losses", 1 if forever else 4)
            ),
            equity_floor_frac=float(cfg.get("hr_equity_floor_frac", (protected / start) if forever and start > 0 else 0.50)),
            allow_unsafe=allow_unsafe,
            thomas_win_frac=float(cfg.get("hr_thomas_win_frac", 0.25)),
            windsor_step_pct=float(cfg.get("hr_windsor_step_pct", 1.0)),
            seed_risk_percent=float(cfg.get("hr_seed_risk_percent", cfg.get("risk_percent", 1.0))),
            house_money_frac=float(cfg.get("hr_house_money_frac", 1.0 if forever else 0.50)),
            halt_on_first_loss=bool(cfg.get("hr_halt_on_first_loss", forever)),
            risk_bankroll_frac=bankroll_frac,
            use_risk_bankroll=use_bankroll and forever,
            start_equity=start,
            peak_equity=start,
            risk_bankroll=bankroll,
            protected_principal=protected,
        )

    def _clamp(self, risk_pct: float) -> float:
        if not self.safe and self.allow_unsafe:
            return max(0.0, float(risk_pct))
        return float(min(self.risk_max_cap, max(self.risk_min, risk_pct)))

    def _forever_safe_risk_pct(self, equity: float) -> float:
        """
        High risk inside a ring-fenced bankroll; protected principal never sized.
        Cap risk_$ so a full stop cannot push equity below protected_principal
        (cost buffer included).
        """
        if equity <= 0:
            return 0.0
        if self.use_risk_bankroll:
            if self.risk_bankroll <= 0:
                return 0.0
            frac = max(0.0, min(1.0, self.house_money_frac))
            # Never risk more than bankroll, and never more than (equity - protected)
            room = max(0.0, equity - self.protected_principal)
            risk_dollars = min(self.risk_bankroll * frac, self.risk_bankroll, room)
            risk_dollars *= 0.90  # leave buffer for spread/slip so floor holds
            if risk_dollars <= 0:
                return 0.0
            return float(min(self.risk_max_cap, 100.0 * risk_dollars / equity))
        profits = equity - self.start_equity
        if profits <= 0:
            return float(min(self.risk_max_cap, max(0.0, self.seed_risk_percent)))
        risk_dollars = min(profits, profits * max(0.0, min(1.0, self.house_money_frac))) * 0.90
        return float(min(self.risk_max_cap, max(0.0, 100.0 * risk_dollars / equity)))

    def check_equity(self, equity: float) -> bool:
        if equity > self.peak_equity:
            self.peak_equity = equity
        if self.start_equity > 0 and equity < self.start_equity * self.equity_floor_frac:
            self.halted = True
            self.halt_reason = f"equity_floor ({equity:.2f} < {self.equity_floor_frac:.0%} of start)"
            return False
        return not self.halted

    def allow(self, equity: float) -> tuple[bool, str]:
        if self.halted:
            return False, self.halt_reason or "hr_halted"
        if not self.check_equity(equity):
            return False, self.halt_reason
        if self.consec_losses >= self.max_consecutive_losses:
            self.halted = True
            self.halt_reason = f"max_consecutive_losses ({self.consec_losses})"
            return False, self.halt_reason
        return True, "ok"

    def effective_risk_percent(self, equity: float) -> float:
        """Risk % of equity for the next entry."""
        mode = self.mode
        if mode in {"forever_safe", "principal_safe", "safe_high_risk"}:
            return self._forever_safe_risk_pct(equity)

        if mode in {"traditional", "safe", "brown_traditional", ""}:
            return self._clamp(self.base_risk_percent)

        if mode in {"fuller_pyramid", "fuller"}:
            return self._clamp(self.base_risk_percent)

        if mode in {"brown_recovery", "recovery"}:
            idx = min(self.step, len(BROWN_FIB) - 1)
            if self.step >= self.max_steps and self.safe:
                return self._clamp(self.base_risk_percent)
            return self._clamp(self.base_risk_percent * BROWN_FIB[idx])

        if mode in {"windsor_escalate", "windsor"}:
            raw = self.base_risk_percent + self.step * self.windsor_step_pct
            if self.safe and not self.allow_unsafe:
                if self.step >= self.max_steps:
                    return self._clamp(self.base_risk_percent)
                return self._clamp(raw)
            return self._clamp(raw) if self.safe else max(0.0, raw)

        if mode in {"thomas_compound", "thomas"}:
            if self.last_win_pnl > 0 and equity > 0:
                risk_dollars = self.last_win_pnl * self.thomas_win_frac
                pct = 100.0 * risk_dollars / equity
                return self._clamp(max(self.base_risk_percent, pct))
            return self._clamp(self.base_risk_percent)

        if mode in {"thomas_growth", "growth_compound", "100_to_thousands"}:
            # Thomas book speculative account: 1% base; after a win, risk
            # thomas_win_frac of that win $ on the next trade; loss → back to 1%.
            # Growth mode: high cap so streaks can compound (book tables assume ~10R wins).
            if self.last_win_pnl > 0 and equity > 0:
                risk_dollars = self.last_win_pnl * self.thomas_win_frac
                pct = 100.0 * risk_dollars / equity
                if self.safe and not self.allow_unsafe:
                    return self._clamp(max(self.base_risk_percent, pct))
                return max(self.base_risk_percent, pct)
            return self._clamp(self.base_risk_percent) if self.safe else self.base_risk_percent

        if mode in {"brown_dca_size", "dca"}:
            idx = min(self.step, len(BROWN_FIB) - 1)
            if self.safe and self.step >= self.max_steps:
                return self._clamp(self.base_risk_percent)
            return self._clamp(self.base_risk_percent * BROWN_FIB[idx])

        return self._clamp(self.base_risk_percent)

    def on_trade_closed(self, pnl: float, equity: float) -> None:
        self.trades_taken += 1
        if self.use_risk_bankroll and self.mode in {"forever_safe", "principal_safe", "safe_high_risk"}:
            # Resync bankroll to whatever sits above protected floor
            self.risk_bankroll = max(0.0, equity - self.protected_principal)
        self.history.append(
            {
                "pnl": pnl,
                "equity": equity,
                "step": self.step,
                "mode": self.mode,
                "risk_bankroll": self.risk_bankroll,
            }
        )
        if pnl > 0:
            self.consec_losses = 0
            self.last_win_pnl = pnl
            if self.mode in {"brown_recovery", "recovery", "brown_dca_size", "dca", "windsor_escalate", "windsor"}:
                self.step = 0
        else:
            self.consec_losses += 1
            self.last_win_pnl = 0.0
            if self.use_risk_bankroll and self.risk_bankroll <= 1e-6:
                self.halted = True
                self.halt_reason = (
                    f"forever_safe: risk bankroll wiped — protected ${self.protected_principal:.2f} locked"
                )
            elif self.halt_on_first_loss:
                # forever_safe defaults this True; fast configs may set False and
                # rely on bankroll wipe + equity floor instead.
                self.halted = True
                self.halt_reason = "forever_safe: first loss — locked (principal protected)"
            if self.mode in {
                "brown_recovery",
                "recovery",
                "brown_dca_size",
                "dca",
                "windsor_escalate",
                "windsor",
            }:
                self.step += 1
                if self.safe and self.step > self.max_steps:
                    self.step = 0

    def fuller_pyramid_enabled(self) -> bool:
        return self.mode in {"fuller_pyramid", "fuller"}


def forever_safe_policy_config(overrides: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """
    Safest *high-risk* policy from the books:
    - Ring-fence 20% of start as risk bankroll (play money)
    - Risk up to 100% of that bankroll per trade (high risk inside the pocket)
    - 80% principal never sized; halt when bankroll wiped or on first loss
    """
    cfg = {
        "high_risk_mode": "forever_safe",
        "high_risk_safe": True,
        "allow_unsafe_high_risk": False,
        "risk_percent": 20.0,
        "hr_use_risk_bankroll": True,
        "hr_risk_bankroll_frac": 0.20,
        "hr_house_money_frac": 0.50,  # risk half the bankroll — leaves cushion vs costs
        "hr_seed_risk_percent": 20.0,
        "hr_halt_on_first_loss": True,
        "hr_risk_min": 0.0,
        "hr_risk_max_cap": 100.0,
        "hr_max_consecutive_losses": 1,
        "hr_equity_floor_frac": 0.80,  # protected 80% of start
        "pyramid_enabled": False,
        "max_daily_loss_percent": 100.0,  # HR cage owns the halt
        "max_total_drawdown_percent": 100.0,
        "kill_switch": False,
    }
    if overrides:
        cfg.update(overrides)
    return cfg


def solved_policy_config(overrides: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """
    Canonical 'solved high risk' policy combining books:
    - Base risk ≤ 2% (Silvani/Brown/DraKoln)
    - Fuller pyramid allowed (winners only, ≤1R)
    - Recovery/compound/escalate: capped ≤ 5%, max 3 steps, 4 loss halt, 50% equity floor
    - Unsafe uncapped modes OFF
    """
    cfg = {
        "high_risk_mode": "fuller_pyramid",
        "high_risk_safe": True,
        "allow_unsafe_high_risk": False,
        "risk_percent": 2.0,
        "hr_risk_min": 0.5,
        "hr_risk_max_cap": 5.0,
        "hr_max_steps": 3,
        "hr_max_consecutive_losses": 4,
        "hr_equity_floor_frac": 0.50,
        "pyramid_enabled": True,
        "pyramid_max_adds": 2,
        "pyramid_add_r": 1.0,
        "pyramid_adx_min": 22.0,
        "max_daily_loss_percent": 6.0,
        "max_total_drawdown_percent": 20.0,
    }
    if overrides:
        cfg.update(overrides)
    return cfg
