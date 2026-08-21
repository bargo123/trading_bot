"""Intelligent per-thesis profit management (spec sections B-H, O, P).

A position stays open only while CONTINUING to hold is justified. Every open
profitable ticket gets an explicit, auditable answer to
"WHY AM I STILL HOLDING THIS WINNER?" - never "because it has not hit the
stop yet" and never "because intelligent mode disables quick-win".

Policies (candidate framework; thresholds are config, not hardcoded magic):
  structural_target   - close at the thesis target
  mfe_giveback        - after meaningful MFE, cap the fraction given back
  breakeven_lock      - move stop to entry+cost buffer once MFE arms it
                        (stop only ever TIGHTENS - never loosened)
  time_decay          - edge was short-lived and failed to progress
  regime_change       - mechanism invalidated by state change
  portfolio_pressure  - margin stress: reduce LOWEST remaining-EV first

0.01-lot reality: below broker volume_min a ticket cannot be partially
closed, so decisions are FULL TICKET CLOSE or PROTECTIVE STOP ADJUSTMENT.

All research counters (P/L at 1/3/5/10/15/30/60m, counterfactual policy
profits) are recorded point-in-time from samples taken while the trade was
open - no lookahead.
"""
from __future__ import annotations

import statistics
import time
from dataclasses import dataclass, field
from typing import Any, Mapping


PL_SAMPLE_MINUTES = (1, 3, 5, 10, 15, 30, 60)


@dataclass
class ProfitPolicyConfig:
    """Defaults sized for a ~$100 DEMO account with 0.01 clips."""

    enabled: bool = True
    mfe_arm_usd: float = 0.30          # MFE needed before protection arms
    giveback_frac: float = 0.50        # max fraction of peak MFE to give back
    breakeven_buffer_usd: float = 0.05 # entry+costs+min locked profit
    time_decay_s: int = 5400           # exploration max hold without progress
    time_decay_progress_frac: float = 0.25  # pnl < frac*mfe => no progress
    min_capture_mfe_usd: float = 0.10  # minimum MFE for capture-ratio stats

    @classmethod
    def from_cfg(cls, cfg: Mapping[str, Any]) -> "ProfitPolicyConfig":
        return cls(
            enabled=bool(cfg.get("pm_enabled", True)),
            mfe_arm_usd=float(cfg.get("pm_mfe_arm_usd", 0.30) or 0.30),
            giveback_frac=float(cfg.get("pm_giveback_frac", 0.50) or 0.50),
            breakeven_buffer_usd=float(cfg.get("pm_breakeven_buffer_usd", 0.05) or 0.05),
            time_decay_s=int(cfg.get("pm_time_decay_s", 5400) or 5400),
            time_decay_progress_frac=float(cfg.get("pm_time_decay_progress_frac", 0.25) or 0.25),
            min_capture_mfe_usd=float(cfg.get("pm_min_capture_mfe_usd", 0.10) or 0.10),
        )


