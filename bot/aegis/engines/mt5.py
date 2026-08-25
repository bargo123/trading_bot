"""MetaTrader 5 engine (Windows demo via the MetaTrader5 package)."""
from __future__ import annotations

import logging
import math
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from aegis.engines.base import (
    AccountSnapshot,
    Bar,
    BrokerEngine,
    ModifyResult,
    OrderRequest,
    OrderResult,
    PositionSnapshot,
    Quote,
)
import re


def sanitize_mt5_comment(tag: str) -> str:
    """MT5 Python order_send rejects punctuation and long comment strings."""
    cleaned = re.sub(r"[^A-Za-z0-9]", "", str(tag or "aegis"))
    if not cleaned.lower().startswith("aegis"):
        cleaned = "aegis" + cleaned
    return (cleaned or "aegis")[:16]


logger = logging.getLogger(__name__)

_DEFAULT_TERMINAL = r"C:\Program Files\MetaTrader 5\terminal64.exe"
_MAX_LOTS_DEFAULT = 0.10
_UNITS_QTY_FLOOR = 100.0  # IB-style FX units; MT5 uses lots
_OK_RETCODES = {10008, 10009, 10010}  # PLACED / DONE / DONE_PARTIAL
_TF_ATTR = {
    "1m": "TIMEFRAME_M1",
    "m1": "TIMEFRAME_M1",
    "5m": "TIMEFRAME_M5",
    "m5": "TIMEFRAME_M5",
    "15m": "TIMEFRAME_M15",
    "m15": "TIMEFRAME_M15",
    "30m": "TIMEFRAME_M30",
    "m30": "TIMEFRAME_M30",
    "1h": "TIMEFRAME_H1",
    "h1": "TIMEFRAME_H1",
    "4h": "TIMEFRAME_H4",
    "h4": "TIMEFRAME_H4",
    "1d": "TIMEFRAME_D1",
    "d1": "TIMEFRAME_D1",
}
_BARS_PER_DAY = {
    "1m": 1440,
    "m1": 1440,
    "5m": 288,
    "m5": 288,
    "15m": 96,
    "m15": 96,
    "30m": 48,
    "m30": 48,
    "1h": 24,
    "h1": 24,
    "4h": 6,
    "h4": 6,
    "1d": 1,
    "d1": 1,
}


