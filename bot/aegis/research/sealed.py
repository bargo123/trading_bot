"""Freeze a challenger before sealed holdout. One frozen id, one holdout score."""
from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

if os.name == "nt":
    import msvcrt
else:
    try:
        import fcntl
    except ImportError:  # pragma: no cover - only unsupported non-Windows hosts
        fcntl = None

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

    @contextmanager
    def _locked(self):
        descriptor = os.open(self.lock_path, os.O_CREAT | os.O_RDWR)
        handle = os.fdopen(descriptor, "r+b", buffering=0)
        deadline = time.monotonic() + self._LOCK_TIMEOUT_S
        try:
            if os.fstat(descriptor).st_size == 0:
                handle.write(b"\0")
                handle.flush()
                os.fsync(descriptor)
            while True:
                try:
                    handle.seek(0)
                    if os.name == "nt":
                        msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
                    else:
                        if fcntl is None:
                            raise RuntimeError("fcntl is unavailable on this platform")
                        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError as exc:
                    if time.monotonic() >= deadline:
                        raise SealedHoldoutError(
                            "timed out acquiring sealed holdout lock"
                        ) from exc
                    time.sleep(self._LOCK_POLL_S)
            try:
                handle.seek(0)
                handle.write(b"\0")
                handle.truncate(1)
                handle.flush()
                os.fsync(descriptor)
                yield
            finally:
                handle.seek(0)
                if os.name == "nt":
                    msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
                elif fcntl is not None:
                    fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            handle.close()

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
        with self._locked():
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

    def _append_terminal(self, record: Mapping[str, Any]) -> None:
        with self._locked():
            self._append(record)

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
