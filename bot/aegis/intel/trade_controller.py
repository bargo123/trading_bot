"""Single canonical owner for per-ticket lifecycle actions."""
from __future__ import annotations

import math
from typing import Any, Mapping


CANONICAL_ACTIONS = frozenset({"HOLD", "LOCK", "HARVEST", "SCRATCH", "ABORT"})


def _canonical_action(source_action: object, reason: object) -> str:
    action = str(source_action or "HOLD").upper()
    why = str(reason or "").lower()
    if action in {"TAKE", "QUICK_TAKE", "HARVEST"}:
        return "HARVEST"
    if action in {"SCRATCH", "REDUCE"}:
        return "SCRATCH"
    if action in {"ABORT"}:
        return "ABORT"
    if action in {"EXIT", "TIME_EXIT"}:
        if any(token in why for token in (
            "remaining_ev", "regime", "invalid", "revoked", "abort", "tail",
        )):
            return "ABORT"
        if any(token in why for token in ("harvest", "take", "target", "giveback", "profit")):
            return "HARVEST"
        return "SCRATCH"
    if action == "LOCK":
        return "LOCK"
    return "HOLD"


class TradeController:
    """Combine evidence adapters into exactly one canonical action.

    ProfitManager and FastExit remain evidence producers.  The runner calls
    this controller once and closes only for HARVEST, SCRATCH, or ABORT.
    """

    def decide(
        self,
        profit_manager_verdict: Mapping[str, Any] | None,
        fast_verdict: Mapping[str, Any] | None,
        *,
        remaining_ev: float | None = None,
        harvest_ev_comparison: Mapping[str, Any] | None = None,
        evidence_snapshot: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        pm = dict(profit_manager_verdict or {})
        fast = dict(fast_verdict or {})
        candidates = [
            ("profit_manager", pm, _canonical_action(pm.get("action"), pm.get("reason"))),
            ("fast_exit", fast, _canonical_action(fast.get("action"), fast.get("reason"))),
        ]
        priority = {"HOLD": 0, "LOCK": 1, "HARVEST": 2, "SCRATCH": 3, "ABORT": 4}
        source, selected, action = max(
            candidates,
            key=lambda item: priority[item[2]],
        )
        why_hold = "; ".join(
            str(item.get("why")) for _, item, mapped in candidates
            if mapped in {"HOLD", "LOCK"} and item.get("why")
        )
        why_exit = str(selected.get("why") or selected.get("reason") or "") if action in {
            "HARVEST", "SCRATCH", "ABORT"
        } else ""
        result = {
            "action": action,
            "reason": str(selected.get("reason") or f"controller_{action.lower()}"),
            "policy": selected.get("policy"),
            "source": source,
            "why_hold": why_hold,
            "why_exit": why_exit,
            "why": why_exit or why_hold,
            "remaining_ev": remaining_ev,
            "harvest_ev_comparison": dict(harvest_ev_comparison or {}),
            "evidence_snapshot": dict(evidence_snapshot or {}),
        }
        if action == "HOLD" and not result["why_hold"]:
            result["why_hold"] = "no exit policy triggered"
        return result

    def replay_quote_path(
        self,
        *,
        quotes: list[Mapping[str, Any]],
        side: str,
        horizon_s: float,
        target_price: float,
        stop_price: float,
        pip_size: float = 0.0001,
        slippage_price: float = 0.0,
        commission_usd: float = 0.0,
        usd_per_price_unit: float = 1.0,
    ) -> dict[str, Any]:
        """Replay the live controller against sequential executable quotes.

        The first quote is the entry quote (ASK for BUY, BID for SELL).  Every
        later decision sees only that quote's liquidation side (BID for BUY,
        ASK for SELL), so the opening spread is represented once and no future
        quote is used before its decision point.  This is intentionally an
        evidence adapter: it never submits or modifies a broker order.
        """
        normalized_side = str(side or "").strip().lower()
        if normalized_side not in {"buy", "sell"}:
            return {"status": "UNAVAILABLE", "reason": "unknown_side"}
        try:
            horizon = float(horizon_s)
            target = float(target_price)
            stop = float(stop_price)
            pip = float(pip_size)
            slippage = float(slippage_price)
            commission = float(commission_usd)
            unit = float(usd_per_price_unit)
        except (TypeError, ValueError, OverflowError):
            return {"status": "UNAVAILABLE", "reason": "invalid_replay_parameters"}
        if not all(math.isfinite(value) for value in (
            horizon, target, stop, pip, slippage, commission, unit
        )):
            return {"status": "UNAVAILABLE", "reason": "invalid_replay_parameters"}
        if horizon <= 0 or pip <= 0 or slippage < 0 or commission < 0 or unit <= 0:
            return {"status": "UNAVAILABLE", "reason": "invalid_replay_parameters"}
        if not isinstance(quotes, list) or not quotes:
            return {"status": "UNAVAILABLE", "reason": "quote_history_missing"}

        normalized: list[tuple[float, float, float]] = []
        for quote in quotes:
            if not isinstance(quote, Mapping):
                return {"status": "UNAVAILABLE", "reason": "quote_history_invalid"}
            try:
                timestamp = float(quote["time"])
                bid = float(quote["bid"])
                ask = float(quote["ask"])
            except (KeyError, TypeError, ValueError, OverflowError):
                return {"status": "UNAVAILABLE", "reason": "quote_history_invalid"}
            if not all(math.isfinite(value) for value in (timestamp, bid, ask)) or bid <= 0 or ask < bid:
                return {"status": "UNAVAILABLE", "reason": "quote_history_invalid"}
            normalized.append((timestamp, bid, ask))
        normalized.sort(key=lambda item: item[0])
        start, entry_bid, entry_ask = normalized[0]
        entry = entry_ask if normalized_side == "buy" else entry_bid
        direction = 1.0 if normalized_side == "buy" else -1.0
        if (
            (normalized_side == "buy" and not (stop < entry < target))
            or (normalized_side == "sell" and not (target < entry < stop))
        ):
            return {"status": "UNAVAILABLE", "reason": "invalid_replay_geometry"}
        future = [item for item in normalized[1:] if start < item[0] <= start + horizon]
        if not future:
            return {"status": "UNAVAILABLE", "reason": "quote_history_missing_future"}

        # FastExitStateMachine is imported lazily to keep the controller usable
        # by the research modules without creating an import cycle at startup.
        from aegis.intel.fast_firehose import FastExitConfig, FastExitStateMachine

        initial_friction_price = (entry_ask - entry_bid) + slippage
        initial_friction_pips = initial_friction_price / pip
        if unit > 0:
            initial_friction_pips += (commission / unit) / pip
        machine = FastExitStateMachine(FastExitConfig(time_exit_s=horizon))
        actions: list[dict[str, Any]] = []
        signed_prices: list[float] = []
        first_green_s: float | None = None
        peak_time_s: float | None = None
        peak_price = -float("inf")
        terminal: dict[str, Any] | None = None
        for timestamp, bid, ask in future:
            mark = bid if normalized_side == "buy" else ask
            signed_price = (mark - entry) * direction
            signed_prices.append(signed_price)
            if signed_price > peak_price:
                peak_price = signed_price
                peak_time_s = timestamp - start
            pnl_pips = signed_price / pip
            mfe_pips = max(signed_prices) / pip
            mae_pips = min(signed_prices) / pip
            net_usd = signed_price * unit - slippage * unit - commission
            if first_green_s is None and net_usd > 0:
                first_green_s = timestamp - start
            fast = machine.evaluate(
                side=normalized_side,
                entry_price=entry,
                current_mark=mark,
                stop_loss=stop,
                target=target,
                opened_ts=start,
                now=timestamp,
                pnl_pips=pnl_pips,
                mfe_pips=mfe_pips,
                mae_pips=mae_pips,
                stop_pips=abs(entry - stop) / pip,
                pip=pip,
                expected_initial_friction_pips=initial_friction_pips,
            )
            decision = self.decide(None, fast)
            action = decision["action"]
            actions.append({
                "time_s": timestamp - start,
                "action": action,
                "reason": decision["reason"],
                "net_pnl_usd": net_usd,
            })
            if action in {"HARVEST", "SCRATCH", "ABORT"}:
                terminal = {
                    "time_s": timestamp - start,
                    # Keep the historical label vocabulary stable while
                    # retaining the exact canonical controller action below.
                    "reason": "harvest" if action == "HARVEST" else "abort",
                    "action": action,
                    "net_pnl_usd": net_usd,
                }
                break

        last_timestamp, last_bid, last_ask = future[-1]
        endpoint_mark = last_bid if normalized_side == "buy" else last_ask
        endpoint_signed = (endpoint_mark - entry) * direction
        endpoint_net = endpoint_signed * unit - slippage * unit - commission
        if terminal is None:
            terminal = {
                "time_s": last_timestamp - start,
                "reason": "timeout",
                "action": "TIMEOUT",
                "net_pnl_usd": endpoint_net,
            }
        max_favorable = max(signed_prices) * unit - slippage * unit - commission
        max_adverse = min(signed_prices) * unit - slippage * unit - commission
        captured = float(terminal["net_pnl_usd"])
        return {
            "status": "REPLAYED",
            "captured_exit_net_pnl": captured,
            "captured_exit_reason": str(terminal["reason"]),
            "captured_exit_action": str(terminal.get("action") or "TIMEOUT"),
            "captured_exit_time_s": float(terminal["time_s"]),
            # Terminal means the last observed executable quote, even when the
            # controller captured earlier. Both values use the same costs.
            "terminal_net_pnl": float(endpoint_net),
            "mfe_net_pnl": float(max_favorable),
            "mae_net_pnl": float(max_adverse),
            "time_to_green_s": first_green_s,
            "time_to_peak_s": peak_time_s,
            "never_green": first_green_s is None,
            "green_then_loser": first_green_s is not None and captured <= 0,
            "tail_loss": captured < 0 and max_adverse < 0,
            "capture_ratio": captured / max_favorable if max_favorable > 0 else None,
            "entry_price": entry,
            "entry_spread_price": entry_ask - entry_bid,
            "expected_initial_friction_pips": initial_friction_pips,
            "actions": actions,
        }
