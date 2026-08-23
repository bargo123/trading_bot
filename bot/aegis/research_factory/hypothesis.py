"""Canonical structured hypothesis schema and registry."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

class HypothesisOrigin(Enum):
    DIRECT_BOOK = "DIRECT_BOOK_HYPOTHESIS"
    BOOK_DERIVED = "BOOK_DERIVED_HYPOTHESIS"
    DATA_DERIVED = "DATA_DERIVED_HYPOTHESIS"
    ML_DISCOVERED = "ML_DISCOVERED_HYPOTHESIS"
    NOVEL_SYNTHESIZED = "NOVEL_SYNTHESIZED_HYPOTHESIS"


class HypothesisStatus(Enum):
    """Status of a hypothesis."""
    PROPOSED = "PROPOSED"
    TESTING = "TESTING"
    REJECTED = "REJECTED"
    CHALLENGER = "CHALLENGER"
    CHAMPION = "CHAMPION"
    ARCHIVED = "ARCHIVED"


@dataclass
class Hypothesis:
    """A falsifiable hypothesis with explicit evidence and trade geometry."""

    hypothesis_id: str
    origin: HypothesisOrigin
    problem: str
    proposed_mechanism: str
    features_required: List[str]
    entry_rule: Dict[str, Any]
    exit_rule: Dict[str, Any]
    side: str
    entry_price: Optional[float]
    invalidation_price: Optional[float]
    target_price: Optional[float]
    max_hold_s: Optional[int]
    expected_effect: str
    falsification_criterion: str
    training_period: str
    validation_period: str
    book_evidence: List[Dict[str, Any]]
    ml_evidence: Dict[str, Any]
    loss_autopsy_evidence: List[Dict[str, Any]]
    walk_forward_result: Optional[Dict[str, Any]] = None
    cost_sensitivity: Optional[float] = None
    decision: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    status: HypothesisStatus = HypothesisStatus.PROPOSED

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["origin"] = self.origin.value
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Hypothesis":
        data = data.copy()
        data["origin"] = HypothesisOrigin(data["origin"])
        data["status"] = HypothesisStatus(data["status"])
        return cls(**data)


class HypothesisRegistry:
    """Registry of all hypotheses with deduplication."""

    def __init__(self):
        self.hypotheses: Dict[str, Hypothesis] = {}

    def register(self, hypothesis: Hypothesis) -> bool:
        """Register a new hypothesis. Returns True if new."""
        if hypothesis.hypothesis_id in self.hypotheses:
            return False
        self.hypotheses[hypothesis.hypothesis_id] = hypothesis
        return True

    def is_tested(self, hypothesis_id: str) -> bool:
        """Check if hypothesis has been tested."""
        return hypothesis_id in self.hypotheses

    def get(self, hypothesis_id: str) -> Optional[Hypothesis]:
        return self.hypotheses.get(hypothesis_id)

    def get_all(self) -> List[Hypothesis]:
        return list(self.hypotheses.values())

    def get_by_status(self, status: str) -> List[Hypothesis]:
        return [h for h in self.hypotheses.values() if h.status.value == status]

    def update_status(self, hypothesis_id: str, status: str) -> bool:
        if hypothesis_id in self.hypotheses:
            self.hypotheses[hypothesis_id].status = HypothesisStatus(status)
            return True
        return False

    def save(self, path: Path) -> None:
        data = {k: v.to_dict() for k, v in self.hypotheses.items()}
        path.write_text(json.dumps(data, indent=2))

    @classmethod
    def load(cls, path: Path) -> "HypothesisRegistry":
        if not path.exists():
            return cls()
        registry = cls()
        data = json.loads(path.read_text())
        registry.hypotheses = {k: Hypothesis.from_dict(v) for k, v in data.items()}
        return registry
