"""Champion pointer. Promote never writes live YAML or starts a runner."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aegis.research.gates import evaluate_promotion
from aegis.research.registry import ExperimentRegistry

_EVENTS = """
CREATE TABLE IF NOT EXISTS champion_events (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_utc TEXT NOT NULL,
    experiment_id TEXT NOT NULL,
    event TEXT NOT NULL
);
"""


class ChampionStore:
    def __init__(self, db_path: Path) -> None:
        self.registry = ExperimentRegistry(db_path)
        self._ensure_events()
        self._current: dict[str, Any] | None = self._load()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.registry.path))

    def _ensure_events(self) -> None:
        with self._connect() as con:
            con.executescript(_EVENTS)

    def _append_event(self, experiment_id: str, event: str) -> None:
        with self._connect() as con:
            con.execute(
                "INSERT INTO champion_events(ts_utc, experiment_id, event) VALUES (?,?,?)",
                (datetime.now(timezone.utc).isoformat(), experiment_id, event),
            )

    def _stack_ids(self) -> list[str]:
        with self._connect() as con:
            rows = con.execute(
                "SELECT experiment_id, event FROM champion_events ORDER BY seq"
            ).fetchall()
        stack: list[str] = []
        for experiment_id, event in rows:
            if event == "promote":
                stack.append(str(experiment_id))
            elif event == "rollback" and stack:
                stack.pop()
        return stack

    def _hydrate(self, experiment_id: str) -> dict[str, Any] | None:
        row = self.registry.get(experiment_id)
        return dict(row) if row else None

    def _load(self) -> dict[str, Any] | None:
        stack = self._stack_ids()
        if stack:
            return self._hydrate(stack[-1])
        rows = [r for r in self.registry.all_rows() if str(r.get("status")) == "accepted"]
        if not rows:
            return None
        return dict(rows[-1])

    def current(self) -> dict[str, Any] | None:
        return dict(self._current) if self._current else None

    def promote(self, row: dict[str, Any]) -> dict[str, Any]:
        evaluate_promotion(row, self._current)
        payload = dict(row)
        payload["status"] = "accepted"
        self.registry.record(payload)
        self._append_event(str(payload["id"]), "promote")
        self._current = payload
        return payload

    def demote(self, reason: str) -> None:
        """Clear the champion when it turned out to be an artifact.

        Appends a rollback event; the experiment row itself is never deleted, so the
        bad result stays on the record with its reason.
        """
        stack = self._stack_ids()
        if not stack:
            return
        self._append_event(stack[-1], "rollback")
        remaining = self._stack_ids()
        self._current = self._hydrate(remaining[-1]) if remaining else None
        self._append_event(stack[-1], f"demote_reason:{reason}"[:200])

    def rollback(self) -> dict[str, Any]:
        """Restore the predecessor champion. Never deletes experiment rows."""
        stack = self._stack_ids()
        if len(stack) < 2:
            raise ValueError("no predecessor champion to restore")
        failed_id = stack[-1]
        restored_id = stack[-2]
        self._append_event(failed_id, "rollback")
        restored = self._hydrate(restored_id)
        if restored is None:
            raise ValueError(f"predecessor {restored_id} missing from registry")
        self._current = restored
        return dict(restored)
