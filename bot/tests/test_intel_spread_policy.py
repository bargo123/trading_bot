"""Evidence-based spread limits for Intelligent Firehose lanes."""
from __future__ import annotations

from aegis.intel.spread_policy import measured_spread_limit_pips


PROFILE = {
    "symbols": {
        "GBPUSD": {
            "pip_size": 0.0001,
            "sessions": {
                "asia": {
                    "evidence_sufficient": True,
                    "observations": 1040,
                    "spread_p75": 1.1,
                    "spread_p90": 1.1,
                    "slippage_pips": 0.1,
                    "commission_pips": 0.0,
                }
            },
        }
    }
}


def test_measured_normal_symbol_session_spread_can_pass() -> None:
    limit = measured_spread_limit_pips(PROFILE, symbol="GBPUSD", session="asia")

    assert limit is not None
    assert limit.max_spread_pips == 1.1
    assert limit.allows(1.1)


def test_measured_abnormal_symbol_session_spread_is_rejected() -> None:
    limit = measured_spread_limit_pips(PROFILE, symbol="GBPUSD", session="asia")

    assert limit is not None
    assert not limit.allows(1.2)


def test_missing_or_insufficient_measurement_cannot_relax_spread_gate() -> None:
    assert measured_spread_limit_pips(PROFILE, symbol="GBPUSD", session="london") is None
