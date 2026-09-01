from __future__ import annotations

from aegis.research.firehose_basket_replay import normalize_firehose_lifecycle_rows


def test_close_attempt_without_confirmed_close_is_not_replay_evidence():
    result = normalize_firehose_lifecycle_rows([
        {
            "event": "pm_exit",
            "ticket": "T1",
            "symbol": "EURUSD",
            "ok": True,
            "realized_pnl": 0.8,
        },
    ])

    assert result == {"status": "NO_EVIDENCE", "reason": "missing_confirmed_close"}


def test_confirmed_close_without_realized_cost_evidence_is_not_replay_evidence():
    result = normalize_firehose_lifecycle_rows([
        {
            "event": "firehose_open", "ticket": "T1", "basket_id": "B1",
            "trigger_id": "Q1", "clip_sequence": 1, "timestamp": "2026-08-24T10:00:00+00:00",
        },
        {
            "event": "firehose_exit_trace", "ticket": "T1", "basket_id": "B1",
            "trigger_id": "Q1", "clip_sequence": 1, "timestamp": "2026-08-24T10:00:01+00:00",
        },
        {
            "event": "firehose_close",
            "ticket": "T1",
            "basket_id": "B1", "trigger_id": "Q1", "clip_sequence": 1,
            "timestamp": "2026-08-24T10:00:02+00:00",
            "confirmed": True,
            "realized_net_usd": None,
            "cost_usd": None,
        },
    ])

    assert result == {"status": "NO_EVIDENCE", "reason": "missing_cost_evidence"}


def test_out_of_order_or_non_exact_lifecycle_is_not_replay_evidence():
    result = normalize_firehose_lifecycle_rows([
        {
            "event": "firehose_exit_trace", "ticket": "T1", "basket_id": "B1",
            "trigger_id": "Q1", "clip_sequence": 1,
            "timestamp": "2026-08-24T10:00:01+00:00",
        },
        {
            "event": "firehose_open", "ticket": "T1", "basket_id": "B1",
            "trigger_id": "Q1", "clip_sequence": 1,
            "timestamp": "2026-08-24T10:00:02+00:00",
        },
        {
            "event": "firehose_close", "ticket": "T1", "basket_id": "B1",
            "trigger_id": "Q1", "clip_sequence": 1,
            "timestamp": "2026-08-24T10:00:03+00:00", "confirmed": True,
            "realized_net_usd": 0.2, "cost_usd": 0.01,
        },
    ])

    assert result == {"status": "NO_EVIDENCE", "reason": "non_chronological_lifecycle"}


def test_complete_exact_lifecycle_normalizes_as_observed():
    result = normalize_firehose_lifecycle_rows([
        {
            "event": "firehose_open", "ticket": "T1", "basket_id": "B1",
            "trigger_id": "Q1", "clip_sequence": 1,
            "timestamp": "2026-08-24T10:00:00+00:00",
        },
        {
            "event": "firehose_exit_trace", "ticket": "T1", "basket_id": "B1",
            "trigger_id": "Q1", "clip_sequence": 1,
            "timestamp": "2026-08-24T10:00:01+00:00",
        },
        {
            "event": "firehose_close", "ticket": "T1", "basket_id": "B1",
            "trigger_id": "Q1", "clip_sequence": 1,
            "timestamp": "2026-08-24T10:00:02+00:00", "confirmed": True,
            "realized_net_usd": 0.2, "cost_usd": 0.01,
        },
    ])

    assert result["status"] == "OBSERVED"
    assert result["rows"][0]["ticket"] == "T1"


def test_naive_open_and_aware_close_are_not_replay_evidence():
    result = normalize_firehose_lifecycle_rows([
        {
            "event": "firehose_open", "ticket": "T1", "basket_id": "B1",
            "trigger_id": "Q1", "clip_sequence": 1,
            "timestamp": "2026-08-24T10:00:00",
        },
        {
            "event": "firehose_exit_trace", "ticket": "T1", "basket_id": "B1",
            "trigger_id": "Q1", "clip_sequence": 1,
            "timestamp": "2026-08-24T10:00:01",
        },
        {
            "event": "firehose_close", "ticket": "T1", "basket_id": "B1",
            "trigger_id": "Q1", "clip_sequence": 1,
            "timestamp": "2026-08-24T10:00:02+00:00", "confirmed": True,
            "realized_net_usd": 0.2, "cost_usd": 0.01,
        },
    ])

    assert result == {"status": "NO_EVIDENCE", "reason": "non_chronological_lifecycle"}


