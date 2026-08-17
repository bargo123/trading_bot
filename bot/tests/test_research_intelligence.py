from __future__ import annotations

import pandas as pd
import pytest

from aegis.research.books_index import BookIndex
from aegis.research.intelligence import form_research_thesis
from aegis.research.intelligence_cycle import intelligence_cycle_markdown, run_intelligence_cycle
from aegis.research.knowledge import (
    SourceKnowledge,
    compile_knowledge_table,
    hypotheses_for_market,
    search_full_book_knowledge,
)
from aegis.research.learning import attribute_outcomes, slice_outcomes
from aegis.research.market_state import MarketStateCache, build_market_state
from aegis.research.market_state_history import (
    match_historical_states,
    trade_state_records,
    validate_state_matched_challengers,
)
from aegis.research.portfolio import portfolio_state
from aegis.research.registry import ExperimentRegistry
from aegis.research.strategy_audit import ARBITRARY_LEGACY, audit_markdown, current_strategy_audit
from aegis.research.thesis import (
    EvidenceItem,
    Thesis,
    calibrate_outcomes,
    explain_thesis,
    target_thesis_exposure,
    thesis_experiment_row,
    thesis_information_id,
)


def _m1(n: int = 1_600) -> pd.DataFrame:
    time = pd.date_range("2026-01-01", periods=n, freq="min", tz="UTC")
    close = pd.Series([1.10 + index * 0.00001 for index in range(n)])
    return pd.DataFrame(
        {
            "time": time,
            "open": close.shift(1).fillna(close.iloc[0]),
            "high": close + 0.00005,
            "low": close - 0.00005,
            "close": close,
            "volume": 100.0,
        }
    )


def test_market_state_uses_completed_resamples_not_m1_htf_alias():
    state = build_market_state(symbol="EURUSD", m1=_m1())
    assert state.lookahead is False
    assert state.provenance["data_source"] == "completed_ohlcv"
    assert state.multi_timeframe["M5"]["complete"] is True
    assert state.multi_timeframe["H1"]["complete"] is True
    assert state.multi_timeframe["H4"]["complete"] is True
    assert state.multi_timeframe["D1"]["complete"] is True
    assert state.regime["source"] == "resampled_completed_bars"
    assert state.htf_ready is True
    assert state.session in {"asia", "london", "newyork"}
    assert state.provenance.get("mtf_schema") == "mtf.v1"


def _thesis(evidence):
    return Thesis(
        thesis_id="EURUSD_LONG_RETEST_20260101_001",
        symbol="EURUSD",
        side="buy",
        setup="breakout retest",
        market_state={"regime": "trend"},
        supporting_evidence=(EvidenceItem("book:test", "retest", True, "completed-bar structure"),),
        contradicting_evidence=(),
        invalidation="completed-bar close below support",
        expected_duration="M15 to H1",
        calibrated_evidence=evidence,
    )


def test_exposure_requires_calibrated_positive_lower_bound_and_validated_policy():
    insufficient = calibrate_outcomes([0.1] * 5)
    decision = target_thesis_exposure(
        thesis=_thesis(insufficient),
        current_risk_usd=1.0,
        correlated_risk_usd=0.0,
        total_risk_budget_usd=10.0,
        validated_risk_fraction=0.2,
    )
    assert decision.action == "reduce_or_wait"
    assert decision.target_risk_usd == 0.0

    calibrated = calibrate_outcomes([0.1] * 30)
    decision = target_thesis_exposure(
        thesis=_thesis(calibrated),
        current_risk_usd=0.0,
        correlated_risk_usd=2.0,
        total_risk_budget_usd=10.0,
        validated_risk_fraction=0.25,
    )
    assert decision.action == "increase"
    assert decision.target_risk_usd == 2.0
    assert "no order placed" in explain_thesis(_thesis(calibrated), decision)


