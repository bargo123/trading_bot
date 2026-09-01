"""Regression tests for dashboard order freshness and classification."""
from __future__ import annotations

import sys
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from run_dashboard import DeskState, collect_order_rows


def trade(status: str, order_id: int):
    order = SimpleNamespace(
        orderId=order_id,
        clientId=71,
        permId=50_000 + order_id,
        action="BUY",
        orderType="LMT",
        totalQuantity=20_000,
        lmtPrice=1.15460,
        auxPrice=0.0,
    )
    return SimpleNamespace(order=order, orderStatus=SimpleNamespace(status=status))


class FakeDashboardIB:
    def __init__(self, refreshed, cached) -> None:
        self.refreshed = refreshed
        self.cached = cached
        self.open_trade_cache_reads = 0

    def reqAllOpenOrders(self):
        return list(self.refreshed)

    def openTrades(self):
        self.open_trade_cache_reads += 1
        return list(self.cached)


def test_dashboard_uses_refresh_result_not_open_trade_cache():
    ib = FakeDashboardIB(refreshed=[], cached=[trade("Submitted", 99)])
    open_orders, cancelling = collect_order_rows(ib)
    assert open_orders == []
    assert cancelling == []
    assert ib.open_trade_cache_reads == 0


def test_dashboard_separates_pending_cancel_from_working_orders():
    ib = FakeDashboardIB(
        refreshed=[trade("Submitted", 100), trade("PendingCancel", 101)],
        cached=[],
    )
    open_orders, cancelling = collect_order_rows(ib)
    assert [row["id"] for row in open_orders] == [100]
    assert [row["id"] for row in cancelling] == [101]


def test_dashboard_does_not_mark_bot_stopped_between_slow_polls():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        reports = root / "reports"
        reports.mkdir()
        (reports / "bot_heartbeat.json").write_text(json.dumps({"ts": 155.0}))
        state = DeskState({"poll_seconds": 30}, reports / "journal.jsonl")
        with patch("run_dashboard.ROOT", root), patch("run_dashboard.time.time", return_value=200.0):
            assert state._bot_running()


def test_dashboard_reads_mgc_feed_and_promotion_fields_from_heartbeat():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        reports = root / "reports"
        reports.mkdir()
        (reports / "bot_heartbeat.json").write_text(
            json.dumps(
                {
                    "ts": 195.0,
                    "symbol": "MGC",
                    "local_symbol": "MGCV6",
                    "feed_usable": True,
                    "feed_age_seconds": 0.4,
                    "trades_today": 0,
                    "modeled_costs_today": 0.0,
                    "paper_promoted": False,
                    "gate_reason": "paper_promoted is false",
                    "regime": "directional_informed",
                    "signal_side": "buy",
                    "flow_score": 0.91,
                    "expected_net_usd": 5.08,
                }
            )
        )
        state = DeskState({"poll_seconds": 2}, reports / "journal.jsonl")
        with patch("run_dashboard.ROOT", root), patch("run_dashboard.time.time", return_value=200.0):
            fields = state._heartbeat_fields()
            with patch.object(state, "_connect", side_effect=RuntimeError("offline")):
                snapshot = state._poll_once()
        assert fields["local_symbol"] == "MGCV6"
        assert fields["feed_usable"] is True
        assert fields["feed_age_seconds"] == 0.4
        assert fields["paper_promoted"] is False
        assert fields["gate_reason"] == "paper_promoted is false"
        assert fields["regime"] == "directional_informed"
        assert fields["signal_side"] == "buy"
        assert fields["flow_score"] == 0.91
        assert fields["expected_net_usd"] == 5.08
        assert snapshot["regime"] == "directional_informed"
        assert snapshot["signal_side"] == "buy"
        assert snapshot["flow_score"] == 0.91
        assert snapshot["expected_net_usd"] == 5.08


def test_dashboard_requests_configured_market_data_type_before_mark_subscription():
    requested = []
    fake_ib = SimpleNamespace(reqMarketDataType=lambda value: requested.append(value))
    DeskState({"ib_market_data_type": 3}, Path("unused"))._set_market_data_type(fake_ib)
    assert requested == [3]


if __name__ == "__main__":
    test_dashboard_uses_refresh_result_not_open_trade_cache()
    test_dashboard_separates_pending_cancel_from_working_orders()
    test_dashboard_does_not_mark_bot_stopped_between_slow_polls()
    print("OK")