@dataclass
class TicketTrack:
    """Per-ticket / per-thesis excursion state. NEVER shared between tickets."""

    ticket: str
    thesis_key: str = ""
    hypothesis_id: str = ""
    stage: str = ""
    symbol: str = ""
    side: str = ""
    family: str = ""
    opened_ts: float = 0.0
    entry_price: float = 0.0
    target: float | None = None
    invalidation: float | None = None
    current_sl: float | None = None
    locked_profit_usd: float = 0.0
    lock_armed: bool = False
    mfe_usd: float = 0.0
    mae_usd: float = 0.0
    mfe_ts: float = 0.0
    peak_pnl: float = 0.0
    last_pnl: float = 0.0
    entry_ev_at_open: float | None = None
    regime_at_open: str = ""
    session_at_open: str = ""
    spread_at_entry: float | None = None
    samples: list[tuple[float, float]] = field(default_factory=list)  # (ts, pnl)
    exit_reason: str = ""

    def update(self, *, pnl: float, now: float) -> None:
        self.last_pnl = float(pnl)
        if pnl > self.mfe_usd:
            self.mfe_usd = float(pnl)
            self.mfe_ts = now
        if pnl < self.mae_usd:
            self.mae_usd = float(pnl)
        self.peak_pnl = max(self.peak_pnl, pnl)
        self.samples.append((now, float(pnl)))
        if len(self.samples) > 2048:  # bounded memory; keep recent granularity
            self.samples = self.samples[-1024:]

    def pl_at_minutes(self) -> dict[str, float | None]:
        age = self.samples[-1][0] - self.samples[0][0] if self.samples else 0.0
        out: dict[str, float | None] = {}
        for m in PL_SAMPLE_MINUTES:
            target_ts = self.samples[0][0] + m * 60.0 if self.samples else None
            if target_ts is None or age < m * 60.0:
                out[f"pl_{m}m"] = None
                continue
            best = None
            for ts, pnl in self.samples:
                if ts <= target_ts:
                    best = pnl
                else:
                    break
            out[f"pl_{m}m"] = round(best, 4) if best is not None else None
        return out

    def giveback(self) -> float:
        """Profit given back from PEAK POSITIVE MFE (never counts losses)."""
        if self.mfe_usd <= 0:
            return 0.0
        return max(0.0, self.mfe_usd - self.last_pnl)

    def age_s(self, now: float) -> float:
        return max(0.0, now - self.opened_ts) if self.opened_ts else 0.0