def test_learning_clusters_outcomes_without_claiming_a_winner():
    clusters = attribute_outcomes(
        [
            {"thesis_id": "t1", "pnl": -0.2, "symbol": "EURUSD", "regime": "range"},
            {"thesis_id": "t1", "pnl": 0.1, "symbol": "EURUSD", "regime": "range"},
        ]
    )
    assert clusters["t1"]["losses"] == 1
    assert clusters["t1"]["next_information_gap"] == "collect more comparable outcomes"
    assert clusters["t1"]["label"] == "research_proxy"
    sliced = slice_outcomes(
        [
            {"thesis_id": "t1", "pnl": -0.2, "symbol": "EURUSD", "side": "buy", "session": "london"},
            {"thesis_id": "t1", "pnl": 0.1, "symbol": "EURUSD", "side": "buy", "session": "london"},
        ]
    )
    assert sliced["schema"] == "attribution.v1"
    assert sliced["overall"]["n"] == 2


def test_full_book_search_mints_only_source_hashed_research_hypotheses(tmp_path):
    books = tmp_path / "books"
    books.mkdir()
    (books / "source.md").write_text(
        "# Source\n\n## Retest\nA breakout retest requires completed-bar confirmation.\n",
        encoding="utf-8",
    )
    index = BookIndex(tmp_path / "books.sqlite")
    index.rebuild(books)
    matches = search_full_book_knowledge(index, "breakout retest")
    proposals = hypotheses_for_market(matches, regime="trend", required_data=set())
    assert matches[0].file_hash
    assert proposals[0].source.filename == "source.md"
    assert "costed expectancy" in proposals[0].falsifiable_claim


def test_full_book_search_falls_back_to_individual_concepts_without_merging_sources(tmp_path):
    books = tmp_path / "books"
    books.mkdir()
    (books / "breakout.md").write_text("# Breakout\nBreakout confirmation only.\n", encoding="utf-8")
    index = BookIndex(tmp_path / "books.sqlite")
    index.rebuild(books)
    matches = search_full_book_knowledge(index, "breakout retest")
    assert [match.filename for match in matches] == ["breakout.md"]


def test_missing_book_data_is_provenance_not_supporting_evidence():
    source = SourceKnowledge(
        filename="l2.md",
        file_hash="abc",
        title="L2 source",
        concepts=(),
        data_requirements=("mt5_l2",),
        setup="",
        entry="",
        exit="",
        risk="",
        limitations=(),
        label="research_proxy",
    )
    proposal = hypotheses_for_market([source], regime="trend", required_data=set())[0]
    assert proposal.label == "unavailable"
    assert proposal.market_conditions["data_available"] is False


def test_thesis_registry_row_preserves_market_and_book_provenance(tmp_path):
    thesis = _thesis(calibrate_outcomes([0.1] * 30))
    row = thesis_experiment_row(
        thesis=thesis,
        dataset_fingerprint="bars:abc",
        status="rejected",
        rejection_reason="holdout pending",
    )
    registry = ExperimentRegistry(tmp_path / "experiments.sqlite")
    registry.record(row)
    stored = registry.get(thesis.thesis_id)
    assert stored is not None
    assert "market_state" in stored["provenance_json"]
    assert "calibration" in stored["provenance_json"]


def test_portfolio_state_tracks_fx_and_thesis_exposure_not_order_count():
    state = portfolio_state(
        [
            {"symbol": "EURUSD", "side": "buy", "quantity": 0.01, "thesis_id": "eur_long"},
            {"symbol": "EURUSD", "side": "buy", "quantity": 0.02, "thesis_id": "eur_long"},
            {"symbol": "GBPUSD", "side": "sell", "quantity": 0.01, "thesis_id": "gbp_short"},
        ]
    )
    assert state["positions"] == 3
    assert state["thesis_exposure"]["eur_long"] == 0.03
    assert state["currency_exposure"]["USD"] == pytest.approx(-0.02)


def test_strategy_audit_exposes_order_count_as_legacy_not_intelligence():
    rows = {row.key: row for row in current_strategy_audit()}
    assert rows["firehose_max_per_symbol"].classification == ARBITRARY_LEGACY
    assert "target_thesis_exposure" in rows["firehose_max_per_symbol"].replacement
    assert "safety_invariant" in audit_markdown()


