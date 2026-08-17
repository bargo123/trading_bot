"""$100/day firehose economics. Scale proven edge with capital, never with reckless leverage."""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Any, Mapping, Sequence

from aegis.intel.expected_value import payoff_metrics
from aegis.research.intelligent_champion import load_intelligent_champion
from aegis.research.thousand_day_gap import _deduped_deals

TARGET_DAILY_USD = 100.0
FORBIDDEN_CLOSE_PATHS = (
    "increase_leverage",
    "increase_lot_size_on_current_account",
    "must_make_100_today",
)


def required_capital_for_target(
    *,
    expected_net_day: float | None,
    current_capital: float,
    target_daily_usd: float = TARGET_DAILY_USD,
    verified: bool,
    validated_risk_fraction: float | None = None,
) -> dict[str, Any]:
    """If edge is proven and positive, scale the account at the same risk fraction."""
    forbidden = "do_not_lever_current_account_to_force_target"
    if not verified:
        return {
            "required_capital_usd": None,
            "method": "no_verified_champion",
            "risk_fraction_held_constant": validated_risk_fraction,
            "leverage_increase": False,
            "forbidden": forbidden,
        }
    if expected_net_day is None or float(expected_net_day) <= 0 or float(current_capital) <= 0:
        return {
            "required_capital_usd": None,
            "method": "non_positive_edge_cannot_be_scaled",
            "risk_fraction_held_constant": validated_risk_fraction,
            "leverage_increase": False,
            "forbidden": forbidden,
        }
    required = float(current_capital) * (float(target_daily_usd) / float(expected_net_day))
    return {
        "required_capital_usd": required,
        "method": "scale_account_at_same_risk_fraction",
        "risk_fraction_held_constant": validated_risk_fraction,
        "leverage_increase": False,
        "forbidden": forbidden,
    }


def classify_gap_close(
    *,
    expectancy: float | None,
    expected_net_day: float | None,
    cosmetic_win_rate: bool,
    profit_factor: float | None,
    trades_per_day: float | None,
    target_daily_usd: float = TARGET_DAILY_USD,
) -> list[str]:
    reasons: list[str] = []
    if expectancy is None or float(expectancy) <= 0:
        reasons.append("better_edge")
    if cosmetic_win_rate or (profit_factor is not None and float(profit_factor) <= 1):
        reasons.append("healthier_payoff")
    if expected_net_day is not None and 0 < float(expected_net_day) < float(target_daily_usd):
        reasons.append("more_independent_opportunities")
        reasons.append("lower_costs")
        reasons.append("better_execution")
        reasons.append("additional_capital")
    return reasons or ["insufficient_evidence"]


