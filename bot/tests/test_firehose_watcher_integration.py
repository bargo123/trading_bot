from __future__ import annotations

import json

import pandas as pd

from aegis.research.watcher_algorithms import ALGORITHM_MODULES
from aegis.intel.watcher_advisory import (
    book_feature_snapshot,
    book_signal_rows,
    watcher_advisory_for_firehose,
)


def _quote_history():
    rows = []
    for index in range(121):
        timestamp = float(index * 5)
        mid = 1.1000 + index * 0.00001
        rows.append({
            "time": timestamp,
            "bid": mid - 0.00002,
            "ask": mid + 0.00002,
            "mid": mid,
            "tick_volume": 10.0,
        })
    rows.append({"time": 9999.0, "bid": 9.0, "ask": 9.1, "mid": 9.05})
    return rows


def test_firehose_advisory_evaluates_all_watcher_algorithms_causally():
    result = watcher_advisory_for_firehose(
        symbol="EURUSD",
        side="buy",
        mechanism="micro_momentum",
        horizon_s=5,
        runtime_state={
            "symbol": "EURUSD",
            "regime": {"label": "trend"},
            "session": "london",
        },
        row={
            "symbol": "EURUSD",
            "time": 600.0,
            "bid": 1.10118,
            "ask": 1.10122,
            "mid": 1.10120,
        },
        symbol_history=_quote_history(),
    )

    assert result["status"] == "AVAILABLE"
    assert result["algorithm_count"] == len(ALGORITHM_MODULES)
    assert result["evaluated_count"] == len(ALGORITHM_MODULES)
    assert result["execution_authority"] is False
    assert result["research_only"] is True
    assert result["no_lookahead"] is True
    assert result["quote_history_future_excluded"] is True
    assert result["symbol"] == "EURUSD"
    assert result["side"] == "BUY"
    assert result["horizon_s"] == 5
    assert result["book_features"]["book_available"] == 1.0
    assert result["book_rank_score"] == result["book_features"]["book_rank_score"]


def test_firehose_advisory_failure_is_fail_closed_and_non_authoritative(monkeypatch):
    import aegis.intel.watcher_advisory as advisory

    def fail(*args, **kwargs):
        raise RuntimeError("feature failure")

    monkeypatch.setattr(advisory, "enrich_watcher_state", fail)

    result = watcher_advisory_for_firehose(
        symbol="EURUSD",
        side="sell",
        mechanism="range_rejection",
        horizon_s=10,
        runtime_state={"symbol": "EURUSD"},
        row={"time": 100.0, "bid": 1.1, "ask": 1.1002},
    )

    assert result["status"] == "UNAVAILABLE"
    assert result["consensus"] == "UNRESOLVED"
    assert result["execution_authority"] is False
    assert result["research_only"] is True
    assert result["order_intent"] is False
    assert "RuntimeError" in result["reason"]


def test_firehose_advisory_rejects_a_watcher_contract_violation(monkeypatch):
    import aegis.intel.watcher_advisory as advisory

    perspectives = [
        {
            "algorithm_id": name,
            "view": "WAIT",
            "applicability": "NOT_APPLICABLE",
            "reasons": [],
            "source_books": [],
            "execution_authority": False,
            "research_only": True,
            "uses_future_data": False,
        }
        for name in ALGORITHM_MODULES
    ]
    perspectives[0]["execution_authority"] = True
    monkeypatch.setattr(
        advisory,
        "analyze_book_perspectives",
        lambda state: {
            "perspectives": perspectives,
            "applicable_count": 0,
            "no_lookahead": True,
        },
    )

    result = watcher_advisory_for_firehose(
        symbol="EURUSD",
        side="buy",
        mechanism="breakout",
        horizon_s=5,
        runtime_state={"symbol": "EURUSD"},
        row={"time": 100.0, "bid": 1.1, "ask": 1.1002},
    )

    assert result["status"] == "UNAVAILABLE"
    assert result["order_intent"] is False
    assert result["execution_authority"] is False
    assert result["reason"] == "watcher_algorithm_contract_violation"


