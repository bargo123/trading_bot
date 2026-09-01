from __future__ import annotations

import gzip
import json
import time
from pathlib import Path

from scripts.watcher_knowledge_engine import (
    ADDITIONAL_KB_FILES,
    STRUCTURED_KB_FILES,
    WatcherKnowledgeEngine,
    evaluate_applicability,
    evaluate_strategy,
    load_knowledge_library,
)
from aegis.research.watcher_algorithms import ALGORITHM_MODULES


def _write_library_fixture(root: Path) -> Path:
    knowledge = root / "knowledge"
    knowledge.mkdir()
    row = {
        "book": "book-a",
        "file_hash": "book-hash-a",
        "passage_hash": "passage-hash-a",
        "location": {"file": "books/book-a.md", "start_line": 7},
        "concept_type": "STRATEGY_HYPOTHESIS",
        "strategy_family": "micro_continuation",
        "side_rule": "buy",
        "required_data": "m1+m15_structure+spread",
        "required_regime": "trend",
        "required_timeframe": "M1",
        "entry_hypothesis": "enter on confirmed continuation",
        "falsification_condition": "negative chronological OOS",
    }
    for name in STRUCTURED_KB_FILES:
        payload = dict(row)
        if name != "strategy_hypotheses.jsonl":
            payload["concept_type"] = {
                "concepts.jsonl": "DESCRIPTIVE",
                "entry_patterns.jsonl": "ENTRY_PRINCIPLE",
                "exit_patterns.jsonl": "EXIT_PRINCIPLE",
                "execution_rules.jsonl": "EXECUTION_RULE",
                "validation_rules.jsonl": "VALIDATION_RULE",
                "risk_rules.jsonl": "RISK_RULE",
                "firehose_hypotheses.jsonl": "FIREHOSE_HYPOTHESIS",
            }[name]
        (knowledge / name).write_text(json.dumps(payload) + "\n", encoding="utf-8")
    extra = root / "research" / "book_memory"
    extra.mkdir(parents=True)
    (extra / "knowledge_records.jsonl").write_text(
        json.dumps({"knowledge_id": "memory-1", "source_title": "book-a", "source_hash": "book-hash-a", "concept": "memory_concept"}) + "\n",
        encoding="utf-8",
    )
    (knowledge / "corpus_manifest.json").write_text(
        json.dumps({"schema": "corpus_manifest.v2", "corpus_version": "fixture-v1"}),
        encoding="utf-8",
    )
    (knowledge / "source_index.json").write_text(
        json.dumps({"schema": "book_source_index.v1", "counts_by_status": {"INDEXED": 1}}),
        encoding="utf-8",
    )
    return knowledge


def _candidate(**overrides):
    event = {
        "event": "candidate_blocked",
        "timestamp": 100.0,
        "candidate_id": "cand-1",
        "symbol": "EURUSD",
        "side": "buy",
        "mechanism": "micro_continuation",
        "horizon_s": 3,
        "entry": 1.1000,
        "stop": 1.0990,
        "target": 1.1010,
        "spread_pips": 1.0,
        "expected_net_ev": 0.04,
        "regime": "trend",
        "timeframe": "M1",
        "m1_context": {"return_1": 0.0001},
        "m15_context": {"trend": "up"},
        "structure": "breakout",
    }
    event.update(overrides)
    return event


def test_library_loads_every_structured_file_and_preserves_provenance(tmp_path):
    knowledge = _write_library_fixture(tmp_path)

    library = load_knowledge_library(knowledge)

    assert library["processed_all_structured_kb"] is True
    assert set(library["counts_by_file"]) == set(STRUCTURED_KB_FILES) | set(ADDITIONAL_KB_FILES)
    assert library["counts"]["records"] == len(STRUCTURED_KB_FILES) + len(ADDITIONAL_KB_FILES)
    assert library["counts"]["book_memory_records"] == 1
    assert library["counts"]["strategy_records"] == 2
    strategy = next(row for row in library["records"] if row["category"] == "strategy")
    assert strategy["raw_record"]["passage_hash"] == "passage-hash-a"
    assert strategy["provenance"]["book_hash"] == "book-hash-a"
    assert strategy["provenance"]["location"]["start_line"] == 7


