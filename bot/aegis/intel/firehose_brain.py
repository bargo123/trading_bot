"""Intelligent Firehose demo brain. Runner imports this module only."""
from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd

from aegis.engines import PositionSnapshot
from aegis.intel.analogue_store import AnalogueStore, is_measured_provenance
from aegis.intel.exploration import (
    ExperimentStore,
    ExplorationLimits,
    check_exploration_limits,
    hypothesis_id as exploration_hypothesis_id,
    risk_lots_for_exploration,
)
from aegis.intel.knowledge_runtime import load_knowledge_rows, match_knowledge
from aegis.intel.lifecycle import exposure_snapshot, pretrade_ok
from aegis.intel.paths import INTEL_DIR, resolve_bot_path
from aegis.intel.state_runtime import build_runtime_state, runtime_signature
from aegis.intel.strategy_model import (
    STAGE_DEMO_CANARY,
    STAGE_DEMO_CHAMPION,
    STAGE_UNVALIDATED_RESEARCH,
    ValidatedStrategyModel,
    strategy_model_ready,
)
from aegis.intel.thesis_fire import ThesisFireDecision, evaluate_thesis_action, evaluate_thesis_fire
from aegis.intel.thesis_sizing import evidence_confidence, size_thesis_clip
from aegis.intel.trade_economics import (
    DEFAULT_MIN_PAYOFF_RATIO,
    TradeEconomics,
    evaluate_trade_economics,
)
from aegis.research.video_style_paper import (
    VideoStyleConfig,
    VideoStyleSignal,
    video_style_geometry,
    video_style_signal,
)


@dataclass
class ThesisMemory:
    """One independent thesis. The reasoning unit is NOT the symbol: two
    validated strategies on the same symbol coexist as separate theses, and a
    thesis owns ONLY the position tickets bound to it (defect 15)."""

    thesis_key: str
    symbol: str
    side: str | None = None
    setup_family: str = ""
    information_id: str | None = None
    current_risk_usd: float = 0.0
    clips: int = 0
    tickets: set[str] = field(default_factory=set)


def thesis_key(symbol: str, side: str | None, setup_family: str,
               regime: str = "", session: str = "") -> str:
    """Stable thesis identity: symbol + side + strategy/setup family + state.

    Two genuinely independent same-side strategies on one symbol produce
    different keys via family and/or state identity.
    """
    return "|".join([
        str(symbol).upper(), str(side or "").lower(),
        str(setup_family or "").lower(), str(regime or "").lower(),
        str(session or "").lower(),
    ])


@dataclass
class DemoBrainState:
    theses: dict[str, ThesisMemory] = field(default_factory=dict)
    # In-flight exploration fires: thesis_key -> [reservation timestamps].
    # A reservation becomes ownership at bind_tickets() or expires (order
    # lifecycle) so the exposure cap cannot be raced within the bar loop.
    exploration_pending: dict[str, list[float]] = field(default_factory=dict)

    PENDING_TTL_S = 180.0

    def expire_pending(self) -> None:
        import time as _time

        now = _time.time()
        for key in list(self.exploration_pending.keys()):
            live = [t for t in self.exploration_pending[key] if now - t <= self.PENDING_TTL_S]
            if live:
                self.exploration_pending[key] = live
            else:
                self.exploration_pending.pop(key, None)

    def get(self, key: str, symbol: str | None = None) -> ThesisMemory:
        mem = self.theses.get(key)
        if mem is None:
            sym = symbol or key.split("|")[0]
            mem = ThesisMemory(thesis_key=key, symbol=str(sym).upper())
            self.theses[key] = mem
        return mem

    def bind_tickets(self, key: str, symbol: str, tickets: Sequence[str]) -> None:
        """Bind freshly opened position tickets to exactly one thesis."""
        mem = self.get(key, symbol)
        wanted = {str(t) for t in tickets if str(t).strip()}
        for other in self.theses.values():
            if other is mem:
                continue
            other.tickets -= wanted
        mem.tickets |= wanted
        # Fill confirmed: the in-flight reservation becomes real ownership.
        self.exploration_pending.pop(key, None)

    def sync_from_positions(self, symbol: str, positions: Sequence[PositionSnapshot], clip_risk: float) -> list[ThesisMemory]:
        """Reconcile open positions into per-thesis memories.

        A thesis owns only its bound tickets. Positions no thesis claims are
        adopted under a single generic held-key per side so exposure accounting
        never loses them - the same positions are never assigned to multiple
        theses (defect 15).
        """
        sym_up = str(symbol).upper()
        open_tickets: dict[str, PositionSnapshot] = {}
        for pos in positions:
            if str(pos.symbol).upper() == sym_up:
                ticket = str(getattr(pos, "ticket", "") or "").strip()
                if ticket:
                    open_tickets[ticket] = pos
        touched: list[ThesisMemory] = []
        claimed: set[str] = set()
        for key, mem in list(self.theses.items()):
            if mem.symbol != sym_up:
                continue
            mine = [t for t in mem.tickets if t in open_tickets]
            if mem.tickets:
                # Owned thesis: exactly its own surviving tickets.
                mem.tickets = set(mine)
                mem.clips = len(mine)
                mem.current_risk_usd = float(clip_risk) * len(mine) if mine else 0.0
                claimed.update(mine)
                if mine:
                    touched.append(mem)
                else:
                    mem.information_id = None
                    mem.side = None
            elif mem.clips > 0:
                # Legacy/unbound exposure: keep counting until it closes.
                still_open = sum(
                    1 for t, pos in open_tickets.items()
                    if t not in claimed and str(pos.side).lower() == str(mem.side or "").lower()
                )
                if still_open:
                    mem.clips = still_open
                    mem.current_risk_usd = max(mem.current_risk_usd, float(clip_risk) * still_open)
                    touched.append(mem)
                else:
                    mem.clips = 0
                    mem.current_risk_usd = 0.0
                    mem.information_id = None
        # Adopt unclaimed positions under ONE held-key per side.
        unclaimed_by_side: dict[str, int] = {}
        sample_side_ticket: dict[str, str] = {}
        for ticket, pos in open_tickets.items():
            if ticket in claimed:
                continue
            side = str(pos.side).lower()
            unclaimed_by_side[side] = unclaimed_by_side.get(side, 0) + 1
            sample_side_ticket.setdefault(side, ticket)
        for side, count in unclaimed_by_side.items():
            key = thesis_key(sym_up, side, "held")
            mem = self.get(key, sym_up)
            mem.side = side
            mem.setup_family = "held"
            mem.clips = count
            mem.current_risk_usd = max(mem.current_risk_usd, float(clip_risk) * count)
            touched.append(mem)
        return touched

    def apply(
        self,
        symbol: str,
        action: str,
        *,
        side: str | None,
        information_id: str | None,
        target_risk: float,
        clips: int | None = None,
        setup_family: str = "",
        regime: str = "",
        session: str = "",
        key: str | None = None,
    ) -> None:
        held = self.get(key or thesis_key(symbol, side, setup_family, regime, session), symbol)
        if action == "exit":
            held.current_risk_usd = 0.0
            held.information_id = None
            held.side = None
            held.clips = 0
            held.tickets.clear()
            return
        if action in {"fire", "scale"}:
            held.side = side
            held.setup_family = setup_family
            held.information_id = information_id
            held.current_risk_usd = max(held.current_risk_usd, float(target_risk))
            if clips is not None:
                held.clips = clips
        elif action == "reduce":
            held.current_risk_usd = float(target_risk)
            if clips is not None:
                held.clips = clips
            if held.current_risk_usd <= 0:
                held.information_id = None
                held.side = None
                held.clips = 0
                held.tickets.clear()


@dataclass(frozen=True)
class DemoDecision:
    action: str
    reason: str
    side: str | None = None
    sl: float | None = None
    tp: float | None = None
    quantity: float | None = None
    expected_net_value: float | None = None
    information_id: str | None = None
    analogue_n: int = 0
    close_clips: int = 0
    journal: Mapping[str, Any] = field(default_factory=dict)


def _information_id(*, symbol: str, side: str, setup: str, invalidation: str, session: str) -> str:
    blob = "|".join([symbol.upper(), side.lower(), setup.lower(), invalidation.lower(), session])
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _geometry(side: str, structure: Mapping[str, Any], pip: float) -> tuple[float | None, float | None]:
    support = structure.get("support")
    resistance = structure.get("resistance")
    if side == "buy":
        if support is None:
            return None, None
        return float(support) - pip, None if resistance is None else float(resistance)
    if side == "sell":
        if resistance is None:
            return None, None
        return float(resistance) + pip, None if support is None else float(support)
    return None, None


def video_style_micro_candidate(
    signal: VideoStyleSignal,
    *,
    entry_price: float,
    pip: float,
    spread_pips: float,
    cfg: VideoStyleConfig,
):
    """Adapt the shared video intent into the existing Firehose gate contract."""
    from aegis.intel.fast_firehose import FirehoseLane, MicroCandidate, firehose_hypothesis_id

    entry = float(entry_price)
    stop, target = video_style_geometry(signal, entry_price=entry, cfg=cfg)
    stop_pips = abs(entry - stop) / max(float(pip), 1e-12)
    target_pips = abs(target - entry) / max(float(pip), 1e-12)
    return MicroCandidate(
        hypothesis_id=firehose_hypothesis_id(
            family="video_style_breakout",
            symbol=signal.symbol,
            side=signal.side,
            regime="",
            session="",
        ),
        family="video_style_breakout",
        symbol=signal.symbol,
        side=signal.side,
        entry_price=entry,
        invalidation=stop,
        target=target,
        max_hold_s=int(cfg.max_hold_s),
        required_regime="",
        required_session="",
        spread_pips=float(spread_pips),
        stop_pips=stop_pips,
        target_pips=target_pips,
        risk_usd_min_lot=0.0,
        lane=FirehoseLane.BROKER_MICRO,
        mechanism="completed-bar breakout with tight stop and larger target",
        falsification="negative net expectancy after measured costs",
    )


