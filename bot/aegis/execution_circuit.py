from __future__ import annotations

import json
import math
import re
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


NO_MONEY_RE = re.compile(r"(?<!\d)10019(?!\d)|\bNo money\b", re.IGNORECASE)


@dataclass
class ExecutionCircuit:
    limit: int
    window_s: float
    backoff_s: float
    blocked_until: float = 0.0
    consecutive_failures: int = 0
    no_money_times: deque[float] = field(default_factory=deque)

    def __post_init__(self) -> None:
        if (
            not isinstance(self.limit, int)
            or isinstance(self.limit, bool)
            or self.limit <= 0
            or not math.isfinite(float(self.window_s))
            or float(self.window_s) <= 0
            or not math.isfinite(float(self.backoff_s))
            or float(self.backoff_s) <= 0
        ):
            raise ValueError("execution circuit settings must be finite and positive")

    def reconfigure(self, *, limit: int, window_s: float, backoff_s: float) -> None:
        validated = ExecutionCircuit(limit=limit, window_s=window_s, backoff_s=backoff_s)
        self.limit = validated.limit
        self.window_s = float(validated.window_s)
        self.backoff_s = float(validated.backoff_s)

    def observe(self, message: str, *, now: float, ok: bool = False) -> None:
        if ok:
            self.consecutive_failures = 0
            return
        self.consecutive_failures += 1
        if not NO_MONEY_RE.search(str(message or "")):
            return
        cutoff = float(now) - self.window_s
        while self.no_money_times and self.no_money_times[0] < cutoff:
            self.no_money_times.popleft()
        self.no_money_times.append(float(now))
        if len(self.no_money_times) >= self.limit:
            self.blocked_until = max(self.blocked_until, float(now) + self.backoff_s)

    def allow(self, *, now: float) -> tuple[bool, str]:
        if float(now) < self.blocked_until:
            return False, "no_money_backoff"
        return True, ""

    def dump(self) -> dict[str, Any]:
        return {
            "limit": self.limit,
            "window_s": self.window_s,
            "backoff_s": self.backoff_s,
            "blocked_until": self.blocked_until,
            "consecutive_failures": self.consecutive_failures,
            "no_money_times": list(self.no_money_times),
        }

    def save_json(self, path: Path) -> None:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(destination.name + ".tmp")
        try:
            temporary.write_text(json.dumps(self.dump(), indent=2), encoding="utf-8")
            temporary.replace(destination)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass

    def load_json(self, path: Path) -> bool:
        source = Path(path)
        try:
            raw = json.loads(source.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return False
            required = {
                "limit",
                "window_s",
                "backoff_s",
                "blocked_until",
                "consecutive_failures",
                "no_money_times",
            }
            if set(raw) != required or not isinstance(raw["no_money_times"], list):
                return False
            if (
                not isinstance(raw["limit"], int)
                or isinstance(raw["limit"], bool)
                or not isinstance(raw["consecutive_failures"], int)
                or isinstance(raw["consecutive_failures"], bool)
            ):
                return False
            numeric_fields = ("window_s", "backoff_s", "blocked_until")
            if any(
                not isinstance(raw[name], (int, float)) or isinstance(raw[name], bool)
                for name in numeric_fields
            ):
                return False
            if any(
                not isinstance(value, (int, float)) or isinstance(value, bool)
                for value in raw["no_money_times"]
            ):
                return False
            limit = int(raw["limit"])
            window_s = float(raw["window_s"])
            backoff_s = float(raw["backoff_s"])
            blocked_until = float(raw["blocked_until"])
            consecutive_failures = int(raw["consecutive_failures"])
            no_money_times = [float(value) for value in raw["no_money_times"]]
            numeric = [window_s, backoff_s, blocked_until, *no_money_times]
            if (
                limit <= 0
                or window_s <= 0
                or backoff_s <= 0
                or blocked_until < 0
                or consecutive_failures < 0
                or any(not math.isfinite(value) for value in numeric)
                or no_money_times != sorted(no_money_times)
            ):
                return False
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return False

        self.blocked_until = blocked_until
        self.consecutive_failures = consecutive_failures
        self.no_money_times = deque(no_money_times)
        return True
