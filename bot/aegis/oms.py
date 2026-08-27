"""Donadio/Ghosh/Rossier OMS + tick-to-trade (2022).

*Developing High-Frequency Trading Systems* Ch.2: the OMS rejects malformed
orders *before* they leave the box (qty, side, stops, outstanding position).
Ch.2 also defines tick-to-trade as the timer from price-update-in to order-out.
Ch.7: live stats off the critical path; logging must not invent a C++/FPGA stack.

This is not colocation HFT and not a 100% WR claim. Python stays the research
path (their Ch.10); MT5 M1 cannot become a 100µs tick-to-trade system.
"""
from __future__ import annotations

import re
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Any

from aegis.engines.base import OrderRequest, Quote

# MetaTrader 5 TRADE_RETCODE_MARKET_CLOSED. Not 10019 TRADE_RETCODE_NO_MONEY.
MARKET_CLOSED_RETCODES = frozenset({10018})
_RETCODE_RE = re.compile(r"(?<!\d)(\d{5})(?!\d)")
_WEEKDAY_CLOSE_BACKOFF_S = 900.0
_FX_WEEKEND_OPEN_HOUR_UTC = 21


def _retcodes_in_message(message: str | None) -> set[int]:
    return {int(tok) for tok in _RETCODE_RE.findall(str(message or ""))}


def is_market_closed_retcode(message: str | None) -> bool:
    """True when a close/flatten reply is MT5 market-closed (10018).

    10019 (no money / margin) is never treated as market-closed.
    """
    text = str(message or "")
    codes = _retcodes_in_message(text)
    if 10019 in codes:
        return False
    if codes & MARKET_CLOSED_RETCODES:
        return True
    return "market closed" in text.casefold()


def _in_fx_weekend(now: datetime) -> bool:
    wd = now.weekday()
    hour = now.hour
    if wd == 5:
        return True
    if wd == 6 and hour < _FX_WEEKEND_OPEN_HOUR_UTC:
        return True
    if wd == 4 and hour >= _FX_WEEKEND_OPEN_HOUR_UTC:
        return True
    return False


def market_closed_backoff_until(
    now: datetime | None = None,
    *,
    weekday_backoff_s: float = _WEEKDAY_CLOSE_BACKOFF_S,
    weekend_open_hour_utc: int = _FX_WEEKEND_OPEN_HOUR_UTC,
) -> datetime:
    """Next close attempt after 10018.

    Weekend (Fri >= 21:00 UTC through Sun 21:00 UTC): skip until Sunday open.
    Weekday / holiday 10018: short backoff so never_green still fires on open sessions.
    """
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    else:
        now = now.astimezone(timezone.utc)
    if _in_fx_weekend(now):
        days = (6 - now.weekday()) % 7
        candidate = now.replace(
            hour=int(weekend_open_hour_utc), minute=0, second=0, microsecond=0
        ) + timedelta(days=days)
        if candidate <= now:
            candidate += timedelta(days=7)
        return candidate
    return now + timedelta(seconds=max(1.0, float(weekday_backoff_s)))


def close_attempt_blocked(now_ts: float, until_ts: float) -> bool:
    return float(until_ts or 0.0) > 0.0 and float(now_ts) < float(until_ts)


def open_attempt_blocked(now_ts: float, until_ts: float) -> bool:
    """Same 10018 clock as flatten. New market orders must not retry while blocked.

    10019 (margin) never sets this clock; callers keep a separate per-poll skip.
    """
    return close_attempt_blocked(now_ts, until_ts)


def update_close_backoff(
    prev_until: float,
    message: str | None,
    now: datetime | None = None,
) -> float:
    """Keep prev_until unless the close/flatten/open message is 10018."""
    if not is_market_closed_retcode(message):
        return float(prev_until or 0.0)
    until = market_closed_backoff_until(now)
    return max(float(prev_until or 0.0), until.timestamp())


def _quote_delta_s(quote: Quote, now: datetime | None = None) -> float | None:
    """Signed seconds between now and the quote timestamp. Positive = quote is old."""
    now = now or datetime.now(timezone.utc)
    ts = quote.time
    if ts is None:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return (now - ts).total_seconds()


def quote_age_s(quote: Quote, now: datetime | None = None) -> float:
    """Age of a quote in seconds, clamped at zero. Missing timestamp is infinitely old."""
    delta = _quote_delta_s(quote, now)
    if delta is None:
        return float("inf")
    return max(0.0, delta)


