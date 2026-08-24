"""Tests for Research Factory."""
from __future__ import annotations

import pytest
import sys
import tempfile
import json
from pathlib import Path

import aegis.research_factory.core as research_factory_core
from aegis.research_factory.core import ResearchFactory, ResearchState, Champion, ExperimentResult, main
from aegis.research_factory.data import DataPipeline, FeatureEngineer, FeatureSet, DatasetSplit
from aegis.research_factory.loss_autopsy import LossAutopsyEngine, LossClass, HypothesisGenerator
from aegis.research_factory.hypothesis import HypothesisRegistry, Hypothesis, HypothesisOrigin, HypothesisStatus
from aegis.research_factory.champion import ChampionChallenger
from aegis.research_factory.data import DataPipeline, FeatureEngineer, FeatureSet, DatasetSplit
import pandas as pd
import numpy as np


class TestDataPipeline:
    """Tests for data pipeline."""

    def test_load_raw_data(self):
        """Test loading raw data from CSV files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            # Create test CSV
            csv_file = tmpdir / "EURUSD_1m_7d.csv"
            df = pd.DataFrame({
                "time": pd.date_range("2024-01-01", periods=100, freq="1min", tz="UTC"),
                "open": np.random.rand(100) * 1.1 + 1.09,
                "high": np.random.rand(100) * 1.1 + 1.095,
                "low": np.random.rand(100) * 1.1 + 1.085,
                "close": np.random.rand(100) * 1.1 + 1.09,
                "volume": np.random.randint(100, 1000, 100),
            })
            df.to_csv(csv_file, index=False)

            pipeline = DataPipeline()
            df_loaded = pipeline.load_raw_data(tmpdir)
            assert len(df_loaded) == 100
            assert "symbol" in df_loaded.columns
            assert "timeframe" in df_loaded.columns

    def test_create_splits(self):
        """Test chronological data splits."""
        df = pd.DataFrame({
            "time": pd.date_range("2024-01-01", periods=1000, freq="1min", tz="UTC"),
            "close": np.linspace(100.0, 110.0, 1000),
            "symbol": "EURUSD",
            "timeframe": "1m",
            "profit_barrier_first": 1.0,
        })

        pipeline = DataPipeline(min_train_size=500)
        splits = pipeline.create_splits(df, label_horizon=3)

        assert len(splits.train) == 597
        assert len(splits.validation) == 197
        assert len(splits.test) == 147
        assert len(splits.sealed_holdout) == 50

        # Check chronological order
        assert splits.train["time"].max() < splits.validation["time"].min()
        assert splits.validation["time"].max() < splits.test["time"].min()
        assert splits.test["time"].max() < splits.sealed_holdout["time"].min()

    def test_dataset_fingerprint(self):
        """Test dataset fingerprint computation."""
        df = pd.DataFrame({
            "time": pd.date_range("2024-01-01", periods=100, freq="1min", tz="UTC"),
            "close": np.random.rand(100),
        })

        pipeline = DataPipeline()
        fp1 = pipeline.compute_dataset_fingerprint(df)
        fp2 = pipeline.compute_dataset_fingerprint(df)
        assert fp1 == fp2
        assert len(fp1) == 64


class TestFeatureEngineer:
    """Tests for feature engineering."""

    def test_engineer_features(self):
        """Test feature engineering."""
        close = np.linspace(100.0, 102.0, 200)
        df = pd.DataFrame({
            "time": pd.date_range("2024-01-01", periods=200, freq="1min", tz="UTC"),
            "open": close,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": np.arange(100, 300),
            "symbol": "EURUSD",
            "timeframe": "1m",
        })

        engineer = FeatureEngineer()
        feature_set = engineer.engineer(
            df, profit_barrier_pct=0.01, loss_barrier_pct=0.01
        )

        # Check features were created
        assert len(feature_set.features) == 200
        assert len(feature_set.feature_names) > 10
        assert len(feature_set.label_names) > 0

        # Check specific features exist
        feature_names = set(feature_set.feature_names)
        assert "returns" in feature_names
        assert "log_returns" in feature_names
        assert "atr_14" in feature_names
        assert "realized_vol_20" in feature_names
        assert "range_position" in feature_names

    def test_labels_created(self):
        """Test labels are created correctly."""
        close = np.linspace(100.0, 102.0, 200)
        df = pd.DataFrame({
            "time": pd.date_range("2024-01-01", periods=200, freq="1min", tz="UTC"),
            "open": close,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": np.arange(100, 300),
            "symbol": "EURUSD",
            "timeframe": "1m",
        })

        engineer = FeatureEngineer()
        feature_set = engineer.engineer(
            df, profit_barrier_pct=0.01, loss_barrier_pct=0.01
        )

        # Check labels
        assert "profit_barrier_first" in feature_set.labels.columns
        assert "mfe" in feature_set.labels.columns
        assert "mae" in feature_set.labels.columns
        assert "no_progress" in feature_set.labels.columns
        assert "tail_loss" in feature_set.labels.columns


class TestLossAutopsy:
    """Tests for loss autopsy engine."""

    def test_classify_loss(self):
        """Test loss classification."""
        engine = LossAutopsyEngine()

        # Test BAD_ENTRY
        trade = {
            "mae": 10.0,
            "mfe": 1.0,
            "hold_time": 30,
            "pnl": -5.0,
        }
        loss_class, confidence = engine.classify_loss(trade)
        assert loss_class == LossClass.BAD_ENTRY
        assert confidence > 0

    def test_perform_autopsy(self):
        """Test complete autopsy."""
        engine = LossAutopsyEngine()

        trade = {
            "trade_id": "test_1",
            "symbol": "EURUSD",
            "side": "buy",
            "entry_price": 1.1000,
            "exit_price": 1.0990,
            "stop_loss": 1.0980,
            "target_price": 1.1020,
            "pnl": -10.0,
            "mfe": 1.0,
            "mae": 15.0,
            "hold_time": 120,
            "regime_at_entry": "trend",
            "regime_at_exit": "range",
            "session": "london",
            "spread_at_entry": 0.0002,
            "volatility_at_entry": 0.001,
        }

        autopsy = engine.perform_autopsy(trade)
        assert "loss_class" in autopsy
        assert "confidence" in autopsy
        assert "trade_details" in autopsy


class TestHypothesisGenerator:
    """Tests for hypothesis generation."""

    def test_generate_from_losses(self):
        """Test hypothesis generation from losses."""
        engine = LossAutopsyEngine()
        generator = HypothesisGenerator(engine)

        losses = []
        for i in range(10):
            losses.append({
                "trade_id": f"trade_{i}",
                "symbol": "EURUSD",
                "side": "buy",
                "pnl": -5.0,
                "mfe": 1.0,
                "mae": 10.0,
                "hold_time": 60,
                "regime_at_entry": "trend",
                "session": "london",
            })

        hypotheses = generator.generate_from_losses(losses)
        assert len(hypotheses) > 0
        for h in hypotheses:
            assert "hypothesis_id" in h
            assert "origin" in h
            assert "problem" in h


class TestHypothesisRegistry:
    """Tests for hypothesis registry."""

    def test_register_and_dedupe(self):
        """Test registration and deduplication."""
        registry = HypothesisRegistry()

        hyp1 = Hypothesis(
            hypothesis_id="hyp_1",
            origin=HypothesisOrigin.DATA_DERIVED,
            problem="test",
            proposed_mechanism="test",
            features_required=["high", "low", "close", "regime"],
            entry_rule={"type": "breakout", "direction": "long", "window": 20},
            exit_rule={"type": "regime_change"},
            side="buy",
            entry_price=None,
            invalidation_price=None,
            target_price=None,
            max_hold_s=None,
            expected_effect="test",
            falsification_criterion="test",
            training_period="2024-01-01 to 2024-06-30",
            validation_period="2024-07-01 to 2024-09-30",
            book_evidence=[],
            ml_evidence={"source": "test fixture"},
            loss_autopsy_evidence=[],
        )

        assert registry.register(hyp1) is True
        assert registry.register(hyp1) is False  # Duplicate
        assert registry.is_tested("hyp_1") is True
        assert registry.is_tested("hyp_2") is False

    def test_save_load(self):
        """Test save and load."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = HypothesisRegistry()

            hyp = Hypothesis(
                hypothesis_id="hyp_1",
                origin=HypothesisOrigin.DATA_DERIVED,
                problem="test",
                proposed_mechanism="test",
                features_required=["high", "low", "close", "regime"],
                entry_rule={"type": "breakout", "direction": "long", "window": 20},
                exit_rule={"type": "regime_change"},
                side="buy",
                entry_price=None,
                invalidation_price=None,
                target_price=None,
                max_hold_s=None,
                expected_effect="test",
                falsification_criterion="test",
                training_period="2024-01-01 to 2024-06-30",
                validation_period="2024-07-01 to 2024-09-30",
                book_evidence=[],
                ml_evidence={"source": "test fixture"},
                loss_autopsy_evidence=[],
            )
            registry.register(hyp)

            path = Path(tmpdir) / "registry.json"
            registry.save(path)

            loaded = HypothesisRegistry.load(path)
            assert loaded.is_tested("hyp_1")


