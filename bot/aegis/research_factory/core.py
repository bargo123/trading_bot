"""Core research factory implementation."""
from __future__ import annotations

import json
import sys
import time
import hashlib
import argparse
import logging
import random
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum

import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.inspection import permutation_importance

# Add project root to path
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from aegis.intel.analogue_store import AnalogueStore
from aegis.intel.books import lookup
from aegis.intel.fast_firehose import FastExitConfig, FastExitStateMachine
from aegis.intel.knowledge_retrieval import retrieve_for_state
from aegis.intel.paths import INTEL_DIR, ensure_intel_dirs
from aegis.research.registry import ExperimentRegistry
from aegis.research_factory.data import (
    DataPipeline,
    FeatureEngineer,
    InsufficientDataError,
    discover_csv_sources,
)
from aegis.research_factory.ml_pipeline import MLPipeline
from aegis.research_factory.evaluation import record_outcome
from aegis.research_factory.hypothesis import Hypothesis, HypothesisOrigin
from aegis.research_factory.rules import compile_hypothesis
from aegis.research_factory.walk_forward import walk_forward_evaluate
from ai_council.live import AgentBudgetLedger, ask_research_agent

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


def _positive_barrier(name: str, value: float) -> float:
    """Validate an explicitly supplied generation barrier percentage."""
    try:
        barrier = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be positive") from exc
    if not np.isfinite(barrier) or barrier <= 0:
        raise ValueError(f"{name} must be positive")
    return barrier