class MT5Engine(BrokerEngine):
    """Talks to a running MT5 terminal. Demo/contest only unless allow_live is set."""

    name = "mt5"

    def __init__(self, cfg: dict[str, Any], *, api: Any = None) -> None:
        self.cfg = cfg
        self._api_mod = api
        self._connected = False
        self._resolved: dict[str, str] = {}
        self.allow_live = bool(cfg.get("allow_live", False))
        self.magic = int(cfg.get("mt5_magic", 260812) or 260812)
        self.deviation = int(cfg.get("mt5_deviation", 20) or 20)
        self.max_lots = float(cfg.get("mt5_max_lots", _MAX_LOTS_DEFAULT) or _MAX_LOTS_DEFAULT)
        self.path = str(cfg.get("mt5_path") or os.environ.get("MT5_PATH") or _DEFAULT_TERMINAL)
        self._server_utc_offset_s: float | None = None
        self._offset_samples: list[float] = []

    def _api(self) -> Any:
        if self._api_mod is not None:
            return self._api_mod
        try:
            import MetaTrader5 as mt5  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "MetaTrader5 package is not installed. "
                "On Windows: pip install MetaTrader5"
            ) from exc
        self._api_mod = mt5
        return mt5

    def _require(self) -> Any:
        if not self._connected:
            raise RuntimeError("MT5Engine not connected — call connect() first")
        return self._api()

    def _last_error(self) -> str:
        err = self._api().last_error()
        if err is None:
            return "unknown error"
        if isinstance(err, tuple) and len(err) >= 2:
            return f"{err[0]} {err[1]}"
        return str(err)

    def _server_utc_offset(self) -> float:
        """Seconds to subtract from MT5 server epoch to get real UTC.

        MetaQuotes demo/contest servers stamp ticks in *server time* (commonly
        UTC+2/+3), while the staleness/future-skew gates compare against
        datetime.now(timezone.utc). Treating server epoch as UTC made every
        quote look ~3h in the future and the max_quote_future_skew_s gate
        rejected the entire feed. Detect the offset from live tick times and
        cache it.
        """
        if self._server_utc_offset_s is not None:
            return self._server_utc_offset_s
        mt5 = self._require()
        for name in ("EURUSD", "GBPUSD", "USDJPY"):
            try:
                tick = mt5.symbol_info_tick(name)
            except Exception:  # pragma: no cover - defensive
                tick = None
            if tick is None:
                continue
            ts_raw = getattr(tick, "time", None)
            if not ts_raw:
                continue
            offset = float(ts_raw) - time.time()
            self._offset_samples.append(offset)
            if len(self._offset_samples) >= 3:
                median = sorted(self._offset_samples)[len(self._offset_samples) // 2]
                self._server_utc_offset_s = round(median)
                self._offset_samples = []
                logger.info("MT5 server->UTC offset detected: %+.0fs", self._server_utc_offset_s)
                return self._server_utc_offset_s
        return 0.0

    def _quote_time_utc(self, ts_raw: Any) -> datetime:
        offset = self._server_utc_offset()
        return datetime.fromtimestamp(int(ts_raw) - offset, tz=timezone.utc)

    def _is_paper_mode(self, trade_mode: int) -> bool:
        mt5 = self._api()
        demo = int(getattr(mt5, "ACCOUNT_TRADE_MODE_DEMO", 0))
        contest = int(getattr(mt5, "ACCOUNT_TRADE_MODE_CONTEST", 1))
        return int(trade_mode) in {demo, contest}

    def connect(self) -> None:
        mt5 = self._api()
        kwargs: dict[str, Any] = {}
        if self.path:
            kwargs["path"] = self.path
        if not mt5.initialize(**kwargs):
            raise RuntimeError(
                f"mt5.initialize failed ({self._last_error()}). "
                "Keep MetaTrader 5 open and logged into a DEMO account."
            )
        self._connected = True
        login = self.cfg.get("mt5_login") or os.environ.get("MT5_LOGIN")
        password = self.cfg.get("mt5_password") or os.environ.get("MT5_PASSWORD")
        server = self.cfg.get("mt5_server") or os.environ.get("MT5_SERVER")
        if login:
            if not password or not server:
                mt5.shutdown()
                self._connected = False
                raise RuntimeError("mt5_login set but mt5_password / mt5_server missing")
            if not mt5.login(int(login), password=str(password), server=str(server)):
                mt5.shutdown()
                self._connected = False
                raise RuntimeError(f"mt5.login failed ({self._last_error()})")
        info = mt5.account_info()
        if info is None:
            mt5.shutdown()
            self._connected = False
            raise RuntimeError(
                "MT5 terminal is open but not logged in. "
                "Log into a DEMO account in MetaTrader 5, then retry."
            )
        if not self._is_paper_mode(int(getattr(info, "trade_mode", 2))) and not self.allow_live:
            mt5.shutdown()
            self._connected = False
            raise RuntimeError(
                f"Refusing non-demo MT5 account {getattr(info, 'login', '?')} "
                f"server={getattr(info, 'server', '')}. Set allow_live: true only when intentional."
            )
        logger.info(
            "MT5 connected login=%s server=%s company=%s demo=%s",
            getattr(info, "login", ""),
            getattr(info, "server", ""),
            getattr(info, "company", ""),
            self._is_paper_mode(int(getattr(info, "trade_mode", 2))),
        )
        if not bool(getattr(info, "trade_expert", True)):
            logger.warning(
                "This MT5 account has trade_expert=False. The server may reject "
                "Python/EA orders with 10026 even if Algo Trading is on."
            )
        term = mt5.terminal_info()
        if term is not None and not bool(getattr(term, "trade_allowed", False)):
            logger.warning(
                "MT5 AutoTrading is OFF. Click Algo Trading in the toolbar "
                "or demo orders will be rejected."
            )

    def connect_readonly(self) -> None:
        """Attach to an already-open terminal for reads. Never calls shutdown().

        A second Python process may initialize() against the same terminal.
        shutdown() from that process kills the live paper runner — do not call
        disconnect() after a successful readonly attach.
        """
        mt5 = self._api()
        kwargs: dict[str, Any] = {}
        if self.path:
            kwargs["path"] = self.path
        if not mt5.initialize(**kwargs):
            raise RuntimeError(
                f"mt5.initialize failed ({self._last_error()}). "
                "Keep MetaTrader 5 open and logged into a DEMO account."
            )
        self._connected = True
        info = mt5.account_info()
        if info is None:
            self._connected = False
            raise RuntimeError(
                "MT5 terminal is open but not logged in. "
                "Log into a DEMO account in MetaTrader 5, then retry."
            )
        if not self._is_paper_mode(int(getattr(info, "trade_mode", 2))) and not self.allow_live:
            raise RuntimeError(
                f"Refusing non-demo MT5 account {getattr(info, 'login', '?')} "
                f"server={getattr(info, 'server', '')}."
            )
        logger.info(
            "MT5 readonly attach login=%s server=%s demo=%s",
            getattr(info, "login", ""),
            getattr(info, "server", ""),
            self._is_paper_mode(int(getattr(info, "trade_mode", 2))),
        )
        if not bool(getattr(info, "trade_expert", True)):
            logger.warning(
                "This MT5 account has trade_expert=False. The server may reject "
                "Python/EA orders with 10026 even if Algo Trading is on."
            )
        term = mt5.terminal_info()
        if term is not None and not bool(getattr(term, "trade_allowed", False)):
            logger.warning(
                "MT5 AutoTrading is OFF. Click Algo Trading in the toolbar "
                "or demo orders will be rejected."
            )

    def disconnect(self, shutdown: bool = False) -> None:
        """Drop the Python handle. Default does **not** call mt5.shutdown().

        shutdown=True kills the terminal IPC and can take down the live demo.
        """
        if not self._connected:
            return
        try:
            if shutdown:
                self._api().shutdown()
        finally:
            self._connected = False
            self._resolved.clear()

    def account(self) -> AccountSnapshot:
        mt5 = self._require()
        info = mt5.account_info()
        if info is None:
            raise RuntimeError("mt5.account_info returned None — not logged in")
        trade_mode = int(getattr(info, "trade_mode", 2))
        return AccountSnapshot(
            account_id=str(getattr(info, "login", "")),
            equity=float(getattr(info, "equity", 0) or 0),
            currency=str(getattr(info, "currency", "USD") or "USD"),
            available_funds=float(getattr(info, "margin_free", 0) or 0),
            is_paper=self._is_paper_mode(trade_mode),
            raw={
                "server": str(getattr(info, "server", "") or ""),
                "company": str(getattr(info, "company", "") or ""),
                "trade_mode": trade_mode,
                "balance": float(getattr(info, "balance", 0) or 0),
                "leverage": int(getattr(info, "leverage", 0) or 0),
                "trade_expert": bool(getattr(info, "trade_expert", True)),
                "trade_allowed": bool(getattr(info, "trade_allowed", True)),
                "margin_level": float(getattr(info, "margin_level", 0) or 0),
                "margin_used": float(getattr(info, "margin", 0) or 0),
            },
        )

    def _resolve_symbol(self, symbol: str) -> str:
        key = symbol.upper().replace("=X", "").replace("/", "")
        if key in self._resolved:
            return self._resolved[key]
        mt5 = self._require()
        candidates = [key, symbol]
        if "." in key:
            candidates.append(key.split(".", 1)[0])
        if key in {"GC", "GCF", "GC=F"}:
            candidates.extend(["XAUUSD", "GOLD", "XAUUSDm"])
        seen: list[str] = []
        for name in candidates:
            if name in seen:
                continue
            seen.append(name)
            info = mt5.symbol_info(name)
            if info is not None:
                resolved = str(getattr(info, "name", name) or name)
                self._ensure_symbol(resolved)
                self._resolved[key] = resolved
                return resolved
        matches: list[str] = []
        all_syms = mt5.symbols_get() or []
        for item in all_syms:
            name = str(getattr(item, "name", "") or "")
            up = name.upper()
            if up == key or up.startswith(key + ".") or up.startswith(key):
                matches.append(name)
        ranked = sorted(
            matches,
            key=lambda n: (
                0 if n.upper() == key else 1 if n.upper().startswith(key + ".") else 2,
                len(n),
            ),
        )
        if ranked:
            resolved = ranked[0]
            self._ensure_symbol(resolved)
            self._resolved[key] = resolved
            logger.info("Resolved MT5 symbol %s -> %s", symbol, resolved)
            return resolved
        raise RuntimeError(
            f"MT5 symbol not found: {symbol}. Near matches: {matches[:8] or 'none'}"
        )

    def _ensure_symbol(self, name: str) -> Any:
        mt5 = self._require()
        info = mt5.symbol_info(name)
        if info is None:
            raise RuntimeError(f"MT5 symbol_info failed for {name} ({self._last_error()})")
        if not bool(getattr(info, "visible", True)):
            if not mt5.symbol_select(name, True):
                raise RuntimeError(f"Could not add {name} to Market Watch ({self._last_error()})")
            info = mt5.symbol_info(name)
            if info is None:
                raise RuntimeError(f"MT5 symbol_info failed after select for {name}")
        return info

    def quote(self, symbol: str) -> Quote:
        mt5 = self._require()
        name = self._resolve_symbol(symbol)
        self._ensure_symbol(name)
        tick = mt5.symbol_info_tick(name)
        if tick is None:
            raise RuntimeError(f"No tick for {name} ({self._last_error()})")
        bid = float(getattr(tick, "bid", 0) or 0)
        ask = float(getattr(tick, "ask", 0) or 0)
        if bid <= 0 and ask <= 0:
            raise RuntimeError(f"No bid/ask for {name}")
        if bid <= 0:
            bid = ask
        if ask <= 0:
            ask = bid
        ts_raw = getattr(tick, "time", None)
        if ts_raw:
            ts = self._quote_time_utc(ts_raw)
        else:
            ts = datetime.now(timezone.utc)
        return Quote(symbol=name, bid=bid, ask=ask, time=ts)

    def symbol_spec(self, symbol: str) -> dict[str, Any]:
        """Broker contract facts (Harris/Aldridge: measure costs before promoting a scalp)."""
        info = self._ensure_symbol(self._resolve_symbol(symbol))
        tick = self._api().symbol_info_tick(str(getattr(info, "name", symbol)))
        bid = float(getattr(tick, "bid", 0) or 0) if tick else 0.0
        ask = float(getattr(tick, "ask", 0) or 0) if tick else 0.0
        spread_price = max(0.0, ask - bid) if bid > 0 and ask > 0 else 0.0
        contract = float(getattr(info, "trade_contract_size", 100000) or 100000)
        return {
            "name": str(getattr(info, "name", symbol)),
            "digits": int(getattr(info, "digits", 5) or 5),
            "point": float(getattr(info, "point", 0) or 0),
            "spread_points": int(getattr(info, "spread", 0) or 0),
            "spread_price": spread_price,
            "bid": bid,
            "ask": ask,
            "volume_min": float(getattr(info, "volume_min", 0.01) or 0.01),
            "volume_step": float(getattr(info, "volume_step", 0.01) or 0.01),
            "volume_max": float(getattr(info, "volume_max", 100) or 100),
            "trade_contract_size": contract,
            "trade_tick_size": float(getattr(info, "trade_tick_size", 0) or getattr(info, "point", 0) or 0),
            "trade_tick_value": float(getattr(info, "trade_tick_value", 0) or 0),
            "trade_tick_value_profit": float(getattr(info, "trade_tick_value_profit", 0) or 0),
            "trade_tick_value_loss": float(getattr(info, "trade_tick_value_loss", 0) or 0),
            "trade_stops_level": int(getattr(info, "trade_stops_level", 0) or 0),
            "trade_freeze_level": int(getattr(info, "trade_freeze_level", 0) or 0),
            "filling_mode": int(getattr(info, "filling_mode", 0) or 0),
            "swap_long": float(getattr(info, "swap_long", 0) or 0),
            "swap_short": float(getattr(info, "swap_short", 0) or 0),
            "trade_mode": int(getattr(info, "trade_mode", 0) or 0),
        }

    def round_trip_spread_usd(self, symbol: str, lots: float) -> float:
        spec = self.symbol_spec(symbol)
        return float(lots) * float(spec["trade_contract_size"]) * float(spec["spread_price"])

    def copy_ticks(self, symbol: str, lookback_seconds: int = 120) -> list[dict[str, Any]]:
        mt5 = self._require()
        name = self._resolve_symbol(symbol)
        self._ensure_symbol(name)
        now = datetime.now(timezone.utc)
        start = now - timedelta(seconds=max(1, int(lookback_seconds)))
        flags = int(getattr(mt5, "COPY_TICKS_ALL", 0))
        raw = mt5.copy_ticks_range(name, start, now, flags)
        if raw is None:
            return []
        out: list[dict[str, Any]] = []
        for row in raw:
            out.append(
                {
                    "time": int(row["time"] if hasattr(row, "__getitem__") else row.time),
                    "bid": float(row["bid"] if hasattr(row, "__getitem__") else row.bid),
                    "ask": float(row["ask"] if hasattr(row, "__getitem__") else row.ask),
                    "last": float(row["last"] if hasattr(row, "__getitem__") else getattr(row, "last", 0) or 0),
                    "volume": float(row["volume"] if hasattr(row, "__getitem__") else getattr(row, "volume", 0) or 0),
                    "flags": int(row["flags"] if hasattr(row, "__getitem__") else getattr(row, "flags", 0) or 0),
                }
            )
        return out

    def bars(self, symbol: str, timeframe: str, lookback_days: int) -> list[Bar]:
        mt5 = self._require()
        name = self._resolve_symbol(symbol)
        self._ensure_symbol(name)
        tf_key = str(timeframe).strip().lower()
        attr = _TF_ATTR.get(tf_key)
        if not attr:
            raise ValueError(f"Unsupported timeframe for MT5: {timeframe}")
        tf = int(getattr(mt5, attr))
        per_day = _BARS_PER_DAY.get(tf_key, 24)
        count = max(50, min(100_000, int(lookback_days) * per_day + 10))
        raw = mt5.copy_rates_from_pos(name, tf, 0, count)
        if raw is None:
            raise RuntimeError(f"copy_rates_from_pos failed for {name} ({self._last_error()})")
        out: list[Bar] = []
        for row in raw:
            ts = self._quote_time_utc(row["time"] if hasattr(row, "__getitem__") else row.time)
            out.append(
                Bar(
                    time=ts,
                    open=float(row["open"] if hasattr(row, "__getitem__") else row.open),
                    high=float(row["high"] if hasattr(row, "__getitem__") else row.high),
                    low=float(row["low"] if hasattr(row, "__getitem__") else row.low),
                    close=float(row["close"] if hasattr(row, "__getitem__") else row.close),
                    volume=float(
                        (row["tick_volume"] if hasattr(row, "__getitem__") else getattr(row, "tick_volume", 0))
                        or 0
                    ),
                )
            )
        return out

    def positions(self, symbol: Optional[str] = None) -> list[PositionSnapshot]:
        mt5 = self._require()
        name = self._resolve_symbol(symbol) if symbol else None
        raw = mt5.positions_get(symbol=name) if name else mt5.positions_get()
        if raw is None:
            return []
        out: list[PositionSnapshot] = []
        for pos in raw:
            qty = float(getattr(pos, "volume", 0) or 0)
            if abs(qty) < 1e-12:
                continue
            side = "buy" if int(getattr(pos, "type", 0) or 0) == 0 else "sell"
            out.append(
                PositionSnapshot(
                    symbol=str(getattr(pos, "symbol", name or "")),
                    side=side,
                    quantity=qty,
                    avg_price=float(getattr(pos, "price_open", 0) or 0),
                    unrealized_pnl=float(getattr(pos, "profit", 0) or 0),
                    ticket=str(int(getattr(pos, "ticket", 0) or 0) or ""),
                    stop_loss=float(getattr(pos, "sl", 0) or 0),
                    take_profit=float(getattr(pos, "tp", 0) or 0),
                    comment=str(getattr(pos, "comment", "") or ""),
                )
            )
        return out

    def history_deals(self, lookback_days: int = 14) -> list[dict[str, Any]]:
        """Read-only deal history. Does not place orders. Caller must not shutdown()."""
        mt5 = self._require()
        # MetaQuotes demo timestamps and history query bounds use the broker's
        # server clock, while the rest of AEGIS uses UTC.  Query through the
        # server-time window and normalize returned deal times back to UTC so
        # reconciliation sees closes that happened after the last watermark.
        server_offset = self._server_utc_offset()
        end = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(seconds=server_offset)
        start = end - timedelta(days=max(1, int(lookback_days)))
        raw = mt5.history_deals_get(start, end)
        if raw is None:
            return []
        out: list[dict[str, Any]] = []
        for row in raw:
            ts = int(getattr(row, "time", 0) or 0)
            out.append(
                {
                    "ticket": str(int(getattr(row, "ticket", 0) or 0)),
                    "order": str(int(getattr(row, "order", 0) or 0)),
                    "symbol": str(getattr(row, "symbol", "") or ""),
                    "side": "buy" if int(getattr(row, "type", 0) or 0) == 0 else "sell",
                    "qty": float(getattr(row, "volume", 0) or 0),
                    "price": float(getattr(row, "price", 0) or 0),
                    "profit": float(getattr(row, "profit", 0) or 0),
                    "commission": float(getattr(row, "commission", 0) or 0),
                    "swap": float(getattr(row, "swap", 0) or 0),
                    "entry": int(getattr(row, "entry", 0) or 0),
                    "position_id": str(int(getattr(row, "position_id", 0) or 0) or ""),
                    "magic": int(getattr(row, "magic", 0) or 0),
                    "comment": str(getattr(row, "comment", "") or ""),
                    "time": (
                        datetime.fromtimestamp(ts - server_offset, tz=timezone.utc).isoformat()
                        if ts else ""
                    ),
                    "time_msc": int(getattr(row, "time_msc", 0) or 0) or None,
                }
            )
        return out

    def history_orders(self, lookback_days: int = 14) -> list[dict[str, Any]]:
        """Read-only order history. Does not place orders. Caller must not shutdown()."""
        mt5 = self._require()
        end = datetime.now(timezone.utc).replace(tzinfo=None)
        start = end - timedelta(days=max(1, int(lookback_days)))
        raw = mt5.history_orders_get(start, end)
        if raw is None:
            return []
        out: list[dict[str, Any]] = []
        for row in raw:
            ts = int(getattr(row, "time_setup", 0) or getattr(row, "time_done", 0) or 0)
            out.append(
                {
                    "ticket": str(int(getattr(row, "ticket", 0) or 0)),
                    "symbol": str(getattr(row, "symbol", "") or ""),
                    "state": int(getattr(row, "state", 0) or 0),
                    "type": int(getattr(row, "type", 0) or 0),
                    "qty": float(getattr(row, "volume_initial", 0) or 0),
                    "price_open": float(getattr(row, "price_open", 0) or 0),
                    "sl": float(getattr(row, "sl", 0) or 0),
                    "tp": float(getattr(row, "tp", 0) or 0),
                    "magic": int(getattr(row, "magic", 0) or 0),
                    "comment": str(getattr(row, "comment", "") or ""),
                    "time": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat() if ts else "",
                }
            )
        return out

    def _filling(self, info: Any) -> int:
        mt5 = self._api()
        override = str(self.cfg.get("mt5_filling") or "").strip().upper()
        if override == "FOK":
            return int(getattr(mt5, "ORDER_FILLING_FOK", 0))
        if override == "IOC":
            return int(getattr(mt5, "ORDER_FILLING_IOC", 1))
        if override == "RETURN":
            return int(getattr(mt5, "ORDER_FILLING_RETURN", 2))
        mode = int(getattr(info, "filling_mode", 0) or 0)
        # SYMBOL_FILLING_FOK=1, IOC=2, RETURN=4
        if mode & 2:
            return int(getattr(mt5, "ORDER_FILLING_IOC", 1))
        if mode & 1:
            return int(getattr(mt5, "ORDER_FILLING_FOK", 0))
        return int(getattr(mt5, "ORDER_FILLING_RETURN", 2))

    def _normalize_lots(self, quantity: float, info: Any) -> tuple[Optional[float], str]:
        if quantity >= _UNITS_QTY_FLOOR:
            return None, (
                f"quantity {quantity} looks like FX units; MT5 uses lots "
                f"(e.g. 0.01). Refusing oversized size."
            )
        step = float(getattr(info, "volume_step", 0.01) or 0.01)
        vmin = float(getattr(info, "volume_min", 0.01) or 0.01)
        vmax = float(getattr(info, "volume_max", 100.0) or 100.0)
        cap = min(vmax, self.max_lots)
        lots = math.floor((quantity + 1e-12) / step) * step
        lots = round(lots, 8)
        if lots + 1e-12 < vmin:
            return None, f"quantity {quantity} below min lot {vmin}"
        if lots > cap + 1e-12:
            return None, f"quantity {lots} exceeds mt5_max_lots={self.max_lots}"
        return lots, ""

    def _round_price(self, price: float, info: Any) -> float:
        tick = float(getattr(info, "trade_tick_size", 0) or 0) or float(getattr(info, "point", 0) or 0)
        digits = int(getattr(info, "digits", 5) or 5)
        if tick > 0:
            price = round(round(price / tick) * tick, digits)
        return round(price, digits)

    @staticmethod
    def _sanitize_comment(tag: str) -> str:
        return sanitize_mt5_comment(tag)

    def _mutation_allowed(self) -> Optional[str]:
        acct = self.account()
        if not acct.is_paper and not self.allow_live:
            return "refusing mutation on non-demo MT5 account"
        return None

    def place_order(self, req: OrderRequest) -> OrderResult:
        blocked = self._mutation_allowed()
        if blocked:
            return OrderResult(ok=False, message=blocked)
        mt5 = self._require()
        name = self._resolve_symbol(req.symbol)
        info = self._ensure_symbol(name)
        lots, err = self._normalize_lots(float(req.quantity), info)
        if lots is None:
            return OrderResult(ok=False, message=err)
        tick = mt5.symbol_info_tick(name)
        if tick is None:
            return OrderResult(ok=False, message=f"no tick for {name}")
        filling = self._filling(info)
        comment = self._sanitize_comment(req.client_tag or "aegis")
        sl = self._round_price(float(req.stop_loss), info) if req.stop_loss is not None else 0.0
        tp = self._round_price(float(req.take_profit), info) if req.take_profit is not None else 0.0
        if req.kind == "limit":
            if req.limit_price is None:
                return OrderResult(ok=False, message="limit_price required")
            price = self._round_price(float(req.limit_price), info)
            order_type = (
                int(getattr(mt5, "ORDER_TYPE_BUY_LIMIT", 2))
                if req.side == "buy"
                else int(getattr(mt5, "ORDER_TYPE_SELL_LIMIT", 3))
            )
            action = int(getattr(mt5, "TRADE_ACTION_PENDING", 5))
        else:
            order_type = (
                int(getattr(mt5, "ORDER_TYPE_BUY", 0))
                if req.side == "buy"
                else int(getattr(mt5, "ORDER_TYPE_SELL", 1))
            )
            action = int(getattr(mt5, "TRADE_ACTION_DEAL", 1))
            price = self._round_price(
                float(tick.ask if req.side == "buy" else tick.bid),
                info,
            )
        request = {
            "action": action,
            "symbol": name,
            "volume": lots,
            "type": order_type,
            "price": price,
            "sl": sl,
            "tp": tp,
            "deviation": self.deviation,
            "magic": self.magic,
            "comment": comment,
            "type_time": int(getattr(mt5, "ORDER_TIME_GTC", 0)),
            "type_filling": filling,
        }
        result = mt5.order_send(request)
        if result is None:
            return OrderResult(ok=False, message=f"order_send returned None ({self._last_error()})")
        retcode = int(getattr(result, "retcode", 0) or 0)
        ticket = str(int(getattr(result, "order", 0) or 0))
        msg = str(getattr(result, "comment", "") or f"retcode={retcode}")
        if retcode not in _OK_RETCODES:
            return OrderResult(ok=False, broker_order_id=ticket, message=f"{retcode} {msg}")
        fill_price = float(getattr(result, "price", 0) or 0) or None
        filled = retcode in {10009, 10010}
        return OrderResult(
            ok=True,
            broker_order_id=ticket,
            message=msg,
            filled=filled,
            fill_price=fill_price,
        )

    def cancel_order(self, broker_order_id: str) -> OrderResult:
        blocked = self._mutation_allowed()
        if blocked:
            return OrderResult(ok=False, message=blocked)
        mt5 = self._require()
        try:
            ticket = int(broker_order_id)
        except (TypeError, ValueError):
            return OrderResult(ok=False, broker_order_id=str(broker_order_id), message="invalid order id")
        request = {
            "action": int(getattr(mt5, "TRADE_ACTION_REMOVE", 8)),
            "order": ticket,
        }
        result = mt5.order_send(request)
        if result is None:
            return OrderResult(
                ok=False,
                broker_order_id=str(ticket),
                message=f"cancel returned None ({self._last_error()})",
            )
        retcode = int(getattr(result, "retcode", 0) or 0)
        msg = str(getattr(result, "comment", "") or f"retcode={retcode}")
        if retcode not in _OK_RETCODES:
            return OrderResult(ok=False, broker_order_id=str(ticket), message=f"{retcode} {msg}")
        return OrderResult(ok=True, broker_order_id=str(ticket), message="cancelled")

    def working_orders(self, symbol: Optional[str] = None) -> list[Any]:
        mt5 = self._require()
        name = self._resolve_symbol(symbol) if symbol else None
        raw = mt5.orders_get(symbol=name) if name else mt5.orders_get()
        if raw is None:
            return []
        return list(raw)

    def cancel_all_orders(
        self,
        timeout_s: float = 10.0,
        poll_s: float = 0.2,
        symbol: Optional[str] = None,
    ) -> OrderResult:
        blocked = self._mutation_allowed()
        if blocked:
            return OrderResult(ok=False, message=blocked)
        deadline = time.monotonic() + max(0.0, float(timeout_s))
        last_fail = ""
        while True:
            open_orders = self.working_orders(symbol)
            if not open_orders:
                return OrderResult(ok=True, message="all orders cleared")
            for order in open_orders:
                ticket = str(int(getattr(order, "ticket", 0) or 0))
                res = self.cancel_order(ticket)
                if not res.ok:
                    last_fail = res.message
            if time.monotonic() >= deadline:
                left = [int(getattr(o, "ticket", 0) or 0) for o in self.working_orders(symbol)]
                return OrderResult(
                    ok=False,
                    message=f"orders did not clear before timeout: {left} {last_fail}",
                )
            time.sleep(max(0.0, min(float(poll_s), deadline - time.monotonic())))

    def _close_position(self, pos: Any) -> OrderResult:
        mt5 = self._require()
        name = str(getattr(pos, "symbol", "") or "")
        info = self._ensure_symbol(name)
        tick = mt5.symbol_info_tick(name)
        if tick is None:
            return OrderResult(ok=False, message=f"no tick to close {name}")
        pos_type = int(getattr(pos, "type", 0) or 0)
        volume = float(getattr(pos, "volume", 0) or 0)
        ticket = int(getattr(pos, "ticket", 0) or 0)
        close_type = (
            int(getattr(mt5, "ORDER_TYPE_SELL", 1))
            if pos_type == 0
            else int(getattr(mt5, "ORDER_TYPE_BUY", 0))
        )
        price = self._round_price(float(tick.bid if pos_type == 0 else tick.ask), info)
        request = {
            "action": int(getattr(mt5, "TRADE_ACTION_DEAL", 1)),
            "symbol": name,
            "volume": volume,
            "type": close_type,
            "position": ticket,
            "price": price,
            "deviation": self.deviation,
            "magic": self.magic,
            "comment": "aegis_flatten"[:31],
            "type_time": int(getattr(mt5, "ORDER_TIME_GTC", 0)),
            "type_filling": self._filling(info),
        }
        result = mt5.order_send(request)
        if result is None:
            return OrderResult(ok=False, message=f"flatten send None ({self._last_error()})")
        retcode = int(getattr(result, "retcode", 0) or 0)
        msg = str(getattr(result, "comment", "") or f"retcode={retcode}")
        if retcode not in _OK_RETCODES:
            return OrderResult(ok=False, message=f"{retcode} {msg}")
        return OrderResult(ok=True, broker_order_id=str(ticket), message=msg)

    def close_ticket(self, ticket: str) -> OrderResult:
        """Close one position by ticket. Does not flatten the rest of the book."""
        blocked = self._mutation_allowed()
        if blocked:
            return OrderResult(ok=False, message=blocked)
        mt5 = self._require()
        want = int(str(ticket).strip() or 0)
        if want <= 0:
            return OrderResult(ok=False, message="invalid ticket")
        for pos in mt5.positions_get() or []:
            if int(getattr(pos, "ticket", 0) or 0) == want:
                return self._close_position(pos)
        return OrderResult(ok=False, message=f"ticket {ticket} not open")

    def modify_stops(self, ticket: str, *, stop_loss: Optional[float] = None,
                     take_profit: Optional[float] = None) -> ModifyResult:
        """Adjust protective stops on an open position (TRADE_ACTION_SLTP).

        Refuses to LOOSEN: a new stop-loss must be tighter (closer to current
        price on the protective side) than the existing one.
        """
        blocked = self._mutation_allowed()
        if blocked:
            return ModifyResult(ok=False, message=blocked)
        mt5 = self._require()
        want = int(str(ticket).strip() or 0)
        if want <= 0:
            return ModifyResult(ok=False, message="invalid ticket")
        target = None
        for pos in mt5.positions_get() or []:
            if int(getattr(pos, "ticket", 0) or 0) == want:
                target = pos
                break
        if target is None:
            return ModifyResult(ok=False, message=f"ticket {ticket} not open")
        cur_sl = float(getattr(target, "sl", 0) or 0)
        cur_tp = float(getattr(target, "tp", 0) or 0)
        side_buy = int(getattr(target, "type", 0) or 0) == 0
        new_sl = float(stop_loss) if stop_loss is not None else (cur_sl or None)
        if new_sl is not None and cur_sl > 0:
            if side_buy and float(new_sl) < cur_sl - 1e-12:
                return ModifyResult(ok=False,
                                    message="refusing to loosen stop-loss (buy)")
            if not side_buy and float(new_sl) > cur_sl + 1e-12:
                return ModifyResult(ok=False,
                                    message="refusing to loosen stop-loss (sell)")
        req = {
            "action": mt5.TRADE_ACTION_SLTP,
            "position": want,
            "symbol": str(getattr(target, "symbol", "") or ""),
            "sl": float(new_sl) if new_sl else 0.0,
            "tp": float(take_profit) if take_profit is not None else cur_tp,
        }
        res = mt5.order_send(req)
        retcode = int(getattr(res, "retcode", 1) or 1)
        ok = retcode == 10009  # TRADE_RETCODE_DONE
        return ModifyResult(
            ok=ok,
            message=str(getattr(res, "comment", retcode) or retcode),
            stop_loss=new_sl,
            take_profit=req["tp"] or None,
        )

    def flatten_positions(
        self,
        symbol: Optional[str] = None,
        timeout_s: float = 15.0,
        poll_s: float = 0.2,
    ) -> OrderResult:
        blocked = self._mutation_allowed()
        if blocked:
            return OrderResult(ok=False, message=blocked)
        mt5 = self._require()
        cleared = self.cancel_all_orders(timeout_s=timeout_s, poll_s=poll_s, symbol=symbol)
        if not cleared.ok:
            return OrderResult(ok=False, message=f"pre-flatten cancel failed: {cleared.message}")
        name = self._resolve_symbol(symbol) if symbol else None
        raw = mt5.positions_get(symbol=name) if name else mt5.positions_get()
        for pos in raw or []:
            result = self._close_position(pos)
            if not result.ok:
                return OrderResult(ok=False, message=f"flatten close failed: {result.message}")
        deadline = time.monotonic() + max(0.0, float(timeout_s))
        while self.positions(symbol):
            if time.monotonic() >= deadline:
                return OrderResult(ok=False, message="positions did not flatten before timeout")
            leftover = mt5.positions_get(symbol=name) if name else mt5.positions_get()
            for pos in leftover or []:
                self._close_position(pos)
            time.sleep(max(0.0, min(float(poll_s), deadline - time.monotonic())))
        final_cancel = self.cancel_all_orders(timeout_s=timeout_s, poll_s=poll_s, symbol=symbol)
        if not final_cancel.ok:
            return OrderResult(ok=False, message=f"post-flatten cancel failed: {final_cancel.message}")
        if self.positions(symbol):
            return OrderResult(ok=False, message="flatten verification found an open position")
        return OrderResult(ok=True, message="positions flat and orders cleared")
