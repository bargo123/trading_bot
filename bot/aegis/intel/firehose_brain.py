"""Intelligent Firehose demo brain. Runner imports this module only."""
from __future__ import annotations

import hashlib
import json
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

    def _rank(rec: dict[str, Any]) -> int:
        return rank.get(str(rec.get("level") or "C"), 0)

    def _ev(rec: dict[str, Any]) -> float:
        return float(rec.get("expectancy_validate")
                     or rec.get("expectancy_validate_pool") or -1e9)

    for rec in payload.get("opportunities") or []:
        if not isinstance(rec, dict):
            continue
        sym = str(rec.get("symbol") or "*").upper()
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
        self._seen_hypotheses: dict[str, float] = {}
        self._stage_events: dict[str, list[float]] = {
            "candidate": [], "shadow": [], "exploration_fire": [],
            "demo_canary_fire": [], "champion_fire": [],
        }
        self.memory = DemoBrainState()
        self._risk_budget = float(cfg.get("intelligent_risk_budget_usd") or cfg.get("starting_equity") or 100.0)
        self.counts: dict[str, Any] = {
            "fire": 0, "scale": 0, "hold": 0, "reduce": 0, "exit": 0, "skip": 0,
            "skip_reasons": {},
            "shadow_fires": 0,
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
            hypothesis_id=hypothesis_id, pnl=pnl, **meta,
        )
        if rec is not None and float(pnl) <= 0:
            self.experiments.note_failure(
                hypothesis_id, self._exploration_limits.cooldown_after_failure_s,
            )
        return rec

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
        invalidation: float,
        target: float | None,
        pip: float,
        info_id: str,
        portfolio_ok: bool,
        portfolio_reason: str,
        symbol_spec: Mapping[str, Any] | None,
        question: str,
    ) -> tuple[DemoDecision | None, str | None]:
        """Exploration Firehose gate chain. Returns (fire_decision, skip_reason).

        Plausibility only - NOT profitability: valid geometry, no absurd payoff
        asymmetry, portfolio room, no known-failed identical hypothesis, hard
        independent limits. Champion validation is NOT required here and this
        NEVER weakens champion requirements.
        """
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
        book_logic: dict[str, Any] = {}
        try:
            from aegis.intel import knowledge_retrieval

            state_ctx = {
                "regime": regime,
                "session": session,
                "structure": str(signature.get("structure") or setup),
                "volatility": str(state.get("volatility") or ""),
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
        except Exception:
            book_logic = {}
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

        sl_dist = abs(float(entry) - float(invalidation))
        if sl_dist <= 0:
            return None, "exploration_no_invalidation"
        if target is not None:
            tp_dist = abs(float(target) - float(entry))
            if tp_dist / sl_dist < 0.25:
                return None, "exploration_absurd_payoff"
        # Self-hedge audit (spec J): opposing exposure on the same symbol is
        # legitimate ONLY with a genuinely different mechanism (family).
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
                if str(mem.setup_family or "").lower() == str(setup).lower():
                    return None, "self_hedge_blocked_same_family"
                # Different family = different mechanism/horizon: allowed, but
                # the double-spread cost must be acknowledged in the record.
        if not portfolio_ok:
            return None, portfolio_reason or "portfolio_risk"

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
        self.experiments.save()
        lots = risk_lots_for_exploration(
            max_risk_usd=self._exploration_limits.max_risk_per_trade_usd,
            entry=entry,
            invalidation=invalidation,
            pip=pip,
            min_lot=float(spec.get("volume_min", 0.01) or 0.01),
            lot_step=float(spec.get("volume_step", 0.01) or 0.01),
        )
        thesis_key_exp = thesis_key(symbol, side, setup, regime=regime, session=session)
        self._exploration_theses.add(thesis_key_exp)
        # Reservation must be visible to audits: record side/family on the
        # thesis memory so self-hedge checks can identify it.
        _mem = self.memory.get(thesis_key_exp, symbol)
        _mem.symbol = str(symbol).upper()
        _mem.side = side
        _mem.setup_family = setup
        # Reserve in-flight exposure BEFORE returning the decision so parallel
        # bar evaluations cannot race past max_positions.
        self.memory.exploration_pending.setdefault(thesis_key_exp, []).append(
            datetime.now(timezone.utc).timestamp()
        )
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
            "exit_plan": exit_plan,
            "book_logic": book_logic,
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
        funnel = {
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
            "counts": {k: v for k, v in self.counts.items() if k != "skip_reasons"},
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
    ) -> DemoDecision:
        clip_qty = float(self.cfg.get("order_quantity", 0.01))
        clip_risk = max(self._risk_budget * float(self.cfg.get("intelligent_risk_fraction", 0.08)) / 5.0, 0.01)
        self.counts["scans"] = int(self.counts.get("scans", 0)) + 1
        self.memory.sync_from_positions(symbol, positions, clip_risk)
        state = build_runtime_state(symbol=symbol, m1=completed_m1)
        m15 = (state.get("structure") or {}).get("M15") or {}
        setup = str(m15.get("kind") or "scan")
        side = str(core_side or "").lower()
        if side not in {"buy", "sell"}:
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
        if invalidation is None and held.clips <= 0:
            self._note_skip("no_structural_invalidation")
            self.counts["skip"] += 1
            return DemoDecision("skip", "no_structural_invalidation", side=side, journal={"brain": "intelligent_firehose"})
        signature = runtime_signature(state, side=side, setup=setup)
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
            # Symbol-aware opportunities first (LEVEL A/B), then pooled LEVEL C.
            opp_key = "|".join([
                str(symbol).upper(),
                str(signature.get("regime") or ""),
                str(signature.get("structure") or ""),
                str(signature.get("session") or ""),
                side,
            ])
            opportunity = self.validated_opportunities.get(opp_key)
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
        exploration_journal: dict[str, Any] | None = None
        if (
            fire.action == "skip"
            and held.clips <= 0
            and invalidation is not None
            and bool(self.cfg.get("intelligent_exploration_enabled", True))
        ):
            book_family = str((books[0] or {}).get("strategy_family") or "") if books else ""
            exp_decision, exp_skip = self._maybe_explore(
                symbol=symbol,
                side=side,
                setup=setup,
                signature=signature,
                entry=float(entry_price if entry_price is not None else close),
                invalidation=float(invalidation),
                target=target,
                pip=pip,
                info_id=info_id,
                portfolio_ok=portfolio_ok,
                portfolio_reason=portfolio_reason,
                symbol_spec=symbol_spec,
                question=(f"book-derived family {book_family}" if book_family
                          else "firehose scan candidate"),
            )
            if exp_decision is not None:
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