def quote_future_skew_s(quote: Quote, now: datetime | None = None) -> float:
    """Seconds the quote timestamp runs *ahead* of now, else 0.0.

    ``quote_age_s`` clamps at zero, so a quote stamped in the future reported an age
    of 0.0 and sailed through the staleness gate as though it were perfectly fresh.
    A future timestamp means broker clock skew or corrupt tick data, and pricing a
    trade off it is exactly the case the staleness check exists to prevent. Missing
    timestamps are handled by ``quote_age_s`` returning infinity, not here.
    """
    delta = _quote_delta_s(quote, now)
    if delta is None:
        return 0.0
    return max(0.0, -delta)


def oms_allows(
    req: OrderRequest,
    quote: Quote,
    cfg: dict[str, Any],
    *,
    open_count: int = 0,
    now: datetime | None = None,
    check_quote_age: bool = True,
) -> tuple[bool, str]:
    """Local OMS gate. True, '' when the order may leave the box."""
    if not bool(cfg.get("oms_pretrade", False)):
        return True, ""
    side = str(req.side or "").lower()
    if side not in {"buy", "sell"}:
        return False, "side"
    qty = float(req.quantity or 0.0)
    if qty <= 0:
        return False, "qty"
    max_lots = float(cfg.get("mt5_max_lots", 0) or 0)
    if max_lots > 0 and qty > max_lots + 1e-12:
        return False, "max_lots"
    max_pos = int(cfg.get("max_positions", 0) or 0)
    if max_pos > 0 and int(open_count) >= max_pos:
        return False, "max_positions"
    bid = float(quote.bid or 0.0)
    ask = float(quote.ask or 0.0)
    if bid <= 0 or ask <= 0 or ask + 1e-12 < bid:
        return False, "crossed_quote"
    if check_quote_age:
        max_age = float(cfg.get("max_quote_age_s", 5.0) or 0.0)
        if max_age > 0 and quote_age_s(quote, now) > max_age:
            return False, "stale_quote"
        # Symmetric with the staleness gate: if now-vs-timestamp is trusted enough to
        # reject an old quote, a quote from the future is just as untrustworthy.
        max_skew = float(cfg.get("max_quote_future_skew_s", max_age) or 0.0)
        if max_skew > 0 and quote_future_skew_s(quote, now) > max_skew:
            return False, "future_quote"
    # Intelligent Firehose orders carry virtual strategy geometry alongside
    # optional emergency broker protection. If either broker-side override is
    # explicit, validate only those levels here; the virtual levels belong to
    # TradeController and must not be subjected to MT5 stop-distance checks.
    # Legacy requests without overrides retain the historical behavior.
    has_broker_geometry = (
        req.broker_stop_loss is not None or req.broker_take_profit is not None
    )
    sl = req.broker_stop_loss if has_broker_geometry else req.stop_loss
    tp = req.broker_take_profit if has_broker_geometry else req.take_profit
    if sl is not None:
        sl_f = float(sl)
        if side == "buy" and sl_f >= bid - 1e-12:
            return False, "stops"
        if side == "sell" and sl_f <= ask + 1e-12:
            return False, "stops"
    if tp is not None:
        tp_f = float(tp)
        if side == "buy" and tp_f <= ask + 1e-12:
            return False, "stops"
        if side == "sell" and tp_f >= bid - 1e-12:
            return False, "stops"
    return True, ""


class TickToTrade:
    """In-memory t2t samples + reject counts. No extra disk on the hot path."""

    def __init__(self, n: int = 256) -> None:
        self.samples_ms: deque[float] = deque(maxlen=max(8, int(n)))
        self.oms_rejects = 0
        self.quote_stale = 0

    def record_ms(self, ms: float) -> None:
        if ms >= 0:
            self.samples_ms.append(float(ms))

    def note_reject(self, reason: str) -> None:
        if reason == "stale_quote":
            self.quote_stale += 1
        else:
            self.oms_rejects += 1

    def snapshot(self) -> dict[str, Any]:
        xs = sorted(self.samples_ms)
        out: dict[str, Any] = {
            "t2t_n": len(xs),
            "oms_rejects": int(self.oms_rejects),
            "quote_stale": int(self.quote_stale),
        }
        if xs:
            out["t2t_p50_ms"] = round(xs[len(xs) // 2], 3)
            out["t2t_p95_ms"] = round(xs[int(0.95 * (len(xs) - 1))], 3)
            out["t2t_last_ms"] = round(self.samples_ms[-1], 3)
        return out
