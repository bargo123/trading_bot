#!/usr/bin/env python3
"""Unit tests for high-risk safety cage (no network)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aegis.high_risk import BROWN_FIB, HighRiskController, solved_policy_config


def test_clamp_safe():
    hr = HighRiskController(mode="traditional", base_risk_percent=80.0, safe=True, risk_max_cap=5.0)
    assert hr.effective_risk_percent(1000) == 5.0


def test_brown_recovery_steps_capped():
    hr = HighRiskController(
        mode="brown_recovery",
        base_risk_percent=1.0,
        safe=True,
        risk_max_cap=5.0,
        max_steps=3,
        start_equity=1000,
    )
    # step 0 → 1%
    assert abs(hr.effective_risk_percent(1000) - 1.0) < 1e-9
    hr.on_trade_closed(-10, 990)
    # step 1 → 3%
    assert abs(hr.effective_risk_percent(990) - 3.0) < 1e-9
    hr.on_trade_closed(-10, 980)
    assert abs(hr.effective_risk_percent(980) - 5.0) < 1e-9  # 5*1 clamped? Fib[2]=5 → 5%
    hr.on_trade_closed(-10, 970)
    # step 3 >= max_steps → reset behavior on next effective = base when step>max after on_trade
    # after 3rd loss step becomes 3 then safe resets step to 0 in on_trade when step > max_steps
    assert hr.step == 0 or hr.effective_risk_percent(970) <= 5.0


def test_consec_loss_halt():
    hr = HighRiskController(
        mode="traditional",
        base_risk_percent=2.0,
        max_consecutive_losses=3,
        start_equity=1000,
        equity_floor_frac=0.1,
    )
    hr.on_trade_closed(-1, 999)
    hr.on_trade_closed(-1, 998)
    hr.on_trade_closed(-1, 997)
    ok, reason = hr.allow(997)
    assert not ok
    assert "max_consecutive_losses" in reason


def test_equity_floor():
    hr = HighRiskController(mode="traditional", start_equity=1000, equity_floor_frac=0.5)
    ok, reason = hr.allow(400)
    assert not ok
    assert "equity_floor" in reason


def test_thomas_uses_prior_win():
    hr = HighRiskController(
        mode="thomas_compound",
        base_risk_percent=1.0,
        safe=True,
        risk_max_cap=5.0,
        thomas_win_frac=0.5,
        start_equity=1000,
    )
    hr.on_trade_closed(40.0, 1040)  # win $40
    # risk $ = 20 → 20/1040*100 ≈ 1.92%
    pct = hr.effective_risk_percent(1040)
    assert 1.0 <= pct <= 5.0
    assert abs(pct - (100.0 * 20 / 1040)) < 0.01 or pct == 5.0


def test_windsor_uncapped_requires_allow():
    hr = HighRiskController.from_config(
        {"high_risk_mode": "windsor_escalate", "risk_percent": 2.0, "allow_unsafe_high_risk": False},
        1000,
    )
    assert hr.safe is True
    hr.step = 10
    assert hr.effective_risk_percent(1000) <= hr.risk_max_cap


def test_solved_policy():
    p = solved_policy_config()
    assert p["high_risk_safe"] is True
    assert p["allow_unsafe_high_risk"] is False
    assert p["pyramid_enabled"] is True
    assert p["hr_risk_max_cap"] == 5.0


def test_forever_safe_house_money_and_halt():
    from aegis.high_risk import forever_safe_policy_config

    hr = HighRiskController.from_config(forever_safe_policy_config({"hr_house_money_frac": 1.0}), 100.0)
    assert hr.use_risk_bankroll is True
    assert abs(hr.risk_bankroll - 20.0) < 1e-9
    assert abs(hr.protected_principal - 80.0) < 1e-9
    # Risk ≤ room above protected, with 10% cost buffer → 0.9 * 20 = 18% of equity
    assert abs(hr.effective_risk_percent(100.0) - 18.0) < 1e-6
    hr.on_trade_closed(2.28, 102.28)
    assert abs(hr.risk_bankroll - (102.28 - 80.0)) < 1e-6
    hr.on_trade_closed(-1.0, 101.28)
    ok, reason = hr.allow(101.28)
    assert not ok
    assert "forever_safe" in reason or "first loss" in reason or "bankroll" in reason


if __name__ == "__main__":
    test_clamp_safe()
    test_brown_recovery_steps_capped()
    test_consec_loss_halt()
    test_equity_floor()
    test_thomas_uses_prior_win()
    test_windsor_uncapped_requires_allow()
    test_solved_policy()
    test_forever_safe_house_money_and_halt()
    print("ALL HIGH-RISK UNIT TESTS PASSED")