def _daily_pnls(rows: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    daily: dict[str, float] = defaultdict(float)
    for row in rows:
        try:
            pnl = float(row["pnl"])
            day = datetime.fromisoformat(str(row["ts"]).replace("Z", "+00:00")).date().isoformat()
        except (KeyError, TypeError, ValueError):
            continue
        daily[day] += pnl
    return dict(sorted(daily.items()))


def _max_drawdown_pct(pnls: Sequence[float], starting_capital: float) -> float | None:
    if not pnls or starting_capital <= 0:
        return None
    equity = float(starting_capital)
    peak = equity
    max_dd = 0.0
    for pnl in pnls:
        equity += float(pnl)
        peak = max(peak, equity)
        if peak > 0:
            max_dd = max(max_dd, (peak - equity) / peak)
    return max_dd * 100.0


def _champion_block(champion: Mapping[str, Any] | None) -> dict[str, Any]:
    raw = dict(champion or {})
    status = str(raw.get("status") or "none")
    champ_id = raw.get("id")
    if status != "accepted" or not champ_id:
        return {
            "id": None,
            "status": "none",
            "expectancy": None,
            "trades_per_day": None,
            "expected_net_day": None,
            "profit_factor": None,
            "avg_win": None,
            "avg_loss": None,
            "max_drawdown_pct": None,
            "tail_loss": None,
            "validated_risk_fraction": None,
            "n_trades": None,
            "n_losses": None,
        }
    expectancy = float(raw["expectancy"])
    trades_per_day = float(raw["trades_per_day"])
    return {
        "id": champ_id,
        "status": "accepted",
        "expectancy": expectancy,
        "trades_per_day": trades_per_day,
        "expected_net_day": expectancy * trades_per_day,
        "profit_factor": raw.get("profit_factor"),
        "avg_win": raw.get("avg_win"),
        "avg_loss": raw.get("avg_loss"),
        "max_drawdown_pct": raw.get("max_drawdown_pct"),
        "tail_loss": raw.get("tail_loss"),
        "validated_risk_fraction": raw.get("validated_risk_fraction"),
        "n_trades": raw.get("n_trades"),
        "n_losses": raw.get("n_losses"),
    }


def firehose_economic_snapshot(
    *,
    deals_path: Path | None,
    current_capital: float,
    champion: Mapping[str, Any] | None = None,
    target_daily_usd: float = TARGET_DAILY_USD,
    margin_use: float | None = None,
    capital_utilization: float | None = None,
) -> dict[str, Any]:
    verified = _champion_block(champion)
    observed: dict[str, Any] = {
        "label": "research_proxy",
        "not_a_champion": True,
        "n_trades": 0,
        "active_days": 0,
        "trades_per_day": None,
        "expectancy": None,
        "expected_net_day": None,
        "median_net_day": None,
        "win_rate": None,
        "avg_win": None,
        "avg_loss": None,
        "profit_factor": None,
        "max_drawdown_pct": None,
        "tail_loss": None,
        "wins_erased_by_average_loss": None,
        "cosmetic_win_rate": False,
        "daily_pnl_usd": {},
    }
    if deals_path is not None and Path(deals_path).exists():
        rows = _deduped_deals(Path(deals_path))
        pnls: list[float] = []
        ordered: list[tuple[str, float]] = []
        for row in rows:
            try:
                pnl = float(row["pnl"])
                ts = str(row["ts"])
            except (KeyError, TypeError, ValueError):
                continue
            pnls.append(pnl)
            ordered.append((ts, pnl))
        ordered.sort(key=lambda item: item[0])
        payoff = payoff_metrics([item[1] for item in ordered])
        daily = _daily_pnls(rows)
        active_days = len(daily)
        expected_net_day = (sum(daily.values()) / active_days) if active_days else None
        observed.update(
            {
                "n_trades": payoff["n"],
                "active_days": active_days,
                "trades_per_day": (payoff["n"] / active_days) if active_days else None,
                "expectancy": payoff["expectancy"],
                "expected_net_day": expected_net_day,
                "median_net_day": median(daily.values()) if daily else None,
                "win_rate": payoff["win_rate"],
                "avg_win": payoff["avg_win"],
                "avg_loss": payoff["avg_loss"],
                "profit_factor": payoff["profit_factor"],
                "max_drawdown_pct": _max_drawdown_pct(
                    [item[1] for item in ordered], float(current_capital)
                ),
                "tail_loss": payoff["tail_loss"],
                "wins_erased_by_average_loss": payoff["wins_erased_by_average_loss"],
                "cosmetic_win_rate": payoff["cosmetic_win_rate"],
                "daily_pnl_usd": daily,
            }
        )

    if verified["status"] == "accepted":
        expected_net_day = verified["expected_net_day"]
        expectancy = verified["expectancy"]
        cosmetic = False
        pf = verified["profit_factor"]
        trades_per_day = verified["trades_per_day"]
        risk_fraction = verified["validated_risk_fraction"]
        close_expectancy = expectancy
    else:
        expected_net_day = observed["expected_net_day"]
        expectancy = observed["expectancy"]
        cosmetic = bool(observed["cosmetic_win_rate"])
        pf = observed["profit_factor"]
        trades_per_day = observed["trades_per_day"]
        risk_fraction = None
        close_expectancy = expectancy

    required = required_capital_for_target(
        expected_net_day=expected_net_day if verified["status"] == "accepted" else None,
        current_capital=float(current_capital),
        target_daily_usd=float(target_daily_usd),
        verified=verified["status"] == "accepted",
        validated_risk_fraction=risk_fraction,
    )
    current_expected = (
        verified["expected_net_day"]
        if verified["status"] == "accepted"
        else observed["expected_net_day"]
    )
    difference = None if current_expected is None else float(target_daily_usd) - float(current_expected)
    close_through = classify_gap_close(
        expectancy=close_expectancy,
        expected_net_day=current_expected,
        cosmetic_win_rate=cosmetic,
        profit_factor=pf,
        trades_per_day=trades_per_day,
        target_daily_usd=float(target_daily_usd),
    )
    return {
        "schema": "firehose_economics.v1",
        "label": "research_proxy",
        "target_daily_usd": float(target_daily_usd),
        "current_capital_usd": float(current_capital),
        "verified_champion": verified,
        "observed": observed,
        "margin_use": margin_use,
        "capital_utilization": capital_utilization,
        "uncertainty": (
            "calibrated"
            if verified["status"] == "accepted"
            else "no_verified_champion_observation_only"
        ),
        "required_capital": required,
        "gap": {
            "current_expected_day": current_expected,
            "difference_usd": difference,
            "close_through": close_through,
        },
        "leverage_increase_recommended": False,
        "principle": "fast_active_intelligent_positive_ev_scalable",
    }


def markdown_firehose_economics(snapshot: Mapping[str, Any]) -> str:
    champ = snapshot["verified_champion"]
    observed = snapshot["observed"]
    required = snapshot["required_capital"]
    gap = snapshot["gap"]
    capital_text = (
        "unavailable"
        if required["required_capital_usd"] is None
        else f"${required['required_capital_usd']:,.2f}"
    )
    expected_text = (
        "unavailable"
        if gap["current_expected_day"] is None
        else f"${gap['current_expected_day']:,.2f}"
    )
    diff = gap["difference_usd"]
    diff_text = "unavailable" if diff is None else f"${diff:,.2f}"

    def money(value: Any) -> str:
        if value is None:
            return "unavailable"
        return f"${float(value):,.4f}" if abs(float(value)) < 1 else f"${float(value):,.2f}"

    return "\n".join(
        [
            "# $100/day firehose economic gap",
            "",
            "This is **not** a `must_make_100_today` quota and **not** a leverage instruction.",
            "Capital estimates, when present, hold the same validated risk fraction and scale the account.",
            "Label: `research_proxy`. No live YAML or runner change.",
            "",
            "## CURRENT VERIFIED CHAMPION",
            "",
            f"- id: `{champ['id']}`",
            f"- status: `{champ['status']}`",
            f"- account capital: {money(snapshot['current_capital_usd'])}",
            f"- expectancy/trade: {champ['expectancy']}",
            f"- trades/day: {champ['trades_per_day']}",
            f"- expected net/day: {money(champ['expected_net_day'])}",
            f"- PF: {champ['profit_factor']}",
            f"- average win: {champ['avg_win']}",
            f"- average loss: {champ['avg_loss']}",
            f"- max DD: {champ['max_drawdown_pct']}",
            f"- tail risk: {champ['tail_loss']}",
            f"- validated risk fraction: {champ['validated_risk_fraction']}",
            f"- margin use: {snapshot['margin_use'] if snapshot['margin_use'] is not None else 'unavailable'}",
            f"- capital utilization: {snapshot['capital_utilization'] if snapshot['capital_utilization'] is not None else 'unavailable'}",
            f"- uncertainty: {snapshot['uncertainty']}",
            "",
            "## CURRENT OBSERVED FIREHOSE (not a champion)",
            "",
            f"- n trades: {observed['n_trades']}",
            f"- active days: {observed['active_days']}",
            f"- trades/day: {observed['trades_per_day']}",
            f"- expectancy/trade: {observed['expectancy']}",
            f"- expected net/day: {money(observed['expected_net_day'])}",
            f"- median net/day: {money(observed['median_net_day'])}",
            f"- win rate: {observed['win_rate']} (never sufficient alone)",
            f"- average win: {observed['avg_win']}",
            f"- average loss: {observed['avg_loss']}",
            f"- PF: {observed['profit_factor']}",
            f"- wins erased by average loss: {observed['wins_erased_by_average_loss']}",
            f"- cosmetic win rate: {observed['cosmetic_win_rate']}",
            f"- max DD % on observed path: {observed['max_drawdown_pct']}",
            f"- tail loss: {observed['tail_loss']}",
            "",
            "## TARGET",
            "",
            f"`${snapshot['target_daily_usd']:,.2f}/day`",
            "",
            "## GAP",
            "",
            f"- current expected/day: {expected_text}",
            f"- difference from $100: {diff_text}",
            f"- close through: {', '.join(gap['close_through'])}",
            f"- leverage increase recommended: {snapshot['leverage_increase_recommended']}",
            "",
            "## REQUIRED CAPITAL",
            "",
            f"- estimate: {capital_text}",
            f"- method: {required['method']}",
            f"- risk fraction held constant: {required['risk_fraction_held_constant']}",
            f"- forbidden: {required['forbidden']}",
            "",
            "If observed expectancy is non-positive, adding lots to a ~$93 account cannot create a $100 day.",
            "Keep scanning. Fire capital only when a validated thesis has positive EV.",
            "",
        ]
    )


def snapshot_from_defaults(
    *,
    deals_path: Path,
    heartbeat_path: Path | None = None,
    champion_path: Path | None = None,
    current_capital: float | None = None,
) -> dict[str, Any]:
    capital = current_capital
    if capital is None and heartbeat_path is not None and Path(heartbeat_path).exists():
        try:
            payload = json.loads(Path(heartbeat_path).read_text(encoding="utf-8"))
            capital = float(payload.get("equity") or 0.0) or None
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            capital = None
    if capital is None:
        capital = 0.0
    champion = load_intelligent_champion(champion_path)
    return firehose_economic_snapshot(
        deals_path=deals_path if Path(deals_path).exists() else None,
        current_capital=float(capital),
        champion=champion,
    )