class TestChampionChallenger:
    """Tests for champion/challenger system."""

    def test_evaluate_challenger(self):
        """Test challenger evaluation."""
        cc = ChampionChallenger()

        challenger = {
            "expectancy": 0.2,
            "profit_factor": 2.0,
            "avg_loss": -0.5,
            "p95_loss": -2.0,
            "max_drawdown": 0.15,
            "total_trades": 100,
            "win_rate": 0.6,
            "payoff_ratio": 1.5,
        }

        passes, reason = cc.evaluate_challenger(challenger)
        assert passes is True
        assert "All gates passed" in reason

    def test_challenger_fails_gates(self):
        """Test challenger that fails gates."""
        cc = ChampionChallenger()

        challenger = {
            "metrics": {
                "expectancy": 0.05,  # Too low
                "profit_factor": 1.0,  # Too low
            }
        }

        passes, reason = cc.evaluate_challenger(challenger)
        assert passes is False
        assert "Failed gates" in reason

    def test_promote_if_better(self):
        """Test promotion logic."""
        cc = ChampionChallenger()

        cc.champion = {
            "hypothesis_id": "champ_1",
            "metrics": {
                "expectancy": 0.15,
                "profit_factor": 1.5,
                "max_drawdown": 0.15,
                "avg_loss": -0.8,
            }
        }

        cc.challenger = {
            "hypothesis_id": "chall_1",
            "metrics": {
                "expectancy": 0.20,  # Better
                "profit_factor": 2.0,  # Better
                "max_drawdown": 0.12,  # Better
                "avg_loss": -0.7,  # Better
            }
        }

        assert cc.promote_if_better(cc.challenger, cc.champion) is True


