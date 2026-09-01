from __future__ import annotations

import pytest

from aegis.research.book_strategy_replay import replay_book_records
from aegis.research.watcher_book_perspectives import evaluate_book_algorithm, strategy_implementation_status


def _row(*, side: str, net: float, structure: str = "m1_range_or_pullback") -> dict:
    return {
        "time": "2026-08-25T14:23:36.000Z",
        "symbol": "EURUSD",
        "side": side,
        "session": "new_york",
        "structure": structure,
        "horizon_s": 3,
        "entry_price": 1.1,
        "entry_spread": 0.5,
        "quote_age_s": 0.2,
        "return_1s": 0.0001 if side == "BUY" else -0.0001,
        "captured_exit_net_pnl": net,
    }


def test_replay_evaluates_each_testable_book_record_without_leaking_outcomes():
    records = [
        {
            "strategy_id": "exact-buy",
            "status": "CODED_EXACT",
            "source_title": "Example Exact",
            "side_rule": "BUY",
            "strategy_family": "breakout",
            "algorithm": {
                "family": "breakout",
                "compiled_entry_predicates": {"structure_eq": "m1_range_or_pullback"},
            },
        },
        {
            "strategy_id": "family-scalp",
            "status": "FAMILY_PROXY",
            "source_title": "Example Family",
            "strategy_family": "scalping",
            "algorithm": {"family": "scalping"},
        },
        {
            "strategy_id": "incomplete",
            "status": "COMPILE_ERROR",
            "source_title": "Incomplete Source",
            "strategy_family": "breakout",
            "algorithm": {"family": "breakout"},
        },
        {
            "strategy_id": "context-only",
            "status": "UNTESTABLE_SOURCE",
            "source_title": "Context Source",
            "strategy_family": "breakout",
            "algorithm": {"family": "breakout"},
        },
    ]

    report = replay_book_records(records, [
        _row(side="BUY", net=0.25),
        _row(side="SELL", net=-0.1, structure="range"),
    ])

    assert report["schema"] == "book_strategy_historical_replay.v1"
    assert report["rows_replayed"] == 2
    assert report["rows_with_net_outcome"] == 2
    assert report["book_record_count"] == 4
    assert report["testable_record_count"] == 4
    assert report["no_lookahead"] is True
    assert report["execution_authority"] is False

    exact = report["strategies"]["exact-buy"]
    assert exact["implementation_status"] == "WATCHER_EXACT_RULE"
    assert exact["signal_samples"] == 1
    assert exact["wins"] == 1
    assert exact["net_pnl"] == 0.25

    family = report["strategies"]["family-scalp"]
    assert family["implementation_status"] == "WATCHER_FAMILY_PERSPECTIVE"
    assert family["signal_samples"] == 2
    assert family["wins"] == 1
    assert family["losses"] == 1

    incomplete = report["strategies"]["incomplete"]
    assert incomplete["implementation_status"] == "WATCHER_FAMILY_PERSPECTIVE"
    assert incomplete["evaluated"] == 2
    assert incomplete["signal_samples"] == 0

    context = report["strategies"]["context-only"]
    assert context["implementation_status"] == "WATCHER_FAMILY_CONTEXT"
    assert context["evaluated"] == 2
    assert context["signal_samples"] == 0


def test_replay_rejects_invalid_rows_and_marks_missing_outcomes():
    record = {
        "strategy_id": "family-scalp",
        "status": "FAMILY_PROXY",
        "strategy_family": "scalping",
        "algorithm": {"family": "scalping"},
    }
    report = replay_book_records(
        [record],
        [None, {"symbol": "EURUSD", "side": "BUY", "horizon_s": 3}],
    )

    assert report["rows_replayed"] == 1
    assert report["rows_without_net_outcome"] == 1
    assert report["strategies"]["family-scalp"]["signal_samples"] == 0