def test_aware_open_and_naive_close_are_not_replay_evidence():
    result = normalize_firehose_lifecycle_rows([
        {
            "event": "firehose_open", "ticket": "T1", "basket_id": "B1",
            "trigger_id": "Q1", "clip_sequence": 1,
            "timestamp": "2026-08-24T10:00:00+00:00",
        },
        {
            "event": "firehose_exit_trace", "ticket": "T1", "basket_id": "B1",
            "trigger_id": "Q1", "clip_sequence": 1,
            "timestamp": "2026-08-24T10:00:01+00:00",
        },
        {
            "event": "firehose_close", "ticket": "T1", "basket_id": "B1",
            "trigger_id": "Q1", "clip_sequence": 1,
            "timestamp": "2026-08-24T10:00:02", "confirmed": True,
            "realized_net_usd": 0.2, "cost_usd": 0.01,
        },
    ])

    assert result == {"status": "NO_EVIDENCE", "reason": "non_chronological_lifecycle"}


def test_mixed_awareness_trace_with_aware_endpoints_is_not_replay_evidence():
    result = normalize_firehose_lifecycle_rows([
        {
            "event": "firehose_open", "ticket": "T1", "basket_id": "B1",
            "trigger_id": "Q1", "clip_sequence": 1,
            "timestamp": "2026-08-24T10:00:00+00:00",
        },
        {
            "event": "firehose_exit_trace", "ticket": "T1", "basket_id": "B1",
            "trigger_id": "Q1", "clip_sequence": 1,
            "timestamp": "2026-08-24T10:00:01",
        },
        {
            "event": "firehose_close", "ticket": "T1", "basket_id": "B1",
            "trigger_id": "Q1", "clip_sequence": 1,
            "timestamp": "2026-08-24T10:00:02+00:00", "confirmed": True,
            "realized_net_usd": 0.2, "cost_usd": 0.01,
        },
    ])

    assert result == {"status": "NO_EVIDENCE", "reason": "non_chronological_lifecycle"}


def test_one_mixed_awareness_trace_among_multiple_traces_is_not_replay_evidence():
    result = normalize_firehose_lifecycle_rows([
        {
            "event": "firehose_open", "ticket": "T1", "basket_id": "B1",
            "trigger_id": "Q1", "clip_sequence": 1,
            "timestamp": "2026-08-24T10:00:00+00:00",
        },
        {
            "event": "firehose_exit_trace", "ticket": "T1", "basket_id": "B1",
            "trigger_id": "Q1", "clip_sequence": 1,
            "timestamp": "2026-08-24T10:00:01+00:00",
        },
        {
            "event": "firehose_exit_trace", "ticket": "T1", "basket_id": "B1",
            "trigger_id": "Q1", "clip_sequence": 1,
            "timestamp": "2026-08-24T10:00:01.500000",
        },
        {
            "event": "firehose_exit_trace", "ticket": "T1", "basket_id": "B1",
            "trigger_id": "Q1", "clip_sequence": 1,
            "timestamp": "2026-08-24T10:00:02+00:00",
        },
        {
            "event": "firehose_close", "ticket": "T1", "basket_id": "B1",
            "trigger_id": "Q1", "clip_sequence": 1,
            "timestamp": "2026-08-24T10:00:03+00:00", "confirmed": True,
            "realized_net_usd": 0.2, "cost_usd": 0.01,
        },
    ])

    assert result == {"status": "NO_EVIDENCE", "reason": "non_chronological_lifecycle"}


def test_complete_all_naive_lifecycle_normalizes_as_observed():
    result = normalize_firehose_lifecycle_rows([
        {
            "event": "firehose_open", "ticket": "T1", "basket_id": "B1",
            "trigger_id": "Q1", "clip_sequence": 1,
            "timestamp": "2026-08-24T10:00:00",
        },
        {
            "event": "firehose_exit_trace", "ticket": "T1", "basket_id": "B1",
            "trigger_id": "Q1", "clip_sequence": 1,
            "timestamp": "2026-08-24T10:00:01",
        },
        {
            "event": "firehose_close", "ticket": "T1", "basket_id": "B1",
            "trigger_id": "Q1", "clip_sequence": 1,
            "timestamp": "2026-08-24T10:00:02", "confirmed": True,
            "realized_net_usd": 0.2, "cost_usd": 0.01,
        },
    ])

    assert result["status"] == "OBSERVED"
    assert result["rows"][0]["ticket"] == "T1"


