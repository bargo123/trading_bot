"""Classify strategy controls before they are treated as intelligence.

The ledger is research documentation only.  It does not change the frozen CORE
configuration or any broker-facing code.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


SAFETY_INVARIANT = "safety_invariant"
BROKER_CONSTRAINT = "broker_market_constraint"
EMPIRICALLY_VALIDATED = "empirically_validated_decision"
RESEARCH_ASSUMPTION = "temporary_research_assumption"
ARBITRARY_LEGACY = "arbitrary_legacy_rule"


@dataclass(frozen=True)
class StrategyAssumption:
    key: str
    value: Any
    classification: str
    reason: str
    replacement: str
    evidence: str = ""


def current_strategy_audit() -> list[StrategyAssumption]:
    """Known live/research controls that require classification and provenance."""
    return [
        StrategyAssumption(
            "allow_live",
            False,
            SAFETY_INVARIANT,
            "Prevents silent real-money activation.",
            "retain deterministic gate",
            "engine paper-mutation guard",
        ),
        StrategyAssumption(
            "completed_bar_only",
            True,
            SAFETY_INVARIANT,
            "Future bars invalidate research and execution evidence.",
            "retain deterministic gate",
            "dataset/assert_no_lookahead and structure tests",
        ),
        StrategyAssumption(
            "broker_volume_min_step",
            "symbol-specific",
            BROKER_CONSTRAINT,
            "Orders outside broker contract limits are invalid.",
            "read contract snapshot per symbol",
            "MT5 symbol capability",
        ),
        StrategyAssumption(
            "firehose_tp_sl_pips",
            "1/30",
            RESEARCH_ASSUMPTION,
            "Frozen CORE benchmark; not a validated challenger payoff.",
            "thesis invalidation and costed candidate payoff",
            "current_best: no champion",
        ),
        StrategyAssumption(
            "firehose_max_per_symbol",
            3,
            ARBITRARY_LEGACY,
            "Order count is not independent evidence or aggregate risk.",
            "target_thesis_exposure with correlated-risk budget",
        ),
        StrategyAssumption(
            "max_positions",
            40,
            RESEARCH_ASSUMPTION,
            "Demo capacity cap; does not express thesis or correlation exposure.",
            "gross-risk safety cap plus thesis exposure policy",
        ),
        StrategyAssumption(
            "intel_mega_min_votes",
            3,
            ARBITRARY_LEGACY,
            "Raw proxy count is not a calibrated probability.",
            "source-independent calibrated evidence",
        ),
        StrategyAssumption(
            "intel_min_er",
            0.15,
            RESEARCH_ASSUMPTION,
            "Threshold has no attached calibration record.",
            "regime-conditional holdout calibration",
        ),
        StrategyAssumption(
            "htf_ema_on_m1",
            "slow EMA proxy",
            ARBITRARY_LEGACY,
            "A slow M1 indicator is not a completed H4/D1 bar.",
            "MarketState genuine M1→D1 resampling",
        ),
        StrategyAssumption(
            "max_spread_pips",
            0.3,
            RESEARCH_ASSUMPTION,
            "Cost protection is needed, but fixed value needs symbol/regime evidence.",
            "cost relative to predicted payoff and observed execution distribution",
        ),
        StrategyAssumption(
            "risk_halt_on_invalid_broker_state",
            True,
            SAFETY_INVARIANT,
            "Invalid/stale execution state must not be traded through.",
            "retain deterministic gate",
            "OMS/execution circuit",
        ),
    ]


def audit_markdown() -> str:
    rows = current_strategy_audit()
    lines = [
        "# Strategy assumption audit",
        "",
        "This classifies controls; it does not alter the frozen CORE runner or YAML.",
        "",
        "| control | value | class | why | replacement / retention | evidence |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        payload = asdict(row)
        lines.append(
            f"| {payload['key']} | {payload['value']} | {payload['classification']} | "
            f"{payload['reason']} | {payload['replacement']} | {payload['evidence']} |"
        )
    return "\n".join(lines) + "\n"
