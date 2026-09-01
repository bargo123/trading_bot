"""$100/day is an economic objective, not a leverage instruction."""
from __future__ import annotations

from pathlib import Path

from aegis.research.firehose_economics import (
    TARGET_DAILY_USD,
    classify_gap_close,
    firehose_economic_snapshot,
    markdown_firehose_economics,
    required_capital_for_target,
)


def test_target_is_one_hundred_not_a_daily_quota():
    assert TARGET_DAILY_USD == 100.0


def test_negative_edge_cannot_be_closed_by_leverage_or_lot_size():
    result = required_capital_for_target(
        expected_net_day=-11.74,
        current_capital=92.2,
        target_daily_usd=100.0,
        verified=True,
    )
    assert result["required_capital_usd"] is None
    assert result["method"] == "non_positive_edge_cannot_be_scaled"
    assert "leverage" not in result["method"]
    assert result["forbidden"] == "do_not_lever_current_account_to_force_target"


def test_positive_edge_scales_capital_not_risk_percentage():
    result = required_capital_for_target(
        expected_net_day=2.0,
        current_capital=100.0,
        target_daily_usd=100.0,
        verified=True,
        validated_risk_fraction=0.01,
    )
    assert result["required_capital_usd"] == 5000.0
    assert result["method"] == "scale_account_at_same_risk_fraction"
    assert result["risk_fraction_held_constant"] == 0.01
    assert result["leverage_increase"] is False


def test_unverified_observation_does_not_invent_required_capital():
    result = required_capital_for_target(
        expected_net_day=2.0,
        current_capital=100.0,
        target_daily_usd=100.0,
        verified=False,
    )
    assert result["required_capital_usd"] is None
    assert result["method"] == "no_verified_champion"


def test_gap_close_for_cosmetic_negative_spray_is_edge_and_payoff_not_more_trades():
    reasons = classify_gap_close(
        expectancy=-0.006,
        expected_net_day=-11.74,
        cosmetic_win_rate=True,
        profit_factor=0.78,
        trades_per_day=400.0,
    )
    assert "better_edge" in reasons
    assert "healthier_payoff" in reasons
    assert "increase_leverage" not in reasons
    assert "increase_lot_size_on_current_account" not in reasons
    assert "must_make_100_today" not in reasons


def test_snapshot_from_tiny_win_fat_loss_deals_refuses_size_up(tmp_path: Path):
    deals = tmp_path / "deals.jsonl"
    lines = []
    for i in range(10):
        lines.append(
            '{"source":"mt5_deal","ticket":"%s","pnl":0.03,"qty":0.01,"ts":"2026-01-01T0%d:00:00+00:00"}'
            % (i + 1, i)
        )
    lines.append(
        '{"source":"mt5_deal","ticket":"99","pnl":-0.40,"qty":0.01,"ts":"2026-01-01T12:00:00+00:00"}'
    )
    deals.write_text("\n".join(lines), encoding="utf-8")
    snap = firehose_economic_snapshot(
        deals_path=deals,
        current_capital=93.0,
        champion={"id": None, "status": "none"},
        target_daily_usd=100.0,
    )
    assert snap["verified_champion"]["status"] == "none"
    assert snap["observed"]["win_rate"] > 0.9
    assert snap["observed"]["expectancy"] < 0
    assert snap["observed"]["cosmetic_win_rate"] is True
    assert snap["observed"]["wins_erased_by_average_loss"] > 10
    assert snap["required_capital"]["required_capital_usd"] is None
    assert snap["gap"]["close_through"][0] == "better_edge"
    assert "must_make_100_today" not in snap
    assert snap["leverage_increase_recommended"] is False
    text = markdown_firehose_economics(snap)
    assert "$100/day" in text
    assert "not a leverage instruction" in text.lower() or "same validated risk" in text.lower()
    assert "93" in text


def test_positive_verified_champion_estimates_capital_at_same_risk():
    snap = firehose_economic_snapshot(
        deals_path=None,
        current_capital=1_000.0,
        champion={
            "id": "failed_break_v1",
            "status": "accepted",
            "expectancy": 0.50,
            "trades_per_day": 4.0,
            "profit_factor": 1.6,
            "avg_win": 1.2,
            "avg_loss": -0.7,
            "max_drawdown_pct": 8.0,
            "tail_loss": 2.0,
            "validated_risk_fraction": 0.01,
            "n_trades": 80,
            "n_losses": 12,
        },
        target_daily_usd=100.0,
    )
    assert snap["verified_champion"]["id"] == "failed_break_v1"
    assert snap["verified_champion"]["expected_net_day"] == 2.0
    assert snap["required_capital"]["required_capital_usd"] == 50_000.0
    assert snap["gap"]["difference_usd"] == 98.0
    assert "additional_capital" in snap["gap"]["close_through"]
    assert snap["leverage_increase_recommended"] is False
