"""Champion/Challenger system with promotion gates."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class Champion:
    """Current champion candidate."""
    hypothesis_id: str
    metrics: Dict[str, Any]
    model_hash: str
    dataset_fingerprint: str
    promoted_at: str
    promotion_generation: int


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
            "min_payoff_ratio": 0.5,
            "min_win_rate": 0.55,
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
            ("payoff_ratio", challenger_metrics.get("payoff_ratio", 0) >= gates["min_payoff_ratio"]),
            ("win_rate", challenger_metrics.get("win_rate", 0) >= gates["min_win_rate"]),
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

        # Handle both full dict and just metrics dict
        if "metrics" in challenger:
            challenger_metrics = challenger["metrics"]
        else:
            challenger_metrics = challenger

        if "metrics" in champion:
            champion_metrics = champion["metrics"]
        else:
            champion_metrics = champion

        # Challenger must beat champion on key metrics
        return (
            challenger_metrics.get("expectancy", 0) > champion_metrics.get("expectancy", 0) * 1.1 and
            challenger_metrics.get("profit_factor", 0) > champion_metrics.get("profit_factor", 0) and
            challenger_metrics.get("max_drawdown", 1) <= champion_metrics.get("max_drawdown", 1) * 1.1 and
            challenger_metrics.get("avg_loss", -999) >= champion_metrics.get("avg_loss", -999) * 0.9
        )

    def promote(self) -> None:
        """Promote challenger to champion."""
        if self.challenger:
            self.champion = self.challenger
            self.challenger = None
            self.history.append({
                "action": "PROMOTE",
                "from": None,
                "to": self.champion["hypothesis_id"] if self.champion else None,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            logger.info(f"NEW CHAMPION: {self.champion['hypothesis_id']}")

    def evaluate_and_promote(self, challenger: Dict[str, Any]) -> bool:
        """Evaluate and potentially promote challenger."""
        # First check gates
        passes, reason = self.evaluate_challenger(challenger)
        if not passes:
            logger.info(f"Challenger {challenger.get('hypothesis_id')} failed gates: {reason}")
            return False

        # Then check if beats champion
        if self.promote_if_better(challenger, self.champion):
            self.promote()
            return True

        return False

    def get_status(self) -> Dict[str, Any]:
        """Get current status."""
        return {
            "champion": self.champion,
            "challenger": self.challenger,
            "history": self.history,
        }