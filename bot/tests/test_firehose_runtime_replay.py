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
