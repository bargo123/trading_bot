"""Private helpers for De Prado information-driven bar diagnostics."""
from __future__ import annotations

from ._deprado_common import finite_series


def positive_series(state, key: str):
    values = finite_series(state, key)
    if values is None or len(values) < 2 or any(value <= 0 for value in values):
        return None
    return values


def tick_signs(prices: list[float]) -> list[int]:
    signs = [0]
    previous = 0
    for before, after in zip(prices, prices[1:]):
        if after > before:
            previous = 1
        elif after < before:
            previous = -1
        signs.append(previous)
    return signs


def imbalance_events(signs: list[int], amounts: list[float], threshold: float) -> list[dict]:
    signed_imbalance = 0.0
    start_index = 0
    events = []
    for index, (sign, amount) in enumerate(zip(signs, amounts)):
        signed_imbalance += sign * amount
        if abs(signed_imbalance) >= threshold:
            events.append({
                "start_index": start_index,
                "end_index": index,
                "direction": "UP" if signed_imbalance > 0 else "DOWN",
                "signed_imbalance": signed_imbalance,
            })
            signed_imbalance = 0.0
            start_index = index + 1
    return events


def run_events(signs: list[int], amounts: list[float] | None, threshold: float) -> list[dict]:
    buy_total = 0.0
    sell_total = 0.0
    start_index = 0
    events = []
    for index, sign in enumerate(signs):
        amount = 1.0 if amounts is None else amounts[index]
        if sign > 0:
            buy_total += amount
        elif sign < 0:
            sell_total += amount
        run_measure = max(buy_total, sell_total)
        if run_measure >= threshold:
            events.append({
                "start_index": start_index,
                "end_index": index,
                "direction": "UP" if buy_total >= sell_total else "DOWN",
                "buy_activity": buy_total,
                "sell_activity": sell_total,
                "run_measure": run_measure,
            })
            buy_total = 0.0
            sell_total = 0.0
            start_index = index + 1
    return events


def standard_bars(prices: list[float], activity: list[float], threshold: float) -> list[dict]:
    bars = []
    start_index = 0
    accumulated = 0.0
    for index, amount in enumerate(activity):
        accumulated += amount
        if accumulated >= threshold or index == len(activity) - 1:
            window = prices[start_index:index + 1]
            bars.append({
                "start_index": start_index,
                "end_index": index,
                "open": window[0],
                "close": window[-1],
                "high": max(window),
                "low": min(window),
                "activity": sum(activity[start_index:index + 1]),
            })
            start_index = index + 1
            accumulated = 0.0
    return bars
