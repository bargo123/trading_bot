"""Interactive Brokers engine (paper via Gateway port 7497, live 7496)."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from aegis.engines.base import (
    AccountSnapshot,
    Bar,
    BrokerEngine,
    OrderRequest,
    OrderResult,
    PositionSnapshot,
    Quote,
)
from aegis.engines.ibkr_order_state import cancelling_trades, working_trades

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class QuoteSubscription:
    symbol: str
    contract: Any
    ticker: Any

_TF_BAR_SIZE = {
    "1s": "1 secs",
    "5s": "5 secs",
    "10s": "10 secs",
    "15s": "15 secs",
    "30s": "30 secs",
    "1m": "1 min",
    "5m": "5 mins",
    "15m": "15 mins",
    "1h": "1 hour",
    "1d": "1 day",
}

# IB historical caps for second bars (durationStr)
_TF_MAX_DURATION_S = {
    "1s": 1800,
    "5s": 3600,
    "10s": 14400,
    "15s": 14400,
    "30s": 28800,
}


class IBKREngine(BrokerEngine):
    name = "ibkr"

    def __init__(self, cfg: dict[str, Any]) -> None:
        self.cfg = cfg
        self.host = str(cfg.get("ib_host", "127.0.0.1"))
        # Gateway paper=4002, Gateway live=4001, TWS paper=7497, TWS live=7496
        self.port = int(cfg.get("ib_port", 4002))
        allow_live = bool(cfg.get("allow_live", False))
        if self.port in {7496, 4001} and not allow_live:
            raise RuntimeError(
                f"IB port {self.port} is typically LIVE. Set allow_live: true only when intentional."
            )
        self.client_id = int(cfg.get("ib_client_id", 7))
        self._ib = None
        self._contracts: dict[str, Any] = {}

    def connect(self) -> None:
        from ib_insync import IB

        if self._ib is not None and self._ib.isConnected():
            return
        ib = IB()
        ib.connect(self.host, self.port, clientId=self.client_id, readonly=False)
        self._ib = ib
        logger.info("IBKR connected %s:%s clientId=%s", self.host, self.port, self.client_id)

    def disconnect(self) -> None:
        if self._ib is not None:
            try:
                self._ib.disconnect()
            finally:
                self._ib = None

    def _require(self):
        if self._ib is None or not self._ib.isConnected():
            raise RuntimeError("IBKREngine not connected — call connect() first")
        return self._ib

    def _is_paper(self) -> bool:
        # Prefer port heuristic; paper Gateway is 4002 / TWS paper 7497
        return self.port in {7497, 4002}

    def _contract_definition(self, symbol: str) -> dict[str, object]:
        key = symbol.upper().replace("=X", "").replace("/", "")
        if key != "MGC":
            raise ValueError(f"No explicit futures contract definition for {symbol}")
        expiry = str(self.cfg.get("ib_futures_expiry", "") or "")
        exchange = str(self.cfg.get("ib_futures_exchange", "COMEX") or "COMEX").upper()
        multiplier = float(self.cfg.get("contract_multiplier", 0.0) or 0.0)
        tick_size = float(self.cfg.get("tick_size", 0.0) or 0.0)
        if len(expiry) != 6 or not expiry.isdigit():
            raise ValueError("MGC requires ib_futures_expiry in YYYYMM format")
        if exchange != "COMEX":
            raise ValueError("MGC requires ib_futures_exchange: COMEX")
        if multiplier != 10.0:
            raise ValueError("MGC requires contract_multiplier: 10")
        if tick_size != 0.1:
            raise ValueError("MGC requires tick_size: 0.1")
        return {
            "sec_type": "FUT",
            "symbol": "MGC",
            "exchange": exchange,
            "currency": "USD",
            "expiry": expiry,
            "multiplier": multiplier,
            "tick_size": tick_size,
        }

    def _contract(self, symbol: str):
        ib = self._require()
        key = symbol.upper().replace("=X", "").replace("/", "")
        definition = self._contract_definition(symbol) if key == "MGC" else None
        cache_key = f"{key}:{definition['expiry']}" if definition else key
        if cache_key in self._contracts:
            return self._contracts[cache_key]

        from ib_insync import ContFuture, Forex, Future, Stock

        if key in {
            "EURUSD",
            "GBPUSD",
            "AUDUSD",
            "NZDUSD",
            "USDCAD",
            "USDJPY",
            "EURJPY",
            "GBPJPY",
        }:
            contract = Forex(key)
        elif key == "MGC":
            contract = Future(
                "MGC",
                str(definition["expiry"]),
                str(definition["exchange"]),
                currency="USD",
                multiplier=str(int(float(definition["multiplier"]))),
            )
        elif key in {"GC", "GCF"} or symbol.upper() in {"GC=F", "GC"}:
            contract = ContFuture("GC", "COMEX")
        else:
            contract = Stock(key, "SMART", "USD")

        qualified = ib.qualifyContracts(contract)
        if not qualified:
            raise RuntimeError(f"Could not qualify IB contract for {symbol}")
        resolved = qualified[0]
        if key == "MGC":
            if str(getattr(resolved, "secType", "")).upper() != "FUT":
                raise RuntimeError("MGC order contract must be a dated FUT, not a continuous future")
            if str(getattr(resolved, "symbol", "")).upper() != "MGC":
                raise RuntimeError("Qualified contract is not MGC")
            if float(getattr(resolved, "multiplier", 0.0) or 0.0) != 10.0:
                raise RuntimeError("Qualified MGC multiplier is not 10")
        self._contracts[cache_key] = resolved
        return self._contracts[cache_key]

    def contract_metadata(self, symbol: str) -> dict[str, object]:
        contract = self._contract(symbol)
        key = symbol.upper().replace("=X", "").replace("/", "")
        definition = self._contract_definition(symbol) if key == "MGC" else None
        return {
            "symbol": str(getattr(contract, "symbol", key) or key),
            "local_symbol": str(getattr(contract, "localSymbol", "") or key),
            "con_id": int(getattr(contract, "conId", 0) or 0),
            "sec_type": str(getattr(contract, "secType", "") or ""),
            "expiry": str(getattr(contract, "lastTradeDateOrContractMonth", "") or ""),
            "exchange": str(getattr(contract, "exchange", "") or ""),
            "currency": str(getattr(contract, "currency", "") or ""),
            "multiplier": float(getattr(contract, "multiplier", 1.0) or 1.0),
            "tick_size": float(definition["tick_size"]) if definition else 0.0,
        }

    def account(self) -> AccountSnapshot:
        ib = self._require()
        # accountValues is a maintained connection cache. Calling accountSummary()
        # in the poll loop stacks subscriptions and eventually triggers IB Error 322.
        by: dict[str, str] = {}
        for v in ib.accountValues():
            if v.currency == "USD":
                by[v.tag] = v.value
        if "NetLiquidation" not in by:
            for v in ib.accountValues():
                if v.currency in ("BASE", ""):
                    by.setdefault(v.tag, v.value)
        if "NetLiquidation" not in by:
            raise RuntimeError(
                "IB accountValues cache has no NetLiquidation yet; "
                "wait for account synchronization instead of opening a summary subscription"
            )
        currency = by.get("Currency", by.get("BaseCurrency", "USD"))
        equity = float(by.get("NetLiquidation", by.get("EquityWithLoanValue", "0") or 0))
        avail = float(by.get("AvailableFunds", by.get("ExcessLiquidity", "0") or 0))
        accts = ib.managedAccounts() or [""]
        return AccountSnapshot(
            account_id=str(accts[0]),
            equity=equity,
            currency=str(currency),
            available_funds=avail,
            is_paper=self._is_paper(),
            raw={k: by[k] for k in list(by)[:40]},
        )

    def quote(self, symbol: str) -> Quote:
        ib = self._require()
        contract = self._contract(symbol)
        tickers = ib.reqTickers(contract)
        if not tickers:
            raise RuntimeError(f"No ticker for {symbol}")
        t = tickers[0]
        bid = float(t.bid) if t.bid and t.bid > 0 else float(t.close or 0)
        ask = float(t.ask) if t.ask and t.ask > 0 else float(t.close or 0)
        if bid <= 0 and ask <= 0:
            raise RuntimeError(f"No bid/ask for {symbol} (market data permission?)")
        if bid <= 0:
            bid = ask
        if ask <= 0:
            ask = bid
        ts = t.time if getattr(t, "time", None) else datetime.now(timezone.utc)
        if getattr(ts, "tzinfo", None) is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return Quote(symbol=symbol, bid=bid, ask=ask, time=ts)

    def subscribe_quote(self, symbol: str) -> QuoteSubscription:
        """Open one persistent streaming subscription for a qualified contract."""
        ib = self._require()
        contract = self._contract(symbol)
        ib.reqMarketDataType(int(self.cfg.get("ib_market_data_type", 1)))
        ticker = ib.reqMktData(contract, "", False, False)
        return QuoteSubscription(symbol=symbol, contract=contract, ticker=ticker)

    def cancel_quote(self, subscription: QuoteSubscription) -> None:
        self._require().cancelMktData(subscription.contract)

    def bars(self, symbol: str, timeframe: str, lookback_days: int) -> list[Bar]:
        import pandas as pd
        from ib_insync import Forex

        ib = self._require()
        contract = self._contract(symbol)
        bar_size = _TF_BAR_SIZE.get(timeframe)
        if not bar_size:
            raise ValueError(f"Unsupported timeframe for IBKR: {timeframe}")

        if timeframe in _TF_MAX_DURATION_S:
            # Second bars: IB requires duration in seconds, with hard caps
            want = int(self.cfg.get("lookback_seconds", _TF_MAX_DURATION_S[timeframe]))
            dur_s = max(60, min(want, _TF_MAX_DURATION_S[timeframe]))
            duration = f"{dur_s} S"
        else:
            days = max(1, int(lookback_days))
            if days <= 7:
                duration = f"{days} D"
            else:
                duration = f"{min(days, 365)} D"

        what = "MIDPOINT" if isinstance(contract, Forex) else "TRADES"
        raw = ib.reqHistoricalData(
            contract,
            endDateTime="",
            durationStr=duration,
            barSizeSetting=bar_size,
            whatToShow=what,
            useRTH=False,
            formatDate=1,
        )
        out: list[Bar] = []
        for b in raw:
            ts = b.date
            if isinstance(ts, str):
                ts = pd.Timestamp(ts, tz="UTC").to_pydatetime()
            elif getattr(ts, "tzinfo", None) is None:
                ts = ts.replace(tzinfo=timezone.utc)
            out.append(
                Bar(
                    time=ts,
                    open=float(b.open),
                    high=float(b.high),
                    low=float(b.low),
                    close=float(b.close),
                    volume=float(getattr(b, "volume", 0) or 0),
                )
            )
        return out

    def positions(self, symbol: Optional[str] = None) -> list[PositionSnapshot]:
        ib = self._require()
        pair = symbol.upper().replace("=X", "").replace("/", "") if symbol else None
        out: list[PositionSnapshot] = []
        for p in ib.positions():
            c = p.contract
            label = f"{c.symbol}{getattr(c, 'currency', '')}"
            if pair and label != pair and c.symbol != pair:
                continue
            qty = float(p.position)
            if abs(qty) < 1e-12:
                continue
            out.append(
                PositionSnapshot(
                    symbol=symbol or label,
                    side="buy" if qty > 0 else "sell",
                    quantity=abs(qty),
                    avg_price=float(p.avgCost),
                )
            )
        return out

    def place_order(self, req: OrderRequest) -> OrderResult:
        from ib_insync import LimitOrder, MarketOrder, StopOrder

        ib = self._require()
        contract = self._contract(req.symbol)
        if str(getattr(contract, "secType", "")).upper() == "CONTFUT":
            return OrderResult(ok=False, message="continuous futures are data-only")
        action = "BUY" if req.side == "buy" else "SELL"
        reverse = "SELL" if action == "BUY" else "BUY"

        if req.kind == "limit":
            if req.limit_price is None:
                return OrderResult(ok=False, message="limit_price required")
            parent = LimitOrder(action, req.quantity, req.limit_price)
        else:
            parent = MarketOrder(action, req.quantity)
        parent.orderId = ib.client.getReqId()
        parent.orderRef = req.client_tag or "aegis"
        parent.tif = str(self.cfg.get("ib_order_tif", "GTC")).upper()
        account = str(self.cfg.get("ib_account", "") or "")
        if account:
            parent.account = account

        children = []
        if req.take_profit is not None:
            tp = LimitOrder(reverse, req.quantity, float(req.take_profit))
            tp.orderId = ib.client.getReqId()
            tp.parentId = parent.orderId
            tp.orderRef = parent.orderRef
            tp.tif = parent.tif
            if account:
                tp.account = account
            children.append(tp)
        if req.stop_loss is not None:
            sl = StopOrder(reverse, req.quantity, float(req.stop_loss))
            sl.orderId = ib.client.getReqId()
            sl.parentId = parent.orderId
            sl.orderRef = parent.orderRef
            sl.tif = parent.tif
            if account:
                sl.account = account
            children.append(sl)

        parent.transmit = not children
        for child in children:
            child.transmit = False
        if children:
            children[-1].transmit = True

        orders = [parent, *children]
        trades = []
        try:
            # All IDs and linkage are fixed before the first order reaches IB.
            trades = [ib.placeOrder(contract, order) for order in orders]
        except Exception as exc:
            self._cancel_order_chain(ib, orders)
            return OrderResult(
                ok=False,
                broker_order_id=str(parent.orderId),
                message=f"submission failed: {exc}",
            )

        trade = trades[0]
        accepted = {"presubmitted", "submitted", "filled"}
        terminal = {"cancelled", "apicancelled", "inactive"}
        timeout_s = max(0.0, float(self.cfg.get("ib_order_ack_timeout", 5.0)))
        deadline = time.monotonic() + timeout_s
        statuses: list[str] = []
        while True:
            statuses = [
                str(getattr(getattr(item, "orderStatus", None), "status", "") or "")
                for item in trades
            ]
            normalized = [status.casefold() for status in statuses]
            failed_index = next(
                (index for index, status in enumerate(normalized) if status in terminal),
                None,
            )
            if failed_index is not None:
                self._cancel_order_chain(ib, orders)
                leg = "parent" if failed_index == 0 else "child"
                return OrderResult(
                    ok=False,
                    broker_order_id=str(parent.orderId),
                    message=f"{leg} not accepted: {statuses[failed_index]}",
                )
            if all(status in accepted for status in normalized):
                break
            if time.monotonic() >= deadline:
                self._cancel_order_chain(ib, orders)
                missing_index = next(
                    (index for index, status in enumerate(normalized) if status not in accepted),
                    0,
                )
                leg = "parent" if missing_index == 0 else "child"
                reason = statuses[missing_index] or "ack timeout"
                return OrderResult(
                    ok=False,
                    broker_order_id=str(parent.orderId),
                    message=f"{leg} not accepted: {reason}",
                )
            ib.sleep(min(0.05, max(0.0, deadline - time.monotonic())))

        status = statuses[0]
        filled = status.casefold() == "filled"
        fill_price = None
        if trade.fills:
            fill_price = float(trade.fills[-1].execution.avgPrice)
        return OrderResult(
            ok=True,
            broker_order_id=str(parent.orderId),
            message=f"status={status}",
            filled=filled,
            fill_price=fill_price,
        )

    @staticmethod
    def _cancel_order_chain(ib, orders: list[Any]) -> None:
        for order in orders:
            try:
                ib.cancelOrder(order)
            except Exception:
                logger.exception("Failed to cancel IB order %s during chain cleanup", order.orderId)
        try:
            ib.sleep(0.2)
        except Exception:
            pass

    def cancel_order(self, broker_order_id: str) -> OrderResult:
        ib = self._require()
        oid = int(broker_order_id)
        for tr in ib.reqAllOpenOrders():
            if tr.order.orderId == oid:
                ib.cancelOrder(tr.order)
                ib.sleep(0.3)
                return OrderResult(ok=True, broker_order_id=broker_order_id, message="cancelled")
        return OrderResult(ok=False, broker_order_id=broker_order_id, message="order not found")

    def working_orders(self) -> list[Any]:
        """Return only the latest broker-refreshed orders that can execute."""
        ib = self._require()
        return working_trades(ib.reqAllOpenOrders() or [])

    def cancel_all_orders(self, timeout_s: float = 10.0, poll_s: float = 0.2) -> OrderResult:
        if not self._is_paper():
            return OrderResult(ok=False, message=f"refusing cancel-all on non-paper port {self.port}")

        ib = self._require()
        ib.reqGlobalCancel()
        deadline = time.monotonic() + max(0.0, float(timeout_s))
        while True:
            refreshed = list(ib.reqAllOpenOrders() or [])
            blockers = working_trades(refreshed) + cancelling_trades(refreshed)
            if not blockers:
                return OrderResult(ok=True, message="all orders cleared")
            if time.monotonic() >= deadline:
                ids = sorted(
                    {
                        int(getattr(getattr(trade, "order", None), "orderId", 0) or 0)
                        for trade in blockers
                    }
                )
                return OrderResult(ok=False, message=f"orders did not clear before timeout: {ids}")
            ib.sleep(max(0.0, min(float(poll_s), deadline - time.monotonic())))

    def flatten_positions(
        self,
        symbol: Optional[str] = None,
        timeout_s: float = 15.0,
        poll_s: float = 0.2,
    ) -> OrderResult:
        if not self._is_paper():
            return OrderResult(ok=False, message=f"refusing flatten on non-paper port {self.port}")

        cleared = self.cancel_all_orders(timeout_s=timeout_s, poll_s=poll_s)
        if not cleared.ok:
            return OrderResult(ok=False, message=f"pre-flatten cancel failed: {cleared.message}")

        for position in self.positions(symbol):
            result = self.place_order(
                OrderRequest(
                    symbol=position.symbol,
                    side="sell" if position.side == "buy" else "buy",
                    quantity=position.quantity,
                    client_tag="aegis_flatten",
                )
            )
            if not result.ok:
                self.cancel_all_orders(timeout_s=timeout_s, poll_s=poll_s)
                return OrderResult(ok=False, message=f"flatten close failed: {result.message}")

        ib = self._require()
        deadline = time.monotonic() + max(0.0, float(timeout_s))
        while self.positions(symbol):
            if time.monotonic() >= deadline:
                self.cancel_all_orders(timeout_s=timeout_s, poll_s=poll_s)
                return OrderResult(ok=False, message="positions did not flatten before timeout")
            ib.sleep(max(0.0, min(float(poll_s), deadline - time.monotonic())))

        final_cancel = self.cancel_all_orders(timeout_s=timeout_s, poll_s=poll_s)
        if not final_cancel.ok:
            return OrderResult(ok=False, message=f"post-flatten cancel failed: {final_cancel.message}")
        if self.positions(symbol):
            return OrderResult(ok=False, message="flatten verification found an open position")
        return OrderResult(ok=True, message="positions flat and orders cleared")
