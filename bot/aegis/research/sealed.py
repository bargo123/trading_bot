"""Freeze a challenger before sealed holdout. One frozen id, one holdout score."""
from __future__ import annotations

import json
import os
import time
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
    training_dataset_fingerprint: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def freeze_candidate(
    *,
    strategy_id: str,
    code_hash: str,
    config: Mapping[str, Any],
    artifact_hash: str,
    training_dataset_fingerprint: str,
) -> FrozenCandidate:
    frozen_at = datetime.now(timezone.utc).isoformat()
    config_hash = config_fingerprint(dict(config))
    if not isinstance(training_dataset_fingerprint, str):
        raise ValueError("training_dataset_fingerprint is required")
    training_fingerprint = training_dataset_fingerprint.strip()
    if not training_fingerprint:
        raise ValueError("training_dataset_fingerprint is required")
    frozen_hash = config_fingerprint(
        {
            "strategy_id": strategy_id,
            "code_hash": code_hash,
            "config_hash": config_hash,
            "artifact_hash": artifact_hash,
            "training_dataset_fingerprint": training_fingerprint,
        }
    )
    return FrozenCandidate(
        frozen_hash=frozen_hash,
        frozen_at=frozen_at,
        code_hash=str(code_hash),
        config_hash=config_hash,
        artifact_hash=str(artifact_hash),
        strategy_id=str(strategy_id),
        training_dataset_fingerprint=training_fingerprint,
    )


class SealedHoldoutStore:
    _LOCK_TIMEOUT_S = 5.0
    _LOCK_POLL_S = 0.01

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.lock_path = self.path.with_name(f"{self.path.name}.lock")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(self.path, os.O_CREAT | os.O_APPEND | os.O_WRONLY)
        os.close(descriptor)

    def _rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        text = self.path.read_text(encoding="utf-8")
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
        return rows

    def _acquire_lock(self) -> int:
        deadline = time.monotonic() + self._LOCK_TIMEOUT_S
        while True:
            try:
                descriptor = os.open(
                    self.lock_path,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                )
                os.write(descriptor, str(os.getpid()).encode("ascii"))
                os.fsync(descriptor)
                return descriptor
            except FileExistsError:
                if time.monotonic() >= deadline:
                    raise SealedHoldoutError("timed out acquiring sealed holdout lock")
                time.sleep(self._LOCK_POLL_S)

    def _release_lock(self, descriptor: int) -> None:
        os.close(descriptor)
        try:
            self.lock_path.unlink()
        except FileNotFoundError:
            pass

    def _append(self, record: Mapping[str, Any]) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(dict(record), default=str) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    @staticmethod
    def _matches(
        row: Mapping[str, Any], key: tuple[str, str]
    ) -> bool:
        return (row.get("frozen_hash"), row.get("holdout_fingerprint")) == key

    def _reserve(
        self,
        frozen: FrozenCandidate,
        holdout_fingerprint: str,
    ) -> dict[str, Any]:
        key = (frozen.frozen_hash, holdout_fingerprint)
        if any(self._matches(row, key) for row in self._rows()):
            raise SealedHoldoutError(
                "frozen candidate already reserved or evaluated on this holdout fingerprint"
            )
        descriptor = self._acquire_lock()
        try:
            if any(self._matches(row, key) for row in self._rows()):
                raise SealedHoldoutError(
                    "frozen candidate already reserved or evaluated on this holdout fingerprint"
                )
            reservation = {
                "record_type": "reservation",
                "status": "reserved",
                "frozen_hash": frozen.frozen_hash,
                "frozen_at": frozen.frozen_at,
                "holdout_fingerprint": holdout_fingerprint,
                "reserved_at": datetime.now(timezone.utc).isoformat(),
                "strategy_id": frozen.strategy_id,
                "training_dataset_fingerprint": frozen.training_dataset_fingerprint,
            }
            self._append(reservation)
            return reservation
        finally:
            self._release_lock(descriptor)

    def _append_terminal(self, record: Mapping[str, Any]) -> None:
        descriptor = self._acquire_lock()
        try:
            self._append(record)
        finally:
            self._release_lock(descriptor)

    def evaluate_once(
        self,
        frozen: FrozenCandidate,
        *,
        holdout_fingerprint: str,
        evaluate: Callable[[], Mapping[str, Any]],
    ) -> dict[str, Any]:
        fingerprint = str(holdout_fingerprint)
        self._reserve(frozen, fingerprint)
        terminal = {
            "record_type": "evaluation",
            "frozen_hash": frozen.frozen_hash,
            "frozen_at": frozen.frozen_at,
            "holdout_fingerprint": fingerprint,
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
            "strategy_id": frozen.strategy_id,
            "training_dataset_fingerprint": frozen.training_dataset_fingerprint,
        }
        try:
            evaluation = dict(evaluate())
            nested_metrics = evaluation.pop("metrics", None)
            if isinstance(nested_metrics, Mapping):
                metrics = dict(nested_metrics)
                pnls = evaluation.pop("pnls", None)
            else:
                metrics = evaluation
                pnls = metrics.pop("pnls", None)
            record = {**terminal, "status": "succeeded", "metrics": metrics}
            if pnls is not None:
                record["pnls"] = list(pnls)
        except BaseException as exc:
            failed = {
                **terminal,
                "status": "failed",
                "error": {"type": type(exc).__name__, "message": str(exc)},
            }
            self._append_terminal(failed)
            raise
        self._append_terminal(record)
        return record