def test_registry_provenance_uses_book_filename_when_source_title_is_a_page_header(tmp_path):
    knowledge = _write_library_fixture(tmp_path)
    registry = tmp_path / "book_strategy_registry.jsonl"
    registry.write_text(
        json.dumps({
            "strategy_id": "exact-1",
            "status": "CODED_EXACT",
            "source_title": "P1: printer header 178 TRADING STRATEGIES",
            "source_path": r"C:\Users\Zaid barghouthi\Downloads\[Wiley finance series] Adam Grimes - The art and science of technical analysis (2012, Wiley) - libgen.li.pdf",
            "source_sha256": "book-hash-a",
            "passage_hash": "passage-hash-a",
            "algorithm": {"compiled_entry_predicates": {"structure_eq": "breakout"}},
        }) + "\n",
        encoding="utf-8",
    )

    library = load_knowledge_library(knowledge, registry_path=registry)
    strategy = next(row for row in library["records"] if row["category"] == "strategy")

    assert strategy["provenance"]["book"] == "Adam Grimes — The art and science of technical analysis"


def test_canonical_registry_keeps_only_fully_implemented_watcher_rules(tmp_path):
    knowledge = _write_library_fixture(tmp_path)
    registry = tmp_path / "book_strategy_registry.jsonl"
    rows = [
        {
            "strategy_id": "exact-1",
            "status": "CODED_EXACT",
            "source_title": "book-a",
            "algorithm": {"compiled_entry_predicates": {"structure_eq": "breakout"}},
        },
        {
            "strategy_id": "family-1",
            "status": "FAMILY_PROXY",
            "source_title": "book-a",
            "strategy_family": "momentum",
        },
        {
            "strategy_id": "context-1",
            "status": "UNTESTABLE_SOURCE",
            "source_title": "book-a",
            "strategy_family": "volatility",
        },
        {
            "strategy_id": "spec-1",
            "status": "UNTESTABLE_SOURCE",
            "source_title": "book-a",
        },
    ]
    registry.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

    library = load_knowledge_library(knowledge, registry_path=registry)

    assert [row["record_id"] for row in library["strategy_records"]] == ["exact-1"]
    assert library["counts"]["strategy_records"] == 1
    assert library["counts"]["filtered_strategy_records"] == 3


def test_applicability_requires_present_state_and_never_invents_features():
    record = {
        "required_data": "m1+m15_structure+spread",
        "required_regime": "trend",
        "required_timeframe": "M1",
    }

    missing = evaluate_applicability(record, {"regime": "trend"})
    wrong_regime = evaluate_applicability(
        record,
        {"regime": "range", "timeframe": "M1", "m1_context": {}, "m15_context": {}, "structure": "x", "spread": 1.0},
    )
    matching = evaluate_applicability(
        record,
        {"regime": "trend", "timeframe": "M1", "m1_context": {"return_1": 0.0001}, "m15_context": {"trend": "up"}, "structure": "x", "spread": 1.0},
    )

    assert missing["status"] == "INSUFFICIENT_DATA"
    assert "m1" in missing["missing"]
    assert wrong_regime["status"] == "NOT_APPLICABLE"
    assert matching["status"] == "APPLICABLE"


def test_applicability_does_not_treat_empty_context_containers_as_evidence():
    record = {
        "required_data": "m1+m15_structure+spread",
        "required_regime": "trend",
        "required_timeframe": "M1",
    }

    result = evaluate_applicability(
        record,
        {
            "regime": "trend",
            "timeframe": "M1",
            "m1_context": {},
            "m15_context": {},
            "structure": "x",
            "spread": 1.0,
        },
    )

    assert result["status"] == "INSUFFICIENT_DATA"
    assert set(result["missing"]) >= {"m1", "m15"}


