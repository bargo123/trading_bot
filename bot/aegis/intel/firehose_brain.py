"""Intelligent Firehose demo brain. Runner imports this module only."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd

from aegis.engines import PositionSnapshot
from aegis.intel.analogue_store import AnalogueStore
from aegis.intel.knowledge_runtime import load_knowledge_rows, match_knowledge
from aegis.intel.lifecycle import exposure_snapshot, pretrade_ok
from aegis.intel.state_runtime import build_runtime_state, runtime_signature
from aegis.intel.strategy_model import ValidatedStrategyModel, strategy_model_ready
from aegis.intel.thesis_fire import ThesisFireDecision, evaluate_thesis_action, evaluate_thesis_fire


@dataclass
class ThesisMemory:
    symbol: str
    side: str | None = None
    information_id: str | None = None
    current_risk_usd: float = 0.0
    clips: int = 0


@dataclass
class DemoBrainState:
    theses: dict[str, ThesisMemory] = field(default_factory=dict)

    def get(self, symbol: str) -> ThesisMemory:
        key = str(symbol).upper()
        return self.theses.setdefault(key, ThesisMemory(symbol=key))

    def sync_from_positions(self, symbol: str, positions: Sequence[PositionSnapshot], clip_risk: float) -> ThesisMemory:
        held = self.get(symbol)
        mine = [pos for pos in positions if str(pos.symbol).upper() == str(symbol).upper()]
        held.clips = len(mine)
        if not mine:
            held.current_risk_usd = 0.0
            held.information_id = None
            held.side = None
            return held
        held.side = str(mine[0].side).lower()
        held.current_risk_usd = max(held.current_risk_usd, float(clip_risk) * len(mine))
        return held

    def apply(
        self,
        symbol: str,
        action: str,
        *,
        side: str | None,
        information_id: str | None,
        target_risk: float,
        clips: int | None = None,
    ) -> None:
        held = self.get(symbol)
        if action == "exit":
            held.current_risk_usd = 0.0
            held.information_id = None
            held.side = None
            held.clips = 0
            return
        if action in {"fire", "scale"}:
            held.side = side
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
    path = Path(
        str(
            cfg.get("intelligent_champion_path")
            or (Path(__file__).resolve().parents[2] / "intel" / "intelligent_champion.json")
        )
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
        )
    except (KeyError, TypeError, ValueError):
        return None
    ready, _ = strategy_model_ready(model)
    return model if ready else None


def _bootstrap_from_evidence(cfg: Mapping[str, Any], evidence: Any) -> ValidatedStrategyModel | None:
    """Use analogue evidence as-is. Never inflate PF or hide a cosmetic WR."""
    if not bool(cfg.get("intelligent_firehose_bootstrap", False)):
        return None
    if not evidence.eligible:
        return None
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
        )
    except (TypeError, ValueError):
        return None
    ready, _ = strategy_model_ready(model)
    return model if ready else None


class IntelligentFirehoseBrain:
    def __init__(self, cfg: Mapping[str, Any]) -> None:
        self.cfg = dict(cfg)
        index_path = Path(
            str(
                cfg.get("analogue_index_path")
                or (Path(__file__).resolve().parents[2] / "intel" / "analogue_index.json")
            )
        )
        knowledge_path = Path(
            str(
                cfg.get("knowledge_table_path")
                or (Path(__file__).resolve().parents[2] / "intel" / "knowledge_table.json")
            )
        )
        self.analogues = AnalogueStore.load(index_path)
        self.knowledge_rows = load_knowledge_rows(knowledge_path)
        self.strategy = _load_strategy(cfg)
        self.memory = DemoBrainState()
        self._risk_budget = float(cfg.get("intelligent_risk_budget_usd") or cfg.get("starting_equity") or 100.0)
        self.counts = {"fire": 0, "scale": 0, "hold": 0, "reduce": 0, "exit": 0, "skip": 0}

    def snapshot(self) -> dict[str, Any]:
        return {
            "brain": "intelligent_firehose",
            "counts": dict(self.counts),
            "analogue_records": len(getattr(self.analogues, "_records", [])),
            "knowledge_rows": len(self.knowledge_rows),
            "champion": None if self.strategy is None else self.strategy.strategy_id,
            "bootstrap": bool(self.cfg.get("intelligent_firehose_bootstrap", False)),
        }

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
    ) -> DemoDecision:
        clip_qty = float(self.cfg.get("order_quantity", 0.01))
        clip_risk = max(self._risk_budget * float(self.cfg.get("intelligent_risk_fraction", 0.08)) / 5.0, 0.01)
        held = self.memory.sync_from_positions(symbol, positions, clip_risk)
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
        invalidation, target = _geometry(side, m15, pip)
        if invalidation is None and held.clips <= 0:
            self.counts["skip"] += 1
            return DemoDecision("skip", "no_structural_invalidation", side=side, journal={"brain": "intelligent_firehose"})
        signature = runtime_signature(state, side=side, setup=setup)
        evidence = self.analogues.query(
            signature=signature,
            before_time=row["time"],
            min_n=int(self.cfg.get("intelligent_min_analogues", 20)),
            min_similarity=float(self.cfg.get("intelligent_min_similarity", 0.55)),
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
        exposure = exposure_snapshot(positions)
        journal = {
            "brain": "intelligent_firehose",
            "action": mapped,
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
        }
        return DemoDecision(
            mapped,
            action.reason,
            side=side,
            sl=invalidation,
            tp=target,
            quantity=clip_qty,
            expected_net_value=action.expected_net_value,
            information_id=info_id,
            analogue_n=evidence.analogue_n,
            close_clips=close_clips,
            journal=journal,
        )