def test_research_thesis_composes_full_book_state_and_outcome_evidence(tmp_path):
    books = tmp_path / "books"
    books.mkdir()
    (books / "retest.md").write_text(
        "# Retest source\n\nA breakout retest continuation needs a completed-bar confirmation.\n",
        encoding="utf-8",
    )
    index = BookIndex(tmp_path / "index.sqlite")
    index.rebuild(books)
    thesis = form_research_thesis(
        thesis_id="EURUSD_LONG_RETEST_20260101_002",
        symbol="EURUSD",
        side="buy",
        setup="breakout retest",
        state=build_market_state(symbol="EURUSD", m1=_m1()),
        historical_outcomes=[0.1] * 30,
        book_query="breakout retest",
        index=index,
        invalidation="completed close below retest low",
        expected_duration="M15",
        outcome_scope="state_matched",
    )
    assert thesis.book_provenance[0]["filename"] == "retest.md"
    assert thesis.calibrated_evidence.eligible is True
    assert thesis.market_state["lookahead"] is False


def test_unavailable_book_requirements_are_explicitly_not_support(tmp_path):
    books = tmp_path / "books"
    books.mkdir()
    (books / "l2.md").write_text("# L2\nLevel 2 breakout confirmation.\n", encoding="utf-8")
    index = BookIndex(tmp_path / "index.sqlite")
    index.rebuild(books)
    thesis = form_research_thesis(
        thesis_id="EURUSD_BUY_L2_20260101_001",
        symbol="EURUSD",
        side="buy",
        setup="L2 breakout",
        state=build_market_state(symbol="EURUSD", m1=_m1()),
        historical_outcomes=[0.1] * 30,
        book_query="breakout",
        index=index,
        invalidation="below support",
        expected_duration="M15",
    )
    assert not thesis.supporting_evidence
    assert "required data unavailable" in thesis.contradicting_evidence[0].detail


def test_shadow_intelligence_cycle_records_explanation_without_orders(tmp_path):
    books = tmp_path / "books"
    books.mkdir()
    (books / "retest.md").write_text("# Retest\nbreakout retest completed-bar setup\n", encoding="utf-8")
    index = BookIndex(tmp_path / "index.sqlite")
    index.rebuild(books)
    result = run_intelligence_cycle(
        thesis_id="EURUSD_BUY_RETEST_20260101_003",
        symbol="EURUSD",
        side="buy",
        setup="breakout retest",
        m1=_m1(),
        historical_outcomes=[0.1] * 30,
        book_query="breakout retest",
        invalidation="close below retest low",
        expected_duration="M15",
        index=index,
        registry=ExperimentRegistry(tmp_path / "experiments.sqlite"),
        total_risk_budget_usd=10.0,
        validated_risk_fraction=0.2,
        outcome_scope="state_matched",
    )
    assert result["placed_orders"] is False
    assert result["promoted_live_yaml"] is False
    assert result["recorded"] is True
    assert result["exposure"]["action"] == "increase"
    assert result["fire_decision"]["action"] == "skip"
    assert result["fire_decision"]["reason"] == "no_validated_strategy_model"
    assert "No orders placed" in intelligence_cycle_markdown(result)