def test_strategy_evaluation_is_research_only_and_produces_independent_opinions(tmp_path):
    knowledge = _write_library_fixture(tmp_path)
    library = load_knowledge_library(knowledge)
    state = _candidate()

    opinions = [evaluate_strategy(row, state) for row in library["strategy_records"]]

    assert any(item["opinion"] == "BUY" for item in opinions)
    assert all(item["execution_authority"] is False for item in opinions)
    assert all(item["uses_future_data"] is False for item in opinions)
    assert all("probability" not in item for item in opinions)


def test_blocked_candidate_creates_exact_shadow_and_future_quote_closes_it(tmp_path):
    knowledge = _write_library_fixture(tmp_path)
    engine = WatcherKnowledgeEngine(knowledge_dir=knowledge, report_dir=tmp_path / "watcher")

    outputs = engine.process_event(_candidate())
    analysis = next(item for item in outputs if item.get("record_type") == "watcher_decision_analysis")
    assert analysis["strategy_opinions"] == []
    assert analysis["evaluated_strategy_count"] == 2
    assert len(analysis["book_perspectives"]) == len(ALGORITHM_MODULES)
    assert analysis["research_only"] is True
    assert engine.stats["per_strategy"]
    shadow = next(item for item in outputs if item.get("record_type") == "shadow_trade")
    assert shadow["shadow_status"] == "OPEN"
    assert shadow["no_lookahead"] is True
    assert shadow["entry"] == 1.1000
    assert shadow["stop"] == 1.0990
    assert shadow["target"] == 1.1010
    assert shadow["book_perspectives"]
    assert shadow["no_lookahead"] is True

    closed = engine.process_event({
        "event": "quote",
        "timestamp": 101.0,
        "symbol": "EURUSD",
        "bid": 1.1010,
        "ask": 1.1011,
    })

    outcome = next(item for item in closed if item.get("record_type") == "shadow_outcome")
    assert outcome["shadow_status"] == "CLOSED"
    assert outcome["exit_reason"] == "TARGET"
    assert outcome["outcome_time"] == 101.0
    assert engine.stats["shadow"]["closed"] == 1


def test_book_algorithm_shadow_outcomes_are_separate_from_broker_capture_probability(tmp_path):
    knowledge = _write_library_fixture(tmp_path)
    report_dir = tmp_path / "watcher"
    engine = WatcherKnowledgeEngine(knowledge_dir=knowledge, report_dir=report_dir)

    outputs = engine.process_event(_candidate(event_id="algorithm-shadow-entry"))
    study = next(item for item in outputs if item.get("record_type") == "blocked_strategy_study")
    trend = next(item for item in study["book_perspectives"] if item["perspective_id"] == "trend_structure")
    assert trend["shadow_sample_size"] == 0
    assert trend["shadow_win_rate"] is None

    closed = engine.process_event({
        "event": "quote",
        "event_id": "algorithm-shadow-target",
        "timestamp": 101.0,
        "symbol": "EURUSD",
        "bid": 1.1010,
        "ask": 1.1011,
    })
    outcome = next(item for item in closed if item.get("record_type") == "shadow_outcome")

    assert outcome["algorithm_shadow_outcomes"]["trend_structure"]["outcome"] == "WIN"
    row = engine.stats["algorithm_perspectives"]["trend_structure"]
    assert row["shadow_sample_size"] == 1
    assert row["shadow_wins"] == 1
    assert row["shadow_losses"] == 0
    assert row["shadow_win_rate"] == 1.0
    assert "p_captured_win" not in row

    persisted = json.loads((report_dir / "strategy_stats.json").read_text(encoding="utf-8"))
    assert persisted["algorithm_perspectives"]["trend_structure"]["shadow_win_rate"] == 1.0

    reloaded = WatcherKnowledgeEngine(knowledge_dir=knowledge, report_dir=report_dir)
    assert reloaded.stats["algorithm_perspectives"]["trend_structure"]["shadow_sample_size"] == 1


