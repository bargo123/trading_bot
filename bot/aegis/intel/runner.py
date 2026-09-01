"""CORE_STRATEGY_V1 research runner — offline only. Does not touch the live YAML."""
from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from aegis.backtest import BacktestResult, run_backtest
from aegis.intel.books import lookup
from aegis.intel.champion import append_experiment, save_champion, save_challenger
from aegis.intel.cluster import family_counts
from aegis.intel.frozen_v1 import research_cfg
from aegis.intel.lossdb import split_and_write, trade_record
from aegis.intel.paths import FROZEN_V1, INTEL_DIR, ensure_intel_dirs
from aegis.optimizer.walk_forward import run_split_backtest, run_walk_forward, summarize_result


GEN1: list[dict[str, Any]] = [
    {
        "id": "intel_quality_55",
        "kind": "INVENTED_ALGORITHM",
        "weakness": "late_entry",
        "patch": {"intel_enabled": True, "intel_quality_min": 55.0},
        "hypothesis": "Skip CORE signals with TradeQualityScore < 55 (Harris+ER+Jansen+Brooks blend).",
    },
    {
        "id": "intel_chop_er",
        "kind": "book",
        "weakness": "chop",
        "patch": {"intel_enabled": True, "intel_min_er": 0.25},
        "hypothesis": "Kaufman: skip CORE firehose when ER < 0.25 (chop). Meta layer, not a new signal.",
    },
    {
        "id": "intel_range_mid",
        "kind": "book",
        "weakness": "false_breakout",
        "patch": {"intel_enabled": True, "intel_skip_range_mid": True},
        "hypothesis": "Brooks: WAIT (skip bar) when overlapping range and close in the middle third.",
    },
    {
        "id": "intel_combo_q_er",
        "kind": "INVENTED_ALGORITHM",
        "weakness": "chop",
        "patch": {"intel_enabled": True, "intel_quality_min": 50.0, "intel_min_er": 0.20},
        "hypothesis": "Combine quality>=50 and ER>=0.20 around CORE.",
    },
]


def _wins_losses(metrics: dict[str, Any]) -> tuple[int, int]:
    n = int(metrics.get("total_trades") or 0)
    if metrics.get("wins") is not None and metrics.get("losses") is not None:
        return int(metrics["wins"] or 0), int(metrics["losses"] or 0)
    wr = float(metrics.get("win_rate") or 0.0) / 100.0
    wins = int(round(n * wr))
    return wins, n - wins


def loss_removal(base: dict[str, Any], cand: dict[str, Any]) -> dict[str, float]:
    bw, bl = _wins_losses(base)
    cw, cl = _wins_losses(cand)
    avoided = bl - cl
    sacrificed = bw - cw
    eff = (avoided / sacrificed) if sacrificed > 0 else (float("inf") if avoided > 0 else 0.0)
    return {
        "losses_avoided": float(avoided),
        "winners_sacrificed": float(sacrificed),
        "loss_removal_efficiency": None if eff == float("inf") else float(eff),
    }