def test_brain_journals_watcher_advisory_without_granting_order_authority(
    tmp_path, monkeypatch
):
    import aegis.intel.firehose_brain as firehose_brain

    index = tmp_path / "analogue_index.json"
    index.write_text(
        json.dumps({"schema": "analogue_index.v1", "records": []}),
        encoding="utf-8",
    )
    advisory = {
        "status": "AVAILABLE",
        "consensus": "BUY",
        "algorithm_count": len(ALGORITHM_MODULES),
        "execution_authority": False,
        "research_only": True,
        "order_intent": False,
    }
    monkeypatch.setattr(
        firehose_brain,
        "watcher_advisory_for_firehose",
        lambda **kwargs: advisory,
    )

    frame = pd.DataFrame(
        {
            "time": pd.date_range("2026-01-01", periods=5, freq="min", tz="UTC"),
            "open": [1.1] * 5,
            "high": [1.101] * 5,
            "low": [1.099] * 5,
            "close": [1.100 + index * 0.0001 for index in range(5)],
            "volume": [100.0] * 5,
        }
    )
    decision = firehose_brain.IntelligentFirehoseBrain(
        {
            "analogue_index_path": str(index),
            "intelligent_exploration_enabled": False,
            "watcher_runtime_enabled": True,
        }
    ).evaluate(
        symbol="EURUSD",
        row=frame.iloc[-1],
        completed_m1=frame,
        positions=[],
        equity=100.0,
        pip=0.0001,
        core_side="buy",
        actual_bid=1.1003,
        actual_ask=1.1005,
        entry_price=1.1005,
    )

    assert decision.journal["watcher_advisory"] == advisory
    assert decision.journal["watcher_advisory"]["execution_authority"] is False
    assert decision.action == "skip"


def test_brain_watcher_helper_preserves_final_candidate_identity(monkeypatch):
    import aegis.intel.firehose_brain as firehose_brain

    calls = []

    def fake_advisory(**kwargs):
        calls.append(kwargs)
        return {
            "status": "AVAILABLE",
            "symbol": str(kwargs["symbol"]).upper(),
            "side": str(kwargs["side"]).upper(),
            "mechanism": kwargs["mechanism"],
            "horizon_s": kwargs["horizon_s"],
            "execution_authority": False,
            "research_only": True,
            "order_intent": False,
        }

    monkeypatch.setattr(
        firehose_brain, "watcher_advisory_for_firehose", fake_advisory
    )
    brain = firehose_brain.IntelligentFirehoseBrain(
        {"watcher_runtime_enabled": True}
    )

    result = brain._watcher_advisory(
        symbol="GBPUSD",
        side="sell",
        mechanism="range_rejection",
        horizon_s=3,
        runtime_state={"symbol": "GBPUSD"},
        row={"time": 100.0, "bid": 1.2, "ask": 1.2002},
        actual_bid=1.2,
        actual_ask=1.2002,
        now_ts=100.0,
    )

    assert result["symbol"] == "GBPUSD"
    assert result["side"] == "SELL"
    assert result["mechanism"] == "range_rejection"
    assert result["horizon_s"] == 3
    assert calls[0]["side"] == "sell"
    assert calls[0]["mechanism"] == "range_rejection"
    assert calls[0]["horizon_s"] == 3


def test_brain_watcher_helper_rejects_authority_claims(monkeypatch):
    import aegis.intel.firehose_brain as firehose_brain

    monkeypatch.setattr(
        firehose_brain,
        "watcher_advisory_for_firehose",
        lambda **kwargs: {
            "status": "AVAILABLE",
            "execution_authority": True,
            "research_only": False,
            "order_intent": True,
        },
    )
    brain = firehose_brain.IntelligentFirehoseBrain(
        {"watcher_runtime_enabled": True}
    )

    result = brain._watcher_advisory(
        symbol="EURUSD",
        side="buy",
        mechanism="breakout",
        horizon_s=5,
        runtime_state={},
        row={"time": 100.0, "bid": 1.1, "ask": 1.1002},
    )

    assert result["status"] == "UNAVAILABLE"
    assert result["reason"] == "watcher_advisory_contract_violation"
    assert result["execution_authority"] is False
    assert result["order_intent"] is False