def test_mismatched_lifecycle_identity_is_not_replay_evidence():
    for field, value in (("basket_id", "B2"), ("trigger_id", "Q2"), ("clip_sequence", 2)):
        rows = [
            {
                "event": "firehose_open", "ticket": "T1", "basket_id": "B1",
                "trigger_id": "Q1", "clip_sequence": 1,
                "timestamp": "2026-08-24T10:00:00+00:00",
            },
            {
                "event": "firehose_exit_trace", "ticket": "T1", "basket_id": "B1",
                "trigger_id": "Q1", "clip_sequence": 1,
                "timestamp": "2026-08-24T10:00:01+00:00",
            },
            {
                "event": "firehose_close", "ticket": "T1", "basket_id": "B1",
                "trigger_id": "Q1", "clip_sequence": 1,
                "timestamp": "2026-08-24T10:00:02+00:00", "confirmed": True,
                "realized_net_usd": 0.2, "cost_usd": 0.01,
            },
        ]
        rows[1][field] = value

        assert normalize_firehose_lifecycle_rows(rows) == {
            "status": "NO_EVIDENCE", "reason": "missing_lifecycle_evidence",
        }


def test_python_equal_clip_impostors_are_not_replay_evidence():
    for event_index in (0, 1, 2):
        for impostor in (True, 1.0):
            rows = [
                {
                    "event": "firehose_open", "ticket": "T1", "basket_id": "B1",
                    "trigger_id": "Q1", "clip_sequence": 1,
                    "timestamp": "2026-08-24T10:00:00+00:00",
                },
                {
                    "event": "firehose_exit_trace", "ticket": "T1", "basket_id": "B1",
                    "trigger_id": "Q1", "clip_sequence": 1,
                    "timestamp": "2026-08-24T10:00:01+00:00",
                },
                {
                    "event": "firehose_close", "ticket": "T1", "basket_id": "B1",
                    "trigger_id": "Q1", "clip_sequence": 1,
                    "timestamp": "2026-08-24T10:00:02+00:00", "confirmed": True,
                    "realized_net_usd": 0.2, "cost_usd": 0.01,
                },
            ]
            rows[event_index]["clip_sequence"] = impostor

            assert normalize_firehose_lifecycle_rows(rows) == {
                "status": "NO_EVIDENCE", "reason": "missing_lifecycle_evidence",
            }


def test_duplicate_primary_events_are_not_replay_evidence():
    for source_index, duplicate in (
        (0, {"event": "firehose_open", "ticket": "T1", "basket_id": "B1", "trigger_id": "Q1", "clip_sequence": 1, "timestamp": "2026-08-24T10:00:00+00:00"}),
        (0, {"event": "firehose_open", "ticket": "T1", "basket_id": "B2", "trigger_id": "Q1", "clip_sequence": 1, "timestamp": "2026-08-24T10:00:00.500000+00:00"}),
        (2, {"event": "firehose_close", "ticket": "T1", "basket_id": "B1", "trigger_id": "Q1", "clip_sequence": 1, "timestamp": "2026-08-24T10:00:02+00:00", "confirmed": True, "realized_net_usd": 0.2, "cost_usd": 0.01}),
        (2, {"event": "firehose_close", "ticket": "T1", "basket_id": "B2", "trigger_id": "Q1", "clip_sequence": 1, "timestamp": "2026-08-24T10:00:03+00:00", "confirmed": True, "realized_net_usd": 0.2, "cost_usd": 0.01}),
    ):
        rows = [
            {
                "event": "firehose_open", "ticket": "T1", "basket_id": "B1",
                "trigger_id": "Q1", "clip_sequence": 1,
                "timestamp": "2026-08-24T10:00:00+00:00",
            },
            {
                "event": "firehose_exit_trace", "ticket": "T1", "basket_id": "B1",
                "trigger_id": "Q1", "clip_sequence": 1,
                "timestamp": "2026-08-24T10:00:01+00:00",
            },
            {
                "event": "firehose_close", "ticket": "T1", "basket_id": "B1",
                "trigger_id": "Q1", "clip_sequence": 1,
                "timestamp": "2026-08-24T10:00:02+00:00", "confirmed": True,
                "realized_net_usd": 0.2, "cost_usd": 0.01,
            },
        ]
        rows.insert(source_index + 1, duplicate)

        assert normalize_firehose_lifecycle_rows(rows) == {
            "status": "NO_EVIDENCE", "reason": "missing_lifecycle_evidence",
        }