def test_book_evaluation_preserves_original_source_for_family_and_specification_records():
    family = evaluate_book_algorithm(
        {
            "status": "FAMILY_PROXY",
            "source_title": "Family Source",
            "strategy_family": "scalping",
            "algorithm": {"family": "scalping"},
        },
        _row(side="BUY", net=0.0),
    )
    specification = evaluate_book_algorithm(
        {
            "status": "UNTESTABLE_SOURCE",
            "source_title": "Opaque Source",
            "algorithm": {},
        },
        _row(side="BUY", net=0.0),
    )

    assert family["source_books"][0] == "Family Source"
    assert specification["source_books"] == ["Opaque Source"]


def test_empty_exact_predicate_map_is_not_promoted_to_an_exact_rule():
    assert strategy_implementation_status(
        {
            "status": "CODED_EXACT",
            "source_title": "Empty Exact",
            "strategy_family": "breakout",
            "algorithm": {"family": "breakout", "compiled_entry_predicates": {}},
        }
    ) == "SPECIFICATION_ONLY"


def test_replay_exposes_deduplicated_evaluator_groups():
    records = [
        {
            "strategy_id": "exact-1",
            "status": "CODED_EXACT",
            "source_title": "Book A",
            "side_rule": "BUY",
            "strategy_family": "breakout",
            "algorithm": {
                "family": "breakout",
                "compiled_entry_predicates": {"structure_eq": "breakout"},
            },
        },
        {
            "strategy_id": "exact-duplicate",
            "status": "CODED_EXACT",
            "side_rule": "BUY",
            "strategy_family": "breakout",
            "algorithm": {
                "family": "breakout",
                "compiled_entry_predicates": {"structure_eq": "breakout"},
            },
        },
        {
            "strategy_id": "family-1",
            "status": "FAMILY_PROXY",
            "strategy_family": "scalping",
            "algorithm": {"family": "scalping"},
        },
    ]

    report = replay_book_records(records, [_row(side="BUY", net=0.1, structure="breakout")])

    groups = report["evaluator_groups"]
    assert report["evaluator_group_count"] == 2
    assert len(groups) == 2
    exact_group = next(group for group in groups if group["representative_record_id"] == "exact-1")
    assert exact_group["record_ids"] == ["exact-1", "exact-duplicate"]
    assert exact_group["duplicate_count"] == 2
    assert exact_group["source_title"] == "Book A"


def test_replay_evaluates_one_time_per_deduplicated_group(monkeypatch):
    calls = 0
    updates = 0

    def fake_evaluate(record, state, **kwargs):
        nonlocal calls
        calls += 1
        return {
            "implementation_status": "WATCHER_FAMILY_PERSPECTIVE",
            "status": "MATCH",
            "view": "BUY",
            "applicability": "APPLICABLE",
            "reasons": [],
        }

    monkeypatch.setattr(
        "aegis.research.book_strategy_replay.evaluate_book_algorithm",
        fake_evaluate,
    )
    import aegis.research.book_strategy_replay as replay_module

    original_update = replay_module._update

    def counting_update(*args, **kwargs):
        nonlocal updates
        updates += 1
        return original_update(*args, **kwargs)

    monkeypatch.setattr(replay_module, "_update", counting_update)
    records = [
        {
            "strategy_id": "family-1",
            "status": "FAMILY_PROXY",
            "strategy_family": "scalping",
            "algorithm": {"family": "scalping"},
        },
        {
            "strategy_id": "family-duplicate",
            "status": "FAMILY_PROXY",
            "strategy_family": "scalping",
            "algorithm": {"family": "scalping"},
        },
    ]

    report = replay_book_records(
        records,
        [_row(side="BUY", net=0.1) for _ in range(3)],
    )

    assert calls == 3
    assert updates == 3
    first = report["strategies"]["family-1"]
    duplicate = report["strategies"]["family-duplicate"]
    assert first["signal_samples"] == duplicate["signal_samples"] == 3
    assert first["net_pnl"] == duplicate["net_pnl"] == 0.3


