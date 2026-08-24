from __future__ import annotations

import ast
from pathlib import Path

from aegis.intel.firehose_turnover import (
    FirehoseReentryGuard,
    basket_lifecycle_trace,
    confirmed_close_cleanup,
)
from aegis.intel.ticket_metadata import TicketMetadataStore, create_ticket_metadata


ROOT = Path(__file__).resolve().parents[1]


def _basket_metadata(ticket: str = "T1"):
    return create_ticket_metadata(
        ticket=ticket,
        hypothesis_id="hyp-1",
        thesis_key="thesis-1",
        strategy_family="breakout",
        expected_mechanism="continuation",
        side="buy",
        entry_price=1.1,
        stop_loss=1.098,
        target_price=1.104,
        max_hold_s=300,
        regime="trend",
        session="london",
        symbol="EURUSD",
        basket_id="basket-1",
        trigger_id=f"trigger-{ticket}",
        clip_sequence=1,
        entry_geometry={"entry_price": 1.1, "stop_loss": 1.098},
        initial_risk=10.0,
        cost_evidence={"spread_usd": 0.2, "commission_usd": 0.1},
    )


def _close_observation():
    return {
        "mfe_usd": 4.0,
        "mae_usd": -0.5,
        "peak_net_profit_usd": 3.7,
        "realized_net_usd": 3.0,
        "capture_ratio": 0.75,
        "age_seconds": 20.0,
        "clips": 1,
        "decision_reasons": ["fast_take"],
        "ev": 0.25,
        "cost_usd": 0.3,
        "turnover": 1.0,
    }


def test_confirmed_basket_close_trace_preserves_exact_lifecycle_fields():
    expected_observation = _close_observation()
    expected_observation.update({
        "realized_net_usd": None,
        "capture_ratio": None,
        "cost_usd": None,
    })
    trace = basket_lifecycle_trace(
        _basket_metadata(),
        event="firehose_basket_close",
        timestamp="2026-08-24T10:00:20+00:00",
        confirmed=True,
        observation=_close_observation(),
        slot_released=True,
        basket_closed=True,
    )

    assert trace == {
        "event": "firehose_basket_close",
        "timestamp": "2026-08-24T10:00:20+00:00",
        "confirmed": True,
        "basket_id": "basket-1",
        "ticket_id": "T1",
        "hypothesis_id": "hyp-1",
        "family": "breakout",
        "symbol": "EURUSD",
        "side": "buy",
        "trigger_id": "trigger-T1",
        "clip_sequence": 1,
        "entry_geometry": {"entry_price": 1.1, "stop_loss": 1.098},
        "initial_risk_usd": 10.0,
        "cost_evidence": {"spread_usd": 0.2, "commission_usd": 0.1},
        **expected_observation,
        "regime": "trend",
        "session": "london",
        "slot_released": True,
        "basket_closed": True,
    }


def test_trace_skips_unconfirmed_or_legacy_ticket_without_basket_ownership():
    meta = _basket_metadata()

    assert basket_lifecycle_trace(
        meta,
        event="firehose_basket_close",
        timestamp="2026-08-24T10:00:20+00:00",
        confirmed=False,
        observation=_close_observation(),
    ) is None


def test_confirmed_basket_trace_retains_point_in_time_evidence_fields():
    trace = basket_lifecycle_trace(
        _basket_metadata(),
        event="firehose_exit_trace",
        timestamp="2026-08-24T10:00:10+00:00",
        confirmed=True,
        observation={
            "evidence_status": "OBSERVED",
            "liquidation_mark": 1.1002,
            "liquidation_mark_side": "BID",
            "return_5s": 0.0001,
            "return_15s": 0.0002,
            "return_30s": 0.0003,
            "remaining_ev": 0.04,
            "remaining_ev_status": "OBSERVED",
            "spread_usd": 0.01,
            "commission_usd": 0.02,
            "decision_reasons": ["missing_validated_policy_artifact"],
        },
    )

    assert trace["evidence_status"] == "OBSERVED"
    assert trace["liquidation_mark"] == 1.1002
    assert trace["liquidation_mark_side"] == "BID"
    assert trace["return_5s"] == 0.0001
    assert trace["remaining_ev_status"] == "OBSERVED"
    assert trace["commission_usd"] == 0.02
    legacy = create_ticket_metadata(
        ticket="legacy",
        hypothesis_id="hyp-legacy",
        thesis_key="thesis-legacy",
        strategy_family="breakout",
        expected_mechanism="continuation",
        side="buy",
        entry_price=1.1,
        stop_loss=1.098,
        target_price=1.104,
        max_hold_s=300,
        regime="trend",
        session="london",
        symbol="EURUSD",
    )
    assert basket_lifecycle_trace(
        legacy,
        event="firehose_basket_close",
        timestamp="2026-08-24T10:00:20+00:00",
        confirmed=True,
        observation=_close_observation(),
    ) is None


def test_restart_preserves_basket_ownership_for_confirmed_trace(tmp_path: Path):
    path = tmp_path / "ticket_metadata.json"
    TicketMetadataStore(path).add(_basket_metadata())
    restored = TicketMetadataStore(path).get("T1")

    trace = basket_lifecycle_trace(
        restored,
        event="firehose_basket_close",
        timestamp="2026-08-24T10:00:20+00:00",
        confirmed=True,
        observation=_close_observation(),
    )

    assert trace["basket_id"] == "basket-1"
    assert trace["trigger_id"] == "trigger-T1"


def test_confirmed_full_basket_close_releases_slot_after_last_owned_ticket(tmp_path: Path):
    store = TicketMetadataStore(tmp_path / "ticket_metadata.json")
    first = _basket_metadata("T1")
    second = _basket_metadata("T2")
    second.clip_sequence = 2
    store.add(first)
    store.add(second)
    guard = FirehoseReentryGuard()

    first_close = confirmed_close_cleanup(
        store, guard, "T1", quote_fingerprint="quote-1", closed_at=10.0,
    )
    final_close = confirmed_close_cleanup(
        store, guard, "T2", quote_fingerprint="quote-2", closed_at=20.0,
    )

    assert first_close.metadata_removed is True
    assert first_close.slot_released is False
    assert first_close.basket_closed is False
    assert final_close.slot_released is True
    assert final_close.basket_closed is True


def test_confirmed_close_rejects_stale_trigger_and_permits_fresh_trigger(tmp_path: Path):
    store = TicketMetadataStore(tmp_path / "ticket_metadata.json")
    store.add(_basket_metadata())
    guard = FirehoseReentryGuard()

    confirmed_close_cleanup(store, guard, "T1", quote_fingerprint="quote-a", closed_at=10.0)

    assert guard.allows("thesis-1", "quote-a", 11.0) == (False, "stale_reentry")
    assert guard.allows("thesis-1", "quote-b", 11.0) == (True, "fresh_quote")


def test_runner_has_no_research_factory_or_council_imports():
    tree = ast.parse((ROOT / "scripts" / "run_broker_paper.py").read_text(encoding="utf-8"))
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)

    assert not [name for name in imports if name.startswith(("aegis.research_factory", "ai_council"))]