def test_book_algorithm_shadow_losses_are_counted_without_net_probability_claim(tmp_path):
    knowledge = _write_library_fixture(tmp_path)
    engine = WatcherKnowledgeEngine(knowledge_dir=knowledge, report_dir=tmp_path / "watcher")

    engine.process_event(_candidate(event_id="algorithm-shadow-loss-entry"))
    closed = engine.process_event({
        "event": "quote",
        "event_id": "algorithm-shadow-loss-stop",
        "timestamp": 101.0,
        "symbol": "EURUSD",
        "bid": 1.0990,
        "ask": 1.0991,
    })

    outcome = next(item for item in closed if item.get("record_type") == "shadow_outcome")
    assert outcome["algorithm_shadow_outcomes"]["trend_structure"]["outcome"] == "LOSS"
    row = engine.stats["algorithm_perspectives"]["trend_structure"]
    assert row["shadow_sample_size"] == 1
    assert row["shadow_wins"] == 0
    assert row["shadow_losses"] == 1
    assert row["shadow_win_rate"] == 0.0
    assert row["shadow_evidence_source"] == "shadow_replay_price_only"
    assert "p_captured_win" not in row


def test_blocked_study_links_raw_event_without_repeating_large_candidate_context(tmp_path):
    knowledge = _write_library_fixture(tmp_path)
    engine = WatcherKnowledgeEngine(knowledge_dir=knowledge, report_dir=tmp_path / "watcher")
    event = _candidate(event_id="compact-study", candidate_details={"large_context": "x" * 100_000})

    outputs = engine.process_event(event)
    study = next(item for item in outputs if item.get("record_type") == "blocked_strategy_study")

    assert study["raw_observation_event_id"] == "compact-study"
    assert study["candidate_state"]["candidate_id"] == "cand-1"
    assert "large_context" not in study["candidate_state"]