def short_horizon_gate(
    prediction: Mapping[str, Any] | None,
    *,
    min_probability: float | None = 0.5,
) -> tuple[bool, str]:
    """Fail-closed gate for an optional calibrated short-horizon prediction."""
    if prediction is None:
        return False, "short_horizon_prediction_missing"
    if str(prediction.get("calibration_status") or "") != "calibrated":
        return False, "short_horizon_not_calibrated"
    if bool(prediction.get("abstain", True)):
        return False, "short_horizon_abstain"
    try:
        probability = float(prediction["probability"])
    except (KeyError, TypeError, ValueError):
        return False, "short_horizon_probability_invalid"
    if probability != probability or not 0.0 <= probability <= 1.0:
        return False, "short_horizon_probability_invalid"
    threshold = min_probability
    if threshold is None:
        threshold = prediction.get("threshold", 0.5)
    try:
        threshold = float(threshold)
    except (TypeError, ValueError):
        return False, "short_horizon_probability_invalid"
    if not 0.0 < threshold < 1.0:
        return False, "short_horizon_probability_invalid"
    if probability < threshold:
        return False, "short_horizon_probability_below_threshold"
    if "decision" in prediction and not bool(prediction["decision"]):
        return False, "short_horizon_negative_prediction"
    if "expected_net_pnl" in prediction:
        try:
            expected = float(prediction["expected_net_pnl"])
        except (TypeError, ValueError):
            return False, "short_horizon_expected_value_invalid"
        if expected != expected or expected <= 0.0:
            return False, "short_horizon_negative_expected_value"
    return True, "short_horizon_eligible"


def _load_strategy(cfg: Mapping[str, Any]) -> ValidatedStrategyModel | None:
    """Load a promoted champion. Only a sealed-validation accepted artifact can
    reach DEMO_CHAMPION stage; anything else returns None (no pseudo-champion)."""
    path = resolve_bot_path(
        cfg.get("intelligent_champion_path"), INTEL_DIR / "intelligent_champion.json"
    )
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if str(payload.get("status") or "") != "accepted":
        return None
    try:
        from aegis.research.intelligent_champion import allowed_states_from_payload

        model = ValidatedStrategyModel(
            strategy_id=str(payload.get("id") or ""),
            promoted=True,
            n_trades=int(payload["n_trades"]),
            n_losses=int(payload["n_losses"]),
            expectancy=float(payload["expectancy"]),
            profit_factor=float(payload["profit_factor"]),
            bootstrap_p05=float(payload.get("bootstrap_p05") or 0.0),
            wins_erased_by_average_loss=float(payload["wins_erased_by_average_loss"]),
            wins_erased_by_tail_loss=float(payload.get("wins_erased_by_tail_loss") or 0.0),
            validated_risk_fraction=payload.get("validated_risk_fraction"),
            artifact_hash=str(payload.get("artifact_hash") or ""),
            allowed_states=allowed_states_from_payload(payload),
            promotion_stage=STAGE_DEMO_CHAMPION,
            dataset_hash=str(payload.get("dataset_hash") or ""),
            validation_hash=str(payload.get("validation_hash") or payload.get("artifact_hash") or ""),
        )
    except (KeyError, TypeError, ValueError):
        return None
    ready, _ = strategy_model_ready(model)
    return model if ready else None


def _load_validated_states(path: Path) -> frozenset[frozenset[str]]:
    """Load the validated-state allowlist written by the research ML pipeline.

    Each entry is a state signature (regime, structure, session, side). An empty
    or missing file means no states are currently validated, so a gated brain
    must not fire on anything.
    """
    from aegis.research.intelligent_champion import STATE_KEYS, state_sig

    target = Path(path)
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return frozenset()
    rows = payload.get("states") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        return frozenset()
    out = set()
    for item in rows:
        if not isinstance(item, dict):
            continue
        if not all(key in item for key in STATE_KEYS):
            continue
        out.add(state_sig(item))
    return frozenset(out)


def _load_validated_opportunities(path: Path) -> dict[str, dict[str, Any]]:
    """Load symbol-aware validated opportunities written by the research pipeline.

    Returns {opportunity_key: record} where key is
    ``symbol|regime|structure|session|side`` for LEVEL A/B records and
    ``*|regime|structure|session|side`` for LEVEL C pooled records that proved
    cross-symbol homogeneity. Missing/corrupt file -> empty (gate closed).
    """
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    out: dict[str, dict[str, Any]] = {}
    rank = {"A": 3, "B": 2, "C": 1}
    schema = str(payload.get("schema") or "validated_opportunities.v1")
    v2 = schema == "validated_opportunities.v2"

    def _rank(rec: dict[str, Any]) -> int:
        return rank.get(str(rec.get("level") or "C"), 0)

    def _ev(rec: dict[str, Any]) -> float:
        return float(rec.get("expectancy_validate")
                     or rec.get("expectancy_validate_pool") or -1e9)

    for rec in payload.get("opportunities") or []:
        if not isinstance(rec, dict):
            continue
        sym = str(rec.get("symbol") or "*").upper()
        if v2:
            required_identity = (
                "strategy_family", "strategy_version", "rule_fingerprint",
                "dataset_hash", "config_hash", "code_version", "index_hash",
            )
            if not str(rec.get("strategy_family") or "").strip() or str(
                rec.get("strategy_family") or ""
            ).strip() in {"*", "*pooled*"}:
                continue
            if any(not str(rec.get(field) or "").strip() for field in required_identity):
                continue
            cost_provenance = (
                rec.get("session_cost_provenance")
                or rec.get("measured_session_cost")
                or rec.get("cost_provenance")
            )
            if not cost_provenance:
                continue
            if isinstance(cost_provenance, Mapping) and not str(
                cost_provenance.get("source") or ""
            ).strip():
                continue
            key = "|".join([
                sym,
                str(rec.get("strategy_family") or ""),
                str(rec.get("regime") or ""),
                str(rec.get("structure") or ""),
                str(rec.get("session") or ""),
                str(rec.get("side") or ""),
            ])
        else:
            key = "|".join([
                sym,
                str(rec.get("regime") or ""),
                str(rec.get("structure") or ""),
                str(rec.get("session") or ""),
                str(rec.get("side") or ""),
            ])
        cur = out.get(key)
        # Runtime preference on collision: higher level, then higher OOS EV.
        if cur is None or (_rank(rec), _ev(rec)) > (_rank(cur), _ev(cur)):
            out[key] = rec
    return out


def _load_canary(path: Path) -> dict[str, Any] | None:
    """Defect 16: load the DEMO_CANARY permission artifact (schema + expiry).

    Index-hash freshness is checked separately against the live analogue index
    via :func:`_canary_index_hash_matches`, so stale validation can never
    authorise orders.
    """
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if str(payload.get("schema") or "") != "demo_canary.v1":
        return None
    expires = str(payload.get("expires_utc") or "")
    try:
        if datetime.fromisoformat(expires) <= datetime.now(timezone.utc):
            return None
    except ValueError:
        return None
    return payload


def _canary_index_hash_matches(canary: Mapping[str, Any], index_path: Path) -> bool:
    expected = str(canary.get("index_file_sha256") or "")
    if not expected:
        return False
    try:
        return hashlib.sha256(Path(index_path).read_bytes()).hexdigest() == expected
    except OSError:
        return False


def _bootstrap_from_evidence(cfg: Mapping[str, Any], evidence: Any,
                             *, canary_allows: bool = False) -> ValidatedStrategyModel | None:
    """State-evidence bootstrap. Governance: this is UNVALIDATED_RESEARCH.

    It can never behave like a champion. By default the returned model is not
    allowed to trade (shadow decisions only). Only an explicit config opt-in
    (``intelligent_bootstrap_canary``) promotes it to DEMO_CANARY, and even then
    every strategy_model_ready gate must pass on measured provenance.

    Refuses synthetic/proxy evidence outright unless synthetic evidence is
    explicitly allowed for offline tests - and then it still cannot trade.
    """
    if not bool(cfg.get("intelligent_firehose_bootstrap", False)):
        return None
    measured = is_measured_provenance(getattr(evidence, "provenance", "unknown"))
    if not measured:
        if bool(cfg.get("intelligent_allow_synthetic_evidence", False)):
            # Explicit opt-in exists only for offline tests and shadow research.
            # Synthetic evidence can never qualify for a trading stage.
            return ValidatedStrategyModel(
                strategy_id="analogue_bootstrap_synthetic",
                promoted=True,
                n_trades=int(getattr(evidence, "analogue_n", 0) or 0),
                n_losses=int(getattr(evidence, "analogue_n_losses", 0) or 0),
                expectancy=float(getattr(evidence, "expectancy", 0.0) or 0.0),
                profit_factor=float(getattr(evidence, "profit_factor", 0.0) or 0.0),
                bootstrap_p05=float(getattr(evidence, "mean_lower_95", 0.0) or 0.0),
                wins_erased_by_average_loss=float(getattr(evidence, "wins_erased_by_average_loss", 99.0) or 99.0),
                wins_erased_by_tail_loss=0.0,
                validated_risk_fraction=float(cfg.get("intelligent_risk_fraction", 0.08)),
                artifact_hash="bootstrap-synthetic",
                promotion_stage=STAGE_UNVALIDATED_RESEARCH,
            )
        return None
    if not getattr(evidence, "eligible", False):
        return None
    # Defect 16: the canary STAGE comes from the explicit generated artifact,
    # never from a global config flag alone.
    stage = STAGE_DEMO_CANARY if canary_allows else STAGE_UNVALIDATED_RESEARCH
    try:
        model = ValidatedStrategyModel(
            strategy_id="analogue_bootstrap",
            promoted=True,
            n_trades=int(evidence.analogue_n),
            n_losses=int(evidence.analogue_n_losses),
            expectancy=float(evidence.expectancy or 0.0),
            profit_factor=float(evidence.profit_factor or 0.0),
            bootstrap_p05=float(evidence.mean_lower_95 or 0.0),
            wins_erased_by_average_loss=float(evidence.wins_erased_by_average_loss or 99.0),
            wins_erased_by_tail_loss=float(evidence.tail_loss or 0.0) / max(float(evidence.avg_win or 0.0), 1e-9),
            validated_risk_fraction=float(cfg.get("intelligent_risk_fraction", 0.08)),
            artifact_hash="bootstrap",
            promotion_stage=stage,
        )
    except (TypeError, ValueError):
        return None
    ready, _ = strategy_model_ready(model)
    return model if ready else None


