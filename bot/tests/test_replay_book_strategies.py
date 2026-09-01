from __future__ import annotations

import pytest

from scripts.replay_book_strategies import _split_ranges_for_rows, record_replay_experiment
from aegis.research.registry import ExperimentRegistry


def test_book_replay_registry_record_is_idempotent_and_hashed(tmp_path):
    strategy_path = tmp_path / "strategies.jsonl"
    input_path = tmp_path / "rows.jsonl"
    registry_path = tmp_path / "experiments.sqlite"
    strategy_path.write_text('{"strategy_id":"one"}\n', encoding="utf-8")
    input_path.write_text('{"symbol":"EURUSD"}\n', encoding="utf-8")
    report = {
        "rows_replayed": 1,
        "rows_with_net_outcome": 1,
        "book_record_count": 1,
        "testable_record_count": 1,
        "evaluator_group_count": 1,
    }

    first = record_replay_experiment(
        report, strategy_path, input_path, max_rows=1, registry_path=registry_path
    )
    second = record_replay_experiment(
        report, strategy_path, input_path, max_rows=1, registry_path=registry_path
    )

    assert first == second
    row = ExperimentRegistry(registry_path).get(first)
    assert row is not None
    assert row["status"] == "shadow"
    assert row["dataset_fingerprint"]


def test_split_ranges_are_chronological_and_cover_the_input(tmp_path):
    input_path = tmp_path / "rows.jsonl"
    input_path.write_text("".join('{"row":%d}\n' % i for i in range(10)), encoding="utf-8")

    ranges = _split_ranges_for_rows(
        input_path,
        ratios=(0.6, 0.2, 0.2),
        max_rows=None,
    )

    assert ranges == {"train": (0, 6), "validation": (6, 8), "sealed": (8, 10)}


def test_split_ranges_purge_forward_label_horizon(tmp_path):
    input_path = tmp_path / "rows.jsonl"
    rows = [
        {"time": f"2026-01-01T00:00:{index:02d}Z", "horizon_s": 2}
        for index in range(20)
    ]
    input_path.write_text(
        "".join(__import__("json").dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )

    ranges = _split_ranges_for_rows(
        input_path,
        ratios=(0.6, 0.2, 0.2),
        max_rows=None,
        purge_seconds=2,
    )

    assert ranges == {"train": (0, 12), "validation": (14, 16), "sealed": (18, 20)}


def test_split_ranges_default_purge_uses_max_row_horizon(tmp_path):
    input_path = tmp_path / "rows.jsonl"
    rows = [
        {"time": f"2026-01-01T00:00:{index:02d}Z", "horizon_s": 2}
        for index in range(20)
    ]
    input_path.write_text(
        "".join(__import__("json").dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )

    ranges = _split_ranges_for_rows(
        input_path,
        ratios=(0.6, 0.2, 0.2),
        max_rows=None,
    )

    assert ranges["validation"][0] == 14
    assert ranges["sealed"][0] == 18


def test_split_ranges_require_three_positive_rows_and_ratios(tmp_path):
    input_path = tmp_path / "rows.jsonl"
    input_path.write_text('{"row":1}\n{"row":2}\n', encoding="utf-8")

    with pytest.raises(ValueError, match="at least three rows"):
        _split_ranges_for_rows(input_path, ratios=(0.6, 0.2, 0.2), max_rows=None)
    with pytest.raises(ValueError, match="three positive"):
        _split_ranges_for_rows(tmp_path / "missing.jsonl", ratios=(0.0, 0.2, 0.8), max_rows=None)