def test_pre_enriched_replay_uses_a_sanitized_row_snapshot(monkeypatch):
    seen_state = {}

    def fake_evaluate(record, state, **kwargs):
        seen_state.update(state)
        return {
            "implementation_status": "WATCHER_FAMILY_PERSPECTIVE",
            "status": "MATCH",
            "view": "BUY",
            "applicability": "APPLICABLE",
            "reasons": [],
        }

    monkeypatch.setattr(
        "aegis.research.book_strategy_replay.evaluate_book_algorithm",
        fake_evaluate,
    )
    record = {
        "strategy_id": "family-scalp",
        "status": "FAMILY_PROXY",
        "strategy_family": "scalping",
        "algorithm": {"family": "scalping"},
    }
    row = _row(side="BUY", net=0.1)
    row.update({"target": 1, "future_quotes": [{"mid": 99.0}]})

    report = replay_book_records(
        [record],
        [row],
        pre_enriched_rows=True,
    )

    assert report["feature_adapter"] == "watcher_feature_engine.row_snapshot.v1"
    assert "captured_exit_net_pnl" not in seen_state
    assert "target" not in seen_state
    assert "future_quotes" not in seen_state
    assert seen_state["structure"] == "m1_range_or_pullback"


def test_replay_emits_disjoint_chronological_split_group_stats():
    records = [
        {
            "strategy_id": "exact-1",
            "status": "CODED_EXACT",
            "side_rule": "BUY",
            "strategy_family": "breakout",
            "algorithm": {
                "family": "breakout",
                "compiled_entry_predicates": {"structure_eq": "breakout"},
            },
        },
        {
            "strategy_id": "exact-duplicate",
            "status": "CODED_EXACT",
            "side_rule": "BUY",
            "strategy_family": "breakout",
            "algorithm": {
                "family": "breakout",
                "compiled_entry_predicates": {"structure_eq": "breakout"},
            },
        },
    ]
    rows = [
        _row(side="BUY", net=0.1, structure="breakout"),
        _row(side="BUY", net=-0.1, structure="range"),
        _row(side="BUY", net=-0.1, structure="range"),
        _row(side="BUY", net=0.2, structure="breakout"),
    ]

    report = replay_book_records(
        records,
        rows,
        split_ranges={
            "train": (0, 2),
            "validation": (2, 3),
            "sealed": (3, 4),
        },
    )

    assert report["split_replay_ranges"] == {
        "train": {"start": 0, "end": 2},
        "validation": {"start": 2, "end": 3},
        "sealed": {"start": 3, "end": 4},
    }
    assert [report["split_replay"][name]["rows_replayed"] for name in (
        "train", "validation", "sealed"
    )] == [2, 1, 1]
    exact_group_id = report["evaluator_groups"][0]["group_id"]
    for name in ("train", "validation", "sealed"):
        groups = report["split_replay"][name]["groups"]
        assert len(groups) == 1
        assert groups[0]["group_id"] == exact_group_id
        assert groups[0]["duplicate_count"] == 2
    assert report["split_replay"]["train"]["groups"][0]["signal_samples"] == 1
    assert report["split_replay"]["validation"]["groups"][0]["signal_samples"] == 0
    assert report["split_replay"]["sealed"]["groups"][0]["signal_samples"] == 1


def test_replay_rejects_overlapping_or_invalid_split_ranges():
    with pytest.raises(ValueError, match="split ranges must be disjoint"):
        replay_book_records(
            [],
            [],
            split_ranges={"train": (0, 2), "validation": (1, 3)},
        )
    with pytest.raises(ValueError, match="split range is invalid"):
        replay_book_records([], [], split_ranges={"train": (2, 1)})


def test_replay_report_uses_filename_book_label_for_registry_records():
    report = replay_book_records(
        [{
            "strategy_id": "exact-1",
            "status": "CODED_EXACT",
            "source_title": "P1: printer header 178 TRADING STRATEGIES",
            "source_path": r"C:\Users\Zaid barghouthi\Downloads\[Wiley finance series] Adam Grimes - The art and science of technical analysis (2012, Wiley) - libgen.li.pdf",
            "side_rule": "BUY",
            "strategy_family": "breakout",
            "algorithm": {"compiled_entry_predicates": {"structure_eq": "breakout"}},
        }],
        [_row(side="BUY", net=0.1, structure="breakout")],
    )

    assert report["strategies"]["exact-1"]["source_title"] == "Adam Grimes — The art and science of technical analysis"
