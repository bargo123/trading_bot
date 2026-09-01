"""Payoff quality, not cosmetic win rate. Runtime EV helpers must not import research."""
from __future__ import annotations

import ast
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_intel_ev_modules_do_not_import_research():
    for rel in (
        "aegis/intel/expected_value.py",
        "aegis/intel/strategy_model.py",
        "aegis/intel/thesis_fire.py",
    ):
        source = (ROOT / rel).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module)
        assert all("research" not in name.split(".") for name in imported), rel
        assert "aegis.research" not in source


def test_tiny_win_large_loss_is_negative_expectancy_despite_high_wr():
    """Scaled 10×$0.03 then 1×$0.40: lots of wins, negative result."""
    from aegis.intel.expected_value import payoff_metrics

    pnls = [0.03] * 91 + [-0.40] * 9
    stats = payoff_metrics(pnls)
    assert stats["n"] == 100
    assert stats["n_losses"] == 9
    assert stats["win_rate"] == pytest.approx(0.91)
    assert stats["avg_win"] == pytest.approx(0.03)
    assert stats["avg_loss"] == pytest.approx(-0.40)
    assert stats["wins_erased_by_average_loss"] == pytest.approx(0.40 / 0.03)
    assert stats["wins_erased_by_tail_loss"] == pytest.approx(0.40 / 0.03)
    assert stats["breakeven_wr"] > 0.90
    assert stats["expectancy"] < 0
    assert stats["profit_factor"] < 1
    assert stats["cosmetic_win_rate"] is True


def test_healthy_payoff_is_not_cosmetic_even_at_lower_win_rate():
    from aegis.intel.expected_value import payoff_metrics

    pnls = [0.20] * 60 + [-0.10] * 40
    stats = payoff_metrics(pnls)
    assert stats["win_rate"] == pytest.approx(0.60)
    assert stats["expectancy"] > 0
    assert stats["profit_factor"] > 1
    assert stats["wins_erased_by_average_loss"] == pytest.approx(0.5)
    assert stats["cosmetic_win_rate"] is False


def test_expected_net_value_subtracts_costs():
    from aegis.intel.expected_value import expected_net_value

    ev = expected_net_value(
        p_win=0.60,
        expected_win=0.20,
        p_loss=0.40,
        expected_loss=0.10,
        expected_cost=0.02,
    )
    assert ev == pytest.approx(0.60 * 0.20 - 0.40 * 0.10 - 0.02)


def test_one_pip_vs_thirty_structural_payoff_fails():
    from aegis.intel.expected_value import payoff_metrics

    stats = payoff_metrics([0.01] * 95 + [-0.30] * 5)
    assert stats["wins_erased_by_average_loss"] == pytest.approx(30.0)
    assert stats["cosmetic_win_rate"] is True
    assert stats["expectancy"] < 0