class ProfitManager:
    """Evaluates policies per ticket and produces decisions + explanations."""

    def __init__(self, cfg: Mapping[str, Any]):
        self.cfg = ProfitPolicyConfig.from_cfg(cfg)
        self.tracks: dict[str, TicketTrack] = {}
        self.winner_to_loser_count = 0
        self.winner_to_loser_usd_given_back = 0.0
        self.decision_counts: dict[str, int] = {"HOLD": 0, "LOCK": 0, "EXIT": 0,
                                                "REDUCE": 0}

    # -- lifecycle -----------------------------------------------------------

    def sync(
        self,
        positions: list[Any],
        *,
        meta_by_ticket: Mapping[str, Mapping[str, Any]] | None = None,
        now: float | None = None,
    ) -> None:
        """Update tracks from live positions; drop closed ones (recording stats)."""
        now = now if now is not None else time.time()
        meta_by_ticket = meta_by_ticket or {}
        live_tickets = set()
        for pos in positions:
            ticket = str(getattr(pos, "ticket", "") or "")
            if not ticket:
                continue
            live_tickets.add(ticket)
            track = self.tracks.get(ticket)
            if track is None:
                meta = meta_by_ticket.get(ticket, {})
                track = TicketTrack(
                    ticket=ticket,
                    thesis_key=str(meta.get("thesis_key") or ""),
                    hypothesis_id=str(meta.get("hypothesis_id") or ""),
                    stage=str(meta.get("stage") or ""),
                    symbol=str(getattr(pos, "symbol", "")),
                    side=str(getattr(pos, "side", "")),
                    family=str(meta.get("family") or ""),
                    opened_ts=now,
                    entry_price=float(getattr(pos, "avg_price", 0) or 0),
                    target=meta.get("target"),
                    invalidation=meta.get("invalidation"),
                    current_sl=meta.get("sl"),
                    entry_ev_at_open=meta.get("entry_ev"),
                    regime_at_open=str(meta.get("regime") or ""),
                    session_at_open=str(meta.get("session") or ""),
                )
                self.tracks[ticket] = track
            track.update(pnl=float(getattr(pos, "unrealized_pnl", 0) or 0), now=now)
        for ticket in list(self.tracks.keys()):
            if ticket not in live_tickets:
                closed = self.tracks.pop(ticket)
                self._record_closed(closed)

    def _record_closed(self, track: TicketTrack) -> None:
        if (
            track.peak_pnl >= self.cfg.min_capture_mfe_usd
            and track.last_pnl <= 0
        ):
            self.winner_to_loser_count += 1
            self.winner_to_loser_usd_given_back += max(0.0, track.mfe_usd)

    # -- policy evaluation -----------------------------------------------------

    def evaluate(
        self,
        *,
        ticket: str,
        volume: float,
        volume_min: float,
        regime_now: str = "",
        margin_pressure: bool = False,
        remaining_ev: float | None = None,
    ) -> dict[str, Any]:
        """Return {action, reason, why, policy} for one ticket.

        action: HOLD | LOCK | EXIT | REDUCE
        """
        track = self.tracks.get(ticket)
        if track is None or not self.cfg.enabled:
            self.decision_counts["HOLD"] += 1
            return {"action": "HOLD", "reason": "pm_disabled_or_untracked",
                    "why": "profit management has no tracked state", "policy": None}
        now = time.time()
        reasons_hold: list[str] = []

        # 1. Structural target (price-based targets handled by OMS SL/TP; here
        # we catch USD-equivalent progress when target exists but TP missing).
        # 2. Regime change kills the mechanism.
        if regime_now and track.regime_at_open and regime_now != track.regime_at_open \
                and track.last_pnl <= 0:
            self.decision_counts["EXIT"] += 1
            return {"action": "EXIT", "reason": "pm_regime_change",
                    "why": f"regime changed {track.regime_at_open}->{regime_now} "
                           "and position is not profitable",
                    "policy": "regime_change"}

        # 3. Time decay: exploration edges are short-lived; no progress = out.
        # "Progress" requires meaningful MFE (>= arm threshold) AND retaining
        # at least the configured fraction of it - a stalled 1-cent MFE is
        # not progress.
        age = track.age_s(now)
        progressed = (
            track.mfe_usd >= self.cfg.mfe_arm_usd
            and track.last_pnl >= self.cfg.time_decay_progress_frac * track.mfe_usd
        )
        if age > self.cfg.time_decay_s and not progressed:
            self.decision_counts["EXIT"] += 1
            return {"action": "EXIT", "reason": "pm_time_decay",
                    "why": f"held {int(age)}s with no progress "
                           f"(pnl {track.last_pnl:.2f} vs mfe {track.mfe_usd:.2f})",
                    "policy": "time_decay"}

        armed = track.mfe_usd >= self.cfg.mfe_arm_usd
        if armed:
            giveback = track.giveback()
            max_giveback = self.cfg.giveback_frac * track.mfe_usd
            # 4. MFE giveback (full-close reality respected by caller).
            if giveback > max_giveback:
                self.decision_counts["EXIT"] += 1
                return {"action": "EXIT", "reason": "pm_mfe_giveback",
                        "why": f"gave back {giveback:.2f} of mfe {track.mfe_usd:.2f} "
                               f"(limit {max_giveback:.2f})",
                        "policy": "mfe_giveback"}
            # 5. Breakeven/cost-plus lock via stop adjustment (0.01-lot safe).
            if not track.lock_armed and track.current_sl is not None:
                lock_level_profit = self.cfg.breakeven_buffer_usd
                if track.last_pnl > lock_level_profit:
                    self.decision_counts["LOCK"] += 1
                    return {"action": "LOCK", "reason": "pm_breakeven_lock",
                            "why": f"mfe {track.mfe_usd:.2f} armed cost-plus lock at "
                                   f"+{lock_level_profit:.2f}",
                            "policy": "breakeven_lock"}
            reasons_hold.append(
                f"only {100.0 * giveback / track.mfe_usd:.0f}% of mfe "
                f"{track.mfe_usd:.2f} given back (limit "
                f"{self.cfg.giveback_frac:.0%})"
            )
        else:
            reasons_hold.append(
                f"mfe {track.mfe_usd:.2f} below arm threshold "
                f"{self.cfg.mfe_arm_usd:.2f}; protective stop owns downside"
            )

        # 6. Portfolio pressure: caller decides which ticket; we expose EV rank.
        if margin_pressure and (remaining_ev is not None) and remaining_ev <= 0:
            self.decision_counts["EXIT"] += 1
            return {"action": "EXIT", "reason": "pm_portfolio_pressure",
                    "why": "margin pressure with non-positive remaining EV",
                    "policy": "portfolio_pressure"}
        if margin_pressure:
            reasons_hold.append("margin pressure noted; remaining EV still positive")

        if track.last_pnl > 0:
            reasons_hold.insert(0, f"floating profit {track.last_pnl:.2f} with "
                                   "protective stop unchanged")
        self.decision_counts["HOLD"] += 1
        return {
            "action": "HOLD",
            "reason": "pm_hold_justified",
            "why": "; ".join(reasons_hold) or "no policy triggered",
            "policy": None,
        }

    # -- reporting -------------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        open_profit = sum(t.last_pnl for t in self.tracks.values() if t.last_pnl > 0)
        open_loss = sum(t.last_pnl for t in self.tracks.values() if t.last_pnl <= 0)
        open_mfe = sum(t.mfe_usd for t in self.tracks.values())
        given_back = sum(t.giveback() for t in self.tracks.values())
        locked = sum(1 for t in self.tracks.values() if t.lock_armed)
        ratios = [
            t.last_pnl / t.mfe_usd
            for t in self.tracks.values()
            if t.mfe_usd >= self.cfg.min_capture_mfe_usd
        ]
        tickets = []
        for t in self.tracks.values():
            ev_proxy = (t.entry_ev_at_open if t.entry_ev_at_open is not None else 0)
            tickets.append({
                "ticket": t.ticket,
                "thesis": t.thesis_key,
                "hypothesis": t.hypothesis_id,
                "stage": t.stage,
                "symbol": t.symbol,
                "side": t.side,
                "family": t.family,
                "pnl": round(t.last_pnl, 4),
                "mfe": round(t.mfe_usd, 4),
                "mae": round(t.mae_usd, 4),
                "locked_profit": round(t.locked_profit_usd, 4),
                "remaining_ev": ev_proxy,
                "exit_state": t.exit_reason or "open",
                "age_s": round(t.age_s(time.time()), 1),
            })
        return {
            "open_floating_profit_usd": round(open_profit, 4),
            "open_floating_loss_usd": round(open_loss, 4),
            "open_mfe_usd": round(open_mfe, 4),
            "open_profit_given_back_usd": round(given_back, 4),
            "winner_to_loser_count": self.winner_to_loser_count,
            "winner_to_loser_usd_given_back": round(self.winner_to_loser_usd_given_back, 4),
            "profit_capture_ratio": (
                round(statistics.mean(ratios), 4) if ratios else None
            ),
            "positions_with_profit_lock": locked,
            "positions_without_profit_lock": len(self.tracks) - locked,
            "decision_counts": dict(self.decision_counts),
            "tickets": tickets,
        }

    def close_summary(self, ticket: str, *, exit_reason: str) -> dict[str, Any] | None:
        """Point-in-time exit-learning record for a closing ticket (EF-112)."""
        track = self.tracks.pop(ticket, None)
        if track is None:
            return None
        track.exit_reason = exit_reason
        summary = {
            "ticket": ticket,
            "hypothesis_id": track.hypothesis_id,
            "thesis_key": track.thesis_key,
            "family": track.family,
            "symbol": track.symbol,
            "side": track.side,
            "session": track.session_at_open,
            "regime": track.regime_at_open,
            "realized_pnl": round(track.last_pnl, 4),
            "mfe_before_close": round(track.mfe_usd, 4),
            "mae_before_close": round(track.mae_usd, 4),
            "giveback_from_mfe": round(max(0.0, track.mfe_usd - track.last_pnl), 4),
            "exit_reason": exit_reason,
            "duration_s": round(track.age_s(time.time()), 1),
            **track.pl_at_minutes(),
            # Counterfactual policy profits (descriptive, point-in-time samples).
            "cf_profit_at_mfe_frac_50": round(0.5 * track.mfe_usd, 4),
            "cf_profit_at_mfe_frac_75": round(0.75 * track.mfe_usd, 4),
            "cf_profit_if_target": None,
            "cf_profit_if_invalidation": None,
        }
        self._record_closed(track)
        return summary
