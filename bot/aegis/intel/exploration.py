"""Exploration Firehose: registered falsifiable experiments + hard limits.

EXPLORATION_CANARY exists so Aegis can actively TEST many falsifiable
hypotheses with tiny bounded DEMO exposure instead of waiting indefinitely for
historical validation. An exploration trade is INFORMATION GAIN, never profit,
never validation.

Every exploration order MUST correspond to a registered experiment record with
a stable hypothesis_id. Sequential evidence updates after every closed trade;
bad experiments are REJECTED permanently and remembered (failed-experiment
memory blocks rediscovery of the same idea).

Hard limits are independent of champion/canary limits and conservative for a
~$100 DEMO account by default. Exploration can NEVER:
  martingale / average down / recover losses / size up when behind /
  bypass max positions or currency concentration / bypass stale-quote or
  spread checks / touch a live account.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

EXPERIMENT_SCHEMA = "exploration_experiments.v1"

# Sequential-learning thresholds (per experiment).
# INVARIANT (audited): MIN_N_TO_JUDGE must be <= max_trades_per_hypothesis,
# otherwise runtime judgement is unreachable. Judgement happens at 4 trades;
# the per-hypothesis cap (5) then EXHAUSTS anything still UNCERTAIN.
MIN_N_TO_JUDGE = 4
REJECT_EXPECTANCY = 0.0     # expectancy <= this at judgement -> REJECTED
PROMISE_P05 = 0.0           # bootstrap-ish lower bound > this -> PROMISING

LIFECYCLE_NEW = "NEW"
LIFECYCLE_ACTIVE = "ACTIVE"
LIFECYCLE_UNCERTAIN = "UNCERTAIN"
LIFECYCLE_PROMISING = "PROMISING"
LIFECYCLE_REJECTED = "REJECTED"
LIFECYCLE_EXHAUSTED = "EXHAUSTED"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def hypothesis_id(*, strategy_family: str, symbol: str, side: str,
                  regime: str, session: str) -> str:
    """Stable identity of a falsifiable idea (NOT timestamp-based)."""
    blob = "|".join([
        str(strategy_family).lower(), str(symbol).upper(), str(side).lower(),
        str(regime).lower(), str(session).lower(),
    ])
    return "exp_" + hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


@dataclass
class ExplorationLimits:
    """Independent hard limits for exploration exposure (DEMO only)."""

    max_positions: int = 2
    max_positions_per_symbol: int = 1
    max_daily_loss_usd: float = 1.0
    max_risk_per_trade_usd: float = 0.15
    max_trades_per_hypothesis: int = 5
    cooldown_after_failure_s: int = 1800

    @classmethod
    def from_cfg(cls, cfg: Mapping[str, Any]) -> "ExplorationLimits":
        daily_loss_limit = cfg.get("exploration_max_daily_loss_usd", 1.0)
        if daily_loss_limit is None:
            daily_loss_limit = 1.0
        return cls(
            max_positions=int(cfg.get("exploration_max_positions", 2) or 2),
            max_positions_per_symbol=int(cfg.get("exploration_max_positions_per_symbol", 1) or 1),
            max_daily_loss_usd=float(daily_loss_limit),
            max_risk_per_trade_usd=float(cfg.get("exploration_max_risk_per_trade_usd", 0.15) or 0.15),
            max_trades_per_hypothesis=int(cfg.get("exploration_max_trades_per_hypothesis", 5) or 5),
            cooldown_after_failure_s=int(cfg.get("exploration_cooldown_after_failure_s", 1800) or 1800),
        )


def _p05_lower_bound(pnls: list[float]) -> float | None:
    import math

    values = [float(v) for v in pnls]
    n = len(values)
    if n < 2:
        return None
    avg = sum(values) / n
    sigma = math.sqrt(sum((v - avg) ** 2 for v in values) / n)
    return avg - 1.96 * (sigma / math.sqrt(n))


class ExperimentStore:
    """Persistent registry of exploration experiments + sequential evidence."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.data: dict[str, Any] = self._load()

    def _load(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(payload, dict) and payload.get("schema") == EXPERIMENT_SCHEMA:
                return payload
        except (OSError, json.JSONDecodeError):
            pass
        return {"schema": EXPERIMENT_SCHEMA, "experiments": {}, "daily": {}}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(self.path)

    # -- registration ------------------------------------------------------

    def identity_key(self, *, strategy_family: str, symbol: str, side: str,
                     regime: str, session: str) -> str:
        return "|".join([
            str(strategy_family).lower(), str(symbol).upper(), str(side).lower(),
            str(regime).lower(), str(session).lower(),
        ])

    def has_failed_identity(self, *, strategy_family: str, symbol: str, side: str,
                            regime: str, session: str) -> dict[str, Any] | None:
        """Failed-experiment memory: same strategy/params/state that was rejected."""
        key = self.identity_key(
            strategy_family=strategy_family, symbol=symbol, side=side,
            regime=regime, session=session,
        )
        for rec in self.data["experiments"].values():
            if rec.get("identity_key") == key and rec.get("status") == "REJECTED":
                return rec
        return None

    def register(self, candidate: Mapping[str, Any], *, reason: str,
                 mechanism: str, provenance: str = "market_state") -> tuple[dict[str, Any], bool]:
        """Register (or return existing) experiment. Returns (record, created)."""
        hyp_id = str(candidate["hypothesis_id"])
        existing = self.data["experiments"].get(hyp_id)
        if existing is not None:
            return existing, False
        record = {
            "hypothesis_id": hyp_id,
            "identity_key": self.identity_key(
                strategy_family=str(candidate.get("strategy_family") or ""),
                symbol=str(candidate.get("symbol") or ""),
                side=str(candidate.get("side") or ""),
                regime=str(candidate.get("regime") or ""),
                session=str(candidate.get("session") or ""),
            ),
            "strategy_family": candidate.get("strategy_family"),
            "symbol": candidate.get("symbol"),
            "side": candidate.get("side"),
            "entry_rule": candidate.get("entry_rule"),
            "invalidation_rule": candidate.get("invalidation"),
            "target_rule": candidate.get("target"),
            "regime": candidate.get("regime"),
            "session": candidate.get("session"),
            "information_id": candidate.get("information_id"),
            "reason_for_experiment": reason,
            "expected_mechanism": mechanism,
            "provenance": provenance,
            "status": LIFECYCLE_NEW,
            "created_utc": _utcnow().isoformat(),
            "updated_utc": _utcnow().isoformat(),
            "trades": [],
            "evidence": self._empty_evidence(),
        }
        self.data["experiments"][hyp_id] = record
        self.save()
        return record, True

    @staticmethod
    def _empty_evidence() -> dict[str, Any]:
        return {
            "n": 0, "wins": 0, "losses": 0,
            "expectancy": None, "profit_factor": None,
            "avg_win": None, "avg_loss": None, "payoff": None,
            "mfe_avg": None, "mae_avg": None,
            "spread_avg": None, "slippage_avg": None,
            "duration_min_avg": None, "sessions": {}, "regimes": {},
            "max_drawdown": 0.0, "bootstrap_p05": None,
        }

    # -- sequential learning -------------------------------------------------

    def record_close(self, hypothesis_id: str, pnl: float,
                     mfe: float | None = None, mae: float | None = None,
                     spread: float | None = None, slippage: float | None = None,
                     duration_min: float | None = None,
                     session: str = "", regime: str = "",
                     max_trades: int | None = None,
                     **extra: Any) -> dict[str, Any] | None:
        """Update one experiment's evidence after a closed trade, then judge it.

        ``max_trades`` passes the runtime per-hypothesis cap so EXHAUSTED is
        reachable in the SAME lifecycle that enforces the cap (audited fix).
        ``extra`` carries point-in-time exit-learning fields (pl_1m..pl_60m,
        cf_* counterfactual policy profits) stored on the trade row (EF-112).
        """
        rec = self.data["experiments"].get(hypothesis_id)
        if rec is None:
            return None
        ev = rec["evidence"]
        pnl = float(pnl)
        ev["n"] += 1
        if pnl > 0:
            ev["wins"] += 1
        else:
            ev["losses"] += 1
        trades = rec.setdefault("trades", [])
        trades.append({
            "pnl": round(pnl, 4),
            "ts_utc": _utcnow().isoformat(),
            "session": session, "regime": regime,
            **{k: v for k, v in extra.items() if v is not None},
        })
        pnls = [t["pnl"] for t in trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]
        ev["expectancy"] = round(sum(pnls) / len(pnls), 5)
        ev["avg_win"] = round(sum(wins) / len(wins), 4) if wins else None
        ev["avg_loss"] = round(sum(losses) / len(losses), 4) if losses else None
        gross_win = sum(wins)
        gross_loss = abs(sum(losses))
        ev["profit_factor"] = (
            round(gross_win / gross_loss, 4) if gross_loss > 0 else
            (None if gross_win == 0 else 99.0)
        )
        if ev["avg_win"] and ev["avg_loss"]:
            ev["payoff"] = round(abs(ev["avg_win"] / ev["avg_loss"]), 4)
        if mfe is not None:
            ev["mfe_avg"] = round(
                ((ev["mfe_avg"] or 0.0) * (ev["n"] - 1) + float(mfe)) / ev["n"], 4)
        if mae is not None:
            ev["mae_avg"] = round(
                ((ev["mae_avg"] or 0.0) * (ev["n"] - 1) + float(mae)) / ev["n"], 4)
        if spread is not None:
            ev["spread_avg"] = round(
                ((ev["spread_avg"] or 0.0) * (ev["n"] - 1) + float(spread)) / ev["n"], 5)
        if slippage is not None:
            ev["slippage_avg"] = round(
                ((ev["slippage_avg"] or 0.0) * (ev["n"] - 1) + float(slippage)) / ev["n"], 5)
        if duration_min is not None:
            ev["duration_min_avg"] = round(
                ((ev["duration_min_avg"] or 0.0) * (ev["n"] - 1) + float(duration_min)) / ev["n"], 2)
        if session:
            ev["sessions"][session] = ev["sessions"].get(session, 0) + 1
        if regime:
            ev["regimes"][regime] = ev["regimes"].get(regime, 0) + 1
        equity = 0.0
        peak = 0.0
        dd = 0.0
        for p in pnls:
            equity += p
            peak = max(peak, equity)
            dd = min(dd, equity - peak)
        ev["max_drawdown"] = round(dd, 4)
        ev["bootstrap_p05"] = (
            round(_p05_lower_bound(pnls), 5) if len(pnls) >= 2 else None
        )
        rec["updated_utc"] = _utcnow().isoformat()
        self._judge(rec, max_trades=max_trades)
        self._track_daily(pnl)
        self.save()
        return rec

    def _judge(self, rec: dict[str, Any], *, max_trades: int | None = None) -> None:
        """Sequential decision with a REACHABLE lifecycle (audited fix).

        NEW -> ACTIVE (first close)
        at n >= MIN_N_TO_JUDGE:
            expectancy <= 0                  -> REJECTED (permanent)
            p05 > 0 and PF > 1               -> PROMISING (route to validation)
            otherwise                        -> UNCERTAIN
        UNCERTAIN at the per-hypothesis cap  -> EXHAUSTED (information spent)
        """
        ev = rec["evidence"]
        if rec.get("status") in {LIFECYCLE_REJECTED, LIFECYCLE_PROMISING,
                                 LIFECYCLE_EXHAUSTED}:
            return
        if ev["n"] >= 1 and rec.get("status") == LIFECYCLE_NEW:
            rec["status"] = LIFECYCLE_ACTIVE
        if ev["n"] >= MIN_N_TO_JUDGE:
            if float(ev["expectancy"] or 0.0) <= REJECT_EXPECTANCY:
                rec["status"] = LIFECYCLE_REJECTED
                rec["reject_reason"] = (
                    f"negative expectancy {ev['expectancy']} after {ev['n']} trades"
                )
                return
            p05 = ev.get("bootstrap_p05")
            pf = ev.get("profit_factor")
            if p05 is not None and float(p05) > PROMISE_P05 and pf and float(pf) > 1:
                rec["status"] = LIFECYCLE_PROMISING
                return
            rec["status"] = LIFECYCLE_UNCERTAIN
        if max_trades is not None and ev["n"] >= max_trades \
                and rec.get("status") in {LIFECYCLE_ACTIVE, LIFECYCLE_UNCERTAIN}:
            rec["status"] = LIFECYCLE_EXHAUSTED
            rec["exhaust_reason"] = (
                f"reached per-hypothesis cap ({max_trades}) without promising evidence"
            )

    def _track_daily(self, pnl: float) -> None:
        today = date.today().isoformat()
        daily = self.data.setdefault("daily", {})
        day = daily.get(today) or {"pnl": 0.0, "trades": 0}
        day["pnl"] = round(float(day["pnl"]) + float(pnl), 4)
        day["trades"] = int(day["trades"]) + 1
        daily[today] = day

    def daily_pnl(self) -> float:
        today = date.today().isoformat()
        day = (self.data.get("daily") or {}).get(today) or {}
        return float(day.get("pnl") or 0.0)

    # -- limit checks ---------------------------------------------------------

    def hypothesis_trade_count(self, hypothesis_id: str) -> int:
        rec = self.data["experiments"].get(hypothesis_id)
        return int(rec["evidence"]["n"]) if rec else 0

    def hypothesis_cooldown_active(self, hypothesis_id: str) -> bool:
        rec = self.data["experiments"].get(hypothesis_id)
        if not rec:
            return False
        last = rec.get("last_failure_utc")
        if not last:
            return False
        try:
            ts = datetime.fromisoformat(last)
        except ValueError:
            return False
        return (_utcnow() - ts).total_seconds() < 0  # set by caller via cfg

    def note_failure(self, hypothesis_id: str, cooldown_s: int) -> None:
        rec = self.data["experiments"].get(hypothesis_id)
        if rec is None:
            return
        rec["last_failure_utc"] = _utcnow().isoformat()
        rec["cooldown_until_utc"] = (
            _utcnow() + timedelta(seconds=cooldown_s)
        ).isoformat()
        self.save()

    # -- broker-side close attribution ---------------------------------------

    def migrate_legacy(self, *, max_trades: int) -> dict[str, int]:
        """Deterministic one-shot migration of pre-lifecycle experiments.

        Applies the NEW judgement to existing evidence WITHOUT inventing
        trades. ACTIVE records at/over the per-hypothesis cap without proof
        become EXHAUSTED; those meeting reject/promising rules classify now;
        genuinely under-evidenced ones stay ACTIVE.
        """
        counts: dict[str, int] = {}
        for rec in self.data.get("experiments", {}).values():
            before = str(rec.get("status") or "")
            if before in {LIFECYCLE_REJECTED, LIFECYCLE_PROMISING,
                          LIFECYCLE_EXHAUSTED}:
                counts["already_final:" + before] = counts.get(
                    "already_final:" + before, 0) + 1
                continue
            n = int((rec.get("evidence") or {}).get("n") or 0)
            self._judge(rec, max_trades=max_trades)
            after = str(rec.get("status") or "")
            key = f"{before}->{after}"
            counts[key] = counts.get(key, 0) + 1
            rec["lifecycle_migrated_from"] = before
        self.data["migration_version"] = "legacy_migration.v1"
        self.data["migration_utc"] = _utcnow().isoformat()
        self.save()
        return counts

    def remember_position(self, position_id: str, hypothesis_id: str) -> None:
        """Map an open position to its experiment so SL/TP closes (whose deal
        comment MT5 overwrites with '[sl ...]'/'[tp ...]') still attribute."""
        if not position_id or not hypothesis_id:
            return
        self.data.setdefault("position_map", {})[str(position_id)] = str(hypothesis_id)

    def hypothesis_for_position(self, position_id: str) -> str | None:
        return (self.data.get("position_map") or {}).get(str(position_id))

    def cooldown_active(self, hypothesis_id: str, cooldown_s: int) -> bool:
        rec = self.data["experiments"].get(hypothesis_id)
        if not rec:
            return False
        until = rec.get("cooldown_until_utc")
        if not until:
            return False
        try:
            return datetime.fromisoformat(until) > _utcnow()
        except ValueError:
            return False


def check_exploration_limits(
    limits: ExplorationLimits,
    store: ExperimentStore,
    *,
    hypothesis_id: str,
    open_positions_total: int,
    open_positions_symbol: int,
    exploration_open_total: int,
    exploration_open_symbol: int,
) -> tuple[bool, str]:
    """All limits must pass; each rejection reason is specific."""
    if exploration_open_total >= limits.max_positions:
        return False, f"exploration_max_positions:{exploration_open_total}"
    if exploration_open_symbol >= limits.max_positions_per_symbol:
        return False, "exploration_max_positions_per_symbol"
    if limits.max_daily_loss_usd > 0 and store.daily_pnl() <= -limits.max_daily_loss_usd:
        return False, f"exploration_max_daily_loss_usd:{store.daily_pnl():.2f}"
    if store.hypothesis_trade_count(hypothesis_id) >= limits.max_trades_per_hypothesis:
        return False, "exploration_max_trades_per_hypothesis"
    if store.cooldown_active(hypothesis_id, limits.cooldown_after_failure_s):
        return False, "exploration_cooldown_after_failure"
    # Portfolio-level caps remain the caller's pretrade_ok responsibility.
    _ = open_positions_total, open_positions_symbol
    return True, "ok"


def exploration_room_reason(
    *,
    total_open: int,
    symbol_open: int,
    limits: ExplorationLimits,
) -> str | None:
    """Prospective-exposure guard (audited defect 3).

    Pre-send semantics: if broker/brain confirmed exposure ALREADY equals the
    cap, there is NO room for the current order - even before counting its own
    reservation. Returns a rejection reason or None when room exists.
    """
    if int(total_open) >= int(limits.max_positions):
        return f"exploration_max_positions:{int(total_open)}"
    if int(symbol_open) >= int(limits.max_positions_per_symbol):
        return "exploration_max_positions_per_symbol"
    return None


def risk_lots_for_exploration(
    *,
    max_risk_usd: float,
    entry: float,
    invalidation: float,
    pip: float,
    contract_size: float = 100000.0,
    tick_value: float | None = None,
    tick_size: float | None = None,
    volume_min: float = 0.01,
    volume_step: float = 0.01,
) -> dict[str, Any]:
    """Broker-native exploration sizing with a HARD risk budget (spec-correct).

    Risk per lot = stop_distance_price * (tick_value / tick_size) when broker
    tick fields are available, else stop_pips * (pip * contract_size).
    The FINAL order quantity must satisfy
        actual_stop_risk_usd <= max_risk_usd
    or the trade is REJECTED - rounding UP to volume_min that would exceed the
    budget is a refusal, never an order.
    """
    desired = abs(float(max_risk_usd))
    stop_dist = abs(float(entry) - float(invalidation))
    if stop_dist <= 0 or pip <= 0:
        return {"allowed": False, "reason": "exploration_invalid_geometry",
                "lots": 0.0, "desired_risk_usd": desired,
                "actual_min_lot_risk_usd": None}
    if tick_value and tick_size:
        usd_per_price_unit_per_lot = float(tick_value) / float(tick_size)
    else:
        usd_per_price_unit_per_lot = float(contract_size)
    risk_per_lot = stop_dist * usd_per_price_unit_per_lot
    min_lot_risk = risk_per_lot * float(volume_min)
    if min_lot_risk > desired + 1e-12:
        return {"allowed": False,
                "reason": "exploration_min_lot_exceeds_risk_budget",
                "lots": 0.0, "desired_risk_usd": round(desired, 4),
                "actual_min_lot_risk_usd": round(min_lot_risk, 4)}
    step = float(volume_step) or float(volume_min) or 0.01
    lots = int(desired / risk_per_lot / step) * step
    lots = max(float(volume_min), round(lots, 2))
    actual = risk_per_lot * lots
    if actual > desired + 1e-9:  # step rounding must never breach budget
        return {"allowed": False,
                "reason": "exploration_min_lot_exceeds_risk_budget",
                "lots": 0.0, "desired_risk_usd": round(desired, 4),
                "actual_min_lot_risk_usd": round(actual, 4)}
    return {"allowed": True, "reason": "ok", "lots": round(lots, 2),
            "desired_risk_usd": round(desired, 4),
            "actual_min_lot_risk_usd": round(min_lot_risk, 4)}