def test_shadow_cycle_inherits_strategy_and_can_fire_without_local_loss_quota(tmp_path):
    from aegis.intel.strategy_model import ValidatedStrategyModel

    books = tmp_path / "books"
    books.mkdir()
    (books / "retest.md").write_text("# Retest\nbreakout retest completed-bar setup\n", encoding="utf-8")
    index = BookIndex(tmp_path / "index.sqlite")
    index.rebuild(books)
    strategy = ValidatedStrategyModel(
        strategy_id="failed_break_v1",
        promoted=True,
        n_trades=80,
        n_losses=12,
        expectancy=0.04,
        profit_factor=1.4,
        bootstrap_p05=0.01,
        wins_erased_by_average_loss=0.5,
        wins_erased_by_tail_loss=1.2,
        validated_risk_fraction=0.10,
        artifact_hash="abc123",
    )
    result = run_intelligence_cycle(
        thesis_id="EURUSD_BUY_RETEST_20260101_004",
        symbol="EURUSD",
        side="buy",
        setup="breakout retest",
        m1=_m1(),
        historical_outcomes=[0.1] * 30,
        book_query="breakout retest",
        invalidation="close below retest low",
        expected_duration="M15",
        index=index,
        registry=ExperimentRegistry(tmp_path / "experiments.sqlite"),
        total_risk_budget_usd=10.0,
        validated_risk_fraction=0.2,
        outcome_scope="state_matched",
        strategy=strategy,
    )
    assert result["placed_orders"] is False
    assert result["fire_decision"]["inherited_strategy"] == "failed_break_v1"
    assert result["fire_decision"]["action"] == "fire"
    assert result["fire_decision"]["reason"] == "positive_state_ev_on_validated_strategy"


def test_shadow_cycle_can_fire_when_inherited_model_and_state_gates_pass(tmp_path):
    from aegis.intel.strategy_model import ValidatedStrategyModel

    books = tmp_path / "books"
    books.mkdir()
    (books / "retest.md").write_text("# Retest\nbreakout retest completed-bar setup\n", encoding="utf-8")
    index = BookIndex(tmp_path / "index.sqlite")
    index.rebuild(books)
    strategy = ValidatedStrategyModel(
        strategy_id="failed_break_v1",
        promoted=True,
        n_trades=80,
        n_losses=12,
        expectancy=0.04,
        profit_factor=1.4,
        bootstrap_p05=0.01,
        wins_erased_by_average_loss=0.5,
        wins_erased_by_tail_loss=1.2,
        validated_risk_fraction=0.10,
        artifact_hash="abc123",
    )
    result = run_intelligence_cycle(
        thesis_id="EURUSD_BUY_RETEST_20260101_005",
        symbol="EURUSD",
        side="buy",
        setup="breakout retest",
        m1=_m1(),
        historical_outcomes=[0.2] * 30 + [-0.05] * 10,
        book_query="breakout retest",
        invalidation="close below retest low",
        expected_duration="M15",
        index=index,
        registry=ExperimentRegistry(tmp_path / "experiments.sqlite"),
        total_risk_budget_usd=10.0,
        validated_risk_fraction=0.2,
        outcome_scope="state_matched",
        strategy=strategy,
    )
    assert result["placed_orders"] is False
    assert result["fire_decision"]["action"] == "fire"
    assert result["fire_decision"]["reason"] == "positive_state_ev_on_validated_strategy"


def test_symbol_only_outcomes_cannot_calibrate_thesis_exposure(tmp_path):
    books = tmp_path / "books"
    books.mkdir()
    (books / "source.md").write_text("# Source\nbreakout setup\n", encoding="utf-8")
    index = BookIndex(tmp_path / "index.sqlite")
    index.rebuild(books)
    thesis = form_research_thesis(
        thesis_id="EURUSD_BUY_SCOPE_20260101_001",
        symbol="EURUSD",
        side="buy",
        setup="breakout",
        state=build_market_state(symbol="EURUSD", m1=_m1()),
        historical_outcomes=[0.1] * 30,
        book_query="breakout",
        index=index,
        invalidation="below support",
        expected_duration="M15",
        outcome_scope="symbol_only",
    )
    assert thesis.calibrated_evidence.eligible is False
    assert thesis.calibrated_evidence.uncertainty == "symbol_only_outcomes_not_market_state_matched"


