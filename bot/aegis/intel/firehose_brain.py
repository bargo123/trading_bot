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
from aegis.intel.state_runtime import build_runtime_state, runtime_signature
from aegis.intel.strategy_model import ValidatedStrategyModel, strategy_model_ready
from aegis.intel.thesis_fire import evaluate_thesis_action, evaluate_thesis_fire
from aegis.portfolio_risk import portfolio_pretrade_decision


@dataclass
class ThesisMemory:
    symbol: str
    side: str | None = None
    information_id: str | None = None
    current_risk_usd: float = 0.0


@dataclass
class DemoBrainState:
    theses: dict[str, ThesisMemory] = field(default_factory=dict)

    def get(self, symbol: str) -> ThesisMemory:
        key = str(symbol).upper()
        return self.theses.setdefault(key, ThesisMemory(symbol=key))

    def apply(
        self,
        symbol: str,
        action: str,
        *,
        side: str | None,
        information_id: str | None,
        target_risk: float,
    ) -> None:
        held = self.get(symbol)
        if action == "exit":
            held.current_risk_usd = 0.0
            held.information_id = None
            held.side = None
            return
        if action in {"fire", "scale"}:
            held.side = side
            held.information_id = information_id
            held.current_risk_usd = max(held.current_risk_usd, float(target_risk))
        elif action == "reduce":
            held.current_risk_usd = float(target_risk)
            if held.current_risk_usd <= 0:
                held.information_id = None
                held.side = None


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


class IntelligentFirehoseBrain:
    def __init__(self, cfg: Mapping[str, Any]) -> None:
        self.cfg = dict(cfg)
        index_path = Path(
            str(
                cfg.get("analogue_index_path")
                or (Path(__file__).resolve().parents[2] / "intel" / "analogue_index.json")
            )
        )
        self.analogues = AnalogueStore.load(index_path)
        self.strategy = _load_strategy(cfg)
        self.memory = DemoBrainState()
        self._risk_budget = float(cfg.get("intelligent_risk_budget_usd") or cfg.get("starting_equity") or 100.0)

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
        _ = equity
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
                side = "buy" if close >= float(completed_m1["close"].iloc[-2]) else "sell"
        invalidation, target = _geometry(side, m15, pip)
        if invalidation is None:
            return DemoDecision("skip", "no_structural_invalidation", side=side, journal={"brain": "intelligent_firehose"})
        signature = runtime_signature(state, side=side, setup=setup)
        evidence = self.analogues.query(
            signature=signature,
            before_time=row["time"],
            min_n=int(self.cfg.get("intelligent_min_analogues", 20)),
            min_similarity=float(self.cfg.get("intelligent_min_similarity", 0.55)),
        )
        held = self.memory.get(symbol)
        portfolio_ok, portfolio_reason, _event = portfolio_pretrade_decision(
            positions=list(positions),
            symbol=str(symbol).upper(),
            side=side,
            quantity=float(self.cfg.get("order_quantity", 0.01)),
            avg_price=float(row["close"]),
            cfg={
                "max_positions": int(self.cfg.get("max_positions", 40)),
                "max_currency_direction_positions": int(self.cfg.get("max_currency_direction_positions", 0) or 0),
                "max_per_symbol": int(self.cfg.get("intelligent_max_clips_per_thesis", 5)),
            },
        )
        strategy = self.strategy
        if strategy is None and bool(self.cfg.get("intelligent_firehose_bootstrap", True)) and evidence.eligible:
            strategy = ValidatedStrategyModel(
                strategy_id="analogue_bootstrap",
                promoted=True,
                n_trades=max(evidence.analogue_n, 20),
                n_losses=max(evidence.analogue_n_losses, 5),
                expectancy=float(evidence.expectancy or 0.0),
                profit_factor=max(float(evidence.profit_factor or 0.0), 1.01),
                bootstrap_p05=max(float(evidence.mean_lower_95 or 0.0), 0.001),
                wins_erased_by_average_loss=min(float(evidence.wins_erased_by_average_loss or 99.0), 3.0),
                wins_erased_by_tail_loss=1.0,
                validated_risk_fraction=float(self.cfg.get("intelligent_risk_fraction", 0.08)),
                artifact_hash="bootstrap",
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
        info_id = _information_id(
            symbol=symbol,
            side=side,
            setup=setup,
            invalidation=f"{invalidation:.5f}",
            session=str(state.get("session") or ""),
        )
        target_risk = 0.0
        if evidence.eligible and strategy is not None and strategy.validated_risk_fraction:
            target_risk = self._risk_budget * float(strategy.validated_risk_fraction)
        action = evaluate_thesis_action(
            fire_decision=fire,
            information_id=info_id,
            last_information_id=held.information_id,
            current_risk_usd=held.current_risk_usd,
            target_risk_usd=target_risk,
            invalidated=False,
        )
        qty = float(self.cfg.get("order_quantity", 0.01))
        if action.action in {"fire", "scale", "reduce", "exit"}:
            self.memory.apply(
                symbol,
                action.action if action.action != "scale" else "scale",
                side=side,
                information_id=info_id,
                target_risk=target_risk,
            )
        journal = {
            "brain": "intelligent_firehose",
            "action": action.action,
            "analogue_n": evidence.analogue_n,
            "expectancy": evidence.expectancy,
            "uncertainty": evidence.uncertainty,
            "similarity": evidence.similarity_score,
            "information_id": info_id,
            "regime": signature.get("regime"),
            "structure": signature.get("structure"),
        }
        return DemoDecision(
            action.action,
            action.reason,
            side=side,
            sl=invalidation,
            tp=target,
            quantity=qty,
            expected_net_value=action.expected_net_value,
            information_id=info_id,
            analogue_n=evidence.analogue_n,
            journal=journal,
        )