class TestResearchState:
    """Tests for research state persistence."""

    def test_save_load(self):
        """Test state save and load."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state = ResearchState(
                generation=5,
                champion=Champion(
                    hypothesis_id="hyp_1",
                    metrics={"expectancy": 0.2},
                    model_hash="abc123",
                    dataset_fingerprint="abc123",
                    promoted_at="2024-01-01T00:00:00",
                    promotion_generation=3,
                ),
                codex_calls=0,
                codex_budget=1,
                last_generation_status="FAILED",
                last_generation_reason="training failed",
            )

            path = Path(tmpdir) / "state.json"
            state.save(path)

            loaded = ResearchState.load(path)
            assert loaded.generation == 5
            assert loaded.champion.hypothesis_id == "hyp_1"
            assert loaded.codex_calls == 0
            assert loaded.codex_budget == 1
            assert loaded.last_generation_status == "FAILED"
            assert loaded.last_generation_reason == "training failed"

    def test_generation_barriers_are_required_and_must_be_positive(self):
        with pytest.raises(TypeError, match="profit_barrier_pct"):
            ResearchFactory()
        with pytest.raises(ValueError, match="label_horizon.*positive integer"):
            ResearchFactory(
                profit_barrier_pct=0.01,
                loss_barrier_pct=0.01,
                label_horizon=True,
            )
        for profit_barrier_pct, loss_barrier_pct in (
            (0.0, 0.01),
            (-0.01, 0.01),
            (0.01, 0.0),
            (0.01, -0.01),
        ):
            with pytest.raises(ValueError, match="barrier_pct"):
                ResearchFactory(
                    profit_barrier_pct=profit_barrier_pct,
                    loss_barrier_pct=loss_barrier_pct,
                )

    def test_cli_requires_positive_generation_barriers(
        self, monkeypatch, capsys
    ):
        monkeypatch.setattr(sys, "argv", ["research-factory"])
        with pytest.raises(SystemExit) as omitted:
            main()
        assert omitted.value.code == 2

        monkeypatch.setattr(
            sys,
            "argv",
            [
                "research-factory",
                "--profit-barrier-pct",
                "0",
                "--loss-barrier-pct",
                "0.01",
            ],
        )
        with pytest.raises(SystemExit) as non_positive:
            main()
        assert non_positive.value.code == 2
        assert "profit_barrier_pct must be positive" in capsys.readouterr().err


def test_factory_initializes_defined_collaborators(monkeypatch, tmp_path):
    for name in (
        "knowledge_table.json",
        "cost_profiles.json",
        "validated_states.json",
        "validated_opportunities.json",
    ):
        (tmp_path / name).write_text("{}")

    analogue_store = object()
    monkeypatch.setattr(research_factory_core, "INTEL_DIR", tmp_path)
    monkeypatch.setattr(research_factory_core, "ensure_intel_dirs", lambda: None)
    monkeypatch.setattr(
        research_factory_core.AnalogueStore, "load", lambda path: analogue_store
    )
    monkeypatch.setattr(research_factory_core, "load_losses", lambda: [])

    factory = object.__new__(ResearchFactory)
    factory.claude_enabled = False
    factory.state = ResearchState()
    factory._init_components()

    assert factory.analogue_store is analogue_store
    assert factory.knowledge_table == {}
    assert factory.cost_profiles == {}
    assert factory.validated_states == {}
    assert factory.validated_opportunities == {}
    assert isinstance(factory.data_pipeline, DataPipeline)
    assert isinstance(factory.feature_engineer, FeatureEngineer)
    assert isinstance(factory.ml_pipeline, research_factory_core.MLPipeline)
    assert factory.losses == []
    assert factory.state.claude_available is False


@pytest.mark.parametrize(
    "agent_result",
    [
        {"ok": False, "status": "UNAVAILABLE_CLI", "error": "CLI not found"},
        {"ok": True, "status": "AVAILABLE", "output": "not a serialized hypothesis"},
    ],
)
def test_claude_adapter_failure_or_malformed_output_never_registers_hypothesis(
    monkeypatch, agent_result
):
    """Accepting adapter failure or malformed text would fabricate a hypothesis."""
    monkeypatch.setattr(
        research_factory_core,
        "ask_research_agent",
        lambda *args, **kwargs: agent_result,
    )
    persisted = []
    monkeypatch.setattr(research_factory_core, "record_outcome", lambda *args: persisted.append(args))

    factory = object.__new__(ResearchFactory)
    factory.state = ResearchState(claude_available=True)
    factory.losses = []
    factory.experiment_registry = object()
    factory.agent_budget_ledger = object()
    factory.reports_dir = Path(tempfile.mkdtemp())

    factory._ask_claude_for_new_direction()

    assert factory.state.hypothesis_registry == {}
    assert factory.state.last_generation_status == "FAILED"
    assert "Claude" in factory.state.last_generation_reason
    assert persisted


def test_public_factory_construction_does_not_start_an_agent_process(monkeypatch, tmp_path):
    """Reintroducing a local client probe would create a process during construction."""
    for name in (
        "knowledge_table.json",
        "cost_profiles.json",
        "validated_states.json",
        "validated_opportunities.json",
    ):
        (tmp_path / name).write_text("{}")

    monkeypatch.setattr(research_factory_core, "INTEL_DIR", tmp_path)
    monkeypatch.setattr(research_factory_core, "ensure_intel_dirs", lambda: None)
    monkeypatch.setattr(research_factory_core.AnalogueStore, "load", lambda path: object())
    monkeypatch.setattr(research_factory_core, "load_losses", lambda: [])
    monkeypatch.setattr(
        research_factory_core,
        "ask_research_agent",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("no agent ask during construction")),
    )
    import ai_council.agents as agent_cli

    monkeypatch.setattr(
        agent_cli.subprocess,
        "Popen",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("no process during construction")),
    )

    factory = ResearchFactory(
        profit_barrier_pct=0.01,
        loss_barrier_pct=0.01,
        reports_dir=tmp_path / "reports",
    )

    assert factory.agent_budget_ledger.remaining("codex") == 0


def test_factory_restart_keeps_state_and_codex_budget_in_reports_dir(monkeypatch, tmp_path):
    """A separate state path would lose restart state or share another ledger."""
    for name in (
        "knowledge_table.json",
        "cost_profiles.json",
        "validated_states.json",
        "validated_opportunities.json",
    ):
        (tmp_path / name).write_text("{}")

    monkeypatch.setattr(research_factory_core, "INTEL_DIR", tmp_path)
    monkeypatch.setattr(research_factory_core, "ensure_intel_dirs", lambda: None)
    monkeypatch.setattr(research_factory_core.AnalogueStore, "load", lambda path: object())
    monkeypatch.setattr(research_factory_core, "load_losses", lambda: [])

    reports_dir = tmp_path / "reports"
    first = ResearchFactory(
        profit_barrier_pct=0.01,
        loss_barrier_pct=0.01,
        reports_dir=reports_dir,
    )
    first.state.generation = 7
    first.state.save(first.state_path)

    resumed = ResearchFactory(
        profit_barrier_pct=0.01,
        loss_barrier_pct=0.01,
        reports_dir=reports_dir,
        resume=True,
    )

    assert first.state_path == reports_dir / "state.json"
    assert resumed.state.generation == 7
    assert resumed.agent_budget_ledger.remaining("codex") == 0


def test_factory_dashboard_uses_durable_exhausted_codex_ledger(capsys, tmp_path):
    """Using ResearchState counters would display a usable Codex budget."""
    factory = object.__new__(ResearchFactory)
    factory.state = ResearchState(codex_calls=0, codex_budget=99)
    factory.agent_budget_ledger = research_factory_core.AgentBudgetLedger(
        tmp_path / "agent_budgets.json"
    )
    factory.reports_dir = tmp_path

    factory._print_dashboard()
    factory.save_report()

    assert "Codex: EXHAUSTED (1 / 1)" in capsys.readouterr().out
    report = json.loads((tmp_path / "final_weekend_report.json").read_text())
    assert report["codex"] == {
        "used": 1,
        "limit": 1,
        "remaining": 0,
        "status": "EXHAUSTED",
    }


def test_run_reaches_restored_plateau_check_without_agent_call(monkeypatch, tmp_path):
    """Removing _check_plateau makes every completed generation fail late."""
    factory = object.__new__(ResearchFactory)
    factory.state = ResearchState(claude_available=False)
    factory.max_generations = 1
    factory.continuous = False
    factory.state_path = tmp_path / "state.json"
    factory._print_dashboard = lambda: None
    factory._run_generation = lambda: None
    factory._ask_claude_for_new_direction = lambda: (_ for _ in ()).throw(
        AssertionError("no agent ask expected")
    )

    assert factory._check_plateau() is False
    factory.run()

    assert factory.state.generation == 1
    assert factory.state_path.exists()


def test_restored_promotion_gate_and_learning_log_are_not_unconditional():
    """The removed gate must reject weaker challengers and retain learning events."""
    factory = object.__new__(ResearchFactory)
    factory.state = ResearchState(
        champion=Champion("champion", {"expectancy": 1.0, "profit_factor": 2.0, "max_drawdown": 0.1}, "", "", "", 1),
        challenger=Champion("challenger", {"expectancy": 0.5, "profit_factor": 1.0, "max_drawdown": 0.5}, "", "", "", 1),
        experiments=[ExperimentResult("hypothesis", 1, {"expectancy": 0.1}, "REJECTED")],
    )
    events = []
    factory._log_event = lambda *args, **kwargs: events.append((args, kwargs))

    assert factory._should_promote_challenger() is False
    factory._log_learning()
    assert events[0][0][:2] == ("LEARNING", "Generation 0 learning")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