def test_every_blocked_candidate_persists_all_strategy_studies(tmp_path):
    knowledge = _write_library_fixture(tmp_path)
    report_dir = tmp_path / "watcher"
    engine = WatcherKnowledgeEngine(knowledge_dir=knowledge, report_dir=report_dir)

    outputs = engine.process_event(_candidate())

    study = next(item for item in outputs if item.get("record_type") == "blocked_strategy_study")
    expected_ids = {row["record_id"] for row in engine.library["strategy_records"]}
    actual_ids = {row["record_id"] for row in study["strategies"]}
    assert study["blocked_event_id"] == engine._event_id(_candidate())
    assert actual_ids == expected_ids
    assert study["strategy_count"] == len(expected_ids)
    assert study["algorithm_count"] == len(study["book_perspectives"]) == len(ALGORITHM_MODULES)
    assert study["strategy_metadata_source"] == "knowledge_library.json"
    assert study["reason_dictionary"]
    assert all("applicability" in row for row in study["strategies"])
    assert all("opinion" in row for row in study["strategies"])
    assert all("algorithm_status" in row for row in study["strategies"])
    assert all("book_algorithm_analysis" in row for row in study["strategies"])
    assert all("reason_codes" in row and "reasons" not in row for row in study["strategies"])
    assert all("source_file" not in row and "book" not in row for row in study["strategies"])
    assert study["research_only"] is True

    persisted = [
        json.loads(line)
        for line in (report_dir / "blocked_strategy_studies_pending.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert persisted == [study]


def test_blocked_study_reports_exact_measured_strategy_win_percentage(tmp_path):
    knowledge = _write_library_fixture(tmp_path)
    engine = WatcherKnowledgeEngine(knowledge_dir=knowledge, report_dir=tmp_path / "watcher")
    strategy_id = engine.library["strategy_records"][0]["record_id"]

    for index, net in enumerate((0.10, -0.05), start=1):
        engine.process_event({
            "event": "firehose_open",
            "event_id": f"open-{index}",
            "timestamp": 200.0 + index,
            "ticket": f"T{index}",
            "symbol": "EURUSD",
            "side": "buy",
            "mechanism": "micro_continuation",
            "horizon_s": 3,
            "strategy_ids": [strategy_id],
        })
        engine.process_event({
            "event": "confirmed_close_finalization",
            "event_id": f"close-{index}",
            "timestamp": 210.0 + index,
            "ticket": f"T{index}",
            "status": "BROKER_CONFIRMED",
            "broker_facts": {"realized_net_usd": net},
        })

    outputs = engine.process_event(_candidate(event_id="blocked-with-history", strategy_ids=[strategy_id]))
    study = next(item for item in outputs if item.get("record_type") == "blocked_strategy_study")
    row = next(item for item in study["strategies"] if item["record_id"] == strategy_id)

    assert row["p_captured_win"] == 0.5
    assert row["p_captured_win_percent"] == 50.0
    assert row["p_captured_win_sample_size"] == 2
    assert row["p_captured_win_source"] == "broker_confirmed_net_pnl"


def test_blocked_study_persists_real_candidate_prediction_evidence(tmp_path):
    knowledge = _write_library_fixture(tmp_path)
    engine = WatcherKnowledgeEngine(knowledge_dir=knowledge, report_dir=tmp_path / "watcher")

    outputs = engine.process_event(_candidate(
        short_horizon_prediction={
            "probability": 0.61,
            "decision": False,
            "abstain": True,
            "abstain_reason": "uncalibrated_model",
            "artifact_status": "candidate",
            "calibration_status": "uncalibrated",
            "side_comparison": {"buy": 0.61, "sell": 0.39},
        },
    ))
    study = next(item for item in outputs if item.get("record_type") == "blocked_strategy_study")

    evidence = study["prediction_evidence"]
    assert evidence["source"] == "short_horizon_prediction"
    assert evidence["probability"] == 0.61
    assert evidence["abstain"] is True
    assert evidence["abstain_reason"] == "uncalibrated_model"
    assert evidence["raw"]["side_comparison"] == {"buy": 0.61, "sell": 0.39}


def test_blocked_study_marks_prediction_unavailable_without_fabricating_one(tmp_path):
    knowledge = _write_library_fixture(tmp_path)
    engine = WatcherKnowledgeEngine(knowledge_dir=knowledge, report_dir=tmp_path / "watcher")

    outputs = engine.process_event(_candidate())
    study = next(item for item in outputs if item.get("record_type") == "blocked_strategy_study")

    evidence = study["prediction_evidence"]
    assert evidence["source"] == "UNAVAILABLE"
    assert evidence["probability"] is None
    assert evidence["reason"] == "prediction_not_recorded_in_source_event"


def test_confirmed_production_outcome_is_truth_and_counterfactuals_are_after_close(tmp_path):
    knowledge = _write_library_fixture(tmp_path)
    engine = WatcherKnowledgeEngine(knowledge_dir=knowledge, report_dir=tmp_path / "watcher")
    engine.process_event({
        "event": "firehose_open",
        "timestamp": 200.0,
        "ticket": "T1",
        "symbol": "EURUSD",
        "side": "buy",
        "mechanism": "micro_continuation",
        "horizon_s": 3,
        "session": "london",
        "regime": "trend",
        "entry": 1.1000,
        "spread_pips": 1.0,
        "entry_ev": 0.05,
        "entry_state": {"m1_return": 0.0001},
    })

    pending = engine.process_event({
        "event": "pm_exit",
        "timestamp": 201.0,
        "ticket": "T1",
        "realized_pnl": -0.20,
    })
    assert not any(item.get("record_type") == "production_outcome" for item in pending)

    confirmed = engine.process_event({
        "event": "confirmed_close_finalization",
        "timestamp": 202.0,
        "ticket": "T1",
        "status": "BROKER_CONFIRMED",
        "broker_facts": {"realized_net_usd": -0.20, "commission_usd": 0.01},
        "lifecycle": {"entry_quality": "bad", "speed_label": "FAST_LOSER"},
        "counterfactual_quotes": [
            {"timestamp": 200.0, "bid": 1.1000, "ask": 1.1002},
            {"timestamp": 201.0, "bid": 1.0990, "ask": 1.0992},
        ],
    })

    outcome = next(item for item in confirmed if item.get("record_type") == "production_outcome")
    assert outcome["broker_confirmed"] is True
    assert outcome["realized_net_usd"] == -0.20
    assert outcome["classification"] == "BAD_ENTRY"
    assert "FAST_LOSER" in outcome["lifecycle_labels"]
    assert outcome["counterfactuals"]["after_the_fact"] is True
    assert {item["side"] for item in outcome["counterfactuals"]["what_if"]} == {"BUY", "SELL"}
    assert engine.stats["production"]["losses"] == 1


def test_persistence_and_deduplication_are_watcher_local(tmp_path):
    knowledge = _write_library_fixture(tmp_path)
    report_dir = tmp_path / "watcher"
    engine = WatcherKnowledgeEngine(knowledge_dir=knowledge, report_dir=report_dir)
    event = _candidate()

    first = engine.process_event(event)
    second = engine.process_event(event)

    assert first
    assert second == []
    assert (report_dir / "knowledge_library.json").is_file()
    assert (report_dir / "decision_analysis.jsonl").is_file()
    assert (report_dir / "shadow_trades.jsonl").is_file()
    assert (report_dir / "strategy_stats.json").is_file()
    assert (report_dir / "state.json").is_file()


def test_watcher_engine_has_no_broker_execution_surface():
    source = Path(__file__).parents[1] / "scripts" / "watcher_knowledge_engine.py"
    text = source.read_text(encoding="utf-8")
    for forbidden in ("mt5.order_send", "place_order", "close_ticket", "aegis.engines", "run_broker_paper"):
        assert forbidden not in text


def test_retention_archives_oldest_thirty_percent_and_keeps_recent_studies(tmp_path):
    knowledge = _write_library_fixture(tmp_path)
    report_dir = tmp_path / "watcher"
    engine = WatcherKnowledgeEngine(knowledge_dir=knowledge, report_dir=report_dir)
    studies_path = report_dir / "blocked_strategy_studies.jsonl"
    with studies_path.open("w", encoding="utf-8") as handle:
        for index in range(600):
            handle.write(json.dumps({
                "record_type": "blocked_strategy_study",
                "study_id": f"study-{index}",
                "strategies": [],
                "strategy_count": 0,
            }) + "\n")

    engine._run_retention(now=time.time())

    active = [json.loads(line) for line in studies_path.read_text(encoding="utf-8").splitlines() if line]
    archive_paths = sorted((report_dir / "archives").glob("*.jsonl.gz"))
    with gzip.open(archive_paths[0], "rt", encoding="utf-8") as handle:
        archived = [json.loads(line) for line in handle if line.strip()]
    assert len(archived) == 180
    assert len(active) == 420
    assert archived[0]["study_id"] == "study-0"
    assert active[0]["study_id"] == "study-180"
    assert active[-1]["study_id"] == "study-599"


def test_retention_ignores_legacy_full_study_log_after_parquet_index_exists(tmp_path):
    knowledge = _write_library_fixture(tmp_path)
    report_dir = tmp_path / "watcher"
    engine = WatcherKnowledgeEngine(knowledge_dir=knowledge, report_dir=report_dir)
    legacy_path = report_dir / "blocked_strategy_studies.jsonl"
    with legacy_path.open("w", encoding="utf-8") as handle:
        for index in range(600):
            handle.write(json.dumps({"record_type": "blocked_strategy_study", "study_id": f"legacy-{index}"}) + "\n")
    (report_dir / "blocked_strategy_studies_index.jsonl").write_text(
        json.dumps({"record_type": "blocked_strategy_study", "study_id": "new-1"}) + "\n",
        encoding="utf-8",
    )

    engine._run_retention(now=time.time())

    assert len(legacy_path.read_text(encoding="utf-8").splitlines()) == 600
