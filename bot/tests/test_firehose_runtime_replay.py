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
        {"event": "firehose_open", "ticket": "T1", "timestamp": "2026-08-24T10:00:00+00:00"},
        {"event": "firehose_exit_trace", "ticket": "T1", "timestamp": "2026-08-24T10:00:01+00:00"},
        {
            "event": "firehose_close",
            "ticket": "T1",
            "timestamp": "2026-08-24T10:00:02+00:00",
            "confirmed": True,
            "realized_net_usd": None,
            "cost_usd": None,
        },
    ])

    assert result == {"status": "NO_EVIDENCE", "reason": "missing_cost_evidence"}
