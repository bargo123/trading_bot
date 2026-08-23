"""Tests for governed champion promotion (research-only, read-only)."""
from __future__ import annotations

import numpy as np

import pytest

from aegis.research.gates import GateReject
from aegis.research.promote import (
    PromotionReject,
    challenger_promotion_result,
    challenger_promotion_result_from_callback,
)
from aegis.research.sealed import SealedHoldoutStore


def _healthy_pnls(seed: int = 0) -> list[float]:
    rng = np.random.default_rng(seed)
    wins = rng.uniform(0.8, 2.0, size=60)
    losses = -rng.uniform(0.4, 0.6, size=20)
    return [float(x) for x in np.concatenate([wins, losses])]


def _healthy_holdout_metrics(pnls: list[float]) -> dict:
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    avg_win = sum(wins) / len(wins)
    avg_loss = sum(losses) / len(losses)
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    return {
        "expectancy": sum(pnls) / len(pnls),
        "profit_factor": gross_win / gross_loss,
        "n_trades": len(pnls),
        "net_pnl": sum(pnls),
        "win_rate": len(wins) / len(pnls),
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "tail_loss": abs(min(losses)),
    }


def _run_promotion(tmp_path, **overrides) -> dict:
    validation = _healthy_pnls(seed=1)
    holdout = _healthy_pnls(seed=2)
    params = dict(
        strategy_id="asia_sell_v1",
        code_hash="code-1",
        artifact_hash="art-1",
        config={"session": "asia", "side": "sell"},
        validation_pnls=validation,
        holdout_metrics=_healthy_holdout_metrics(holdout),
        holdout_pnls=holdout,
        validated_risk_fraction=0.10,
        n_searches=1,
        champion=None,
        sealed_store=SealedHoldoutStore(tmp_path / "sealed.jsonl"),
        champion_path=tmp_path / "intelligent_champion.json",
    )
    params.update(overrides)
    return challenger_promotion_result(**params)


def test_healthy_challenger_promotes(tmp_path):
    result = _run_promotion(tmp_path)
    assert result["champion"]["status"] == "accepted"
    assert result["champion"]["id"] == "asia_sell_v1"
    assert result["champion"]["n_trades"] == 80
    assert result["champion"]["n_losses"] == 20
    assert result["champion"]["profit_factor"] > 1
    assert result["champion"]["wins_erased_by_average_loss"] < 1
    assert result["placed_orders"] is False


def test_rejected_on_negative_holdout_expectancy(tmp_path):
    pnls = [float(x) for x in np.linspace(-0.5, 0.5, 80)]
    with pytest.raises(PromotionReject):
        _run_promotion(tmp_path, holdout_metrics=_healthy_holdout_metrics(pnls))


def test_rejected_when_holdout_lacks_loss_tail(tmp_path):
    pnls = [0.5] * 80
    with pytest.raises(PromotionReject):
        _run_promotion(tmp_path, holdout_pnls=pnls)


def test_rejected_when_validation_too_thin(tmp_path):
    with pytest.raises(PromotionReject, match=">=20 trades"):
        _run_promotion(tmp_path, validation_pnls=[0.1] * 10)


def test_champion_requires_strict_improvement(tmp_path):
    champion = {
        "expectancy": 1.0,
        "net_pnl": 500.0,
    }
    holdout = _healthy_pnls(seed=2)
    with pytest.raises(GateReject):
        _run_promotion(
            tmp_path,
            champion=champion,
            holdout_metrics={
                **_healthy_holdout_metrics(holdout),
                "expectancy": 0.9,
                "net_pnl": 400.0,
            },
        )


def test_promotion_writes_governed_artifact(tmp_path):
    path = tmp_path / "champion.json"
    result = _run_promotion(tmp_path, champion_path=path)
    assert path.exists()
    import json

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["status"] == "accepted"
    assert payload["id"] == "asia_sell_v1"
    assert payload["role"] == "INTELLIGENT_FIREHOSE_CHAMPION"


def test_destructive_payoff_geometry_fails(tmp_path):
    rng = np.random.default_rng(7)
    wins = [0.02] * 76
    losses = [-1.0] * 4
    pnls = [float(x) for x in wins + losses]
    metrics = _healthy_holdout_metrics(pnls)
    with pytest.raises(PromotionReject):
        _run_promotion(tmp_path, holdout_metrics=metrics, holdout_pnls=pnls)


def test_callback_promotion_freezes_before_sealed_evaluation(tmp_path):
    validation = _healthy_pnls(seed=1)
    holdout = _healthy_pnls(seed=2)
    callback_candidates = []

    def evaluate_holdout(frozen):
        callback_candidates.append(frozen)
        assert frozen.strategy_id == "asia_sell_callback_v1"
        assert not hasattr(frozen, "sealed_holdout")
        return {
            "metrics": _healthy_holdout_metrics(holdout),
            "pnls": holdout,
        }

    result = challenger_promotion_result_from_callback(
        strategy_id="asia_sell_callback_v1",
        code_hash="code-callback",
        artifact_hash="artifact-callback",
        config={"session": "asia", "side": "sell"},
        validation_pnls=validation,
        holdout_fingerprint="holdout-full-content-fingerprint",
        evaluate_holdout=evaluate_holdout,
        validated_risk_fraction=0.10,
        sealed_store=SealedHoldoutStore(tmp_path / "callback-sealed.jsonl"),
        champion_path=tmp_path / "callback-champion.json",
    )

    assert callback_candidates[0].frozen_hash == result["frozen"]["frozen_hash"]
    assert result["sealed_holdout"]["holdout_fingerprint"] == (
        "holdout-full-content-fingerprint"
    )
    assert result["holdout_metrics"]["n_trades"] == 80
    assert result["champion"]["status"] == "accepted"


def test_callback_promotion_rejects_thin_validation_before_sealed_callback(tmp_path):
    called = False

    def evaluate_holdout(frozen):
        nonlocal called
        called = True
        return {"metrics": {}, "pnls": []}

    with pytest.raises(PromotionReject, match=">=20 trades"):
        challenger_promotion_result_from_callback(
            strategy_id="asia_sell_callback_v1",
            code_hash="code-callback",
            artifact_hash="artifact-callback",
            config={"session": "asia", "side": "sell"},
            validation_pnls=[0.1] * 10,
            holdout_fingerprint="holdout-full-content-fingerprint",
            evaluate_holdout=evaluate_holdout,
            validated_risk_fraction=0.10,
            sealed_store=SealedHoldoutStore(tmp_path / "callback-sealed.jsonl"),
            champion_path=tmp_path / "callback-champion.json",
        )
    assert called is False
