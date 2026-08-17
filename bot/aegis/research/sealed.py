"""Freeze a challenger before sealed holdout. One frozen id, one holdout score."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from aegis.research.fingerprint import config_fingerprint


class SealedHoldoutError(ValueError):
    """Second peek at the same frozen candidate and holdout fingerprint."""


@dataclass(frozen=True)
class FrozenCandidate:
    frozen_hash: str
    frozen_at: str
    code_hash: str
    config_hash: str
    artifact_hash: str
    strategy_id: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def freeze_candidate(
    *,
    strategy_id: str,
    code_hash: str,
    config: Mapping[str, Any],
    artifact_hash: str,
) -> FrozenCandidate:
    frozen_at = datetime.now(timezone.utc).isoformat()
    config_hash = config_fingerprint(dict(config))
    frozen_hash = config_fingerprint(
        {
            "strategy_id": strategy_id,
            "code_hash": code_hash,
            "config_hash": config_hash,
            "artifact_hash": artifact_hash,
            "frozen_at": frozen_at,
        }
    )
    return FrozenCandidate(
        frozen_hash=frozen_hash,
        frozen_at=frozen_at,
        code_hash=str(code_hash),
        config_hash=config_hash,
        artifact_hash=str(artifact_hash),
        strategy_id=str(strategy_id),
    )


class SealedHoldoutStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("", encoding="utf-8")

    def _rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        text = self.path.read_text(encoding="utf-8")
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
        return rows

    def evaluate_once(
        self,
        frozen: FrozenCandidate,
        *,
        holdout_fingerprint: str,
        evaluate: Callable[[], Mapping[str, Any]],
    ) -> dict[str, Any]:
        key = (frozen.frozen_hash, str(holdout_fingerprint))
        for row in self._rows():
            if (row.get("frozen_hash"), row.get("holdout_fingerprint")) == key:
                raise SealedHoldoutError(
                    "frozen candidate already scored on this holdout fingerprint"
                )
        metrics = dict(evaluate())
        record = {
            "frozen_hash": frozen.frozen_hash,
            "frozen_at": frozen.frozen_at,
            "holdout_fingerprint": str(holdout_fingerprint),
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
            "strategy_id": frozen.strategy_id,
            "metrics": metrics,
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, default=str) + "\n")
        return record
