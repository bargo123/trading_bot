from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from aegis.data import add_spread_proxy, fetch_ohlcv
from aegis.high_risk import HighRiskController
from aegis.journal import append_journal
from aegis.risk import RiskEngine
from aegis.strategy import latest_signal

logger = logging.getLogger(__name__)


@dataclass
class PaperPosition:
    side: str
    mode: str
    entry: float
    sl: float
    tp: float | None
    trail_atr_mult: float | None
    units: float
    reason: str
    risk_pct: float = 0.0


@dataclass
class PaperBroker:
    equity: float
    position: PaperPosition | None = None
    history: list[dict[str, Any]] = field(default_factory=list)

    def close(self, price: float, reason: str) -> float:
        assert self.position is not None
        pos = self.position
        move = (price - pos.entry) if pos.side == "buy" else (pos.entry - price)
        pnl = pos.units * move
        self.equity += pnl
        self.history.append(
            {
                "side": pos.side,
                "entry": pos.entry,
                "exit": price,
                "pnl": pnl,
                "reason": reason,
                "risk_pct": pos.risk_pct,
            }
        )
        self.position = None
        return pnl


class PaperBot:
    def __init__(self, cfg: dict[str, Any], journal_path) -> None:
        self.cfg = cfg
        self.risk = RiskEngine.from_config(cfg)
        start = float(cfg.get("starting_equity", 10_000))
        self.broker = PaperBroker(equity=start)
        self.hr = HighRiskController.from_config(cfg, start)
        self.journal_path = journal_path
        self.start_equity = start
        self.protected = float(getattr(self.hr, "protected_principal", start * 0.8))

    def manage_open(self, bar: dict[str, Any]) -> None:
        pos = self.broker.position
        if pos is None:
            return
        high, low, close = float(bar["high"]), float(bar["low"]), float(bar["close"])
        atr_v = float(bar.get("atr") or 0)
        if pos.trail_atr_mult and atr_v > 0:
            if pos.side == "buy":
                pos.sl = max(pos.sl, close - pos.trail_atr_mult * atr_v)
            else:
                pos.sl = min(pos.sl, close + pos.trail_atr_mult * atr_v)

        pnl = None
        how = None
        if pos.side == "buy":
            if low <= pos.sl:
                pnl = self.broker.close(pos.sl, "sl")
                how = "sl"
            elif pos.tp is not None and high >= pos.tp:
                pnl = self.broker.close(pos.tp, "tp")
                how = "tp"
        else:
            if high >= pos.sl:
                pnl = self.broker.close(pos.sl, "sl")
                how = "sl"
            elif pos.tp is not None and low <= pos.tp:
                pnl = self.broker.close(pos.tp, "tp")
                how = "tp"
        if pnl is not None and how is not None:
            self.hr.on_trade_closed(pnl, self.broker.equity)
            append_journal(
                self.journal_path,
                {
                    "event": "exit",
                    "pnl": pnl,
                    "how": how,
                    "equity": self.broker.equity,
                    "hr_halt": self.hr.halted,
                    "hr_reason": self.hr.halt_reason,
                    "risk_bankroll": self.hr.risk_bankroll,
                    "protected": self.protected,
                },
            )

    def step_once(self) -> None:
        from aegis.strategy import prepare

        df = fetch_ohlcv(self.cfg["symbol"], self.cfg["timeframe"], int(self.cfg.get("lookback_days", 365)))
        df = add_spread_proxy(df, float(self.cfg.get("spread_bps", 1.0)))
        frame = prepare(df, self.cfg)
        bar = frame.iloc[-2].to_dict()
        self.manage_open(bar)

        open_n = 0 if self.broker.position is None else 1
        ok, reason = self.risk.allow(self.broker.equity, open_n)
        if not ok:
            logger.info("No new entries: %s", reason)
            return
        hr_ok, hr_reason = self.hr.allow(self.broker.equity)
        if not hr_ok:
            logger.info("HR halt — no new entries: %s", hr_reason)
            return
        if self.broker.position is not None:
            return

        sig = latest_signal(df, self.cfg)
        if sig is None:
            logger.info("No signal")
            return
        if abs(sig.entry - sig.sl) <= 0:
            logger.info("Skip — no stop")
            return

        risk_pct = self.hr.effective_risk_percent(self.broker.equity)
        units = self.risk.size_units(
            self.broker.equity,
            sig.entry,
            sig.sl,
            min_stop=abs(sig.entry) * float(self.cfg.get("min_atr_pct", 0.0004)),
            risk_percent=risk_pct,
        )
        if units <= 0:
            logger.info("Skip — zero size")
            return
        self.broker.position = PaperPosition(
            side=sig.side,
            mode=sig.mode,
            entry=sig.entry,
            sl=sig.sl,
            tp=sig.tp,
            trail_atr_mult=sig.trail_atr_mult,
            units=units,
            reason=sig.reason,
            risk_pct=risk_pct,
        )
        append_journal(
            self.journal_path,
            {
                "event": "entry",
                "side": sig.side,
                "mode": sig.mode,
                "reason": sig.reason,
                "entry": sig.entry,
                "sl": sig.sl,
                "tp": sig.tp,
                "units": units,
                "risk_pct": risk_pct,
                "equity": self.broker.equity,
                "risk_bankroll": self.hr.risk_bankroll,
                "protected": self.protected,
            },
        )
        logger.info(
            "PAPER ENTRY %s %s @ %.5f SL=%.5f risk=%.2f%% equity=%.2f bankroll=%.2f",
            sig.mode,
            sig.side,
            sig.entry,
            sig.sl,
            risk_pct,
            self.broker.equity,
            self.hr.risk_bankroll,
        )

    def run_forever(self) -> None:
        poll = float(self.cfg.get("poll_seconds", 60))
        logger.info("Paper bot started symbol=%s tf=%s", self.cfg["symbol"], self.cfg["timeframe"])
        try:
            while True:
                try:
                    self.step_once()
                except Exception:
                    logger.exception("step failed")
                time.sleep(poll)
        except KeyboardInterrupt:
            logger.info("Stopped. Equity=%.2f", self.broker.equity)
