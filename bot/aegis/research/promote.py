"""Governed Intelligent Firehose champion promotion.

Ties the existing research stack together so a challenger can only reach
`intel/intelligent_champion.json` through: validation gates -> freeze ->
one-shot sealed holdout -> bootstrap/tail/stress gates -> strategy model
readiness. It never writes live YAML and never places orders.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from aegis.intel.strategy_model import ValidatedStrategyModel, strategy_model_ready
from aegis.research.govern import governed_accept
from aegis.research.gates import GateReject, evaluate_promotion
from aegis.research.intelligent_champion import (
    INTELLIGENT_CHAMPION_PATH,
    save_intelligent_champion,
)
from aegis.research.sealed import SealedHoldoutStore, freeze_candidate
from aegis.research.stress import bootstrap_expectancy, tail_stress

SEALED_STORE_PATH = Path(__file__).resolve().parents[2] / "research" / "sealed_holdouts.jsonl"


class PromotionReject(GateReject):
    """Challenger failed the governed promotion path. Kept on record; not promoted."""


def challenger_promotion_result(
    *,
    strategy_id: str,
    code_hash: str,
    artifact_hash: str,
    config: Mapping[str, Any],
    validation_pnls: Sequence[float],
    holdout_metrics: Mapping[str, Any],
    holdout_pnls: Sequence[float],
    validated_risk_fraction: float,
    n_searches: int = 1,
    champion: Mapping[str, Any] | None = None,
    sealed_store: SealedHoldoutStore | None = None,
    champion_path: Path | None = None,
) -> dict[str, Any]:
    """Run the full promotion path. Raises PromotionReject on any failed gate.

    The sealed holdout is scored exactly once per (frozen, holdout) pair, so a
    rejected challenger cannot be re-peeked against the same holdout.
    """
    validation = bootstrap_expectancy(list(validation_pnls))
    if int(validation["n"]) < 20:
        raise PromotionReject(f"validation bootstrap needs >=20 trades, got {int(validation['n'])}")

    holdout = dict(holdout_metrics)
    n_holdout = int(holdout.get("n_trades") or 0)
    holdout_pf = holdout.get("profit_factor")
    if n_holdout < 20:
        raise PromotionReject(f"holdout needs >=20 trades, got {n_holdout}")
    if holdout_pf is None or float(holdout_pf) <= 1.0:
        raise PromotionReject(f"holdout profit_factor must be > 1, got {holdout_pf}")

    tail = tail_stress(list(holdout_pnls))
    if tail["n_losses"] < 5:
        raise PromotionReject(f"holdout needs >=5 losses, got {int(tail['n_losses'])}")

    governed_accept(
        dict(holdout),
        champion=dict(champion) if champion else None,
        pnls=list(holdout_pnls),
        n_searches=n_searches,
        worst_case_loss=tail["worst_loss"] or None,
    )

    frozen = freeze_candidate(
        strategy_id=strategy_id,
        code_hash=code_hash,
        config=dict(config),
        artifact_hash=artifact_hash,
    )
    store = sealed_store if sealed_store is not None else SealedHoldoutStore(SEALED_STORE_PATH)
    record = store.evaluate_once(
        frozen,
        holdout_fingerprint=artifact_hash,
        evaluate=lambda: {
            "expectancy": float(holdout.get("expectancy") or holdout.get("expectancy_r") or 0.0),
            "profit_factor": float(holdout_pf),
            "n_trades": n_holdout,
            "net_pnl": float(holdout.get("net_pnl") or 0.0),
            "win_rate": float(holdout.get("win_rate") or 0.0),
        },
    )

    pf = float(holdout_pf)
    expectancy = float(holdout.get("expectancy") or holdout.get("expectancy_r") or 0.0)
    avg_win = float(holdout.get("avg_win") or 0.0)
    avg_loss = float(holdout.get("avg_loss") or 0.0)
    if avg_win > 0 and avg_loss < 0:
        erased_avg = abs(avg_loss) / avg_win
        tail_loss = float(holdout.get("tail_loss") or 0.0)
        erased_tail = tail_loss / avg_win if tail_loss > 0 else 0.0
    else:
        erased_avg = 0.0
        erased_tail = 0.0

    model = ValidatedStrategyModel(
        strategy_id=strategy_id,
        promoted=True,
        n_trades=n_holdout,
        n_losses=int(tail["n_losses"]),
        expectancy=expectancy,
        profit_factor=pf,
        bootstrap_p05=float(validation["p05"]),
        wins_erased_by_average_loss=float(erased_avg),
        wins_erased_by_tail_loss=float(erased_tail),
        validated_risk_fraction=float(validated_risk_fraction),
        artifact_hash=str(artifact_hash),
    )
    ready, reason = strategy_model_ready(model)
    if not ready:
        raise PromotionReject(f"strategy model not ready after sealed holdout: {reason}")

    payload = save_intelligent_champion(
        model,
        path=champion_path if champion_path is not None else INTELLIGENT_CHAMPION_PATH,
    )
    return {
        "schema": "champion_promotion.v1",
        "label": "research_proxy",
        "placed_orders": False,
        "mt5_touched": False,
        "promoted_live_yaml": False,
        "champion": payload,
        "frozen": frozen.as_dict(),
        "sealed_holdout": record,
        "validation": validation,
        "holdout_metrics": holdout,
        "strategy_model_ready": reason,
    }


def promotion_result_markdown(result: Mapping[str, Any]) -> str:
    champ = result.get("champion") or {}
    frozen = result.get("frozen") or {}
    sealed = result.get("sealed_holdout") or {}
    return "\n".join(
        [
            "# Intelligent Champion promotion (governed)",
            "",
            "Label: `research_proxy`. No orders placed; no live YAML promotion.",
            "",
            f"- strategy_id: {champ.get('id')}",
            f"- status: {champ.get('status')}",
            f"- n_trades: {champ.get('n_trades')}",
            f"- n_losses: {champ.get('n_losses')}",
            f"- expectancy: {champ.get('expectancy')}",
            f"- profit_factor: {champ.get('profit_factor')}",
            f"- bootstrap_p05: {champ.get('bootstrap_p05')}",
            f"- wins_erased_by_average_loss: {champ.get('wins_erased_by_average_loss')}",
            f"- validated_risk_fraction: {champ.get('validated_risk_fraction')}",
            "",
            "## Frozen candidate",
            "",
            f"- frozen_hash: {frozen.get('frozen_hash')}",
            f"- frozen_at: {frozen.get('frozen_at')}",
            f"- artifact_hash: {frozen.get('artifact_hash')}",
            "",
            "## Sealed holdout",
            "",
            f"- evaluated_at: {sealed.get('evaluated_at')}",
            f"- expectancy: {sealed.get('metrics', {}).get('expectancy')}",
            f"- profit_factor: {sealed.get('metrics', {}).get('profit_factor')}",
            f"- n_trades: {sealed.get('metrics', {}).get('n_trades')}",
            "",
        ]
    )