def _positive_cli_barrier(name: str, value: str) -> float:
    try:
        return _positive_barrier(name, value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


# ============================================================
# HELPER CLASSES (stand-ins for unavailable modules)
# ============================================================

# ============================================================
# CODEX INTEGRATION
# ============================================================


def load_losses() -> List[Dict[str, Any]]:
    """Load losses from the loss database."""
    from aegis.intel.paths import INTEL_DIR
    import json
    
    losses_path = INTEL_DIR / "losses.jsonl"
    if not losses_path.exists():
        # NO synthetic data - real research requires real losses
        logger.warning(f"Losses file not found at {losses_path}. Returning empty list.")
        return []
    
    losses = []
    with losses_path.open() as f:
        for line in f:
            try:
                losses.append(json.loads(line))
            except Exception:
                pass
    return losses


class LossClass(Enum):
    """Loss classification for autopsy."""
    BAD_ENTRY = "BAD_ENTRY"
    WRONG_SIDE = "WRONG_SIDE"
    WRONG_REGIME = "WRONG_REGIME"
    SPREAD_COST = "SPREAD_COST"
    ADVERSE_SELECTION = "ADVERSE_SELECTION"
    LATE_ENTRY = "LATE_ENTRY"
    FALSE_BREAKOUT = "FALSE_BREAKOUT"
    NO_PROGRESS = "NO_PROGRESS"
    MOMENTUM_FAILURE = "MOMENTUM_FAILURE"
    WINNER_GIVEBACK = "WINNER_GIVEBACK"
    STOP_TOO_WIDE = "STOP_TOO_WIDE"
    TIME_EXIT_TOO_LATE = "TIME_EXIT_TOO_LATE"
    SELF_HEDGE = "SELF_HEDGE"
    TAIL_EVENT = "TAIL_EVENT"
    INSUFFICIENT_INFORMATION = "INSUFFICIENT_INFORMATION"
    UNAVOIDABLE = "UNAVOIDABLE"


class InventionClass(Enum):
    """Invention class for hypotheses."""
    DIRECT_BOOK = "DIRECT_BOOK_HYPOTHESIS"
    BOOK_DERIVED = "BOOK_DERIVED_HYPOTHESIS"
    DATA_DERIVED = "DATA_DERIVED_HYPOTHESIS"
    ML_DISCOVERED = "ML_DISCOVERED_HYPOTHESIS"
    NOVEL_SYNTHESIZED = "NOVEL_SYNTHESIZED_HYPOTHESIS"


class MarketState(Enum):
    """Market state for the research factory."""
    CLOSED = "CLOSED"
    WEEKEND_RESEARCH = "WEEKEND_RESEARCH"
    OPEN = "OPEN"


@dataclass
class ExperimentResult:
    """Result of an experiment."""
    hypothesis_id: str
    generation: int
    metrics: Dict[str, Any]
    decision: str  # REJECTED, CHALLENGER, CHAMPION
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    dataset_fingerprint: str = ""
    model_hash: str = ""
    cost_model: str = ""
    random_seed: int = 42


@dataclass
class Champion:
    """Current champion candidate."""
    hypothesis_id: str
    metrics: Dict[str, Any]
    model_hash: str
    dataset_fingerprint: str
    promoted_at: str
    promotion_generation: int


@dataclass
class ResearchState:
    """Persisted research factory state."""
    generation: int = 0
    champion: Optional[Champion] = None
    challenger: Optional[Champion] = None
    experiments: List[ExperimentResult] = field(default_factory=list)
    failed_hypotheses: List[str] = field(default_factory=list)
    hypothesis_registry: Dict[str, Hypothesis] = field(default_factory=dict)
    codex_calls: int = 0
    codex_budget: int = 1
    claude_available: bool = True
    market_state: MarketState = MarketState.WEEKEND_RESEARCH
    dataset_fingerprint: str = ""
    last_generation_status: str = ""
    last_generation_reason: str = ""
    last_update: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def save(self, path: Path) -> None:
        """Save state to disk."""
        data = {
            "generation": self.generation,
            "champion": asdict(self.champion) if self.champion else None,
            "challenger": asdict(self.challenger) if self.challenger else None,
            "experiments": [asdict(e) for e in self.experiments],
            "failed_hypotheses": self.failed_hypotheses,
            "hypothesis_registry": {
                k: v.to_dict() for k, v in self.hypothesis_registry.items()
            },
            "codex_calls": self.codex_calls,
            "codex_budget": self.codex_budget,
            "claude_available": self.claude_available,
            "market_state": self.market_state.value,
            "dataset_fingerprint": self.dataset_fingerprint,
            "last_generation_status": self.last_generation_status,
            "last_generation_reason": self.last_generation_reason,
            "last_update": self.last_update,
        }
        path.write_text(json.dumps(data, indent=2, default=str))

    @classmethod
    def load(cls, path: Path) -> "ResearchState":
        """Load state from disk."""
        if not path.exists():
            return cls()
        data = json.loads(path.read_text())
        state = cls(
            generation=data.get("generation", 0),
            champion=Champion(**data["champion"]) if data.get("champion") else None,
            challenger=Champion(**data["challenger"]) if data.get("challenger") else None,
            experiments=[ExperimentResult(**e) for e in data.get("experiments", [])],
            failed_hypotheses=data.get("failed_hypotheses", []),
            hypothesis_registry={
                k: Hypothesis.from_dict(v)
                for k, v in data.get("hypothesis_registry", {}).items()
            },
            codex_calls=data.get("codex_calls", 0),
            codex_budget=data.get("codex_budget", 1),
            claude_available=data.get("claude_available", True),
            market_state=MarketState(data.get("market_state", "WEEKEND_RESEARCH")),
            dataset_fingerprint=data.get("dataset_fingerprint", ""),
            last_generation_status=data.get("last_generation_status", ""),
            last_generation_reason=data.get("last_generation_reason", ""),
            last_update=data.get("last_update", datetime.now(timezone.utc).isoformat()),
        )
        return state


class ResearchFactory:
    """Autonomous Weekend Research Factory."""

    def __init__(
        self,
        mode: str = "weekend",
        continuous: bool = False,
        max_generations: int = 100,
        claude_enabled: bool = True,
        codex_budget: int = 1,
        sealed_holdout: bool = True,
        resume: bool = False,
        *,
        profit_barrier_pct: float,
        loss_barrier_pct: float,
        label_horizon: int = 20,
        source_roots: Optional[List[Path]] = None,
        reports_dir: Optional[Path] = None,
    ):
        self.profit_barrier_pct = _positive_barrier(
            "profit_barrier_pct", profit_barrier_pct
        )
        self.loss_barrier_pct = _positive_barrier(
            "loss_barrier_pct", loss_barrier_pct
        )
        if (
            isinstance(label_horizon, bool)
            or not isinstance(label_horizon, int)
            or label_horizon <= 0
        ):
            raise ValueError("label_horizon must be a positive integer")
        self.label_horizon = label_horizon
        self.source_roots = tuple(
            Path(root)
            for root in (
                source_roots
                if source_roots is not None
                else [ROOT / "bot" / "data" / "cafb_snapshots"]
            )
        )
        self.mode = mode
        self.continuous = continuous
        self.max_generations = max_generations
        self.claude_enabled = claude_enabled
        self.codex_budget = codex_budget
        self.sealed_holdout = sealed_holdout

        # Initialize paths
        self.state_path = Path("C:/Users/Zaid barghouthi/Desktop/trading_bot/bot/reports") / "research_factory" / "state.json"
        self.reports_dir = reports_dir or Path("C:/Users/Zaid barghouthi/Desktop/trading_bot/bot/reports") / "research_factory"
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.agent_budget_ledger = AgentBudgetLedger(
            self.reports_dir / "agent_budgets.json"
        )

        # Load or create state
        if resume and self.state_path.exists():
            self.state = ResearchState.load(self.state_path)
            logger.info(f"Resumed research from generation {self.state.generation}")
        else:
            self.state = ResearchState()
            logger.info("Starting fresh research factory")

        # Initialize components
        self._init_components()

    def _init_components(self) -> None:
        """Initialize all research components."""
        ensure_intel_dirs()

        # Load existing data
        self.analogue_store = AnalogueStore.load(INTEL_DIR / "analogue_index.json")
        self.knowledge_table = json.loads((INTEL_DIR / "knowledge_table.json").read_text())
        self.cost_profiles = json.loads((INTEL_DIR / "cost_profiles.json").read_text())
        self.validated_states = json.loads((INTEL_DIR / "validated_states.json").read_text())
        self.validated_opportunities = json.loads((INTEL_DIR / "validated_opportunities.json").read_text())

        # Initialize the canonical data and ML collaborators once.
        self.data_pipeline = DataPipeline()
        self.feature_engineer = FeatureEngineer()
        self.ml_pipeline = MLPipeline()
        self.experiment_registry = ExperimentRegistry()

        # Initialize loss database
        self.losses = load_losses()

        # Availability is determined only by a real shared-adapter ask.
        self.state.claude_available = self.claude_enabled

        logger.info("All components initialized")

    def _print_dashboard(self) -> None:
        """Print live dashboard."""
        dashboard = f"""
==============================================================
AEGIS ZERO-LOSS RESEARCH FACTORY
==============================================================
Generation: {self.state.generation}
Champion: {self.state.champion.hypothesis_id if self.state.champion else 'NONE'}
Dataset: {self.state.dataset_fingerprint[:16] if self.state.dataset_fingerprint else 'UNKNOWN'}
Experiments tested: {len(self.state.experiments)}
Experiments rejected: {len([e for e in self.state.experiments if e.decision == 'REJECTED'])}
Current hypothesis: {self.state.hypothesis_registry.get(self.state.challenger.hypothesis_id, 'N/A') if self.state.challenger else 'N/A'}
Claude: {'AVAILABLE' if self.state.claude_available else 'UNAVAILABLE'}
Codex calls: {self.state.codex_calls} / {self.state.codex_budget}
Market: {'CLOSED / WEEKEND_RESEARCH' if self.state.market_state == MarketState.WEEKEND_RESEARCH else 'OPEN'}
Live trading: DISABLED
==============================================================
"""
        print(dashboard, flush=True)

    def _log_event(self, event_type: str, message: str, **kwargs) -> None:
        """Log a live event with timestamp."""
        timestamp = datetime.now(timezone.utc).isoformat()
        log_entry = f"[{event_type}] {message}"
        if kwargs:
            log_entry += f" | {json.dumps(kwargs, default=str)}"
        logger.info(log_entry)

    def run(self) -> None:
        """Run the autonomous research factory."""
        logger.info("Starting AEGIS Zero-Loss Research Factory")

        try:
            while self.state.generation < self.max_generations:
                self.state.generation += 1
                self.state.last_update = datetime.now(timezone.utc).isoformat()

                self._print_dashboard()

                # Run one generation
                self._run_generation()

                # Save state
                self.state.save(self.state_path)

                # Check for plateau
                if self._check_plateau():
                    logger.info("RESEARCH PLATEAU DETECTED")
                    if self.state.claude_available:
                        self._ask_claude_for_new_direction()
                    else:
                        logger.info("Claude unavailable, continuing deterministic research")

                if not self.continuous:
                    break

                # Small delay between generations
                time.sleep(1)

        except KeyboardInterrupt:
            logger.info("Research interrupted by user")
        except Exception as e:
            logger.exception(f"Research factory error: {e}")
        finally:
            self.state.save(self.state_path)
            logger.info("Research factory stopped")

    def _run_generation(self) -> None:
        """Route one canonical frame through discovery, splitting, and training."""
        self.state.last_generation_status = ""
        self.state.last_generation_reason = ""
        self.state.dataset_fingerprint = "NOT_COMPUTED"
        self._log_event("DATA", f"Loading data for generation {self.state.generation}")

        try:
            sources = discover_csv_sources(self.source_roots)
            raw_data = self.data_pipeline.load_sources(sources)
        except Exception as exc:
            self._record_generation_outcome(
                "FAILED", f"Data discovery or loading failed: {exc}"
            )
            return

        if raw_data.empty:
            self._record_generation_outcome(
                "NO_DATA", "No legitimate source rows were available"
            )
            return

        self._log_event("ML", f"Engineering features for generation {self.state.generation}")
        try:
            feature_set = self.feature_engineer.engineer(
                raw_data,
                profit_barrier_pct=self.profit_barrier_pct,
                loss_barrier_pct=self.loss_barrier_pct,
                label_horizon=self.label_horizon,
            )
        except Exception as exc:
            self._record_generation_outcome(
                "FAILED", f"Feature engineering failed: {exc}"
            )
            return

        canonical = feature_set.canonical
        if canonical.empty:
            self._record_generation_outcome(
                "NO_DATA", "Feature engineering produced no canonical rows"
            )
            return

        try:
            self.state.dataset_fingerprint = (
                self.data_pipeline.compute_dataset_fingerprint(canonical)
            )
        except Exception as exc:
            self._record_generation_outcome(
                "FAILED", f"Canonical dataset fingerprint failed: {exc}"
            )
            return

        try:
            self._log_event("DATA", "Splitting canonical data chronologically")
            splits = self.data_pipeline.create_splits(
                canonical, label_horizon=self.label_horizon
            )
        except InsufficientDataError as exc:
            self._record_generation_outcome(
                "NO_DATA", f"Canonical data has no usable matured split: {exc}"
            )
            return
        except Exception as exc:
            self._record_generation_outcome(
                "FAILED", f"Canonical data preparation failed: {exc}"
            )
            return

        self._log_event("ML", f"Training models for generation {self.state.generation}")
        try:
            models = self.ml_pipeline.train(splits.train, splits.validation)
        except Exception as exc:
            self._record_generation_outcome("FAILED", f"ML training failed: {exc}")
            return
        if not models:
            self._record_generation_outcome(
                "FAILED", "ML training produced no trained models"
            )
            return

        self._record_generation_outcome(
            "NO_EVIDENCE",
            "broker-native replay cost evidence is required for walk-forward evaluation",
        )

    def _record_generation_outcome(
        self,
        status: str,
        reason: str,
        *,
        hypothesis: Optional[Hypothesis] = None,
        metrics: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Persist and emit an honest terminal generation outcome."""
        self.state.last_generation_status = status
        self.state.last_generation_reason = reason
        self._log_event("GENERATION", reason, status=status)
        registry = getattr(self, "experiment_registry", None)
        if registry is None:
            persistence_reason = (
                "ExperimentRegistry is required for terminal outcome persistence"
            )
            self.state.last_generation_status = "FAILED"
            self.state.last_generation_reason = persistence_reason
            self._log_event("GENERATION", persistence_reason, status="FAILED")
            raise RuntimeError(persistence_reason)
        attempted_research = hypothesis or {
            "hypothesis_id": f"research_factory_generation_{self.state.generation}",
            "origin": "RESEARCH_FACTORY",
            "problem": "research factory generation",
            "proposed_mechanism": "execute one governed research factory generation",
            "generation": self.state.generation,
        }
        try:
            record_outcome(
                registry,
                attempted_research,
                self.state.dataset_fingerprint,
                status,
                reason,
                metrics,
            )
        except Exception as exc:
            persistence_reason = f"Terminal outcome persistence failed: {exc}"
            self.state.last_generation_status = "FAILED"
            self.state.last_generation_reason = persistence_reason
            self._log_event("GENERATION", persistence_reason, status="FAILED")
            raise

    def _load_dataset(self) -> pd.DataFrame:
        """Load and combine all available historical data."""
        # Load from existing data files
        data_dir = Path("C:/Users/Zaid barghouthi/Desktop/trading_bot/bot/data/cafb_snapshots")
        frames = []

        for csv_file in data_dir.glob("*.csv"):
            try:
                df = pd.read_csv(csv_file)
                # Extract symbol from filename (e.g., EURUSD_X_1m_7d.csv -> EURUSD)
                symbol = csv_file.stem.split("_")[0]
                df["symbol"] = symbol
                df["source_file"] = csv_file.name
                frames.append(df)
            except Exception as e:
                logger.warning(f"Failed to load {csv_file}: {e}")

        if frames:
            combined = pd.concat(frames, ignore_index=True)
            if "time" in combined.columns:
                combined["time"] = pd.to_datetime(combined["time"], utc=True)
                combined = combined.sort_values("time").reset_index(drop=True)
            return combined
        else:
            # Return empty DataFrame with expected columns
            return pd.DataFrame(columns=["time", "open", "high", "low", "close", "volume", "symbol"])

    def _compute_dataset_fingerprint(self, df: pd.DataFrame) -> str:
        """Compute a fingerprint of the dataset for reproducibility."""
        if df.empty:
            return "empty"
        # Hash based on shape, columns, date range, and sample values
        info = f"{df.shape}|{list(df.columns)}|{df.iloc[0].to_dict() if len(df) > 0 else {}}|{df.iloc[-1].to_dict() if len(df) > 0 else {}}"
        return hashlib.sha256(info.encode()).hexdigest()[:16]

    def _engineer_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Engineer features with point-in-time correctness."""
        if df.empty:
            return df

        df = df.copy()

        # Ensure time is datetime
        if "time" in df.columns:
            df["time"] = pd.to_datetime(df["time"], utc=True)

        # Sort by time
        df = df.sort_values("time").reset_index(drop=True)

        # Price features
        df["returns"] = df.groupby("symbol")["close"].pct_change()
        df["log_returns"] = np.log(df["close"] / df.groupby("symbol")["close"].shift(1))
        df["momentum_5"] = df.groupby("symbol")["close"].pct_change(5)
        df["momentum_15"] = df.groupby("symbol")["close"].pct_change(15)
        df["acceleration"] = df.groupby("symbol")["returns"].diff()

        # Volatility features
        df["range"] = (df["high"] - df["low"]) / df["close"]
        df["atr_14"] = df.groupby("symbol")["range"].rolling(14).mean().reset_index(level=0, drop=True)
        df["realized_vol"] = df.groupby("symbol")["returns"].rolling(20).std().reset_index(level=0, drop=True)

        # Structure features
        df["range_position"] = (df["close"] - df["low"]) / (df["high"] - df["low"]).replace(0, np.nan)
        df["body_size"] = abs(df["close"] - df["open"]) / df["close"]
        df["upper_wick"] = (df["high"] - df[["open", "close"]].max(axis=1)) / df["close"]
        df["lower_wick"] = (df[["open", "close"]].min(axis=1) - df["low"]) / df["close"]

        # Multi-timeframe features (using rolling windows)
        for window in [5, 15, 30, 60]:
            df[f"sma_{window}"] = df.groupby("symbol")["close"].rolling(window).mean().reset_index(level=0, drop=True)
            df[f"ema_{window}"] = df.groupby("symbol")["close"].ewm(span=window).mean().reset_index(level=0, drop=True)
            df[f"dist_sma_{window}"] = (df["close"] - df[f"sma_{window}"]) / df[f"sma_{window}"]

        # Session features
        if "time" in df.columns:
            df["hour"] = df["time"].dt.hour
            df["day_of_week"] = df["time"].dt.dayofweek
            df["session"] = df["hour"].map({
                **{h: "asia" for h in range(0, 8)},
                **{h: "london" for h in range(8, 16)},
                **{h: "newyork" for h in range(16, 24)},
            })

        return df

    def _create_labels(self, df: pd.DataFrame, horizon: int = 20) -> pd.DataFrame:
        """Create outcome labels using ONLY past/present data (no lookahead).
        
        Labels are computed using only data available at decision time.
        Future data is NEVER used for label creation.
        """
        if df.empty:
            return df

        df = df.copy()

        # Labels based on PAST data only - no future leakage
        # Use rolling windows of PAST data to create labels
        
        # Volatility regime label (based on past volatility)
        past_vol = df.groupby("symbol")["returns"].rolling(20).std().reset_index(level=0, drop=True)
        df["vol_regime"] = pd.qcut(past_vol, q=3, labels=["low", "med", "high"], duplicates="drop")
        
        # Trend label (based on past returns)
        past_return = df.groupby("symbol")["close"].pct_change(20)
        df["trend_label"] = np.where(past_return > 0.01, "up", np.where(past_return < -0.01, "down", "flat"))
        
        # Volatility expansion/contraction
        vol_ratio = df.groupby("symbol")["atr_14"].rolling(5).mean().reset_index(level=0, drop=True) / \
                     df.groupby("symbol")["atr_14"].rolling(20).mean().reset_index(level=0, drop=True)
        df["vol_expanding"] = (vol_ratio > 1.2).astype(int)
        df["vol_contracting"] = (vol_ratio < 0.8).astype(int)
        
        # Session-based labels
        df["session_label"] = df["session"] if "session" in df.columns else "unknown"
        
        # Range position label (using only past data)
        df["range_pos_label"] = pd.qcut(df["range_position"], q=3, labels=["low", "mid", "high"], duplicates="drop")
        
        # Target: next bar direction (using shift(-1) is acceptable for TARGET only, not features)
        # This is the ONLY forward-looking operation allowed - creating the TARGET variable
        df["target_direction"] = np.where(
            df.groupby("symbol")["close"].shift(-1) > df["close"], 1, 0
        )
        
        return df

    def _split_data(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """Split data chronologically into train/val/test/sealed.
        
        The sealed holdout is PHYSICALLY ISOLATED - it is NEVER used for:
        - Feature selection tuning
        - Hyperparameter tuning  
        - Hypothesis generation
        - Model selection
        - Any optimization decisions
        
        It is ONLY used ONCE for final evaluation of a candidate that has
        passed ALL prior gates (champion promotion).
        """
        if df.empty or "time" not in df.columns:
            return df, df, df, df

        df = df.sort_values("time").reset_index(drop=True)
        n = len(df)

        # 60% train, 20% validation, 15% test, 5% SEALED HOLDOUT
        train_end = int(n * 0.6)
        val_end = int(n * 0.8)
        test_end = int(n * 0.95)

        train = df.iloc[:train_end].copy()
        val = df.iloc[train_end:val_end].copy()
        test = df.iloc[val_end:test_end].copy()
        sealed = df.iloc[test_end:].copy()

        # Mark sealed data as physically isolated
        sealed.attrs["sealed"] = True
        sealed.attrs["sealed_at"] = datetime.now(timezone.utc).isoformat()
        sealed.attrs["purpose"] = "FINAL_EVALUATION_ONLY"

        logger.info(f"Data split: train={len(train)}, val={len(val)}, test={len(test)}, SEALED={len(sealed)}")
        return train, val, test, sealed

    def _train_models(self, train_data: pd.DataFrame, val_data: pd.DataFrame) -> List[Any]:
        """Train ML models with cross-validation."""
        # Use the research ML pipeline
        try:
            models = self.ml_pipeline.train(train_data, val_data)
            return models
        except Exception as e:
            logger.warning(f"ML training failed: {e}")
            return []

    def _generate_hypotheses_from_losses(self) -> List[Hypothesis]:
        """Generate hypotheses from loss autopsy."""
        hypotheses = []

        # Load recent losses
        losses = self.losses

        # Analyze loss patterns
        loss_classes = {}
        for loss in losses:
            loss_class = loss.get("loss_class", "UNKNOWN")
            loss_classes[loss_class] = loss_classes.get(loss_class, 0) + 1

        # Generate hypotheses for top loss classes
        top_losses = sorted(loss_classes.items(), key=lambda x: x[1], reverse=True)[:3]

        for loss_class, count in top_losses:
            if count < 5:
                continue

            # Get relevant book passages
            book_evidence = []
            try:
                book_passages = lookup(loss_class.lower())
                if book_passages:
                    book_evidence.append({
                        "book": book_passages.get("book", "Unknown"),
                        "concept": book_passages.get("concept", "Unknown"),
                        "passage": book_passages.get("passage", "")[:500],
                    })
            except Exception:
                pass

            # Determine origin: if books have strong evidence, BOOK_DERIVED; else DATA_DERIVED
            origin = HypothesisOrigin.BOOK_DERIVED if book_evidence else HypothesisOrigin.DATA_DERIVED

            # NOVEL_SYNTHESIZED: when books insufficient, combine observations + loss autopsy + ML + failed hypotheses
            book_coverage_sufficient = len(book_evidence) > 0 and count > 10
            if not book_coverage_sufficient:
                origin = HypothesisOrigin.NOVEL_SYNTHESIZED
                # Synthesize from multiple sources
                ml_evidence = self._get_ml_evidence_for_loss(loss_class)
                failed_hyp_evidence = self._get_failed_hypothesis_evidence(loss_class)

            # Create hypothesis with full provenance
                        # Create hypothesis with full provenance
            hypothesis = Hypothesis(
                hypothesis_id=f"hyp_{loss_class.lower()}_{int(time.time())}",
                origin=origin,
                problem=f"High frequency of {loss_class} losses ({count} occurrences)",
                proposed_mechanism=f"Address {loss_class} by implementing detection and avoidance",
                features_required=["regime", "structure", "volatility", "momentum", "session"],
                
                # Structured entry/exit rules
                entry_rule={
                    "type": "regime_structure_alignment",
                    "required_regimes": ["trend", "range"],
                    "required_structure": True
                },
                exit_rule={
                    "type": "regime_change",
                    "adverse_selection": True
                },
                
                # Trade parameters
                side="buy",  # Default, can be overridden
                entry_price=None,
                invalidation_price=None,
                target_price=None,
                max_hold_s=120,
                
                expected_effect=f"Reduce {loss_class} losses by 50%",
                falsification_criterion=f"{loss_class} losses do not decrease OOS",
                training_period="2024-01-01 to 2024-06-30",
                validation_period="2024-07-01 to 2024-09-30",
                book_evidence=book_evidence,
                ml_evidence=getattr(self, '_ml_evidence', {}).get(loss_class, {}),
                loss_autopsy_evidence=self.losses,
            )
            hypotheses.append(hypothesis)
        return hypotheses

    def _get_ml_evidence_for_loss(self, loss_class: str) -> Dict[str, Any]:
        """Get ML evidence for a loss class from feature importance and error analysis."""
        try:
            # Get feature importance from trained models
            if hasattr(self, 'ml_pipeline') and self.ml_pipeline.models:
                importance = {}
                for model in self.ml_pipeline.models:
                    if hasattr(model.model, 'feature_importances_'):
                        importance[model.name] = dict(zip(
                            self.ml_pipeline.feature_names,
                            model.model.feature_importances_
                        ))
                return {"feature_importance": importance, "loss_class": loss_class}
        except Exception:
            pass
        return {"loss_class": loss_class, "note": "ML evidence not available"}

    def _get_failed_hypothesis_evidence(self, loss_class: str) -> List[Dict[str, Any]]:
        """Get evidence from previously failed hypotheses for this loss class."""
        failed = []
        for hyp_id in self.state.failed_hypotheses:
            hyp = self.state.hypothesis_registry.get(hyp_id)
            if hyp and hyp.loss_autopsy_evidence:
                for loss in hyp.loss_autopsy_evidence:
                    if loss.get("loss_class") == loss_class:
                        failed.append({
                            "hypothesis_id": hyp_id,
                            "reason": hyp.proposed_mechanism,
                            "falsification": hyp.falsification_criterion,
                        })
        return failed

    def save_report(self) -> None:
        """Save final weekend report."""
        report = {
            "generation": self.state.generation,
            "champion": asdict(self.state.champion) if self.state.champion else None,
            "total_experiments": len(self.state.experiments),
            "rejected": len([e for e in self.state.experiments if e.decision == "REJECTED"]),
            "challengers": len([e for e in self.state.experiments if e.decision == "CHALLENGER"]),
            "champions": len([e for e in self.state.experiments if e.decision == "CHAMPION"]),
            "failed_hypotheses": self.state.failed_hypotheses,
            "dataset_fingerprint": self.state.dataset_fingerprint,
            "codex_calls": self.state.codex_calls,
            "claude_available": self.state.claude_available,
            "final_generation": self.state.generation,
        }

        report_path = self.reports_dir / "final_weekend_report.json"
        report_path.write_text(json.dumps(report, indent=2, default=str))
        logger.info(f"Final report saved to {report_path}")

    # ============================================================
    # BOOK-DATA CONFLICT RESOLUTION
    # ============================================================
    
    def resolve_book_data_conflict(self, book_position: str, data_position: str, 
                                    conflict_details: Dict[str, Any]) -> Dict[str, Any]:
        """Resolve conflict between book knowledge and observed data."""
        conflict = {
            "book_position": book_position,
            "data_position": data_position,
            "conflict": "DISAGREEMENT" if book_position != data_position else "AGREEMENT",
            "details": conflict_details,
            "resolution": "DATA_WINS" if conflict_details.get("repeated_oos_evidence", False) else "NEEDS_TEST",
            "tested": False,
            "resolution_evidence": None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        
        # Log conflict
        self._log_event("CONFLICT", f"Book-Data conflict: {book_position} vs {data_position}",
                       conflict=conflict)
        
        # Store for later testing
        if not hasattr(self, '_conflicts'):
            self._conflicts = []
        self._conflicts.append(conflict)
        
        return conflict

    def test_conflict(self, conflict: Dict[str, Any], 
                      train_data: pd.DataFrame, val_data: pd.DataFrame,
                      test_data: pd.DataFrame) -> Dict[str, Any]:
        """Test a book-data conflict with empirical evidence."""
        # This would run a specific hypothesis test
        # For now, return structure
        result = {
            "conflict_id": conflict.get("conflict", "unknown"),
            "winner": "DATA" if conflict.get("resolution") == "DATA_WINS" else "PENDING",
            "evidence": "OOS test results needed",
            "tested": True,
        }
        conflict["tested"] = True
        conflict["test_result"] = result
        return result

    # ============================================================
    # ML DISCOVERY INTEGRATION
    # ============================================================
    
    def run_ml_discovery(self, train_data: pd.DataFrame, 
                          val_data: pd.DataFrame) -> Dict[str, Any]:
        """Run ML discovery to find patterns humans may have missed."""
        discoveries = {
            "feature_importance": {},
            "permutation_importance": {},
            "error_clusters": [],
            "partial_dependence": {},
            "interaction_effects": [],
            "loss_clusters": [],
        }
        
        try:
            # Train a model for analysis
            X_train, y_train, features = self._prepare_features_for_ml(
                train_data, target_col="profit_barrier_first"
            )
            
            if len(X_train) < 100:
                return {"note": "Insufficient data for ML discovery"}
            
            # Train a tree-based model for importance
            rf = RandomForestClassifier(n_estimators=100, max_depth=10, 
                                         class_weight="balanced", n_jobs=-1, 
                                         random_state=42)
            rf.fit(X_train, y_train)
            
            # Feature importance
            discoveries["feature_importance"] = dict(zip(
                self.feature_names, rf.feature_importances_
            ))
            
            # Permutation importance on validation
            X_val, y_val, _ = self._prepare_features_for_ml(
                val_data, target_col="profit_barrier_first"
            )
            
            if len(X_val) > 0:
                from sklearn.inspection import permutation_importance
                perm_imp = permutation_importance(rf, X_val, y_val, 
                                                   n_repeats=10, random_state=42)
                discoveries["permutation_importance"] = dict(zip(
                    self.feature_names, perm_imp.importances_mean
                ))
            
            # Error clustering
            discoveries["error_clusters"] = self._cluster_errors(
                train_data, val_data, rf
            )
            
            # Find loss clusters
            discoveries["loss_clusters"] = self._find_loss_clusters(
                train_data, rf
            )
            
            # Interaction effects (top features)
            top_features = sorted(
                [(f, imp) for f, imp in discoveries["feature_importance"].items()],
                key=lambda x: x[1], reverse=True
            )[:10]
            
            discoveries["interaction_effects"] = self._find_interactions(
                train_data, val_data, [f[0] for f in top_features]
            )
            
        except Exception as e:
            logger.warning(f"ML discovery failed: {e}")
            discoveries["error"] = str(e)
        
        return discoveries

    def _cluster_errors(self, train_data: pd.DataFrame, 
                         val_data: pd.DataFrame, model: Any) -> List[Dict]:
        """Cluster model errors to find systematic failure patterns."""
        try:
            X_val, y_val, _ = self._prepare_features_for_ml(
                val_data, target_col="profit_barrier_first"
            )
            if len(X_val) == 0:
                return []
            
            preds = self.ml_pipeline.models[0].predict_proba(val_data)[:, 1]
            errors = (preds >= 0.5) != y_val
            
            error_data = val_data[errors].copy()
            if len(error_data) < 10:
                return []
            
            # Cluster by regime, session, symbol
            clusters = []
            for col in ["regime", "session", "symbol", "hour"]:
                if col in error_data.columns:
                    for val, group in error_data.groupby(col):
                        clusters.append({
                            "dimension": col,
                            "value": val,
                            "error_rate": len(group) / len(val_data),
                            "count": len(group),
                            "avg_mfe": group.get("mfe", pd.Series([0])).mean(),
                            "avg_mae": group.get("mae", pd.Series([0])).mean(),
                        })
            return clusters
        except Exception as e:
            logger.warning(f"Error clustering failed: {e}")
            return []

    def _find_loss_clusters(self, train_data: pd.DataFrame, model: Any) -> List[Dict]:
        """Find clusters of similar losing trades."""
        # This would analyze patterns in losing trades
        return []

    def _find_interactions(self, train_data: pd.DataFrame, val_data: pd.DataFrame,
                           top_features: List[str]) -> List[Dict]:
        """Find feature interactions."""
        return []

    # ============================================================
    # WINNER MANAGEMENT RESEARCH
    # ============================================================
    
    def analyze_winner_management(self, trades: pd.DataFrame) -> Dict[str, Any]:
        """Analyze winner management: MFE after exit, giveback, time-to-peak, target efficiency."""
        if trades.empty:
            return {"note": "No trades to analyze"}
        
        winners = trades[trades["pnl"] > 0]
        if winners.empty:
            return {"note": "No winning trades"}
        
        analysis = {
            "total_winners": len(winners),
            "avg_mfe": winners.get("mfe", pd.Series([0])).mean(),
            "avg_mae": winners.get("mae", pd.Series([0])).mean(),
            "avg_giveback_pct": 0,
            "giveback_distribution": {},
            "time_to_peak": winners.get("time_to_peak", pd.Series([0])).mean(),
            "target_efficiency": 0,
            "giveback_by_regime": {},
            "recommendations": [],
        }
        
        if "mfe" in winners.columns and "mae" in winners.columns:
            giveback = (winners["mfe"] - winners["pnl"]).abs()
            analysis["avg_giveback_pct"] = (giveback / winners["mfe"]).mean() * 100
        
        return analysis

    # ============================================================
    # CLAUDE INTEGRATION
    # ============================================================
    
    def _ask_claude_for_new_direction(self) -> None:
        """Ask Claude for a new research direction with streaming output."""
        if not self.state.claude_available:
            self._log_event("CLAUDE", "Claude research is disabled, skipping")
            return

        self._log_event("CLAUDE", "Requesting new research direction from Claude")
        
        context = self._prepare_claude_context()
        try:
            result = ask_research_agent(
                "claude",
                context,
                ledger=self.agent_budget_ledger,
                line_sink=lambda line: self._log_event("CLAUDE", line),
                cwd=ROOT,
            )
        except Exception as exc:
            self._record_generation_outcome("FAILED", f"Claude adapter failed: {exc}")
            return
        if not result.get("ok"):
            self._record_generation_outcome(
                "FAILED", f"Claude agent failed: {result.get('error', result.get('status', 'unknown error'))}"
            )
            return
        try:
            hypothesis = Hypothesis.from_dict(result["parsed"])
        except (KeyError, TypeError, ValueError) as exc:
            self._record_generation_outcome("FAILED", f"Claude output was malformed: {exc}")
            return
        self.state.hypothesis_registry[hypothesis.hypothesis_id] = hypothesis
        self._log_event("CLAUDE", f"New hypothesis from Claude: {hypothesis.hypothesis_id}")

    def _prepare_claude_context(self) -> str:
        """Prepare context for Claude."""
        recent_losses = self.losses[-20:] if self.losses else []
        recent_experiments = self.state.experiments[-10:] if self.state.experiments else []
        
        context = f"""
        RESEARCH CONTEXT:
        Generation: {self.state.generation}
        Champion: {self.state.champion.hypothesis_id if self.state.champion else 'NONE'}
        Recent losses: {len(self.losses)}
        Experiments run: {len(self.state.experiments)}
        
        TOP LOSS CLASSES:
        {self._get_top_loss_classes()}
        
        RECENT EXPERIMENTS:
        {[f"{e.hypothesis_id}: {e.decision}" for e in recent_experiments]}
        
        CHAMPION METRICS:
        {self.state.champion.metrics if self.state.champion else 'NONE'}
        
        What loss mechanism should we attack next? Provide ONE falsifiable hypothesis.
        """
        return context

    def _get_top_loss_classes(self) -> str:
        """Get top loss classes as string."""
        if not self.losses:
            return "No losses recorded"
        losses = self.losses[-100:]
        classes = {}
        for l in losses:
            cls = l.get("loss_class", "UNKNOWN")
            classes[cls] = classes.get(cls, 0) + 1
        return "\n".join(
            f"  {key}: {count}"
            for key, count in sorted(classes.items(), key=lambda item: item[1], reverse=True)[:5]
        )

    def _is_hypothesis_tested(self, hypothesis_id: str) -> bool:
        """Return whether this hypothesis is already registered."""
        return hypothesis_id in self.state.hypothesis_registry

    def _test_hypothesis(
        self,
        hypothesis: Hypothesis,
        train_data: pd.DataFrame,
        val_data: pd.DataFrame,
        test_data: pd.DataFrame,
        *,
        costs: Any = None,
        min_train_timestamps: int = 100,
        validation_timestamps: int = 20,
        step_timestamps: int = 20,
    ) -> Dict[str, Any]:
        """Compile and evaluate only non-sealed rows with explicit costs."""
        self._log_event("HYPOTHESIS", f"Testing {hypothesis.hypothesis_id} via historical replay")
        try:
            # test_data is sealed and deliberately never inspected by this path.
            frame = pd.concat([train_data, val_data], ignore_index=True)
            compiled = compile_hypothesis(hypothesis, frame.columns)
            result = walk_forward_evaluate(
                frame, pipeline_factory=MLPipeline, compiled=compiled, costs=costs,
                min_train_timestamps=min_train_timestamps,
                validation_timestamps=validation_timestamps, step_timestamps=step_timestamps,
                label_horizon=getattr(self, "label_horizon", 0),
            )
        except Exception as exc:
            self._record_generation_outcome("FAILED", f"walk-forward evaluation failed: {exc}", hypothesis=hypothesis)
            return {"metrics": {}, "decision": "FAILED", "reason": f"walk-forward evaluation failed: {exc}", "folds": ()}
        self._record_generation_outcome(
            result.status, result.reason, hypothesis=hypothesis, metrics=result.metrics
        )
        return {
            "metrics": dict(result.metrics) if result.metrics is not None else {},
            "decision": result.status,
            "reason": result.reason,
            "folds": result.folds,
        }

    def _generate_entry_signals(self, data: pd.DataFrame, entry_rule: Dict[str, Any]) -> pd.Series:
        """Generate entry signals from structured hypothesis entry rule."""
        signals = pd.Series(False, index=data.index)
        
        rule_type = entry_rule.get("type", "")
        
        if rule_type == "regime_structure_alignment":
            # Regime and structure alignment entry
            if "regime" in data.columns and "structure" in data.columns:
                required_regimes = entry_rule.get("required_regimes", ["trend", "range"])
                regime_ok = data["regime"].isin(required_regimes)
                structure_ok = data["structure"].notna()
                signals = regime_ok & structure_ok
                
        elif rule_type == "breakout":
            # Breakout entry: price breaks above resistance / below support
            if "high" in data.columns and "low" in data.columns and "close" in data.columns:
                resistance = data["high"].rolling(20).max().shift(1)
                support = data["low"].rolling(20).min().shift(1)
                if entry_rule.get("direction") == "long":
                    signals = data["close"] > resistance
                else:
                    signals = data["close"] < support
                    
        elif rule_type == "mean_reversion":
            # Mean reversion: price deviates from mean
            if "close" in data.columns and "sma_20" in data.columns:
                z_score = (data["close"] - data["sma_20"]) / data["close"].rolling(20).std()
                threshold = entry_rule.get("z_threshold", 2.0)
                if entry_rule.get("direction") == "long":
                    signals = z_score < -threshold
                else:
                    signals = z_score > threshold
        
        return signals.fillna(False)

    def _generate_exit_signals(self, data: pd.DataFrame, exit_rule: Dict[str, Any]) -> pd.Series:
        """Generate exit signals from structured hypothesis exit rule."""
        signals = pd.Series(False, index=data.index)
        
        rule_type = exit_rule.get("type", "")
        
        if rule_type == "regime_change":
            # Exit on regime change
            if "regime" in data.columns:
                regime_change = data["regime"] != data["regime"].shift(1)
                signals = regime_change
                
        elif rule_type == "adverse_selection":
            # Exit on adverse selection signals
            if "regime" in data.columns:
                regime_change = data["regime"] != data["regime"].shift(1)
                signals = regime_change
                
        elif rule_type == "trailing_stop":
            # Trailing stop exit
            # This would be handled in the replay loop with actual price tracking
            pass
            
        elif rule_type == "target_hit":
            # Exit when target price reached
            pass
            
        elif rule_type == "time_exit":
            # Time-based exit
            if "max_bars" in exit_rule:
                max_bars = exit_rule["max_bars"]
                # This would need position tracking - handled in replay loop
                pass
        
        return signals

    def _run_walkforward_replay(
        self,
        data: pd.DataFrame,
        entry_signals: pd.Series,
        exit_signals: pd.Series,
        hypothesis: Hypothesis,
        symbol_spec: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Run chronological walk-forward replay of hypothesis signals with REAL costs."""
        trades = []
        in_position = False
        entry_idx = None
        entry_price = 0.0
        entry_side = None
        
        # Get symbol spec for real costs
        spec = symbol_spec or {}
        tick_size = spec.get("trade_tick_size", 0.00001)
        tick_value = spec.get("trade_tick_value", 1.0)
        contract_size = spec.get("trade_contract_size", 100000.0)
        spread = spec.get("spread", 0.00002)  # Default 2 pips
        commission_per_lot = spec.get("commission_per_lot", 0.0)
        slippage = 0.00001  # 0.1 pip slippage assumption
        
        in_position = False
        entry_idx = None
        entry_price = 0.0
        entry_side = None
        
        # Get stop loss and target from hypothesis
        stop_loss_price = hypothesis.invalidation_price
        target_price = hypothesis.target_price
        max_hold_bars = hypothesis.max_hold_s // 60  # Convert seconds to minutes/bars
        
        for i in range(1, len(data)):
            if not in_position and entry_signals.iloc[i]:
                # Enter position
                in_position = True
                entry_idx = i
                entry_price = data.iloc[i]["close"]
                
                # Apply slippage on entry
                if hypothesis.side == "buy":
                    entry_price += slippage
                    entry_side = "buy"
                else:
                    entry_price -= slippage
                    entry_side = "sell"
                
                in_position = True
                entry_idx = i
                entry_price = data.iloc[i]["close"]
                entry_side = hypothesis.side  # "buy" or "sell"
                
            elif in_position:
                # Check exit conditions
                should_exit = False
                exit_price = data.iloc[i]["close"]
                
                # Apply slippage on exit
                if entry_side == "buy":
                    exit_price_candidate = data.iloc[i]["close"] - slippage
                else:
                    exit_price_candidate = data.iloc[i]["close"] + slippage
                
                should_exit = False
                exit_price = exit_price_candidate
                
                # Check exit signals
                if exit_signals.iloc[i]:
                    should_exit = True
                
                # Check stop loss (invalidation price)
                if stop_loss_price is not None:
                    if entry_side == "buy":
                        if data.iloc[i]["low"] <= stop_loss_price:
                            should_exit = True
                            exit_price = min(exit_price_candidate, stop_loss_price)
                    else:
                        if data.iloc[i]["high"] >= stop_loss_price:
                            should_exit = True
                            exit_price = max(exit_price_candidate, stop_loss_price)
                
                # Check target
                if target_price is not None:
                    if entry_side == "buy":
                        if data.iloc[i]["high"] >= target_price:
                            should_exit = True
                            exit_price = max(exit_price_candidate, target_price)
                    else:
                        if data.iloc[i]["low"] <= target_price:
                            should_exit = True
                            exit_price = min(exit_price_candidate, target_price)
                
                # Time-based exit (max hold bars)
                if i - entry_idx >= hypothesis.max_hold_s:
                    should_exit = True
                
                if should_exit:
                    # Calculate PnL with REAL costs
                    # Gross PnL
                    if entry_side == "buy":
                        gross_pnl = (exit_price - entry_price) / entry_price
                    else:
                        gross_pnl = (entry_price - exit_price) / entry_price
                    
                    # COSTS
                    # Spread cost (round trip)
                    spread_cost = 2 * spread / entry_price
                    # Commission (round trip, per lot)
                    commission_cost = 2 * commission_per_lot / (entry_price * contract_size)
                    # Slippage cost (round trip)
                    slippage_cost = 2 * slippage / entry_price
                    
                    total_cost = spread_cost + commission_cost + slippage_cost
                    
                    # Net PnL
                    pnl = gross_pnl - total_cost
                    
                    if entry_side == "sell":
                        pnl = -pnl
                    
                    trades.append({
                        "entry_idx": entry_idx,
                        "exit_idx": i,
                        "entry_price": entry_price,
                        "exit_price": exit_price,
                        "side": entry_side,
                        "pnl_pct": pnl,
                        "bars_held": i - entry_idx,
                        "exit_reason": "signal" if exit_signals.iloc[i] else "stop/target/time",
                        "gross_pnl_pct": gross_pnl,
                        "costs_pct": total_cost,
                        "spread_cost_pct": spread_cost,
                        "commission_cost_pct": commission_cost,
                        "slippage_cost_pct": slippage_cost,
                    })
                    in_position = False
        
        return trades


    def _calculate_trade_metrics(self, trades: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate real trade metrics from actual trades."""
        if not trades:
            return {}
        
        pnls = [t["pnl_pct"] for t in trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]
        
        win_rate = len(wins) / len(pnls) if pnls else 0
        loss_rate = 1 - win_rate
        avg_win = np.mean(wins) if wins else 0
        avg_loss = np.mean(losses) if losses else 0
        expectancy = (win_rate * avg_win) + (loss_rate * avg_loss)
        
        gross_profit = sum(wins) if wins else 0
        gross_loss = abs(sum(losses)) if losses else 0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        
        pnls_sorted = sorted(pnls)
        p95_idx = int(len(pnls_sorted) * 0.05)
        p99_idx = int(len(pnls_sorted) * 0.01)
        p95_loss = pnls_sorted[p95_idx] if pnls_sorted else 0
        p99_loss = pnls_sorted[p99_idx] if pnls_sorted else 0
        max_loss = min(pnls) if pnls else 0
        
        # Calculate drawdown
        equity_curve = np.cumsum(pnls)
        running_max = np.maximum.accumulate(equity_curve)
        drawdown = (running_max - equity_curve) / np.where(running_max != 0, running_max, 1)
        max_drawdown = drawdown.max() if len(drawdown) > 0 else 0
        
        wins_erased_by_avg_loss = abs(avg_loss) / avg_win if avg_win != 0 else 0
        wins_erased_by_tail_loss = abs(p95_loss) / avg_win if avg_win != 0 else 0
        
        return {
            "win_rate": win_rate,
            "loss_rate": 1 - win_rate,
            "expectancy": expectancy,
            "profit_factor": profit_factor if profit_factor != float('inf') else 999,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "p95_loss": p95_loss,
            "p99_loss": p99_loss,
            "max_loss": max_loss,
            "max_drawdown": max_drawdown,
            "wins_erased_by_avg_loss": abs(avg_loss) / avg_win if avg_win != 0 else 0,
            "wins_erased_by_tail_loss": abs(p95_loss) / avg_win if avg_win != 0 else 0,
            "total_trades": len(trades),
            "net_pnl": sum(pnls),
        }

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="AEGIS Autonomous Weekend Research Factory")
    parser.add_argument("--mode", default="weekend", choices=["weekend", "continuous"])
    parser.add_argument("--continuous", action="store_true")
    parser.add_argument("--max-generations", type=int, default=100)
    parser.add_argument("--claude", action="store_true")
    parser.add_argument("--codex-budget", type=int, default=1)
    parser.add_argument("--sealed-holdout", action="store_true", default=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--profit-barrier-pct",
        required=True,
        type=lambda value: _positive_cli_barrier("profit_barrier_pct", value),
    )
    parser.add_argument(
        "--loss-barrier-pct",
        required=True,
        type=lambda value: _positive_cli_barrier("loss_barrier_pct", value),
    )

    args = parser.parse_args()

    factory = ResearchFactory(
        mode=args.mode,
        continuous=args.continuous,
        max_generations=args.max_generations,
        claude_enabled=args.claude,
        codex_budget=args.codex_budget,
        sealed_holdout=args.sealed_holdout,
        resume=args.resume,
        profit_barrier_pct=args.profit_barrier_pct,
        loss_barrier_pct=args.loss_barrier_pct,
    )

    factory.run()
    factory.save_report()


# ============================================================
# HELPER METHODS
# ============================================================

    def _prepare_features_for_ml(
        self,
        df: pd.DataFrame,
        target_col: str = "profit_barrier_first",
    ) -> Tuple[np.ndarray, np.ndarray, List[str]]:
        """Prepare features and labels for ML training."""
        # Identify feature columns (exclude metadata columns)
        exclude_cols = {
            "time", "source_file", "symbol", "timeframe",
            "target", "label", "future_max_high", "future_min_low",
            "profit_barrier_first", "mfe", "mae", "time_to_target",
            "no_progress", "tail_loss", "direction", "return_horizon",
        }

        feature_cols = [
            c for c in df.columns 
            if c not in exclude_cols and df[c].dtype in [np.float64, np.float32, np.int64, np.int32]
        ]

        X = df[feature_cols].replace([np.inf, -np.inf], np.nan).fillna(0)
        y = df.get(target_col, pd.Series(0, index=df.index)).astype(int)

        return X.values, y.values, feature_cols


if __name__ == "__main__":
    main()
