"""Budget-aware orchestration for real AI Council research asks."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ai_council.agents import ask_agent


class AgentBudgetLedger:
    """Persist per-agent call budgets; Codex begins permanently exhausted."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._payload = self._load()

    def _load(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or not isinstance(payload.get("agents"), dict):
                raise ValueError("invalid budget ledger")
        except (OSError, ValueError, json.JSONDecodeError):
            payload = {"agents": {"codex": {"used": 1, "limit": 1}}}
            self._payload = payload
            self._persist()
            return payload
        if "codex" not in payload["agents"]:
            payload["agents"]["codex"] = {"used": 1, "limit": 1}
            self._payload = payload
            self._persist()
        return payload

    def _persist(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(self._payload, indent=2, sort_keys=True), encoding="utf-8"
        )
        temporary.replace(self.path)

    def remaining(self, agent: str) -> int | None:
        entry = self._payload["agents"].get(agent)
        if entry is None:
            return None
        try:
            return max(0, int(entry["limit"]) - int(entry["used"]))
        except (KeyError, TypeError, ValueError):
            return 0

    def consume(self, agent: str) -> bool:
        entry = self._payload["agents"].get(agent)
        if entry is None:
            return True
        if self.remaining(agent) == 0:
            return False
        entry["used"] = int(entry["used"]) + 1
        self._persist()
        return True

    def usage(self, agent: str) -> tuple[int, int] | None:
        """Return persisted used and limit values for status displays."""
        entry = self._payload["agents"].get(agent)
        if entry is None:
            return None
        try:
            return int(entry["used"]), int(entry["limit"])
        except (KeyError, TypeError, ValueError):
            return None


def ask_research_agent(
    agent: str,
    prompt: str,
    *,
    ledger: AgentBudgetLedger,
    line_sink: Any = None,
    cwd: Path | None = None,
) -> dict[str, Any]:
    """Consume a permitted budget immediately before one shared-adapter ask."""
    if not ledger.consume(agent):
        return {
            "agent": agent,
            "ok": False,
            "status": "BUDGET_EXHAUSTED",
            "error": "persisted agent budget is exhausted",
        }
    return ask_agent(agent, prompt, cwd=cwd, line_sink=line_sink)