def _historical_trades(outcomes: list[float], *, side: str = "buy") -> pd.DataFrame:
    start = pd.Timestamp("2026-01-01", tz="UTC")
    return pd.DataFrame(
        [
            {
                "entry_time": start + pd.Timedelta(minutes=i),
                "symbol": "EURUSD",
                "side": side,
                "r": outcome,
                "intel_snap": {
                    "h1_up": 1.0,
                    "m5_up": 1.0,
                    "atr_expand": False,
                },
            }
            for i, outcome in enumerate(outcomes)
        ]
    )


def test_historical_analogues_match_only_entry_time_market_state():
    records = trade_state_records(_historical_trades([0.5, -1.0]))
    matched = match_historical_states(
        records,
        {
            "side": "buy",
            "regime": "trend",
            "h1_direction": "up",
            "m5_direction": "up",
            "volatility": "compressing",
        },
    )
    assert matched["outcome"].tolist() == [0.5, -1.0]
    assert match_historical_states(
        records,
        {
            "side": "sell",
            "regime": "trend",
            "h1_direction": "up",
            "m5_direction": "up",
            "volatility": "compressing",
        },
    ).empty


def test_challenger_is_selected_on_train_then_rejected_on_sealed_holdout():
    candidates = {
        "train_winner": _historical_trades([0.5] * 70 + [-1.0] * 30),
        "runner_up": _historical_trades([0.1] * 100),
    }
    result = validate_state_matched_challengers(
        candidates,
        signature={
            "side": "buy",
            "regime": "trend",
            "h1_direction": "up",
            "m5_direction": "up",
            "volatility": "stable",
        },
    )
    assert result["selected"] == "train_winner"
    assert result["decision"] == "rejected"
    assert result["sealed_holdout"]["expectancy"] == pytest.approx(-1.0)
    assert pd.Timestamp(result["train_max"]) < pd.Timestamp(result["holdout_min"])


def test_market_state_cache_skips_rebuild_when_fingerprint_unchanged():
    cache = MarketStateCache()
    frame = _m1()
    first, changed = cache.update(symbol="EURUSD", m1=frame)
    assert changed is True
    again, changed = cache.update(symbol="EURUSD", m1=frame)
    assert changed is False
    assert again is first
    grown = pd.concat([frame, frame.iloc[[-1]].assign(time=frame["time"].iloc[-1] + pd.Timedelta(minutes=1))], ignore_index=True)
    rebuilt, changed = cache.update(symbol="EURUSD", m1=grown)
    assert changed is True
    assert rebuilt.observed_at != first.observed_at


def test_duplicate_ema_prints_share_information_id():
    first = thesis_information_id(
        symbol="EURUSD",
        side="buy",
        setup="ema side",
        invalidation="close below M15 swing",
        htf_bucket="2026-01-01T12:00",
        session="london",
    )
    second = thesis_information_id(
        symbol="EURUSD",
        side="buy",
        setup="ema side",
        invalidation="close below M15 swing",
        htf_bucket="2026-01-01T12:00",
        session="london",
    )
    h1_new = thesis_information_id(
        symbol="EURUSD",
        side="buy",
        setup="ema side",
        invalidation="close below M15 swing",
        htf_bucket="2026-01-01T13:00",
        session="london",
    )
    assert first == second
    assert first != h1_new


def test_compile_knowledge_table_drops_unhashed_and_unavailable_sources():
    rows = compile_knowledge_table(
        [
            SourceKnowledge(
                filename="good.md",
                file_hash="abc123",
                title="Good",
                concepts=("retest",),
                data_requirements=("completed_ohlcv",),
                setup="retest",
                entry="completed close",
                exit="below support",
                risk="defined invalidation",
                limitations=("no L2",),
                label="research_proxy",
            ),
            SourceKnowledge(
                filename="placeholder.md",
                file_hash="",
                title="Missing",
                concepts=(),
                data_requirements=(),
                setup="",
                entry="",
                exit="",
                risk="",
                limitations=(),
                label="unavailable",
            ),
        ]
    )
    assert len(rows) == 1
    assert rows[0]["file_hash"] == "abc123"
    assert rows[0]["invalidation"] == "below support"
    assert "damir_retest" in rows[0]["strategy_modules"]
