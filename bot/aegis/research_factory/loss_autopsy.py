"""Loss autopsy and hypothesis generation."""
from __future__ import annotations

import json
import hashlib
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import numpy as np


def load_losses() -> List[Dict[str, Any]]:
    """Load losses from the loss database."""
    from aegis.intel.lossdb import split_and_write
    from aegis.intel.paths import INTEL_DIR
    import pandas as pd

    losses_path = INTEL_DIR / "losses.jsonl"
    if not losses_path.exists():
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


@dataclass
class LossAutopsy:
    """Complete loss autopsy record."""
    trade_id: str
    timestamp: str
    symbol: str
    side: str
    entry_price: float
    exit_price: float
    stop_loss: float
    target_price: Optional[float]
    pnl: float
    mfe: float
    mae: float
    hold_time_seconds: float
    loss_class: LossClass
    confidence: float  # 0-1 confidence in classification
    features_at_entry: Dict[str, float]
    features_at_exit: Dict[str, float]
    regime_at_entry: str
    regime_at_exit: str
    session: str
    spread_at_entry: float
    volatility_at_entry: float
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        d = asdict(self)
        d["loss_class"] = self.loss_class.value
        return d


class LossAutopsyEngine:
    """Classify losses and generate hypotheses."""

    def __init__(self):
        self.classification_rules = self._load_classification_rules()

    def _load_classification_rules(self) -> Dict[str, Any]:
        """Load classification rules."""
        return {
            "BAD_ENTRY": {
                "condition": lambda r: r["mae"] > 2 * r["mfe"] and r["hold_time"] < 60,
                "description": "Price immediately moved against position",
            },
            "WRONG_SIDE": {
                "condition": lambda r: r["side"] == "buy" and r["pnl"] < 0 and r["mae"] > abs(r["mfe"] * 3),
                "description": "Trend was clearly against position",
            },
            "WRONG_REGIME": {
                "condition": lambda r: r["regime_change"] and r["pnl"] < 0,
                "description": "Regime changed against position",
            },
            "SPREAD_COST": {
                "condition": lambda r: abs(r["pnl"]) < r["spread"] * 2 and r["pnl"] < 0,
                "description": "Loss primarily from spread cost",
            },
            "ADVERSE_SELECTION": {
                "condition": lambda r: r["mae"] > r["mfe"] * 3 and r["hold_time"] > 60,
                "description": "Price moved against then reversed (adverse selection)",
            },
            "LATE_ENTRY": {
                "condition": lambda r: r["entry_distance_from_extreme"] > 0.8 and r["pnl"] < 0,
                "description": "Entered late in move",
            },
            "FALSE_BREAKOUT": {
                "condition": lambda r: r["breakout_failed"] and r["hold_time"] < 300,
                "description": "Breakout failed quickly",
            },
            "NO_PROGRESS": {
                "condition": lambda r: r["mfe"] < 1e-6 and r["hold_time"] > 300,
                "description": "Trade never moved in favor",
            },
            "MOMENTUM_FAILURE": {
                "condition": lambda r: r["momentum_at_entry"] > 0.5 and r["pnl"] < 0,
                "description": "Momentum reversed",
            },
            "WINNER_GIVEBACK": {
                "condition": lambda r: r["mfe"] > 2 * abs(r["pnl"]) and r["pnl"] > 0,
                "description": "Winner gave back most gains",
            },
            "STOP_TOO_WIDE": {
                "condition": lambda r: abs(r["entry_price"] - r["stop_loss"]) > r["atr"] * 3,
                "description": "Stop loss too wide for volatility",
            },
            "TIME_EXIT_TOO_LATE": {
                "condition": lambda r: r["hold_time"] > r["max_hold"] and r["pnl"] < 0,
                "description": "Held past optimal exit time",
            },
            "SELF_HEDGE": {
                "condition": lambda r: r["opposite_position_open"] and r["pnl"] < 0,
                "description": "Hedged own position",
            },
            "TAIL_EVENT": {
                "condition": lambda r: abs(r["pnl"]) > r["atr"] * 5,
                "description": "Extreme market move",
            },
            "INSUFFICIENT_INFORMATION": {
                "condition": lambda r: r["feature_completeness"] < 0.5,
                "description": "Not enough information at entry",
            },
            "UNAVOIDABLE": {
                "condition": lambda r: True,  # Default catch-all
                "description": "Loss appears unavoidable with available information",
            },
        }

    def classify_loss(self, trade_record: Dict[str, Any]) -> Tuple[LossClass, float]:
        """Classify a loss with confidence score."""
        # Evaluate all rules
        scores = {}
        for loss_class, rule in self.classification_rules.items():
            try:
                if rule["condition"](trade_record):
                    # Score based on how specific the rule is
                    scores[LossClass[loss_class]] = 1.0
                else:
                    scores[LossClass[loss_class]] = 0.0
            except Exception:
                scores[LossClass[loss_class]] = 0.0

        # Find highest scoring class
        best_class = max(scores, key=scores.get)
        confidence = scores[best_class]

        # If no specific rule matched, default to UNAVOIDABLE
        if confidence == 0.0:
            return LossClass.UNAVOIDABLE, 1.0

        return best_class, confidence

    def perform_autopsy(self, trade_record: Dict[str, Any]) -> Dict[str, Any]:
        """Perform complete loss autopsy."""
        loss_class, confidence = self.classify_loss(trade_record)

        autopsy = {
            "trade_id": trade_record.get("trade_id", "unknown"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "loss_class": loss_class.value,
            "confidence": confidence,
            "rule_description": self.classification_rules.get(loss_class.value, {}).get("description", ""),
            "trade_details": {
                "symbol": trade_record.get("symbol"),
                "side": trade_record.get("side"),
                "entry_price": trade_record.get("entry_price"),
                "exit_price": trade_record.get("exit_price"),
                "pnl": trade_record.get("pnl"),
                "mfe": trade_record.get("mfe"),
                "mae": trade_record.get("mae"),
                "hold_time": trade_record.get("hold_time"),
            },
            "features_at_entry": {k: v for k, v in trade_record.items() if k.startswith("feat_")},
        }

        return autopsy


class HypothesisGenerator:
    """Generate hypotheses from loss patterns and ML insights."""

    def __init__(self, loss_autopsy: LossAutopsyEngine):
        self.loss_autopsy = loss_autopsy

    def generate_from_losses(
        self,
        losses: List[Dict[str, Any]],
        min_occurrences: int = 5,
    ) -> List[Dict[str, Any]]:
        """Generate hypotheses from loss patterns."""
        # Classify all losses
        classified = []
        for loss in losses:
            autopsy = self.loss_autopsy.perform_autopsy(loss)
            classified.append(autopsy)

        # Count by loss class
        class_counts = {}
        for a in classified:
            cls = a["loss_class"]
            class_counts[cls] = class_counts.get(cls, 0) + 1

        # Generate hypotheses for frequent loss classes
        hypotheses = []
        for loss_class, count in class_counts.items():
            if count < min_occurrences:
                continue

            # Get book evidence
            book_evidence = self._get_book_evidence(loss_class)

            # Create hypothesis
            hypothesis = {
                "hypothesis_id": f"hyp_{loss_class.lower()}_{int(time.time())}",
                "origin": "DATA_DERIVED" if count > 10 else "BOOK_DERIVED",
                "problem": f"High frequency of {loss_class} losses ({count} occurrences)",
                "proposed_mechanism": f"Address {loss_class} by implementing detection and avoidance",
                "features_required": ["regime", "structure", "volatility", "momentum", "session"],
                "entry_rule": f"Avoid entries when {loss_class.lower()} risk is elevated",
                "exit_rule": f"Exit on {loss_class.lower()} signal",
                "expected_effect": f"Reduce {loss_class} losses by 50%",
                "falsification_criterion": f"{loss_class} losses do not decrease OOS",
                "training_period": "2024-01-01 to 2024-06-30",
                "validation_period": "2024-07-01 to 2024-09-30",
                "book_evidence": book_evidence,
                "loss_class": loss_class,
                "occurrences": count,
            }
            hypotheses.append(hypothesis)

        return hypotheses

    def _get_book_evidence(self, loss_class: str) -> List[Dict[str, Any]]:
        """Get relevant book passages for loss class."""
        try:
            from aegis.intel.books import lookup
            passages = lookup(loss_class.lower())
            if passages:
                return [{
                    "book": passages.get("book", "Unknown"),
                    "concept": passages.get("concept", "Unknown"),
                    "passage": passages.get("passage", "")[:500],
                }]
        except Exception:
            pass
        return []

    def generate_from_ml_insights(
        self,
        feature_importance: Dict[str, float],
        model_errors: pd.DataFrame,
    ) -> List[Dict[str, Any]]:
        """Generate hypotheses from ML model insights."""
        hypotheses = []

        # Find features that predict losses
        error_features = model_errors.corrwith(model_errors["is_loss"]).abs().sort_values(ascending=False)

        for feature, corr in error_features.head(5).items():
            if corr > 0.3:
                hypothesis = {
                    "hypothesis_id": f"hyp_ml_{feature}_{int(time.time())}",
                    "origin": "ML_DISCOVERED",
                    "problem": f"Feature {feature} strongly correlates with losses (corr={corr:.3f})",
                    "proposed_mechanism": f"Use {feature} as a filter to avoid high-loss regimes",
                    "features_required": [feature],
                    "entry_rule": f"Only enter when {feature} is in favorable range",
                    "exit_rule": f"Exit if {feature} moves against position",
                    "expected_effect": f"Reduce losses associated with {feature}",
                    "falsification_criterion": f"{feature} correlation with losses disappears OOS",
                    "training_period": "2024-01-01 to 2024-06-30",
                    "validation_period": "2024-07-01 to 2024-09-30",
                    "ml_evidence": {
                        "feature": feature,
                        "correlation": corr,
                        "feature_importance": feature_importance.get(feature, 0),
                    },
                }
                hypotheses.append(hypothesis)

        return hypotheses


class HypothesisRegistry:
    """Registry of all hypotheses with deduplication."""

    def __init__(self):
        self.hypotheses: Dict[str, Dict[str, Any]] = {}

    def register(self, hypothesis: Dict[str, Any]) -> bool:
        """Register a new hypothesis. Returns True if new."""
        hyp_id = hypothesis["hypothesis_id"]
        if hyp_id in self.hypotheses:
            return False
        self.hypotheses[hyp_id] = hypothesis
        return True

    def is_tested(self, hypothesis_id: str) -> bool:
        """Check if hypothesis has been tested."""
        return hypothesis_id in self.hypotheses

    def get(self, hypothesis_id: str) -> Optional[Dict[str, Any]]:
        return self.hypotheses.get(hypothesis_id)

    def get_all(self) -> List[Dict[str, Any]]:
        return list(self.hypotheses.values())

    def save(self, path: Path) -> None:
        path.write_text(json.dumps({k: v for k, v in self.hypotheses.items()}, indent=2))

    @classmethod
    def load(cls, path: Path) -> "HypothesisRegistry":
        if not path.exists():
            return cls()
        registry = cls()
        registry.hypotheses = json.loads(path.read_text())
        return registry


class ChampionChallenger:
    """Champion/Challenger system with promotion gates."""

    def __init__(self, promotion_gates: Optional[Dict[str, Any]] = None):
        self.champion: Optional[Dict[str, Any]] = None
        self.challenger: Optional[Dict[str, Any]] = None
        self.history: List[Dict[str, Any]] = []

        self.promotion_gates = promotion_gates or {
            "min_expectancy": 0.1,
            "min_profit_factor": 1.5,
            "max_avg_loss": -1.0,
            "max_p95_loss": -3.0,
            "max_drawdown": 0.20,
            "min_trades": 50,
            "min_stability_windows": 3,
            "max_train_test_gap": 0.05,
        }

    def evaluate_challenger(self, challenger_metrics: Dict[str, Any]) -> Tuple[bool, str]:
        """Evaluate if challenger meets promotion gates."""
        gates = self.promotion_gates

        checks = [
            ("expectancy", challenger_metrics.get("expectancy", 0) >= gates["min_expectancy"]),
            ("profit_factor", challenger_metrics.get("profit_factor", 0) >= gates["min_profit_factor"]),
            ("avg_loss", challenger_metrics.get("avg_loss", -999) >= gates["max_avg_loss"]),
            ("p95_loss", challenger_metrics.get("p95_loss", -999) >= gates["max_p95_loss"]),
            ("max_drawdown", challenger_metrics.get("max_drawdown", 1) <= gates["max_drawdown"]),
            ("min_trades", challenger_metrics.get("total_trades", 0) >= gates["min_trades"]),
        ]

        failed = [name for name, passed in checks if not passed]
        if failed:
            return False, f"Failed gates: {', '.join(failed)}"

        return True, "All gates passed"

    def promote_if_better(self, challenger: Dict[str, Any], champion: Optional[Dict[str, Any]]) -> bool:
        """Promote challenger if it beats champion."""
        if not self.challenger:
            return False

        if not self.champion:
            # No champion yet
            return True

        challenger_metrics = self.challenger["metrics"]
        champion_metrics = self.champion["metrics"]

        # Challenger must beat champion on key metrics
        return (
            challenger["expectancy"] > champion["expectancy"] * 1.1 and
            challenger["profit_factor"] > champion["profit_factor"] and
            challenger["max_drawdown"] <= champion["max_drawdown"] * 1.1 and
            challenger["avg_loss"] >= champion["avg_loss"] * 0.9
        )

    def promote(self, champion: Dict[str, Any]) -> None:
        """Promote challenger to champion."""
        self.champion = self.challenger
        self.challenger = None
        self.history.append({
            "action": "PROMOTE",
            "from": self.champion["hypothesis_id"] if self.champion else None,
            "to": self.champion["hypothesis_id"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })


def analyze_loss_patterns(trades: pd.DataFrame) -> Dict[str, Any]:
    """Analyze loss patterns in trade data."""
    if trades.empty:
        return {}

    losses = trades[trades["pnl"] < 0]

    if losses.empty:
        return {"message": "No losses found"}

    analysis = {
        "total_losses": len(losses),
        "loss_rate": len(losses) / len(trades),
        "avg_loss": losses["pnl"].mean(),
        "median_loss": losses["pnl"].median(),
        "max_loss": losses["pnl"].min(),
        "p95_loss": losses["pnl"].quantile(0.05),
        "p99_loss": losses["pnl"].quantile(0.01),
        "wins_erased_by_avg_loss": abs(losses["pnl"].mean()) / trades[trades["pnl"] > 0]["pnl"].mean() if len(trades[trades["pnl"] > 0]) > 0 else 0,
        "loss_by_regime": losses.groupby("regime")["pnl"].mean().to_dict() if "regime" in losses.columns else {},
        "loss_by_session": losses.groupby("session")["pnl"].mean().to_dict() if "session" in losses.columns else {},
        "loss_by_symbol": losses.groupby("symbol")["pnl"].mean().to_dict() if "symbol" in losses.columns else {},
        "loss_by_side": losses.groupby("side")["pnl"].mean().to_dict() if "side" in losses.columns else {},
        "mfe_mae_ratio": (losses["mfe"] / losses["mae"].abs()).mean() if "mfe" in losses.columns and "mae" in losses.columns else 0,
        "hold_time_avg": losses["hold_time"].mean() if "hold_time" in losses.columns else 0,
    }

    return analysis