def _records_from_result(res: BacktestResult, cfg: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if res.trades is None or res.trades.empty:
        return out
    for rec in res.trades.to_dict("records"):
        snap = rec.get("intel_snap")
        row = pd.Series(snap) if isinstance(snap, dict) else None
        out.append(trade_record(rec, row, cfg))
    return out


GEN2: list[dict[str, Any]] = [
    {
        "id": "intel_barbwire",
        "kind": "book",
        "weakness": "barbwire",
        "patch": {"intel_enabled": True, "intel_skip_barbwire": True},
        "hypothesis": "Brooks: WAIT on barbwire (3 overlapping bars + doji). Don't touch.",
    },
    {
        "id": "intel_impulse_against",
        "kind": "book",
        "weakness": "exhaustion",
        "patch": {"intel_enabled": True, "intel_skip_impulse_against": True},
        "hypothesis": "Elder Impulse: reject CORE buy on red impulse / sell on green impulse.",
    },
    {
        "id": "intel_ema_streak_12",
        "kind": "INVENTED_ALGORITHM",
        "weakness": "exhaustion",
        "patch": {"intel_enabled": True, "intel_max_ema_streak": 12},
        "hypothesis": "Skip CORE when close has been on the same EMA side > 12 M1 bars (lag).",
    },
    {
        "id": "intel_chop_doji",
        "kind": "INVENTED_ALGORITHM",
        "weakness": "chop",
        "patch": {"intel_enabled": True, "intel_skip_chop_doji": True},
        "hypothesis": "Volman/Nison doji only when Kaufman ER < 0.20 (chop doji, not all dojis).",
    },
    {
        "id": "intel_rsi_ext",
        "kind": "book",
        "weakness": "exhaustion",
        "patch": {"intel_enabled": True, "intel_skip_rsi_ext": True},
        "hypothesis": "Wilder/Elder: reject buy RSI>=70 and sell RSI<=30 (exhaustion fade risk).",
    },
    {
        "id": "intel_scratch_4",
        "kind": "book",
        "weakness": "left_tail",
        "patch": {"intel_enabled": True, "intel_scratch_pips": 4.0},
        "hypothesis": "Tharp: scratch overlay at 4 pips. CORE TP/SL formula stays 1/30.",
    },
    {
        "id": "intel_scratch_6",
        "kind": "book",
        "weakness": "left_tail",
        "patch": {"intel_enabled": True, "intel_scratch_pips": 6.0},
        "hypothesis": "Tharp: scratch overlay at 6 pips. CORE 1/30 unchanged.",
    },
    {
        "id": "intel_barb_impulse",
        "kind": "INVENTED_ALGORITHM",
        "weakness": "barbwire",
        "patch": {
            "intel_enabled": True,
            "intel_skip_barbwire": True,
            "intel_skip_impulse_against": True,
        },
        "hypothesis": "Combine Brooks barbwire WAIT + Elder impulse-against REJECT.",
    },
    {
        "id": "intel_barb_impulse_scratch5",
        "kind": "INVENTED_ALGORITHM",
        "weakness": "left_tail",
        "patch": {
            "intel_enabled": True,
            "intel_skip_barbwire": True,
            "intel_skip_impulse_against": True,
            "intel_scratch_pips": 5.0,
        },
        "hypothesis": "Barbwire + impulse-against + 5-pip scratch overlay around CORE.",
    },
    {
        "id": "intel_knn_90",
        "kind": "INVENTED_ALGORITHM",
        "weakness": "high_wr_neg_e",
        "patch": {"intel_enabled": True, "intel_knn_min_wr": 0.90, "intel_knn_k": 15},
        "hypothesis": "kNN on past CORE trades only; reject if neighbor WR < 90%.",
    },
    {
        "id": "intel_atr_expand_1_6",
        "kind": "INVENTED_ALGORITHM",
        "weakness": "left_tail",
        "patch": {"intel_enabled": True, "intel_max_atr_expand": 1.6},
        "hypothesis": "WAIT when ATR is 1.6x its SMA (expansion that can tag the 30-pip stop).",
    },
]

GEN2B: list[dict[str, Any]] = [
    {
        "id": "intel_wrong_edge",
        "kind": "book",
        "weakness": "false_breakout",
        "patch": {"intel_enabled": True, "intel_skip_wrong_edge": True},
        "hypothesis": "Brooks/Damir: in a range, reject buy-high and sell-low (CORE does the opposite).",
    },
    {
        "id": "intel_rsi_streak",
        "kind": "INVENTED_ALGORITHM",
        "weakness": "exhaustion",
        "patch": {
            "intel_enabled": True,
            "intel_skip_rsi_ext": True,
            "intel_max_ema_streak": 12,
        },
        "hypothesis": "Combine RSI exhaustion + EMA-side streak>12 (both beat CORE OOS E alone).",
    },
    {
        "id": "intel_time_45",
        "kind": "book",
        "weakness": "left_tail",
        "patch": {"intel_enabled": True, "intel_max_hold_bars": 45},
        "hypothesis": "Grimes/Volman: if the 1-pip scalp has not paid in 45 M1 bars, flatten. CORE SL stays 30.",
    },
    {
        "id": "intel_rsi_time_45",
        "kind": "INVENTED_ALGORITHM",
        "weakness": "left_tail",
        "patch": {
            "intel_enabled": True,
            "intel_skip_rsi_ext": True,
            "intel_max_hold_bars": 45,
        },
        "hypothesis": "Skip RSI-extreme entries and time-stop leftovers at 45 bars.",
    },
    {
        "id": "intel_friday_15",
        "kind": "book",
        "weakness": "left_tail",
        "patch": {"intel_enabled": True, "intel_skip_friday_hour": 15},
        "hypothesis": "Skip CORE from Friday 15:00 UTC (weekend gap on 30-pip stop).",
    },
]

GEN3: list[dict[str, Any]] = [
    {
        "id": "intel_rsi_ext",
        "kind": "book",
        "weakness": "exhaustion",
        "patch": {"intel_enabled": True, "intel_skip_rsi_ext": True},
        "hypothesis": "Reference: Wilder/Elder RSI>=70 buy / <=30 sell already on live YAML.",
    },
    {
        "id": "intel_wrong_extreme",
        "kind": "book",
        "weakness": "false_breakout",
        "patch": {
            "intel_enabled": True,
            "intel_skip_wrong_edge": True,
            "intel_wrong_buy_loc": 0.90,
            "intel_wrong_sell_loc": 0.10,
        },
        "hypothesis": "Brooks/Damir: reject only loc>=0.90 buys / loc<=0.10 sells (all measured SL).",
    },
    {
        "id": "intel_quality_min_40",
        "kind": "INVENTED_ALGORITHM",
        "weakness": "late_entry",
        "patch": {"intel_enabled": True, "intel_quality_min": 40.0},
        "hypothesis": "Quality cap 28 on wrong-extreme / RSI-ext; reject score < 40.",
    },
    {
        "id": "intel_rsi_ext_wrong_extreme",
        "kind": "INVENTED_ALGORITHM",
        "weakness": "exhaustion",
        "patch": {
            "intel_enabled": True,
            "intel_skip_rsi_ext": True,
            "intel_skip_wrong_edge": True,
            "intel_wrong_buy_loc": 0.90,
            "intel_wrong_sell_loc": 0.10,
        },
        "hypothesis": "Live RSI-ext plus extreme wrong-edge (does not replace CORE 1/30).",
    },
    {
        "id": "intel_rsi_ext_quality_40",
        "kind": "INVENTED_ALGORITHM",
        "weakness": "late_entry",
        "patch": {
            "intel_enabled": True,
            "intel_skip_rsi_ext": True,
            "intel_quality_min": 40.0,
        },
        "hypothesis": "Live RSI-ext plus confidence min 40 (wrong-extreme caps at 28).",
    },
]

GEN4: list[dict[str, Any]] = [
    {
        "id": "intel_rsi_ext",
        "kind": "book",
        "weakness": "exhaustion",
        "patch": {"intel_enabled": True, "intel_skip_rsi_ext": True},
        "hypothesis": "Reference: already live. Wilder/Elder RSI exhaustion around CORE.",
    },
    {
        "id": "intel_weak_adx_edge",
        "kind": "book",
        "weakness": "false_breakout",
        "patch": {
            "intel_enabled": True,
            "intel_skip_weak_adx_edge": True,
            "intel_weak_adx": 22.0,
        },
        "hypothesis": (
            "Leftover never-green after rsi_ext: ADX<22 at loc>=0.90 buy / loc<=0.10 sell. "
            "Wilder range + Brooks/Damir edge. Not full wrong_edge."
        ),
    },
    {
        "id": "intel_rsi_ext_weak_adx",
        "kind": "INVENTED_ALGORITHM",
        "weakness": "false_breakout",
        "patch": {
            "intel_enabled": True,
            "intel_skip_rsi_ext": True,
            "intel_skip_weak_adx_edge": True,
            "intel_weak_adx": 22.0,
        },
        "hypothesis": "Live RSI-ext plus weak-ADX range-edge skip around CORE 1/30.",
    },
]

GEN5: list[dict[str, Any]] = [
    {
        "id": "intel_rsi_ext_unready",
        "kind": "book",
        "weakness": "chop",
        "patch": {
            "intel_enabled": True,
            "intel_skip_rsi_ext": True,
            "intel_skip_incomplete": True,
            "intel_skip_extreme_doji": True,
        },
        "hypothesis": (
            "Around live rsi_ext: WAIT if RSI/ADX/ER/range_loc is NaN (warmup, no lookahead); "
            "REJECT Volman doji at buy loc>=0.90 or sell loc<=0.10. Not weak-ADX, not wrong_edge."
        ),
    },
]


GEN6: list[dict[str, Any]] = [
    {
        "id": "intel_rsi_ext",
        "kind": "book",
        "weakness": "exhaustion",
        "patch": {"intel_enabled": True, "intel_skip_rsi_ext": True},
        "hypothesis": "Live reference: RSI exhaustion around CORE.",
    },
    {
        "id": "intel_rsi_ext_floor_chop",
        "kind": "book",
        "weakness": "chop",
        "patch": {
            "intel_enabled": True,
            "intel_skip_rsi_ext": True,
            "intel_skip_floor_chop_sell": True,
            "intel_floor_chop_er": 0.05,
            "intel_floor_chop_loc": 0.15,
        },
        "hypothesis": (
            "Around rsi_ext: skip SELL only when Kaufman ER<0.05 and range_loc<=0.15 "
            "(floor chop leftover). Buys unchanged. Not a global firehose_min_er."
        ),
    },
]


def first_loss_pattern(records: list[dict[str, Any]]) -> dict[str, Any]:
    """What distinguished losses from wins on the signal bar (no future data)."""
    wins = [r for r in records if r.get("win")]
    losses = [r for r in records if not r.get("win")]
    sl = [r for r in losses if str(r.get("outcome")) == "sl"]
    never_green = [r for r in sl if float(r.get("mfe") or 0) <= 1e-12]

    def rate(rows: list[dict[str, Any]], pred) -> dict[str, float]:
        n = len(rows)
        if n == 0:
            return {"n": 0, "hits": 0, "frac": 0.0}
        hits = sum(1 for r in rows if pred(r))
        return {"n": n, "hits": hits, "frac": hits / n}

    def feat(r: dict[str, Any], key: str):
        return (r.get("features") or {}).get(key)

    def barb(r):
        return bool(feat(r, "brooks_barbwire"))

    def in_range(r):
        return bool(feat(r, "brooks_in_range"))

    def doji(r):
        return bool(feat(r, "volman_doji"))

    def impulse_against(r):
        side = str(r.get("side") or "")
        if side == "buy":
            return bool(feat(r, "impulse_red"))
        if side == "sell":
            return bool(feat(r, "impulse_green"))
        return False

    def chop_doji(r):
        er = feat(r, "kaufman_er")
        try:
            return doji(r) and (er is None or float(er) < 0.20)
        except (TypeError, ValueError):
            return doji(r)

    def _loc(r):
        try:
            return float(feat(r, "range_loc"))
        except (TypeError, ValueError):
            return None

    def wrong_extreme(r):
        if not in_range(r):
            return False
        loc = _loc(r)
        if loc is None:
            return False
        side = str(r.get("side") or "")
        return (side == "buy" and loc >= 0.90) or (side == "sell" and loc <= 0.10)

    def rsi_ext(r):
        try:
            rsi = float(feat(r, "rsi"))
        except (TypeError, ValueError):
            return False
        side = str(r.get("side") or "")
        return (side == "buy" and rsi >= 70.0) or (side == "sell" and rsi <= 30.0)

    avg_win = float(sum(float(r.get("pnl") or 0) for r in wins) / len(wins)) if wins else 0.0
    avg_loss = float(sum(float(r.get("pnl") or 0) for r in losses) / len(losses)) if losses else 0.0
    return {
        "n_win": len(wins),
        "n_loss": len(losses),
        "n_sl": len(sl),
        "n_never_green_sl": len(never_green),
        "avg_win_usd": avg_win,
        "avg_loss_usd": avg_loss,
        "loss_to_win_ratio": (abs(avg_loss) / avg_win) if avg_win > 0 else None,
        "breakeven_wr": (
            abs(avg_loss) / (avg_win + abs(avg_loss)) if (avg_win + abs(avg_loss)) > 0 else None
        ),
        "pattern": (
            "CORE losses are almost all 30-pip stop-outs. Most of those never went "
            "1 pip in favor (MFE=0). Pre-entry: buy at range ceiling / sell at floor "
            "(Brooks/Damir wrong-edge) and/or RSI exhaustion. 1-pip winners also print "
            "at those edges on noise, so WR is not the gate — OOS E after costs is."
        ),
        "pre_entry": {
            "brooks_in_range": {"win": rate(wins, in_range), "loss": rate(losses, in_range)},
            "brooks_barbwire": {"win": rate(wins, barb), "loss": rate(losses, barb)},
            "volman_doji": {"win": rate(wins, doji), "loss": rate(losses, doji)},
            "chop_doji": {"win": rate(wins, chop_doji), "loss": rate(losses, chop_doji)},
            "impulse_against": {
                "win": rate(wins, impulse_against),
                "loss": rate(losses, impulse_against),
            },
            "wrong_extreme": {
                "win": rate(wins, wrong_extreme),
                "loss": rate(losses, wrong_extreme),
            },
            "rsi_ext": {"win": rate(wins, rsi_ext), "loss": rate(losses, rsi_ext)},
        },
    }


def run_generation(
    df: pd.DataFrame,
    *,
    is_fraction: float = 0.7,
    folds: int = 3,
    persist: bool = True,
    experiments: list[dict[str, Any]] | None = None,
    generation: str = "gen1",
    baseline_patch: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ensure_intel_dirs()
    base_cfg = research_cfg()
    if baseline_patch:
        base_cfg.update(baseline_patch)
    baseline_split = run_split_backtest(df, base_cfg, is_fraction=is_fraction)
    baseline_full = run_backtest(df, base_cfg)
    base_sum = summarize_result(baseline_full)
    records = _records_from_result(baseline_full, base_cfg)
    db_stats = split_and_write(records) if persist else {"wins": 0, "losses": 0}
    families = family_counts(records)
    pattern = first_loss_pattern(records)

    champ = {
        "id": "CORE_STRATEGY_V1",
        "metrics": base_sum,
        "oos": baseline_split["oos"],
        "is": baseline_split["is"],
        "families": families,
        "intel": False,
    }
    if persist:
        save_champion(champ)
        (INTEL_DIR / "baseline.json").write_text(
            json.dumps(
                {
                    "id": "CORE_STRATEGY_V1",
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "full": base_sum,
                    "split": baseline_split,
                    "families": families,
                    "pattern": pattern,
                    "generation": generation,
                    "db": db_stats,
                    "frozen": json.loads(FROZEN_V1.read_text(encoding="utf-8")),
                },
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )

    results = []
    best: dict[str, Any] | None = None
    specs = experiments if experiments is not None else GEN1
    for spec in specs:
        cfg = copy.deepcopy(base_cfg)
        cfg.update(spec["patch"])
        split = run_split_backtest(df, cfg, is_fraction=is_fraction)
        full = summarize_result(run_backtest(df, cfg))
        wf = run_walk_forward(df, cfg, folds=folds) if int(folds) > 0 else []
        book = lookup(str(spec["weakness"]))
        lre = loss_removal(base_sum, full)
        row = {
            "id": spec["id"],
            "kind": spec["kind"],
            "hypothesis": spec["hypothesis"],
            "inspiration": book,
            "patch": spec["patch"],
            "baseline": {"full": base_sum, "oos": baseline_split["oos"]},
            "candidate": {"full": full, "oos": split["oos"], "is": split["is"]},
            "walk_forward": wf,
            "loss_removal": lre,
            "win_rate": full.get("win_rate"),
            "profit": full.get("net_pnl"),
            "expectancy": full.get("expectancy_r"),
            "profit_factor": full.get("profit_factor"),
            "drawdown": full.get("max_drawdown_pct"),
            "number_of_trades": full.get("total_trades"),
        }
        oos_e = float(split["oos"].get("expectancy_r") or 0.0)
        base_e = float(baseline_split["oos"].get("expectancy_r") or 0.0)
        oos_n = int(split["oos"].get("total_trades") or 0)
        full_pnl = float(full.get("net_pnl") or 0.0)
        base_pnl = float(base_sum.get("net_pnl") or 0.0)
        accept = oos_e > base_e and oos_n >= 8 and full_pnl >= base_pnl
        row["accepted"] = accept
        row["decision"] = "accept" if accept else "reject"
        row["reason"] = (
            f"OOS E {oos_e:.4f} vs baseline {base_e:.4f}, n={oos_n}, "
            f"full pnl {full_pnl:.2f} vs {base_pnl:.2f}"
        )
        row["lesson"] = (
            "Keep CORE. Meta filter only if OOS expectancy rises after costs."
        )
        if persist:
            append_experiment(row)
        results.append(row)
        if accept and (best is None or oos_e > float(best["candidate"]["oos"].get("expectancy_r") or 0)):
            best = row

    if best and persist:
        save_challenger(best)

    return {
        "baseline": champ,
        "db": db_stats,
        "families": families,
        "pattern": pattern,
        "generation": generation,
        "experiments": results,
        "challenger": best["id"] if best else None,
    }
