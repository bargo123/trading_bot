from __future__ import annotations

from pathlib import Path

from scripts.watcher_parquet import (
    append_study,
    flush_pending_to_parquet,
    load_study_from_parquet,
    load_study_from_pending,
    load_study_index,
)


def _study() -> dict:
    return {
        "record_type": "blocked_strategy_study",
        "study_id": "study-1",
        "blocked_event_id": "event-1",
        "timestamp": "2026-08-28T18:00:00Z",
        "candidate_state": {"symbol": "GBPUSD", "side": "BUY", "horizon_s": 15},
        "strategy_count": 2,
        "strategies": [
            {"record_id": "s-buy", "opinion": "BUY", "reason_codes": [1], "p_captured_win": 0.75},
            {"record_id": "s-sell", "opinion": "SELL", "reason_codes": [2], "p_captured_win": None},
        ],
    }


def test_parquet_batch_round_trip_preserves_all_strategy_rows(tmp_path: Path):
    report_dir = tmp_path / "watcher"
    report_dir.mkdir()

    append_study(report_dir, _study())
    batch = flush_pending_to_parquet(report_dir)

    assert batch is not None
    loaded = load_study_from_parquet(report_dir, "study-1")
    assert loaded is not None
    assert loaded["study_id"] == "study-1"
    assert {row["record_id"] for row in loaded["strategies"]} == {"s-buy", "s-sell"}
    assert loaded["strategies"][0]["reason_codes"] == [1]


def test_live_index_is_compact_and_has_strategy_counts(tmp_path: Path):
    report_dir = tmp_path / "watcher"
    report_dir.mkdir()

    append_study(report_dir, _study())
    rows = load_study_index(report_dir)

    assert len(rows) == 1
    assert rows[0]["strategy_count"] == 2
    assert rows[0]["opinion_counts"] == {"BUY": 1, "SELL": 1, "NO_TRADE": 0, "NOT_APPLICABLE": 0}
    assert "strategies" not in rows[0]
    assert isinstance(rows[0]["pending_offset"], int)
    loaded = load_study_from_pending(report_dir, "study-1", offset=rows[0]["pending_offset"])
    assert loaded is not None
    assert len(loaded["strategies"]) == 2
