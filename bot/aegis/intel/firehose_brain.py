"""Intelligent Firehose demo brain. Runner imports this module only."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd

from aegis.engines import PositionSnapshot
from aegis.intel.analogue_store import AnalogueStore, is_measured_provenance
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
    validated strategies on the same symbol coexist as separate theses."""

    thesis_key: str
    symbol: str
    side: str | None = None
    setup_family: str = ""
    information_id: str | None = None
    current_risk_usd: float = 0.0
    clips: int = 0


def thesis_key(symbol: str, side: str | None, setup_family: str) -> str:
    return "|".join([str(symbol).upper(), str(side or "").lower(), str(setup_family or "").lower()])


@dataclass
class DemoBrainState:
    theses: dict[str, ThesisMemory] = field(default_factory=dict)

    def get(self, key: str, symbol: str | None = None) -> ThesisMemory:
        mem = self.theses.get(key)
        if mem is None:
            sym = symbol or key.split("|")[0]
            mem = ThesisMemory(thesis_key=key, symbol=str(sym).upper())
            self.theses[key] = mem
        return mem

    def sync_from_positions(self, symbol: str, positions: Sequence[PositionSnapshot], clip_risk: float) -> list[ThesisMemory]:
        """Reconcile open positions into per-thesis memories (symbol+side match).

        Returns every thesis of this symbol that currently holds exposure.
        Positions whose side matches no tracked thesis are adopted under a
        generic held-key so exposure accounting never loses them.
        """
        mine = [pos for pos in positions if str(pos.symbol).upper() == str(symbol).upper()]
        by_side: dict[str, list[PositionSnapshot]] = {}
        for pos in mine:
            by_side.setdefault(str(pos.side).lower(), []).append(pos)
        touched: list[ThesisMemory] = []
        matched_sides: set[str] = set()
        for key, mem in self.theses.items():
            if mem.symbol != str(symbol).upper():
                continue
            side_positions = by_side.get(str(mem.side or "").lower(), [])
            if mem.side and side_positions:
                matched_sides.add(str(mem.side).lower())
                mem.clips = len(side_positions)
                mem.current_risk_usd = max(mem.current_risk_usd, float(clip_risk) * len(side_positions))
                touched.append(mem)
            elif mem.clips > 0:
                # Position closed upstream (flatten/stop): clear the thesis.
                mem.clips = 0
                mem.current_risk_usd = 0.0
                mem.information_id = None
        for side, side_positions in by_side.items():
            if side in matched_sides:
                continue
            key = thesis_key(symbol, side, "held")
            mem = self.get(key, symbol)
            mem.side = side
            mem.setup_family = "held"
            mem.clips = len(side_positions)
            mem.current_risk_usd = max(mem.current_risk_usd, float(clip_risk) * len(side_positions))
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
    ) -> None:
        key = thesis_key(symbol, side, setup_family)
        held = self.get(key, symbol)
        if action == "exit":
            held.current_risk_usd = 0.0
            held.information_id = None
            held.side = None
            held.clips = 0
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
        out[key] = rec
    return out


def _bootstrap_from_evidence(cfg: Mapping[str, Any], evidence: Any) -> ValidatedStrategyModel | None:
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
    stage = STAGE_DEMO_CANARY if bool(cfg.get("intelligent_bootstrap_canary", False)) \
        else STAGE_UNVALIDATED_RESEARCH
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
        return {
            "brain": "intelligent_firehose",
            "counts": {k: v for k, v in self.counts.items() if k != "skip_reasons"},
            "skip_reasons": dict(
                sorted(self.counts.get("skip_reasons", {}).items(), key=lambda kv: -kv[1])[:20]
            ),
            "shadow_fires": int(self.counts.get("shadow_fires", 0)),
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
            # An empty index means every decision is made on no evidence. That is a
            # misconfiguration, not a quiet market, so make it visible.
            "warnings": [
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
            ],
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
        held = self.memory.get(thesis_key(symbol, side, setup), symbol)
        invalidation, target = _geometry(side, m15, pip)
        if invalidation is None and held.clips <= 0:
            self._note_skip("no_structural_invalidation")
            self.counts["skip"] += 1
            return DemoDecision("skip", "no_structural_invalidation", side=side, journal={"brain": "intelligent_firehose"})
        signature = runtime_signature(state, side=side, setup=setup)
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
        strategy = self.strategy or _bootstrap_from_evidence(self.cfg, evidence)
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
