"""Global ranking and allocation for already-gated Firehose opportunities."""
from __future__ import annotations

import math
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Iterable


@dataclass(frozen=True)
class FrozenOpportunity(Mapping[str, Any]):
    """Immutable point-in-time opportunity selected by the global allocator.

    The runner may revalidate the quote used for this object, but it must not
    regenerate or silently replace the side, mechanism, horizon, or geometry.
    """

    values: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "values", _freeze_value(dict(self.values)))

    def __getitem__(self, key: str) -> Any:
        return self.values[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.values)

    def __len__(self) -> int:
        return len(self.values)

    def to_dict(self) -> dict[str, Any]:
        return dict(self.values)


def freeze_opportunity(candidate: Mapping[str, Any]) -> FrozenOpportunity:
    """Snapshot a candidate before global ranking and broker execution."""
    if isinstance(candidate, FrozenOpportunity):
        return candidate
    return FrozenOpportunity(dict(candidate))


def _freeze_value(value: Any) -> Any:
    """Recursively freeze nested candidate metadata as well as top-level fields."""
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze_value(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_value(item) for item in value)
    if isinstance(value, set):
        return frozenset(_freeze_value(item) for item in value)
    return value


def _number(row: Mapping[str, Any], *keys: str, default: float = 0.0) -> float:
    for key in keys:
        try:
            value = float(row.get(key))
        except (TypeError, ValueError):
            continue
        if math.isfinite(value):
            return value
    return default


def rank_and_allocate(
    candidates: Iterable[Mapping[str, Any]],
    *,
    max_positions: int | None,
    occupied_theses: Iterable[str] = (),
    max_total_risk_usd: float | None = None,
) -> tuple[list[FrozenOpportunity], list[FrozenOpportunity]]:
    """Rank all valid opportunities, then allocate independent theses.

    Validated/calibrated candidates are ranked by measured capture probability.
    The explicitly marked forced DEMO lane is ranked by its comparative search
    score and may have null probability/EV; it is still subject to the runner's
    fresh-quote, risk, margin, portfolio, and broker gates. Duplicate thesis
    identities are never counted as separate opportunities.
    """
    ranked: list[FrozenOpportunity] = []
    for candidate in candidates:
        row = freeze_opportunity(candidate)
        if row.get("portfolio_ok") is False:
            continue
        lane = str(row.get("lane") or "").lower()
        forced_demo = lane in {
            "forced_demo_exploration",
            "forced_demo",
        } or str(row.get("authority_type") or "").upper() == "FORCED_DEMO_EXPLORATION"
        if forced_demo:
            if row.get("execution_hard_block") is True:
                continue
            score = _number(row, "selection_score", "comparative_score", default=float("nan"))
            if not math.isfinite(score):
                continue
            ranked.append(row)
            continue
        p_capture = _number(row, "p_captured_win", "p_capture", default=float("nan"))
        expected_ev = _number(row, "expected_net_ev", "expected_net_value_usd", default=float("nan"))
        if not math.isfinite(p_capture) or not 0.0 <= p_capture <= 1.0:
            continue
        if not math.isfinite(expected_ev) or expected_ev <= 0.0:
            continue
        ranked.append(row)

    def _rank_key(row: FrozenOpportunity) -> tuple[Any, ...]:
        lane = str(row.get("lane") or "").lower()
        forced_demo = lane in {"forced_demo_exploration", "forced_demo"} or str(
            row.get("authority_type") or ""
        ).upper() == "FORCED_DEMO_EXPLORATION"
        if forced_demo:
            return (
                2,
                -_number(row, "selection_score", "comparative_score", default=float("-inf")),
                _number(row, "fast_loser_similarity"),
                str(row.get("candidate_id") or row.get("thesis_key") or ""),
            )
        return (
            0 if lane == "validated" else 1,
            -_number(
                row,
                "p_captured_win_lcb95",
                "authority_capture_lcb95",
                "p_captured_win",
            ),
            -_number(row, "p_captured_win", default=float("-inf")),
            _number(row, "uncertainty", default=float("inf")),
            _number(row, "fast_loser_similarity"),
            _number(row, "tail_loss_probability"),
            -_number(row, "expected_net_ev_lcb95", "expected_net_ev_lcb", default=float("-inf")),
            _number(row, "expected_time_to_green_s", default=float("inf")),
            -_number(row, "fast_winner_similarity"),
            -_number(row, "expected_net_ev"),
            str(row.get("candidate_id") or row.get("thesis_key") or ""),
        )

    ranked.sort(key=_rank_key)

    selected: list[FrozenOpportunity] = []
    used_theses = {str(value) for value in occupied_theses if str(value)}
    risk_used = 0.0
    capacity = None if max_positions is None or int(max_positions) <= 0 else int(max_positions)
    risk_cap = None if max_total_risk_usd is None or float(max_total_risk_usd) <= 0 else float(max_total_risk_usd)
    for row in ranked:
        if capacity is not None and len(selected) >= capacity:
            break
        thesis = str(row.get("thesis_key") or row.get("candidate_id") or "")
        if thesis and thesis in used_theses:
            continue
        marginal_risk = max(0.0, _number(row, "marginal_risk_usd", "risk_usd"))
        if risk_cap is not None and risk_used + marginal_risk > risk_cap + 1e-12:
            continue
        selected.append(row)
        if thesis:
            used_theses.add(thesis)
        risk_used += marginal_risk
    return ranked, selected
