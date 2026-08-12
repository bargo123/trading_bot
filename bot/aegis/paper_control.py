"""Paper-only mutation, cost, and process-safety controls."""
from __future__ import annotations

import fcntl
import os
from pathlib import Path
from typing import IO, Any

IB_PAPER_PORTS = frozenset({4002, 7497})


def heartbeat_max_age(cfg: dict[str, Any]) -> float:
    """Allow two configured poll cycles plus broker-call scheduling margin."""
    poll_seconds = max(0.0, float(cfg.get("poll_seconds", 0.0) or 0.0))
    return max(15.0, 2.0 * poll_seconds + 15.0)


def assert_paper_mutation_allowed(cfg: dict[str, Any]) -> None:
    """Refuse any broker mutation not explicitly enabled on a known paper port."""
    if str(cfg.get("engine", "ibkr")).casefold() != "ibkr":
        raise RuntimeError("paper mutation control currently supports only IBKR")
    port = int(cfg.get("ib_port", 0) or 0)
    if port not in IB_PAPER_PORTS:
        raise RuntimeError(f"refusing broker mutation on non-paper IB port {port}")
    if bool(cfg.get("allow_live", False)):
        raise RuntimeError("refusing mutation while allow_live is enabled")
    if not bool(cfg.get("paper_trading_enabled", False)):
        raise RuntimeError("paper_trading_enabled must be true before orders can be sent")


def paper_execution_enabled(cfg: dict[str, Any]) -> bool:
    """Return false for observation-only mode; validate every real paper mutation."""
    if bool(cfg.get("dry_run", True)):
        return False
    assert_paper_mutation_allowed(cfg)
    return True


def estimated_target_net_usd(
    *,
    quantity: float,
    entry: float,
    target: float,
    commission_round_trip_usd: float,
    spread_bps: float,
    slippage_bps: float,
    contract_multiplier: float = 1.0,
    spread_price: float = 0.0,
    slippage_price: float = 0.0,
    quote_currency: str = "USD",
) -> float:
    """Estimate target P&L after explicit USD-quoted round-trip costs."""
    if str(quote_currency).upper() != "USD":
        raise ValueError("cost gate requires a USD quote currency or an explicit FX conversion")
    if quantity <= 0 or entry <= 0 or target <= 0 or contract_multiplier <= 0:
        raise ValueError("quantity, multiplier, entry, and target must be positive")
    units = float(quantity) * float(contract_multiplier)
    gross = units * abs(float(target) - float(entry))
    round_trip_notional = 2.0 * units * float(entry)
    variable_cost = round_trip_notional * (
        max(0.0, float(spread_bps)) + max(0.0, float(slippage_bps))
    ) / 10_000.0
    price_cost = units * (
        max(0.0, float(spread_price)) + max(0.0, float(slippage_price))
    )
    return gross - max(0.0, float(commission_round_trip_usd)) - variable_cost - price_cost


def target_clears_costs(*, min_expected_net_usd: float, **kwargs: float) -> tuple[bool, float]:
    net = estimated_target_net_usd(**kwargs)
    return net >= float(min_expected_net_usd), net


class ProcessLock:
    """Non-blocking advisory lock that prevents duplicate local processes."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._handle: IO[str] | None = None

    def acquire(self) -> "ProcessLock":
        if self._handle is not None:
            return self
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            handle.close()
            raise RuntimeError(f"another process holds {self.path}") from exc
        handle.seek(0)
        handle.truncate()
        handle.write(f"{os.getpid()}\n")
        handle.flush()
        self._handle = handle
        return self

    def release(self) -> None:
        handle = self._handle
        if handle is None:
            return
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()
            self._handle = None

    def __enter__(self) -> "ProcessLock":
        return self.acquire()

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.release()