def test_book_signal_rows_preserve_each_applicable_algorithm_without_authority():
    advisory = {
        "status": "AVAILABLE",
        "symbol": "EURUSD",
        "side": "BUY",
        "mechanism": "donch55",
        "horizon_s": 5,
        "execution_authority": False,
        "research_only": True,
        "no_lookahead": True,
        "perspectives": [
            {
                "algorithm_id": "trend_continuation",
                "view": "BUY",
                "applicability": "APPLICABLE",
                "reasons": ["trend aligned"],
                "source_books": ["Systematic Trading"],
                "execution_authority": False,
                "research_only": True,
                "uses_future_data": False,
            },
            {
                "algorithm_id": "range_edge_fade",
                "view": "SELL",
                "applicability": "APPLICABLE",
                "reasons": ["range edge"],
                "source_books": ["Technical Analysis"],
                "execution_authority": False,
                "research_only": True,
                "uses_future_data": False,
            },
            {
                "algorithm_id": "time_stop",
                "view": "WAIT",
                "applicability": "NOT_APPLICABLE",
                "reasons": [],
                "source_books": [],
                "execution_authority": False,
                "research_only": True,
                "uses_future_data": False,
            },
        ],
    }

    rows = book_signal_rows(
        advisory,
        symbol="EURUSD",
        side="buy",
        mechanism="donch55",
        horizon_s=5,
    )

    assert [row["algorithm_id"] for row in rows] == [
        "trend_continuation",
        "range_edge_fade",
    ]
    assert rows[0]["signal_side"] == "BUY"
    assert rows[1]["signal_side"] == "SELL"
    assert all(row["execution_authority"] is False for row in rows)
    assert all(row["research_only"] is True for row in rows)
    assert all(row["uses_future_data"] is False for row in rows)
    assert all(row["symbol"] == "EURUSD" for row in rows)
    assert all(row["horizon_s"] == 5 for row in rows)


def test_book_signal_rows_fail_closed_for_unavailable_or_contract_violation():
    assert book_signal_rows(
        {"status": "UNAVAILABLE", "execution_authority": False},
        symbol="EURUSD",
        side="buy",
        mechanism="breakout",
        horizon_s=3,
    ) == []


def test_book_signal_rows_accepts_compact_directional_signals_from_runtime_advisory():
    rows = book_signal_rows(
        {
            "status": "AVAILABLE",
            "symbol": "EURUSD",
            "side": "SELL",
            "mechanism": "bb_mr",
            "horizon_s": 10,
            "execution_authority": False,
            "research_only": True,
            "no_lookahead": True,
            "directional_signals": [
                {
                    "algorithm_id": "range_edge_fade",
                    "view": "SELL",
                    "applicability": "APPLICABLE",
                    "reasons": ["range edge"],
                    "source_books": ["Technical Analysis"],
                    "execution_authority": False,
                    "research_only": True,
                    "uses_future_data": False,
                },
            ],
        },
        symbol="EURUSD",
        side="sell",
        mechanism="bb_mr",
        horizon_s=10,
    )

    assert len(rows) == 1
    assert rows[0]["algorithm_id"] == "range_edge_fade"
    assert rows[0]["alignment"] == "SUPPORTS"
    assert book_signal_rows(
        {
            "status": "AVAILABLE",
            "execution_authority": True,
            "research_only": False,
            "no_lookahead": True,
            "perspectives": [],
        },
        symbol="EURUSD",
        side="buy",
        mechanism="breakout",
        horizon_s=3,
    ) == []


def test_book_feature_snapshot_shrinks_sparse_directional_support():
    features = book_feature_snapshot(
        {
            "status": "AVAILABLE",
            "algorithm_count": len(ALGORITHM_MODULES),
            "evaluated_count": len(ALGORITHM_MODULES),
            "applicable_count": 10,
            "supporting_count": 8,
            "opposing_count": 2,
            "missing_data_algorithm_count": len(ALGORITHM_MODULES) - 10,
            "execution_authority": False,
            "research_only": True,
            "no_lookahead": True,
            "order_intent": False,
        },
        candidate_side="BUY",
    )

    assert features["book_available"] == 1.0
    assert features["book_support_ratio"] == 0.8
    assert features["book_directional_ratio"] == 10 / len(ALGORITHM_MODULES)
    assert 0.5 < features["book_rank_score"] < features["book_support_ratio"]
    assert features["book_registry_complete"] == 1.0

    sell_features = book_feature_snapshot(
        {
            "status": "AVAILABLE",
            "side": "SELL",
            "algorithm_count": len(ALGORITHM_MODULES),
            "evaluated_count": len(ALGORITHM_MODULES),
            "applicable_count": 10,
            "supporting_count": 8,
            "opposing_count": 2,
            "missing_data_algorithm_count": len(ALGORITHM_MODULES) - 10,
            "execution_authority": False,
            "research_only": True,
            "no_lookahead": True,
            "order_intent": False,
        },
        candidate_side="SELL",
    )
    assert sell_features["book_support_ratio"] == 0.8


def test_book_feature_snapshot_is_neutral_for_unsafe_or_unavailable_advisory():
    features = book_feature_snapshot(
        {
            "status": "UNAVAILABLE",
            "execution_authority": False,
            "research_only": True,
            "no_lookahead": False,
        },
        candidate_side="SELL",
    )

    assert features["book_available"] == 0.0
    assert features["book_support_ratio"] == 0.5
    assert features["book_rank_score"] == 0.5
    assert features["book_algorithm_count"] == 0.0