class IntelligentFirehoseBrain:
    def __init__(self, cfg: Mapping[str, Any]) -> None:
        self.cfg = dict(cfg)
        index_path = resolve_bot_path(
            cfg.get("analogue_index_path"), INTEL_DIR / "analogue_index.json"
        )
        knowledge_path = resolve_bot_path(
            cfg.get("knowledge_table_path"), INTEL_DIR / "knowledge_table.json"
        )
        validated_path = resolve_bot_path(
            cfg.get("validated_states_path"), INTEL_DIR / "validated_states.json"
        )
        self.index_path = index_path
        self.knowledge_path = knowledge_path
        self.validated_path = validated_path
        self.analogues = AnalogueStore.load(index_path)
        self.knowledge_rows = load_knowledge_rows(knowledge_path)
        self.strategy = _load_strategy(cfg)
        self.validated_states = _load_validated_states(validated_path)
        self.validated_opportunities = _load_validated_opportunities(
            resolve_bot_path(
                cfg.get("validated_opportunities_path"),
                INTEL_DIR / "validated_opportunities.json",
            )
        )
        self.canary_path = resolve_bot_path(
            cfg.get("demo_canary_path"), INTEL_DIR / "demo_canary.json"
        )
        self.canary = _load_canary(self.canary_path)
        # Exploration Firehose: registered falsifiable experiments + limits.
        self.experiments = ExperimentStore(
            resolve_bot_path(
                cfg.get("exploration_experiments_path"),
                INTEL_DIR / "exploration_experiments.json",
            )
        )
        self._exploration_limits = ExplorationLimits.from_cfg(cfg)
        self._exploration_theses: set[str] = set()
        self._last_exploration_micro_diagnostics: dict[str, Any] = {}
        self._seen_hypotheses: dict[str, float] = {}
        self._stage_events: dict[str, list[float]] = {
            "candidate": [], "shadow": [], "exploration_fire": [],
            "demo_canary_fire": [], "champion_fire": [],
        }
        self.memory = DemoBrainState()
        # Current regime label per symbol (consumed by runner profit-management
        # pre-pass for regime_change policy).
        self.regime_by_symbol: dict[str, str] = {}
        self._risk_budget = float(cfg.get("intelligent_risk_budget_usd") or cfg.get("starting_equity") or 100.0)
        self.counts: dict[str, Any] = {
            "fire": 0, "scale": 0, "hold": 0, "reduce": 0, "exit": 0, "skip": 0,
            "skip_reasons": {},
            "shadow_fires": 0,
            "raw_signals": 0,
            "ml_eligible": 0,
            "high_confidence": 0,
            "uncertainty_reject": 0,
            "model_disagreement": 0,
            "tail_reject": 0,
            "short_horizon_probability_reject": 0,
            "short_horizon_expected_value_reject": 0,
            "short_horizon_missing": 0,
            "short_horizon_abstain_reasons": {},
        }

    def _note_skip(self, reason: str) -> None:
        reasons = self.counts.setdefault("skip_reasons", {})
        reasons[reason] = int(reasons.get(reason, 0)) + 1

    def _note_stage(self, stage: str) -> None:
        import time as _time

        self._stage_events.setdefault(stage, []).append(_time.time())

    def _rate_per_hour(self, stage: str) -> float:
        import time as _time

        now = _time.time()
        events = [t for t in self._stage_events.get(stage, []) if now - t <= 3600.0]
        self._stage_events[stage] = events
        return float(len(events))

    def _minutes_since(self, stage: str) -> float | None:
        import time as _time

        events = self._stage_events.get(stage) or []
        if not events:
            return None
        return round((_time.time() - max(events)) / 60.0, 1)

    def exploration_open_counts(self, symbol: str | None = None) -> tuple[int, int]:
        """(exploration open total, exploration open for symbol).

        Counts BOUND tickets plus in-flight reservations (decision sent, fill
        not yet confirmed) so the cap cannot be raced within the bar loop.
        """
        self.memory.expire_pending()
        total = 0
        sym_count = 0
        sym_up = str(symbol or "").upper()
        live_keys = set(self._exploration_theses) | set(self.memory.exploration_pending)
        for key in live_keys:
            mem = self.memory.theses.get(key)
            n = len(mem.tickets) if mem is not None else 0
            n = max(n, len(self.memory.exploration_pending.get(key) or []))
            total += n
            key_symbol = str(key.split("|")[0] or "").upper()
            if key_symbol == sym_up:
                sym_count += n
        return total, sym_count

    def record_exploration_close(self, *, hypothesis_id: str, pnl: float,
                                 **meta: Any) -> dict[str, Any] | None:
        """Sequential-learning hook: every closed exploration trade updates its
        experiment's evidence; losses arm the per-hypothesis cooldown."""
        rec = self.experiments.record_close(
            hypothesis_id=hypothesis_id, pnl=pnl,
            max_trades=self._exploration_limits.max_trades_per_hypothesis,
            **meta,
        )
        if rec is not None and float(pnl) <= 0:
            self.experiments.note_failure(
                hypothesis_id, self._exploration_limits.cooldown_after_failure_s,
            )
        return rec

    def _measured_hedge_cost(self, symbol: str) -> float | None:
        """Measured double-spread cost for one symbol from cost_profiles.json."""
        try:
            profile = json.loads(
                resolve_bot_path(
                    self.cfg.get("cost_profiles_path"),
                    INTEL_DIR / "cost_profiles.json").read_text(encoding="utf-8")
            )
            sym_prof = (profile.get("symbols") or {}).get(str(symbol).upper())
            if not sym_prof:
                return None
            spread_p75 = float(sym_prof.get("spread_p75") or 0.0)
            pip = float(sym_prof.get("pip_size") or 0.0001)
            # Double-spread cost in USD for one 0.01-lot position.
            return round(spread_p75 * pip * 100000.0 * 0.01 * 2.0, 4)
        except (OSError, json.JSONDecodeError, KeyError, ValueError, TypeError):
            return None

    def _measured_spread_limit(self, symbol: str, session: str):
        """Load the fail-closed measured spread limit for this runtime state."""
        from aegis.intel.spread_policy import measured_spread_limit_pips

        try:
            profile = json.loads(
                resolve_bot_path(
                    self.cfg.get("cost_profiles_path"), INTEL_DIR / "cost_profiles.json"
                ).read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            return None
        return measured_spread_limit_pips(profile, symbol=symbol, session=session)

    def find_experiment_by_tag(self, tag: str) -> dict[str, Any] | None:
        """Attribute a broker-side close via its compact EXP tag.

        Brokers may prepend their own prefix to the comment (e.g. ``aegisEXP…``),
        so match on the EXP marker anywhere in the string.
        """
        tag = str(tag or "")
        idx = tag.find("EXP")
        if idx < 0:
            return None
        suffix = tag[idx + 3 :].strip()
        if len(suffix) < 6:
            return None
        for rec in self.experiments.data.get("experiments", {}).values():
            if str(rec.get("hypothesis_id") or "").endswith(suffix):
                return rec
        return None

    def _maybe_explore(
        self,
        *,
        symbol: str,
        side: str,
        setup: str,
        signature: Mapping[str, Any],
        entry: float,
        invalidation: float | None,
        target: float | None,
        pip: float,
        info_id: str,
        portfolio_ok: bool,
        portfolio_reason: str,
        symbol_spec: Mapping[str, Any] | None,
        question: str,
        volatility: str = "",
        regime_label: str = "",
        evidence: Any = None,
        spread_price: float | None = None,
        row: Any = None,
        completed_m1: Any = None,
        state: Mapping[str, Any] | None = None,
        actual_bid: float | None = None,
        actual_ask: float | None = None,
        market_ctx: Any = None,
        quote_buffer: Any = None,
        now_ts: float | None = None,
        video_candidate: Any = None,
    ) -> tuple[DemoDecision | None, str | None]:
        """Exploration Firehose gate chain. Returns (fire_decision, skip_reason).

        Plausibility only - NOT profitability: valid geometry, no absurd payoff
        asymmetry, portfolio room, no known-failed identical hypothesis, hard
        independent limits. Champion validation is NOT required here and this
        NEVER weakens champion requirements.
        """
        self._last_exploration_micro_diagnostics = {}
        if not bool(self.cfg.get("intelligent_exploration_enabled", True)):
            return None, None
        regime = str(signature.get("regime") or "")
        session = str(signature.get("session") or "")
        hyp_id = exploration_hypothesis_id(
            strategy_family=setup, symbol=symbol, side=side,
            regime=regime, session=session,
        )
        # Book-derived logic (spec A): retrieve relevant source concepts for
        # THIS state and attach real derived rules - never just a label.
        # Programming errors here MUST surface (audited fix): only the
        # expected "no knowledge available" case yields empty logic.
        book_logic: dict[str, Any] = {}
        from aegis.intel import knowledge_retrieval

        state_ctx = {
            "regime": regime_label or regime,
            "session": session,
            "structure": str(signature.get("structure") or setup),
            "volatility": str(volatility or ""),
            "family": setup,
            "symbol": symbol,
            "side": side,
        }
        hits = knowledge_retrieval.retrieve_for_state(state_ctx, limit=6)
        if hits:
            top = hits[0]
            book_logic = {
                "source_book": top.get("book"),
                "source_author": top.get("author"),
                "source_passage_hash": top.get("passage_hash"),
                "source_location": top.get("location"),
                "concept_type": top.get("concept_type"),
                "polarity": top.get("polarity"),
                "conflict_topic": top.get("conflict_topic"),
                "exit_plan": knowledge_retrieval.exit_plan_for_state(state_ctx),
                "matched_records": [
                    {k: h.get(k) for k in ("book", "concept_type",
                                           "passage_hash", "_score")}
                    for h in hits[:4]
                ],
            }
        # Candidate counted once per brain lifetime per hypothesis.
        import time as _time

        if hyp_id not in self._seen_hypotheses:
            self._seen_hypotheses[hyp_id] = _time.time()
            self.counts["candidates"] = int(self.counts.get("candidates", 0)) + 1
            self._note_stage("candidate")

        failed = self.experiments.has_failed_identity(
            strategy_family=setup, symbol=symbol, side=side,
            regime=regime, session=session,
        )
        if failed is not None:
            return None, f"known_failed_hypothesis:{failed.get('hypothesis_id', '')[:16]}"

        # NEGATIVE_STATE_EV: measured analogue evidence against this state is
        # a HARD rejection - economics never returns through exploration.
        ev_obj = evidence
        if ev_obj is not None and getattr(ev_obj, "eligible", False):
            exp_val = getattr(ev_obj, "expectancy", None)
            if exp_val is not None and float(exp_val) <= 0:
                return None, "state_ev_not_positive"
        # Self-hedge audit (spec J, audited fix): opposing exposure on the
        # same symbol requires INDEPENDENT mechanism evidence - different
        # family AND different polarity/mechanism class. Same family is
        # always blocked; different family must also differ in polarity
        # (continuation vs fade) to prove a distinct thesis.
        opposite_side = "sell" if side == "buy" else "buy"
        for key in self._exploration_theses:
            mem = self.memory.theses.get(key)
            if (
                mem is not None
                and mem.symbol == str(symbol).upper()
                and str(mem.side or "").lower() == opposite_side
                and (len(mem.tickets) > 0
                     or len(self.memory.exploration_pending.get(key) or []) > 0)
            ):
                same_family = str(mem.setup_family or "").lower() == str(setup).lower()
                polarity_map = {"breakout": "continuation", "momentum": "continuation",
                                "pullback": "fade", "retest": "fade",
                                "reversal": "fade", "mean_reversion": "fade"}
                my_pol = polarity_map.get(str(setup).lower(), "")
                their_pol = polarity_map.get(str(mem.setup_family or "").lower(), "")
                independent = (
                    not same_family
                    and my_pol and their_pol and my_pol != their_pol
                )
                if not independent:
                    return None, (
                        "self_hedge_blocked_same_family" if same_family
                        else "self_hedge_blocked_insufficient_independence"
                    )
                # Incremental cost assessment using measured spread data.
                spread_cost = self._measured_hedge_cost(symbol)
                budget2 = self._exploration_limits.max_risk_per_trade_usd * 2
                if spread_cost is not None and spread_cost > budget2:
                    return None, "self_hedge_blocked_spread_cost_exceeds_budget"
        if not portfolio_ok:
            return None, portfolio_reason or "portfolio_risk"

        # --- FAST_TURNOVER_FIREHOSE: build REAL FastMarketContext from
        # genuine point-in-time M1/M5/M15 data. NO fabricated values.
        from aegis.intel.fast_firehose import (
            FastMarketContext,
            check_entry_economics,
            diagnose_micro_candidates,
        )

        bid_px = float(actual_bid) if actual_bid is not None else None
        ask_px = float(actual_ask) if actual_ask is not None else None
        if bid_px is None or ask_px is None:
            return None, "no_genuine_quote"

        # Genuine M1 OHLCV from the completed bar.
        m1_o = float(row["open"]) if row is not None and "open" in row.index else None
        m1_h = float(row["high"]) if row is not None and "high" in row.index else None
        m1_l = float(row["low"]) if row is not None and "low" in row.index else None
        m1_c = float(row["close"]) if row is not None and "close" in row.index else None
        m1_vol = float(row.get("volume", 0) or 0) if row is not None and hasattr(row, 'get') else None

        # ATR proxy from recent completed bars (genuine, point-in-time).
        m1_atr = None
        if completed_m1 is not None and len(completed_m1) >= 5:
            highs = completed_m1["high"].iloc[-5:].astype(float)
            lows = completed_m1["low"].iloc[-5:].astype(float)
            closes = completed_m1["close"].iloc[-5:].astype(float)
            prev_closes = completed_m1["close"].iloc[-6:-1].astype(float) if len(completed_m1) >= 6 else closes
            trs = pd.Series([
                max(h - l, abs(h - pc), abs(l - pc))
                for h, l, pc in zip(highs, lows, prev_closes)
            ])
            m1_atr = round(float(trs.mean()), 8)

        prev_close = None
        if completed_m1 is not None and len(completed_m1) >= 2:
            prev_close = float(completed_m1["close"].iloc[-2])

        # M5/M15 from runtime state (centralized genuine completed-bar data).
        # State now provides full M5/M15 structure: kind, support, resistance,
        # direction, ATR, compression (M5 only).
        st = state or {}
        structure = st.get("structure") or {}
        m15_struct = structure.get("M15") or {}
        m5_struct = structure.get("M5") or {}
        m15_kind = str(m15_struct.get("kind") or "")
        m15_dir = str(m15_struct.get("direction") or "")  # genuine M15 direction
        m15_sup = float(m15_struct["support"]) if m15_struct.get("support") else None
        m15_res = float(m15_struct["resistance"]) if m15_struct.get("resistance") else None
        m15_mid = (m15_sup + m15_res) / 2.0 if m15_sup and m15_res else None
        m15_hw = abs(m15_res - m15_sup) / 2.0 if m15_sup and m15_res else None
        m5_dir = str(m5_struct.get("direction") or "")  # genuine M5 direction
        m5_kind = str(m5_struct.get("kind") or "")
        m5_sup = float(m5_struct["support"]) if m5_struct.get("support") else None
        m5_res = float(m5_struct["resistance"]) if m5_struct.get("resistance") else None
        m5_atr = float(m5_struct["atr"]) if m5_struct.get("atr") else None
        m5_comp = float(m5_struct["compression"]) if m5_struct.get("compression") else None

        regime_raw = st.get("regime")
        regime_label_str = str(regime_raw.get("label", "") if isinstance(regime_raw, dict) else regime_raw or "")

        # Genuine sub-minute returns from quote buffer (point-in-time, no lookahead).
        # Uses liquidation-side semantics: BUY -> BID, SELL -> ASK.
        now_ts_val = now_ts or time.time()
        ret_5s_buy = ret_5s_sell = None
        ret_15s_buy = ret_15s_sell = None
        ret_30s_buy = ret_30s_sell = None
        ret_60s_buy = ret_60s_sell = None
        tick_rate = quote_change = short_vol = signed_imbalance = None
        if quote_buffer is not None:
            # The exploration side determines which liquidation price to use.
            # For candidate evaluation, we need both sides; use the current
            # signature side as primary, but micro candidates may differ.
            # We provide returns for BOTH sides; micro candidates pick theirs.
            ret_5s_buy = quote_buffer.return_5s(symbol, "buy", now_ts_val)
            ret_5s_sell = quote_buffer.return_5s(symbol, "sell", now_ts_val)
            ret_15s_buy = quote_buffer.return_15s(symbol, "buy", now_ts_val)
            ret_15s_sell = quote_buffer.return_15s(symbol, "sell", now_ts_val)
            ret_30s_buy = quote_buffer.return_30s(symbol, "buy", now_ts_val)
            ret_30s_sell = quote_buffer.return_30s(symbol, "sell", now_ts_val)
            ret_60s_buy = quote_buffer.return_60s(symbol, "buy", now_ts_val)
            ret_60s_sell = quote_buffer.return_60s(symbol, "sell", now_ts_val)
            # Store both; FastMarketContext will pick based on candidate side.
            tick_rate = quote_buffer.tick_rate_per_min(symbol, now_ts_val)
            quote_change = quote_buffer.quote_change_rate(symbol, now_ts_val)
            short_vol = quote_buffer.short_volatility(symbol, now_ts_val)
            signed_imbalance = quote_buffer.signed_tick_imbalance(symbol, now_ts_val)

        ctx = FastMarketContext(
            symbol=symbol,
            timestamp=datetime.now(timezone.utc).isoformat(),
            bid=bid_px, ask=ask_px,
            spread_pips=round((spread_price or 0) / max(pip, 1e-10), 1),
            m1_open=m1_o, m1_high=m1_h, m1_low=m1_l,
            m1_close=m1_c, m1_prev_close=prev_close,
            m1_atr=m1_atr, m1_volume=m1_vol,
            m1_range=(m1_h - m1_l) if m1_h and m1_l else None,
            m1_body=abs(m1_c - m1_o) if m1_c and m1_o else None,
            m15_direction=m15_dir,
            m15_structure=m15_kind,
            m15_support=m15_sup,
            m15_resistance=m15_res,
            m15_range_mid=m15_mid, m15_range_half_width=m15_hw,
            m5_direction=m5_dir,
            m5_structure=m5_kind,
            m5_support=m5_sup,
            m5_resistance=m5_res,
            m5_atr=m5_atr,
            m5_compression=m5_comp,
            # Genuine sub-minute returns from quote buffer (liquidation-side aware).
            return_5s_buy=ret_5s_buy,
            return_5s_sell=ret_5s_sell,
            return_15s_buy=ret_15s_buy,
            return_15s_sell=ret_15s_sell,
            return_30s_buy=ret_30s_buy,
            return_30s_sell=ret_30s_sell,
            return_60s_buy=ret_60s_buy,
            return_60s_sell=ret_60s_sell,
            tick_rate_per_min=tick_rate,
            quote_change_rate=quote_change,
            short_volatility=short_vol,
            signed_tick_imbalance=signed_imbalance,
            session=session or None,
            regime=regime_label_str or regime_label or regime or None,
        )
        # Use externally-provided context if given (for deterministic tests),
        # otherwise build from genuine row/completed_m1/state data.
        if market_ctx is not None:
            ctx = market_ctx
        micro_cands, micro_diagnostics = diagnose_micro_candidates(ctx)
        if video_candidate is not None:
            micro_cands.append(video_candidate)
            micro_diagnostics = dict(micro_diagnostics)
            micro_diagnostics["video_style_candidate"] = True
        self._last_exploration_micro_diagnostics = {
            "micro_candidate_count": len(micro_cands),
            "micro_diagnostics": micro_diagnostics,
        }
        if not micro_cands:
            return None, "no_micro_candidate_matched"

        # Evaluate economics INDEPENDENTLY for each candidate.
        viable = []
        all_rejections = []
        for mc in micro_cands:
            spec_tick_val = (symbol_spec or {}).get("trade_tick_value")
            spec_tick_sz = (symbol_spec or {}).get("trade_tick_size")
            econ = check_entry_economics(
                mc,
                max_risk_usd=self._exploration_limits.max_risk_per_trade_usd,
                volume_min=float((symbol_spec or {}).get("volume_min", 0.01)),
                contract_size=float((symbol_spec or {}).get("trade_contract_size", 100000)),
                tick_value=spec_tick_val,
                tick_size=spec_tick_sz,
            )
            if econ["allowed"]:
                viable.append(mc)
            else:
                all_rejections.extend(econ.get("rejections", []))
        if not viable:
            return None, f"exploration_economics_rejected:{all_rejections[0] if all_rejections else 'unknown'}"

        # Select strongest: highest payoff among economically viable.
        viable.sort(key=lambda c: -c.payoff)
        mc = viable[0]

        # Structural payoff/spread checks apply to the FINAL candidate's
        # own geometry, not the legacy structural geometry.
        if mc.target_pips / max(mc.stop_pips, 0.1) < 0.25:
            return None, "exploration_destructive_payoff"
        if spread_price is not None and mc.target_pips <= 2.0 * float(spread_price) / max(pip, 1e-10):
            return None, "exploration_spread_failure"

        # FINAL CANDIDATE OWNS ALL EXECUTION IDENTITY.
        side = mc.side          # may differ from legacy hint!
        entry = mc.entry_price
        invalidation = mc.invalidation
        target = mc.target
        setup = mc.family       # family from source mechanism

        # Recompute ALL identity from FINAL candidate.
        hyp_id = exploration_hypothesis_id(
            strategy_family=setup, symbol=symbol, side=side,
            regime=regime, session=session,
        )
        info_id = hashlib.sha256(
            f"{hyp_id}|{info_id}".encode()).hexdigest()[:16]

        book_logic["firehose_family"] = mc.family
        book_logic["micro_mechanism"] = mc.mechanism
        book_logic["lane"] = mc.lane.value

        spec = symbol_spec or {}
        sizing = risk_lots_for_exploration(
            max_risk_usd=self._exploration_limits.max_risk_per_trade_usd,
            entry=entry,
            invalidation=invalidation,
            pip=pip,
            contract_size=float(spec.get("trade_contract_size", 100000.0) or 100000.0),
            tick_value=spec.get("trade_tick_value"),
            tick_size=spec.get("trade_tick_size"),
            volume_min=float(spec.get("volume_min", 0.01) or 0.01),
            volume_step=float(spec.get("volume_step", 0.01) or 0.01),
        )
        if not sizing.get("allowed"):
            # Hard risk rejection: broker-minimum lot would breach the budget.
            # Structured RISK_GRANULARITY_BLOCKED state (audited fix 8).
            self.counts["risk_granularity_blocked"] = int(
                self.counts.get("risk_granularity_blocked", 0)) + 1
            samples = self.counts.setdefault("risk_granularity_samples", [])
            if len(samples) < 10:
                stop_pips = round(abs(entry - invalidation) / pip, 1) if pip else 0
                samples.append({
                    "symbol": symbol,
                    "stop_pips": stop_pips,
                    "volume_min": float(spec.get("volume_min", 0.01) or 0.01),
                    "min_lot_risk_usd": sizing.get("actual_min_lot_risk_usd"),
                    "risk_budget_usd": sizing.get("desired_risk_usd"),
                })
            return None, str(sizing.get("reason"))
        lots = float(sizing["lots"])

        exp_open_total, exp_open_symbol = self.exploration_open_counts(symbol)
        ok, reason = check_exploration_limits(
            self._exploration_limits,
            self.experiments,
            hypothesis_id=hyp_id,
            open_positions_total=0,
            open_positions_symbol=0,
            exploration_open_total=exp_open_total,
            exploration_open_symbol=exp_open_symbol,
        )
        if not ok:
            return None, reason

        spec = symbol_spec or {}
        record, created = self.experiments.register(
            {
                "hypothesis_id": hyp_id,
                "strategy_family": setup,
                "symbol": symbol,
                "side": side,
                "entry_rule": f"{setup} {side} on {regime}/{session} state at market"
                + (
                    f" [book: {book_logic.get('source_book')}]" if book_logic else ""
                ),
                "invalidation": f"close beyond {invalidation:.5f}",
                "target": (f"structure target {target:.5f}" if target is not None
                           else "profit-management policies (mfe giveback / time decay)"),
                "regime": regime,
                "session": session,
                "information_id": info_id,
            },
            reason=question or "state candidate offered by the firehose scan",
            mechanism=(
                f"{setup} {side} edge in {regime}/{session}; "
                + (
                    f"mechanism per source: {(book_logic.get('source_book') or '')} "
                    f"({book_logic.get('polarity') or 'n/a'}); "
                    if book_logic
                    else ""
                )
                + "tiny DEMO risk to buy information, not profit",
            ),
            provenance=(
                f"market_state+analogue_index+book:{book_logic.get('source_passage_hash')}"
                if book_logic else "market_state+analogue_index"
            ),
        )
        # Explicit executable exit plan (spec P): target-less exploration still
        # has one - profit-management policies + optional book-derived plan.
        exit_plan = (book_logic or {}).get("exit_plan") or {
            "plan_type": "pm_policies",
            "policies": ["mfe_giveback", "breakeven_lock", "time_decay",
                         "regime_change"],
        }
        record["exit_plan"] = exit_plan
        record["book_logic"] = book_logic
        record["target_price"] = target
        record["initial_stop_price"] = invalidation
        record["max_hold_s"] = mc.max_hold_s if micro_cands else 120
        self.experiments.save()
        thesis_key_exp = thesis_key(symbol, side, setup, regime=regime, session=session)
        self._exploration_theses.add(thesis_key_exp)
        # Set identity on the thesis memory so self-hedge checks can find it.
        _mem = self.memory.get(thesis_key_exp, symbol)
        _mem.symbol = str(symbol).upper()
        _mem.side = side
        _mem.setup_family = setup
        # Reservation happens in the RUNNER after the pre-send guard passes,
        # not here — otherwise the guard sees its own decision as a conflict.
        self.counts["exploration_eligible"] = int(self.counts.get("exploration_eligible", 0)) + 1
        journal = {
            "brain": "intelligent_firehose",
            "action": "fire",
            "shadow_action": None,
            "setup_family": setup,
            "thesis_key": thesis_key_exp,
            "exploration": True,
            "promotion_stage": "EXPLORATION_CANARY",
            "hypothesis_id": hyp_id,
            "experiment_created": created,
            "experiment_status": record.get("status"),
            "regime": regime,
            "session": session,
            "max_risk_usd": self._exploration_limits.max_risk_per_trade_usd,
            "sizing": sizing,
            "exit_plan": exit_plan,
            "book_logic": book_logic,
            **self._last_exploration_micro_diagnostics,
        }
        decision = DemoDecision(
            "fire",
            "exploration_hypothesis_test",
            side=side,
            sl=invalidation,
            tp=target,
            quantity=lots,
            information_id=info_id,
            analogue_n=0,
            close_clips=0,
            journal=journal,
        )
        return decision, None

    def refresh(self, cfg: Mapping[str, Any] | None = None) -> None:
        """Re-read the champion and validated-state allowlist.

        The runner calls this each poll so a watcher-regenerated allowlist takes
        effect without a restart. Memory and counts are preserved.
        """
        if cfg is not None:
            self.cfg.update(dict(cfg))
        self.strategy = _load_strategy(self.cfg)
        validated_path = resolve_bot_path(
            self.cfg.get("validated_states_path"), INTEL_DIR / "validated_states.json"
        )
        self.validated_states = _load_validated_states(validated_path)
        self.validated_opportunities = _load_validated_opportunities(
            resolve_bot_path(
                self.cfg.get("validated_opportunities_path"),
                INTEL_DIR / "validated_opportunities.json",
            )
        )
        self.canary = _load_canary(self.canary_path)
        self._exploration_limits = ExplorationLimits.from_cfg(self.cfg)

    def snapshot(self) -> dict[str, Any]:
        records = len(getattr(self.analogues, "_records", []))
        model = self.strategy
        if model is None:
            strategy_identity: dict[str, Any] = {
                "strategy_id": None,
                "strategy_status": "UNQUALIFIED_NO_VALIDATED_MODEL",
                "strategy_version": None,
                "dataset_hash": None,
                "validation_hash": None,
                "promotion_stage": None,
            }
        else:
            strategy_identity = {
                "strategy_id": model.strategy_id,
                "strategy_status": (
                    "QUALIFIED_TRADING" if model.may_trade else "QUALIFIED_SHADOW_ONLY"
                ),
                "strategy_version": str(model.artifact_hash or "")[:16],
                "dataset_hash": model.dataset_hash or None,
                "validation_hash": model.validation_hash or None,
                "promotion_stage": model.promotion_stage,
            }
        skip_reasons = self.counts.get("skip_reasons", {})

        def rejected(*needles: str) -> int:
            return sum(
                int(value)
                for reason, value in skip_reasons.items()
                if any(needle in str(reason).lower() for needle in needles)
            )

        funnel = {
            # Truthful broker funnel names. Brain intent is never FIRES/FILLS.
            "SCANS": int(self.counts.get("scans", 0)),
            "MICRO_CANDIDATES": int(self.counts.get("micro_candidates", self.counts.get("candidates", 0))),
            "BOOK_SUPPORTED": int(self.counts.get("book_supported", 0)),
            "VALIDATED_MATCH": int(self.counts.get("validated_match", 0)),
            "EXPLORATION_ELIGIBLE": int(self.counts.get("exploration_eligible", 0)),
            "SPREAD_REJECT": rejected("spread"),
            "ECONOMICS_REJECT": rejected("economics", "expected_net", "ev_"),
            "GEOMETRY_REJECT": rejected("geometry", "invalid_stop", "target"),
            "RISK_REJECT": rejected("risk", "margin", "sizing", "lot", "halt"),
            "STALE_REJECT": rejected("stale", "quote_refresh", "future_quote"),
            "OTHER_REJECT": max(0, int(self.counts.get("skip", 0)) - sum(
                rejected_group
                for rejected_group in (
                    rejected("spread"),
                    rejected("economics", "expected_net", "ev_"),
                    rejected("geometry", "invalid_stop", "target"),
                    rejected("risk", "margin", "sizing", "lot", "halt"),
                    rejected("stale", "quote_refresh", "future_quote"),
                )
            )),
            "FIRES": int(self.counts.get("broker_fires", 0)),
            "FILLS": int(self.counts.get("broker_fills", 0)),
            # Legacy brain-only labels retained for existing consumers.
            "scans": int(self.counts.get("scans", 0)),
            "candidates": int(self.counts.get("candidates", 0)),
            "shadow": int(self.counts.get("shadow_fires", 0)),
            "exploration_eligible": int(self.counts.get("exploration_eligible", 0)),
            "exploration_fire": int(self.counts.get("exploration_fire", 0)),
            "demo_canary_fire": int(self.counts.get("demo_canary_fire", 0)),
            "champion_fire": int(self.counts.get("champion_fire", 0)),
            "skip": int(self.counts.get("skip", 0)),
        }
        rates = {
            "candidate_rate_per_hour": self._rate_per_hour("candidate"),
            "shadow_candidates_per_hour": self._rate_per_hour("shadow"),
            "exploration_fires_per_hour": self._rate_per_hour("exploration_fire"),
            "demo_canary_fires_per_hour": self._rate_per_hour("demo_canary_fire"),
            "champion_fires_per_hour": self._rate_per_hour("champion_fire"),
        }
        recency = {
            "minutes_since_last_candidate": self._minutes_since("candidate"),
            "minutes_since_last_exploration_fire": self._minutes_since("exploration_fire"),
            "minutes_since_last_validated_fire": self._minutes_since("demo_canary_fire")
            if (self._minutes_since("demo_canary_fire") or 1e9)
            < (self._minutes_since("champion_fire") or 1e9)
            else self._minutes_since("champion_fire"),
        }
        warnings = [
            warning
            for warning in (
                f"analogue index empty or unreadable: {self.index_path}" if records == 0 else "",
                f"knowledge table empty or unreadable: {self.knowledge_path}"
                if not self.knowledge_rows
                else "",
                f"analogue provenance is not measured market history: {self.analogues.provenance}"
                if records and not self.analogues.is_measured
                else "",
            )
            if warning
        ]
        inactivity_min = float(self.cfg.get("exploration_inactivity_warn_min", 90) or 90)
        msc = recency["minutes_since_last_candidate"]
        if funnel["scans"] > 50 and (msc is None or msc > inactivity_min):
            warnings.append(
                f"FIREHOSE_CANDIDATE_INACTIVITY: no candidates for {msc} min; "
                "diagnose candidate generation"
            )
        return {
            "brain": "intelligent_firehose",
            "counts": {k: v for k, v in self.counts.items()
                       if k not in ("skip_reasons", "risk_granularity_samples")},
            "risk_granularity_blocked": int(self.counts.get("risk_granularity_blocked", 0)),
            "risk_granularity_samples": self.counts.get("risk_granularity_samples", [])[:5],
            "funnel": funnel,
            **rates,
            **recency,
            "skip_reasons": dict(
                sorted(self.counts.get("skip_reasons", {}).items(), key=lambda kv: -kv[1])[:20]
            ),
            "shadow_fires": int(self.counts.get("shadow_fires", 0)),
            "experiments_active": sum(
                1 for r in self.experiments.data.get("experiments", {}).values()
                if r.get("status") == "ACTIVE"
            ),
            "experiments_rejected": sum(
                1 for r in self.experiments.data.get("experiments", {}).values()
                if r.get("status") == "REJECTED"
            ),
            "experiments_promising": sum(
                1 for r in self.experiments.data.get("experiments", {}).values()
                if r.get("status") == "PROMISING"
            ),
            **strategy_identity,
            "analogue_records": records,
            "analogue_provenance": self.analogues.provenance,
            "analogue_measured": self.analogues.is_measured,
            "analogue_index_path": str(self.index_path),
            "knowledge_rows": len(self.knowledge_rows),
            "knowledge_table_path": str(self.knowledge_path),
            "champion": None if self.strategy is None else self.strategy.strategy_id,
            "validated_states": len(self.validated_states),
            "validated_opportunities": len(self.validated_opportunities),
            "gate_validated_states": bool(self.cfg.get("intelligent_gate_validated_states", False)),
            "bootstrap": bool(self.cfg.get("intelligent_firehose_bootstrap", False)),
            "bootstrap_canary": bool(self.cfg.get("intelligent_bootstrap_canary", False)),
            "exploration_enabled": bool(self.cfg.get("intelligent_exploration_enabled", True)),
            # An empty index means every decision is made on no evidence. That is a
            # misconfiguration, not a quiet market, so make it visible.
            "warnings": warnings,
        }

    def _trade_economics(
        self,
        *,
        side: str,
        entry: float,
        invalidation: float | None,
        target: float | None,
        lots: float,
        spec: Mapping[str, Any] | None,
        spread_price: float | None,
        slippage_price: float | None,
        evidence: Any,
    ) -> TradeEconomics:
        """Price the prospective trade. Win probability comes from analogue evidence.

        The analogue win rate is only used when the evidence is measured; a proxy
        index must not supply a probability that authorises real size. When no
        probability survives, ``evaluate_trade_economics`` rejects on
        ``no_win_probability_evidence`` rather than assuming a favourable one.
        """
        measured = is_measured_provenance(getattr(evidence, "provenance", "unknown")) or bool(
            self.cfg.get("intelligent_allow_synthetic_evidence", False)
        )
        analogue_n = int(getattr(evidence, "analogue_n", 0) or 0) if measured else 0
        analogue_losses = int(getattr(evidence, "analogue_n_losses", 0) or 0) if measured else 0
        return evaluate_trade_economics(
            side=side,
            entry=entry,
            invalidation=invalidation,
            target=target,
            lots=lots,
            spec=spec,
            spread_price=spread_price,
            slippage_price=slippage_price,
            commission_round_trip_usd=float(self.cfg.get("commission_round_trip_usd", 0.0) or 0.0),
            analogue_n=analogue_n,
            analogue_n_losses=analogue_losses,
            min_payoff_ratio=float(
                self.cfg.get("intelligent_min_payoff_ratio", DEFAULT_MIN_PAYOFF_RATIO)
            ),
            min_expected_net_usd=float(self.cfg.get("intelligent_min_expected_net_usd", 0.0) or 0.0),
        )

    def evaluate(
        self,
        *,
        symbol: str,
        row: pd.Series,
        completed_m1: pd.DataFrame,
        positions: Sequence[PositionSnapshot],
        equity: float,
        pip: float,
        core_side: str | None,
        spread_price: float | None = None,
        symbol_spec: Mapping[str, Any] | None = None,
        entry_price: float | None = None,
        actual_bid: float | None = None,
        actual_ask: float | None = None,
        quote_buffer: Any = None,
        now_ts: float | None = None,
        video_style: bool = False,
        short_horizon_prediction: Mapping[str, Any] | None = None,
    ) -> DemoDecision:
        clip_qty = float(self.cfg.get("order_quantity", 0.01))
        clip_risk = max(self._risk_budget * float(self.cfg.get("intelligent_risk_fraction", 0.08)) / 5.0, 0.01)
        self.counts["scans"] = int(self.counts.get("scans", 0)) + 1
        self.memory.sync_from_positions(symbol, positions, clip_risk)
        state = build_runtime_state(symbol=symbol, m1=completed_m1)
        m15 = (state.get("structure") or {}).get("M15") or {}
        video_signal = None
        if video_style:
            video_signal = video_style_signal(completed_m1, symbol=symbol)
            if video_signal is not None:
                self.counts["raw_signals"] = int(self.counts.get("raw_signals", 0)) + 1
        setup = "video_style_breakout" if video_signal is not None else str(m15.get("kind") or "scan")
        side = video_signal.side if video_signal is not None else str(core_side or "").lower()
        if video_signal is None and side not in {"buy", "sell"}:
            close = float(row["close"])
            ema = row.get("ema_20")
            if ema is not None and not pd.isna(ema):
                side = "buy" if close >= float(ema) else "sell"
            else:
                prev = float(completed_m1["close"].iloc[-2]) if len(completed_m1) >= 2 else close
                side = "buy" if close >= prev else "sell"
        held = self.memory.get(
            thesis_key(symbol, side, setup,
                       regime=str(state.get("regime") or ""),
                       session=str(state.get("session") or "")),
            symbol,
        )
        invalidation, target = _geometry(side, m15, pip)
        video_candidate = None
        if video_signal is not None:
            video_entry = entry_price
            if video_entry is None:
                video_entry = actual_ask if video_signal.side == "buy" else actual_bid
            if video_entry is None:
                video_entry = float(row["close"])
            video_cfg = VideoStyleConfig(
                risk_per_trade=max(self._exploration_limits.max_risk_per_trade_usd, 0.01),
                max_hold_bars=0,
            )
            invalidation, target = video_style_geometry(
                video_signal, entry_price=float(video_entry), cfg=video_cfg
            )
            video_candidate = video_style_micro_candidate(
                video_signal,
                entry_price=float(video_entry),
                pip=float(pip),
                spread_pips=(
                    abs(float(spread_price)) / max(float(pip), 1e-12)
                    if spread_price is not None else 0.0
                ),
                cfg=video_cfg,
            )
        signature = runtime_signature(state, side=side, setup=setup)
        measured_spread = self._measured_spread_limit(
            symbol, str(signature.get("session") or "")
        )
        if spread_price is not None:
            spread_pips = abs(float(spread_price)) / max(float(pip), 1e-12)
            if measured_spread is None:
                self._note_skip("spread_policy_no_measured_evidence")
                self.counts["skip"] += 1
                return DemoDecision("skip", "spread_policy_no_measured_evidence", side=side)
            if not measured_spread.allows(spread_pips):
                self._note_skip("spread_above_measured_session_limit")
                self.counts["skip"] += 1
                return DemoDecision("skip", "spread_above_measured_session_limit", side=side)
        self.regime_by_symbol[str(symbol).upper()] = str(
            signature.get("regime") or ""
        )
        # Keep the thesis identity consistent with the memory lookup above.
        held.thesis_key = thesis_key(
            symbol, side, setup,
            regime=str(signature.get("regime") or ""),
            session=str(signature.get("session") or ""),
        )
        gating = bool(self.cfg.get("intelligent_gate_validated_states", False))
        exact_state = None
        current_state = None
        opportunity: dict[str, Any] | None = None
        if gating:
            from aegis.research.intelligent_champion import state_sig

            allowed = set(self.validated_states)
            if self.strategy is not None and self.strategy.allowed_states:
                allowed |= set(self.strategy.allowed_states)
            current_state = state_sig(
                {
                    "regime": signature.get("regime") or "",
                    "structure": signature.get("structure") or "",
                    "session": signature.get("session") or "",
                    "side": side,
                }
            )
            # V2 permissions are family-scoped before state matching. V1 is
            # retained as a legacy state-only read path for old artifacts.
            opp_key = "|".join([
                str(symbol).upper(),
                setup,
                str(signature.get("regime") or ""),
                str(signature.get("structure") or ""),
                str(signature.get("session") or ""),
                side,
            ])
            opportunity = self.validated_opportunities.get(opp_key)
            if opportunity is None:
                legacy_key = "|".join([
                    str(symbol).upper(),
                    str(signature.get("regime") or ""),
                    str(signature.get("structure") or ""),
                    str(signature.get("session") or ""),
                    side,
                ])
                opportunity = self.validated_opportunities.get(legacy_key)
            if opportunity is not None:
                exact_state = {
                    "regime": signature.get("regime") or "",
                    "structure": signature.get("structure") or "",
                    "session": signature.get("session") or "",
                    "side": side,
                }
                allowed.add(current_state)
            elif current_state in allowed:
                exact_state = {
                    "regime": signature.get("regime") or "",
                    "structure": signature.get("structure") or "",
                    "session": signature.get("session") or "",
                    "side": side,
                }
        evidence = self.analogues.query(
            signature=signature,
            before_time=row["time"],
            min_n=int(self.cfg.get("intelligent_min_analogues", 20)),
            min_similarity=float(self.cfg.get("intelligent_min_similarity", 0.55)),
            pool_across_symbols=bool(self.cfg.get("intelligent_pool_across_symbols", False)),
            exact_state=exact_state,
        )
        books = match_knowledge(
            self.knowledge_rows,
            regime=str(signature.get("regime") or ""),
            structure=str(signature.get("structure") or setup),
        )
        portfolio_ok, portfolio_reason = pretrade_ok(
            positions=list(positions),
            symbol=str(symbol).upper(),
            side=side,
            quantity=clip_qty,
            avg_price=float(row["close"]),
            cfg={
                "max_positions": int(self.cfg.get("max_positions", 40)),
                "max_currency_direction_positions": int(self.cfg.get("max_currency_direction_positions", 0) or 0),
                "max_per_symbol": int(self.cfg.get("intelligent_max_clips_per_thesis", 5)),
            },
        )
        strategy = self.strategy or _bootstrap_from_evidence(
            self.cfg,
            evidence,
            canary_allows=(
                bool(self.cfg.get("intelligent_bootstrap_canary", True))
                and self.canary is not None
                and _canary_index_hash_matches(self.canary, self.index_path)
            ),
        )
        fire = evaluate_thesis_fire(
            strategy=strategy,
            state_expected_net_value=evidence.expectancy if evidence.eligible else None,
            analogue_n=evidence.analogue_n,
            analogue_n_losses=evidence.analogue_n_losses,
            uncertainty=evidence.uncertainty,
            eligible=evidence.eligible,
            portfolio_ok=portfolio_ok,
            portfolio_reason=portfolio_reason,
        )
        # Gate to validated states. The full analogue index has no edge after costs;
        # only the states the research pipeline validated may fire. When gating is on
        # and no states are validated, nothing fires.
        if gating and current_state not in allowed:
            fire = ThesisFireDecision("skip", "state_not_in_validated_set", None)
        short_horizon_journal: dict[str, Any] = {}
        if video_candidate is not None:
            # Preserve candidate discovery telemetry even when the calibrated
            # short-horizon model vetoes the entry before exploration runs.
            self.counts["micro_candidates"] = int(
                self.counts.get("micro_candidates", 0)
            ) + 1
            short_horizon_journal.update({
                "micro_candidate_count": 1,
                "micro_diagnostics": {
                    "video_style_candidate": "candidate_matched",
                },
            })
        if short_horizon_prediction is not None:
            calibration_status = str(short_horizon_prediction.get("calibration_status") or "")
            if calibration_status == "calibrated":
                self.counts["ml_eligible"] = int(self.counts.get("ml_eligible", 0)) + 1
            if bool(short_horizon_prediction.get("model_disagreement", False)):
                self.counts["model_disagreement"] = int(self.counts.get("model_disagreement", 0)) + 1
            prediction_ok, prediction_reason = short_horizon_gate(
                short_horizon_prediction,
                min_probability=(
                    float(self.cfg["short_horizon_min_probability"])
                    if self.cfg.get("short_horizon_min_probability") is not None
                    else None
                ),
            )
            short_horizon_journal = {
                **short_horizon_journal,
                "short_horizon_prediction": {
                    key: short_horizon_prediction.get(key)
                    for key in (
                        "probability",
                        "decision",
                        "expected_net_pnl",
                        "expected_net_pnl_lcb95",
                        "calibration_status",
                        "abstain",
                        "abstain_reason",
                        "model_agreement",
                        "model_disagreement",
                        "uncertainty",
                        "threshold",
                        "decision_horizon_s",
                        "harvest_mode",
                    )
                    if key in short_horizon_prediction
                },
                "short_horizon_gate": prediction_reason,
            }
            if not prediction_ok:
                diagnostic_reason = str(
                    short_horizon_prediction.get("abstain_reason")
                    or prediction_reason
                )
                abstain_reasons = self.counts.setdefault(
                    "short_horizon_abstain_reasons", {}
                )
                abstain_reasons[diagnostic_reason] = int(
                    abstain_reasons.get(diagnostic_reason, 0)
                ) + 1
                if any(token in prediction_reason for token in ("uncertainty", "abstain", "not_calibrated")):
                    self.counts["uncertainty_reject"] = int(
                        self.counts.get("uncertainty_reject", 0)
                    ) + 1
                if "tail" in prediction_reason:
                    self.counts["tail_reject"] = int(self.counts.get("tail_reject", 0)) + 1
                if prediction_reason in {
                    "short_horizon_probability_below_threshold",
                    "short_horizon_negative_prediction",
                }:
                    self.counts["short_horizon_probability_reject"] = int(
                        self.counts.get("short_horizon_probability_reject", 0)
                    ) + 1
                elif prediction_reason == "short_horizon_negative_expected_value":
                    self.counts["short_horizon_expected_value_reject"] = int(
                        self.counts.get("short_horizon_expected_value_reject", 0)
                    ) + 1
                elif prediction_reason == "short_horizon_prediction_missing":
                    self.counts["short_horizon_missing"] = int(
                        self.counts.get("short_horizon_missing", 0)
                    ) + 1
                fire = ThesisFireDecision("skip", prediction_reason, fire.expected_net_value)
            elif calibration_status == "calibrated":
                self.counts["high_confidence"] = int(self.counts.get("high_confidence", 0)) + 1
        info_id = _information_id(
            symbol=symbol,
            side=side,
            setup=setup,
            invalidation=f"{invalidation:.5f}" if invalidation is not None else "none",
            session=str(state.get("session") or ""),
        )
        target_risk = 0.0
        if evidence.eligible and strategy is not None and strategy.validated_risk_fraction:
            target_risk = self._risk_budget * float(strategy.validated_risk_fraction)
        close = float(row["close"])
        invalidated = False
        target_hit = False
        if held.clips > 0 and held.side == "buy":
            if invalidation is not None and close <= float(invalidation):
                invalidated = True
            if target is not None and close >= float(target):
                target_hit = True
        elif held.clips > 0 and held.side == "sell":
            if invalidation is not None and close >= float(invalidation):
                invalidated = True
            if target is not None and close <= float(target):
                target_hit = True
        opposite = bool(held.clips > 0 and held.side and held.side != side)
        weak_payoff = bool(
            evidence.avg_win is not None
            and evidence.avg_loss is not None
            and abs(float(evidence.avg_loss)) > 4.0 * max(float(evidence.avg_win), 1e-9)
        )
        if weak_payoff and held.clips <= 0 and fire.action == "fire":
            fire = ThesisFireDecision("skip", "payoff_worse_than_cost", fire.expected_net_value)

        entry = float(entry_price if entry_price is not None else close)

        # Size first, then price. A fixed lot silently risks 10x more behind a
        # 50-pip stop than a 5-pip one, and the economics have to be computed for
        # the size actually being sent - commission does not scale with lots, so
        # pricing the wrong size can flip the EV sign.
        sizing = None
        if bool(self.cfg.get("intelligent_edge_sizing", True)) and strategy is not None:
            sizing = size_thesis_clip(
                entry=entry,
                invalidation=invalidation,
                spec=symbol_spec,
                risk_budget_usd=self._risk_budget,
                validated_risk_fraction=strategy.validated_risk_fraction,
                current_risk_usd=held.current_risk_usd,
                max_clips=int(self.cfg.get("intelligent_max_clips_per_thesis", 5)),
                confidence=evidence_confidence(
                    analogue_n=evidence.analogue_n,
                    min_n=int(self.cfg.get("intelligent_min_analogues", 20)),
                    uncertainty=str(evidence.uncertainty),
                ),
                hard_max_lots=float(self.cfg.get("mt5_max_lots") or 0.0) or None,
            )
            if sizing.allowed:
                clip_qty = sizing.lots
            elif fire.action == "fire":
                fire = ThesisFireDecision("skip", f"sizing:{sizing.reason}", fire.expected_net_value)

        # Per-trade economics. State-level expectancy says the *situation* pays;
        # this says *this fill*, against this invalidation, toward this target,
        # after this moment's spread, pays. Both must hold before FIRE.
        econ = self._trade_economics(
            side=side,
            entry=entry,
            invalidation=invalidation,
            target=target,
            lots=clip_qty,
            spec=symbol_spec,
            spread_price=spread_price,
            slippage_price=(
                None if measured_spread is None else measured_spread.slippage_pips * float(pip)
            ),
            evidence=evidence,
        )
        if fire.action == "fire" and not econ.acceptable:
            fire = ThesisFireDecision(
                "skip", f"trade_economics:{econ.reason}", econ.expected_net_value_usd
            )
        elif fire.action == "fire":
            fire = ThesisFireDecision(fire.action, fire.reason, econ.expected_net_value_usd)
        # Governance: a model without a trading stage (research bootstrap, or
        # canary disabled) may decide in shadow but never send an order. The
        # latent demand is journaled so throughput analysis sees it.
        shadow_action: str | None = None
        if fire.action in {"fire", "scale"} and (strategy is None or not strategy.may_trade):
            shadow_action = fire.action
            stage = "none" if strategy is None else str(strategy.promotion_stage)
            fire = ThesisFireDecision(
                "skip",
                f"shadow:not_trading_stage:{stage}",
                fire.expected_net_value,
            )
        if shadow_action is not None:
            self.counts["shadow_fires"] = int(self.counts.get("shadow_fires", 0)) + 1
            self._note_stage("shadow")
        # Exploration Firehose: with no validated trading model, a flat thesis
        # with valid geometry can still become a REGISTERED tiny-risk DEMO
        # experiment. This never bypasses champion validation - it buys
        # information while capital stays protected.
        #
        # Audited fix (spec-defect 6): exploration is a CLASSIFIED path, not a
        # generic skip-fallthrough. Hard economic rejections can NEVER return
        # through exploration.
        _HARD_REJECT_BASES = (
            "trade_economics",          # NEGATIVE_EXPECTED_NET_AFTER_COST /
                                        # SPREAD_FAILURE / DESTRUCTIVE_PAYOFF
            "state_ev_not_positive",    # NEGATIVE_STATE_EV
            "destructive_payoff",
            "payoff_worse_than_cost",
            "sizing:",                  # RISK_FAILURE
        )
        _EXPLORATION_ALLOWED_BASES = (
            "no_validated_strategy_model",      # INSUFFICIENT_EVIDENCE
            "state_not_in_validated_set",       # UNDERCOVERED_STATE
            "unacceptable_uncertainty",         # UNCERTAIN_PLAUSIBLE_MECHANISM
            "insufficient_analogue_evidence",   # INSUFFICIENT_EVIDENCE
            "shadow:not_trading_stage",         # research-stage demand
        )
        fire_base = str(fire.reason or "").split(":", 1)[0]
        exploration_classified = (
            fire.action == "skip"
            and (fire_base in _EXPLORATION_ALLOWED_BASES
                 or str(fire.reason or "").startswith("shadow:"))
        )
        economics_hard_reject = (
            fire.action == "skip" and fire_base in _HARD_REJECT_BASES
        )
        if economics_hard_reject:
            self._note_skip(str(fire.reason))
        exploration_journal: dict[str, Any] | None = None
        if (
            exploration_classified
            and held.clips <= 0
            and bool(self.cfg.get("intelligent_exploration_enabled", True))
        ):
            book_family = str((books[0] or {}).get("strategy_family") or "") if books else ""
            exp_decision, exp_skip = self._maybe_explore(
                symbol=symbol,
                side=side,
                setup=setup,
                signature=signature,
                entry=float(entry_price if entry_price is not None else close),
                invalidation=invalidation,
                target=target,
                pip=pip,
                info_id=info_id,
                portfolio_ok=portfolio_ok,
                portfolio_reason=portfolio_reason,
                symbol_spec=symbol_spec,
                question=(f"book-derived family {book_family}" if book_family
                          else "firehose scan candidate"),
                volatility=str((state.get("volatility") or {}).get("phase")
                               if isinstance(state.get("volatility"), Mapping)
                               else (state.get("volatility") or "")),
                regime_label=str((state.get("regime") or {}).get("label", "")
                                  if isinstance(state.get("regime"), Mapping)
                                  else (state.get("regime") or "")),
                evidence=evidence,
                spread_price=spread_price,
                row=row,
                completed_m1=completed_m1,
                state=state,
                actual_bid=actual_bid,
                actual_ask=actual_ask,
                quote_buffer=quote_buffer,
                now_ts=now_ts,
                video_candidate=video_candidate,
            )
            if exp_decision is not None:
                # Explicit exploration classification (audited fix, defect 6).
                _trigger_map = {
                    "no_validated_strategy_model": "INSUFFICIENT_EVIDENCE",
                    "insufficient_analogue_evidence": "INSUFFICIENT_EVIDENCE",
                    "state_not_in_validated_set": "UNDERCOVERED_STATE",
                    "unacceptable_uncertainty": "UNCERTAIN_PLAUSIBLE_MECHANISM",
                }
                _base = str(fire.reason or "").split(":", 1)[0]
                _trigger = _trigger_map.get(
                    _base,
                    ("NEW_BOOK_HYPOTHESIS"
                     if (exp_decision.journal.get("book_logic")
                         and (exp_decision.journal["book_logic"].get("source_book")))
                     else "NEW_DATA_HYPOTHESIS"),
                )
                exp_decision.journal["exploration_trigger"] = _trigger
                self.counts["exploration_fire"] = int(self.counts.get("exploration_fire", 0)) + 1
                self._note_stage("exploration_fire")
                self.counts["fire"] = int(self.counts.get("fire", 0)) + 1
                exposure = exposure_snapshot(positions)
                return DemoDecision(
                    "fire",
                    exp_decision.reason,
                    side=exp_decision.side,
                    sl=exp_decision.sl,
                    tp=exp_decision.tp,
                    quantity=exp_decision.quantity,
                    expected_net_value=None,
                    information_id=info_id,
                    analogue_n=evidence.analogue_n,
                    close_clips=0,
                    journal={**exp_decision.journal,
                             "equity": equity,
                             "currency_exposure": exposure.get("currency_direction"),
                             **econ.journal()},
                )
            if exp_skip:
                self._note_skip(exp_skip)
                exploration_journal = {
                    "exploration_skip": exp_skip,
                    **self._last_exploration_micro_diagnostics,
                }
        action = evaluate_thesis_action(
            fire_decision=fire,
            information_id=info_id,
            last_information_id=held.information_id,
            current_risk_usd=held.current_risk_usd,
            target_risk_usd=target_risk,
            invalidated=invalidated,
            target_reached=target_hit,
            opposite_side=opposite,
        )
        mapped = action.action
        if mapped == "skip" and action.reason == "hold_at_target_exposure" and held.clips > 0:
            mapped = "hold"
        close_clips = 0
        if mapped == "exit":
            close_clips = held.clips
        elif mapped == "reduce" and held.clips > 1:
            close_clips = 1
        elif mapped == "reduce":
            mapped = "exit"
            close_clips = held.clips
        self.counts[mapped] = int(self.counts.get(mapped, 0)) + 1
        if mapped == "skip":
            self._note_skip(str(action.reason))
        if mapped == "fire" and strategy is not None:
            # Validated-stage fires (exploration fires return earlier).
            if strategy.promotion_stage == "DEMO_CANARY":
                self.counts["demo_canary_fire"] = int(self.counts.get("demo_canary_fire", 0)) + 1
                self._note_stage("demo_canary_fire")
            elif strategy.promotion_stage == "DEMO_CHAMPION":
                self.counts["champion_fire"] = int(self.counts.get("champion_fire", 0)) + 1
                self._note_stage("champion_fire")
        exposure = exposure_snapshot(positions)
        journal = {
            "brain": "intelligent_firehose",
            "action": mapped,
            "shadow_action": shadow_action,
            "setup_family": setup,
            "thesis_key": held.thesis_key,
            "analogue_n": evidence.analogue_n,
            "expectancy": evidence.expectancy,
            "uncertainty": evidence.uncertainty,
            "similarity": evidence.similarity_score,
            "information_id": info_id,
            "regime": signature.get("regime"),
            "structure": signature.get("structure"),
            "book_hashes": [row.get("file_hash") for row in books[:4]],
            "families": [row.get("strategy_family") for row in books[:4]],
            "champion": None if strategy is None else strategy.strategy_id,
            "equity": equity,
            "currency_exposure": exposure.get("currency_direction"),
            "invalidated": invalidated,
            "target_hit": target_hit,
            "analogue_provenance": getattr(evidence, "provenance", "unknown"),
            "analogue_measured": is_measured_provenance(getattr(evidence, "provenance", "unknown")),
            **econ.journal(),
            **({} if sizing is None else sizing.journal()),
            **short_horizon_journal,
            **(exploration_journal or {}),
        }
        return DemoDecision(
            mapped,
            action.reason,
            side=side,
            sl=invalidation,
            # Use the priced target so the order carries the geometry that was
            # actually validated, including a synthesised one when structure gave
            # no usable level.
            tp=econ.target if econ.target is not None else target,
            quantity=clip_qty,
            expected_net_value=action.expected_net_value,
            information_id=info_id,
            analogue_n=evidence.analogue_n,
            close_clips=close_clips,
            journal=journal,
        )
