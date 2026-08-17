"""Governed promotion: research gates + bootstrap tail + search-count correction."""
from __future__ import annotations

from typing import Any, Sequence

from aegis.research.gates import GateReject, evaluate_promotion
from aegis.research.stress import bootstrap_expectancy, family_wise_ok, tail_stress
from aegis.intel.expected_value import MAX_WINS_ERASED_BY_AVERAGE_LOSS, payoff_metrics

MIN_OBSERVED_LOSSES = 5


def require_positive_holdout(oos: dict[str, Any]) -> None:
    e = oos.get("expectancy")
    if e is None:
        e = oos.get("expectancy_r")
    n = int(oos.get("n_trades") or oos.get("total_trades") or 0)
    pf = oos.get("profit_factor")
    evaluate_promotion(
        {
            "expectancy": float(e or 0.0),
            "profit_factor": pf if pf is not None else 0.0,
            "n_trades": n,
            "net_pnl": float(oos.get("net_pnl") or 0.0),
            "win_rate": float(oos.get("win_rate") or 0.0),
        },
        champion=None,
    )


def governed_accept(
    metrics: dict[str, Any],
    champion: dict[str, Any] | None,
    *,
    pnls: Sequence[float],
    n_searches: int,
    worst_case_loss: float | None = None,
    sl_pips: float | None = None,
    tp_pips: float | None = None,
) -> None:
    evaluate_promotion(metrics, champion)
    if sl_pips is not None and tp_pips is not None:
        tp = float(tp_pips)
        if tp <= 0:
            raise GateReject("tp_pips must be positive to judge structural payoff")
        structural = float(sl_pips) / tp
        if structural >= MAX_WINS_ERASED_BY_AVERAGE_LOSS:
            raise GateReject(
                f"structural payoff wins_erased={structural:.1f} from SL/TP "
                f"{float(sl_pips):.1f}/{tp:.1f}"
            )
    tail = tail_stress(pnls, worst_case_loss=worst_case_loss)
    if tail["n_losses"] < MIN_OBSERVED_LOSSES:
        raise GateReject(
            f"only {int(tail['n_losses'])} observed loss(es); need at least "
            f"{MIN_OBSERVED_LOSSES} before a win rate can be trusted"
        )
    payoff = payoff_metrics(pnls)
    if payoff.get("cosmetic_win_rate"):
        raise GateReject(
            "destructive payoff asymmetry: "
            f"wins_erased_by_average_loss={payoff.get('wins_erased_by_average_loss')}"
        )
    if tail["expectancy_after_one_more_loss"] <= 0:
        raise GateReject(
            "expectancy does not survive one more worst-case loss "
            f"({tail['expectancy_after_one_more_loss']:.6f})"
        )
    boot = bootstrap_expectancy(pnls)
    if boot["n"] < 20:
        raise GateReject("bootstrap needs at least 20 trades")
    if boot["p05"] <= 0:
        raise GateReject("bootstrap 5th-percentile expectancy is not > 0")
    p_raw = 1.0 - float(boot["frac_positive"])
    if not family_wise_ok(p_raw, n_searches=n_searches):
        raise GateReject(
            f"search-count correction failed (p_raw={p_raw:.4f}, n_searches={n_searches})"
        )
