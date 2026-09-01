"""Outcome attribution for thesis research. It observes; it never changes trading."""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable, Mapping

from aegis.research.costs import pnl_summary
from aegis.research.thesis import calibrate_outcomes


def attribute_outcomes(rows: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Cluster outcomes by thesis/context and expose one evidence gap at a time."""
    buckets: dict[str, list[float]] = defaultdict(list)
    metadata: dict[str, dict[str, Any]] = {}
    for row in rows:
        thesis_id = str(row.get("thesis_id") or "unattributed")
        try:
            pnl = float(row["pnl"])
        except (KeyError, TypeError, ValueError):
            continue
        buckets[thesis_id].append(pnl)
        metadata.setdefault(
            thesis_id,
            {
                "regime": row.get("regime") or "unknown",
                "symbol": row.get("symbol") or "unknown",
                "side": row.get("side") or "unknown",
                "session": row.get("session") or "unknown",
                "execution_state": row.get("execution_state") or "unknown",
            },
        )
    out: dict[str, dict[str, Any]] = {}
    for thesis_id, outcomes in buckets.items():
        calibration = calibrate_outcomes(outcomes)
        losses = sum(value < 0 for value in outcomes)
        wins = sum(value > 0 for value in outcomes)
        out[thesis_id] = {
            "thesis_id": thesis_id,
            **metadata[thesis_id],
            "n": len(outcomes),
            "wins": wins,
            "losses": losses,
            "calibration": calibration.as_dict(),
            "next_information_gap": (
                "collect more comparable outcomes"
                if calibration.uncertainty == "insufficient_sample"
                else "diagnose regime/execution mismatch"
                if not calibration.eligible
                else "validate on a sealed holdout"
            ),
            "label": "research_proxy",
        }
    return out


def slice_outcomes(
    rows: Iterable[Mapping[str, Any]],
    *,
    by: tuple[str, ...] = ("symbol", "side", "session"),
) -> dict[str, Any]:
    """Slice observed PnL without inventing missing context fields."""
    from aegis.research.costs import pnl_summary

    slices: dict[str, list[float]] = defaultdict(list)
    all_pnls: list[float] = []
    for row in rows:
        try:
            pnl = float(row["pnl"])
        except (KeyError, TypeError, ValueError):
            continue
        all_pnls.append(pnl)
        key = "|".join(str(row.get(field) or "unknown") for field in by)
        slices[key].append(pnl)
    ranked = sorted(
        ({"key": key, **pnl_summary(values)} for key, values in slices.items()),
        key=lambda item: float(item.get("net_pnl") or 0.0),
    )
    return {
        "schema": "attribution.v1",
        "by": list(by),
        "overall": pnl_summary(all_pnls),
        "slices": ranked,
        "label": "research_proxy",
    }
