"""Paper-only mutation, cost, and process-safety controls."""
from __future__ import annotations

import os
from pathlib import Path
from typing import IO, Any

try:
    import fcntl
except ImportError:  # Windows
    fcntl = None  # type: ignore[assignment]

IB_PAPER_PORTS = frozenset({4002, 7497})
MT5_DEMO_MODES = frozenset({"mt5_demo", "mt5_paper", "demo"})


def heartbeat_max_age(cfg: dict[str, Any]) -> float:
    """Allow two configured poll cycles plus broker-call scheduling margin."""
    poll_seconds = max(0.0, float(cfg.get("poll_seconds", 0.0) or 0.0))
    return max(15.0, 2.0 * poll_seconds + 15.0)


def assert_paper_mutation_allowed(cfg: dict[str, Any]) -> None:
    """Refuse any broker mutation not explicitly enabled on a known paper/demo path."""
    if bool(cfg.get("allow_live", False)):
        raise RuntimeError("refusing mutation while allow_live is enabled")
    engine = str(cfg.get("engine", "ibkr")).casefold()
    if engine in {"mt5", "metatrader5"}:
        mode = str(cfg.get("mode") or "").casefold()
        if mode not in MT5_DEMO_MODES:
            raise RuntimeError("MT5 mutations require mode: mt5_demo")
        if not bool(cfg.get("paper_trading_enabled", False)):
            raise RuntimeError("paper_trading_enabled must be true before orders can be sent")
        return
    if engine != "ibkr":
        raise RuntimeError("paper mutation control currently supports only IBKR or MT5")
    port = int(cfg.get("ib_port", 0) or 0)
    if port not in IB_PAPER_PORTS:
        raise RuntimeError(f"refusing broker mutation on non-paper IB port {port}")
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
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                if handle.read(1) == "":
                    handle.write("\0")
                    handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                if fcntl is None:
                    raise RuntimeError("fcntl is unavailable on this platform")
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (BlockingIOError, OSError) as exc:
            handle.close()
            raise RuntimeError(f"another process holds {self.path}") from exc
        handle.seek(0)
        handle.truncate()
        handle.write(f"{os.getpid()}\n")
        handle.flush()
        self._handle = handle
        return self

    def try_acquire(self) -> bool:
        try:
            self.acquire()
            return True
        except RuntimeError:
            return False

    def release(self) -> None:
        handle = self._handle
        if handle is None:
            return
        try:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            elif fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()
            self._handle = None

    def __enter__(self) -> "ProcessLock":
        return self.acquire()

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.release()


def lock_pid(path: Path) -> int | None:
    p = Path(path)
    if not p.exists():
        return None
    try:
        text = p.read_text(encoding="utf-8", errors="replace").replace("\0", " ").strip()
        for token in text.split():
            try:
                return int(token)
            except ValueError:
                continue
        return None
    except (OSError, ValueError):
        return None


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid)
        )
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def lock_appears_held(path: Path) -> bool:
    """Best-effort: lock file exists and recorded pid is still alive. Does not acquire."""
    pid = lock_pid(path)
    if pid is None:
        return Path(path).exists()
    return pid_alive(pid)


def is_jpy_symbol(name: str) -> bool:
    return "JPY" in str(name or "").upper()


def firehose_consume_bar(
    *,
    spread_skip: bool = False,
    halted: bool = False,
    no_signal: bool = False,
    order_ok: bool = False,
    order_failed: bool = False,
    stack_more: bool = False,
) -> bool:
    """Stamp last_bar_time only when this M1 bar is done.

    Spread/halt/reject must not consume the bar. Otherwise the hose waits a
    full minute after the first wide quote and looks like 1–2 clips, not bullets.
    stack_more: a fill that should allow another same-bar clip on this product.
    """
    if spread_skip or halted or order_failed or stack_more:
        return False
    return bool(no_signal or order_ok)


def firehose_can_add(
    *,
    open_total: int,
    max_positions: int,
    held_sides: list[str],
    signal_side: str,
    stack: bool = False,
    max_per_symbol: int = 1,
    last_entry_age_s: float | None = None,
    clip_interval_s: float = 0.0,
    held_pnl: float | None = None,
    no_stack_if_red: bool = False,
) -> bool:
    """Allow another 0.01 clip, including a second ticket on the same product.

    Same-side only so a netting account does not reverse-close the winner.
    no_stack_if_red: do not average down into an already-losing clip.
    Not a 100% win claim — Volman/Brooks scalp geometry + Harris spread gate.
    """
    if int(open_total) >= int(max_positions):
        return False
    interval = float(clip_interval_s or 0.0)
    if interval > 0 and last_entry_age_s is not None and float(last_entry_age_s) < interval:
        return False
    n = len(held_sides)
    if n <= 0:
        return True
    if not stack:
        return False
    if bool(no_stack_if_red) and held_pnl is not None and float(held_pnl) <= 0.0:
        return False
    cap = int(max_per_symbol or 0)
    if cap > 0 and n >= cap:
        return False
    side = str(signal_side or "").lower()
    for held in held_sides:
        if str(held or "").lower() != side:
            return False
    return True


def jpy_cluster_blocks(open_symbols: list[str], candidate: str, max_jpy: int) -> bool:
    """Davey/Clenow: correlated yen names are not independent bets.

    max_jpy <= 0 disables the gate so the user can still fill a wide book.
    """
    cap = int(max_jpy or 0)
    if cap <= 0 or not is_jpy_symbol(candidate):
        return False
    held = sum(1 for s in open_symbols if is_jpy_symbol(s))
    return held >= cap
