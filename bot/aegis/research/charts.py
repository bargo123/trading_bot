"""Point-and-figure, Renko, Kagi, and three-line-break from ordered ticks."""
from __future__ import annotations

from typing import Any

import pandas as pd

from aegis.research.dataplane import ticks_frame


def _mids(ticks: pd.DataFrame) -> list[float]:
    frame = ticks_frame(ticks.to_dict("records"))
    mid = (frame["bid"].astype(float) + frame["ask"].astype(float)) / 2.0
    last = frame["last"].astype(float)
    px = last.where(last > 0, mid)
    return [float(x) for x in px.tolist()]


def point_and_figure(ticks: pd.DataFrame, *, box: float, reversal_boxes: int = 3) -> dict[str, Any]:
    prices = _mids(ticks)
    if not prices or box <= 0:
        return {"label": "research_proxy", "lookahead": False, "n": 0, "kind": "pnf"}
    cols: list[str] = []
    last_box = prices[0] // box * box
    direction = 0
    for px in prices[1:]:
        level = px // box * box
        if direction == 0:
            if level > last_box:
                direction = 1
                cols.append("X")
                last_box = level
            elif level < last_box:
                direction = -1
                cols.append("O")
                last_box = level
            continue
        if direction == 1 and level >= last_box + box:
            cols.append("X")
            last_box = level
        elif direction == 1 and level <= last_box - reversal_boxes * box:
            direction = -1
            cols.append("O")
            last_box = level
        elif direction == -1 and level <= last_box - box:
            cols.append("O")
            last_box = level
        elif direction == -1 and level >= last_box + reversal_boxes * box:
            direction = 1
            cols.append("X")
            last_box = level
    return {"label": "research_proxy", "lookahead": False, "n": max(len(cols), 1), "kind": "pnf", "source": "nison-duplessis-inspired"}


def renko_bricks(ticks: pd.DataFrame, *, brick: float) -> dict[str, Any]:
    prices = _mids(ticks)
    if not prices or brick <= 0:
        return {"label": "research_proxy", "lookahead": False, "n": 0, "kind": "renko"}
    bricks: list[int] = []
    ref = prices[0]
    for px in prices[1:]:
        while px - ref >= brick:
            bricks.append(1)
            ref += brick
        while ref - px >= brick:
            bricks.append(-1)
            ref -= brick
    return {"label": "research_proxy", "lookahead": False, "n": max(len(bricks), 1), "kind": "renko", "source": "nison-inspired"}


def kagi_state(ticks: pd.DataFrame, *, reversal: float) -> dict[str, Any]:
    prices = _mids(ticks)
    if not prices or reversal <= 0:
        return {"label": "research_proxy", "lookahead": False, "n": 0, "kind": "kagi"}
    yang = True
    extreme = prices[0]
    turns = 1
    for px in prices[1:]:
        if yang and px > extreme:
            extreme = px
        elif yang and extreme - px >= reversal:
            yang = False
            extreme = px
            turns += 1
        elif not yang and px < extreme:
            extreme = px
        elif not yang and px - extreme >= reversal:
            yang = True
            extreme = px
            turns += 1
    return {"label": "research_proxy", "lookahead": False, "n": turns, "kind": "kagi", "source": "nison-inspired"}


def three_line_break(ticks: pd.DataFrame, *, lines: int = 3) -> dict[str, Any]:
    prices = _mids(ticks)
    if not prices:
        return {"label": "research_proxy", "lookahead": False, "n": 0, "kind": "tlb"}
    lines_n = max(int(lines), 1)
    closes: list[float] = [prices[0]]
    direction = 0
    for px in prices[1:]:
        if direction == 0:
            if px > closes[-1]:
                direction = 1
                closes.append(px)
            elif px < closes[-1]:
                direction = -1
                closes.append(px)
            continue
        window = closes[-lines_n:]
        if direction == 1 and px > max(window):
            closes.append(px)
        elif direction == 1 and px < min(window):
            direction = -1
            closes.append(px)
        elif direction == -1 and px < min(window):
            closes.append(px)
        elif direction == -1 and px > max(window):
            direction = 1
            closes.append(px)
    return {"label": "research_proxy", "lookahead": False, "n": max(len(closes) - 1, 1), "kind": "tlb", "source": "nison-inspired"}
