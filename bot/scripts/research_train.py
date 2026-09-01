#!/usr/bin/env python3
"""Train the research-only PnL filter on recorded journal clips. Never trades."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BOT))

from aegis.research.cycle import run_research_cycle  # noqa: E402
from aegis.research.fingerprint import config_fingerprint  # noqa: E402
from aegis.research.ingest import PROTECTED_LIVE_YAML  # noqa: E402
from aegis.research.paths import DEFAULT_REGISTRY, RESEARCH_DIR  # noqa: E402
from aegis.research.reports import write_reports  # noqa: E402
from aegis.research.train import (  # noqa: E402
    MIN_SAMPLED_LOSSES,
    named_always_take_baseline,
    pick_sweep_winner,
    search_bar_clip_filters,
    search_meta_label_filters,
    search_pnl_filters,
    train_pnl_filter,
)


# Alternatives to the live 1-pip/30-pip shape. A target that never risks the stop
# needs a ~97% win rate just to break even, so give the stop a sampled chance.
PAYOFF_GRID = ((1.0, 30.0), (4.0, 8.0), (8.0, 8.0), (12.0, 6.0))


def _replay_config(live_cfg: dict, symbol: str) -> dict:
    """CORE live geometry per symbol, so clips describe the strategy actually running."""
    from aegis.research.baseline import firehose_benchmark_config
    from aegis.research.news import CalendarError, DEFAULT_CALENDAR_PATH, load_calendar_file

    cfg = firehose_benchmark_config()
    cfg["symbol"] = symbol
    for key in (
        "firehose_tp_pips",
        "firehose_sl_pips",
        "firehose_every_bar",
        "firehose_pip_size",
        "session_start_utc",
        "session_end_utc",
        "max_positions",
        "risk_percent",
    ):
        if key in live_cfg:
            cfg[key] = live_cfg[key]
    try:
        cfg["calendar_events"] = load_calendar_file(DEFAULT_CALENDAR_PATH)
    except CalendarError:
        cfg["calendar_events"] = []
    return cfg


def _write_sweep_report(path: Path, sweep: list) -> None:
    """Always persist the sweep, including when nothing qualified. The misses are data."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# Payoff sweep on replayed MT5 bars\n\n"
        "Filtered expectancy is after costs on an untouched time holdout. A row with "
        f"fewer than {MIN_SAMPLED_LOSSES} sampled losses cannot be judged, however good "
        "it looks: a 100% win rate over one trade is not a result.\n\n"
        "| TP pips | SL pips | clips | kept | losses seen | filtered E | always-take E | WR | note |\n"
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
        + "".join(
            f"| {r.get('tp')} | {r.get('sl')} | {r.get('clips')} | {r.get('kept', '-')} | "
            f"{r.get('losses_seen', '-')} | {r.get('filtered_expectancy', '-')} | "
            f"{r.get('always_take_expectancy', '-')} | {r.get('win_rate', '-')} | "
            f"{r.get('skipped', 'judged' if int(r.get('losses_seen') or 0) >= MIN_SAMPLED_LOSSES else 'tail not sampled')} |\n"
            for r in sweep
        ),
        encoding="utf-8",
    )


def _write_entry_report(path: Path, rows: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# Research entry families on replayed MT5 bars\n\n"
        "Challengers to the live every-bar EMA trigger, with ATR stops and R-multiple "
        "targets. `always-take E` is the family's own expectancy after costs on an "
        "untouched time holdout; `filtered E` adds the market-state filter. A family "
        f"with fewer than {MIN_SAMPLED_LOSSES} sampled losses cannot be judged.\n\n"
        "| entry | RR | clips | kept | losses seen | always-take E | filtered E | WR | note |\n"
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
        + "".join(
            f"| {r.get('entry')} | {r.get('rr', '-')} | {r.get('clips')} | {r.get('kept', '-')} | "
            f"{r.get('losses_seen', '-')} | {r.get('always_take_expectancy', '-')} | "
            f"{r.get('filtered_expectancy', '-')} | {r.get('win_rate', '-')} | "
            f"{r.get('skipped', 'judged' if int(r.get('losses_seen') or 0) >= MIN_SAMPLED_LOSSES else 'tail not sampled')} |\n"
            for r in rows
        ),
        encoding="utf-8",
    )


def _worst_case_loss(pnls: list, live_cfg: dict | None) -> float | None:
    """Scale the observed average win by the strategy's stop/target ratio.

    A 1-pip target against a 30-pip stop can print a long win streak before a single
    stop-out lands, so the observed worst loss understates the real risk.
    """
    if not live_cfg:
        return None
    try:
        tp = float(live_cfg.get("firehose_tp_pips") or 0.0)
        sl = float(live_cfg.get("firehose_sl_pips") or 0.0)
    except (TypeError, ValueError):
        return None
    if tp <= 0 or sl <= 0:
        return None
    wins = [float(p) for p in pnls if float(p) > 0]
    if not wins:
        return None
    return (sum(wins) / len(wins)) * (sl / tp)


def _fetch_bars(live_cfg: dict, *, days: int, limit: int) -> tuple[dict, dict]:
    """Read-only MT5 M1 bars per symbol. Never calls shutdown() or disconnect()."""
    import pandas as pd

    from aegis.config import configured_symbols
    from aegis.engines import create_engine

    engine = create_engine({**live_cfg, "allow_live": False})
    if not hasattr(engine, "connect_readonly"):
        raise RuntimeError("engine has no read-only attach; refusing to touch the live terminal")
    engine.connect_readonly()
    frames: dict = {}
    coverage: dict = {}
    for symbol in list(configured_symbols(live_cfg))[: max(1, int(limit))]:
        try:
            bars = engine.bars(symbol, "1m", int(days))
        except Exception as exc:  # noqa: BLE001 - one bad symbol must not kill the round
            coverage[symbol] = {"error": str(exc)[:120]}
            continue
        frame = pd.DataFrame(
            [
                {
                    "time": b.time,
                    "open": b.open,
                    "high": b.high,
                    "low": b.low,
                    "close": b.close,
                    "volume": b.volume,
                }
                for b in bars
            ]
        )
        if len(frame) < 200:
            coverage[symbol] = {"bars": len(frame), "skipped": "too few bars"}
            continue
        frames[symbol] = frame
        coverage[symbol] = {"bars": len(frame)}
    return frames, coverage


def _clips_for_geometry(
    frames: dict,
    live_cfg: dict,
    *,
    tp: float,
    sl: float,
    entry: str = "firehose",
    rr: float = 2.0,
) -> tuple[list, dict]:
    from aegis.backtest import run_backtest
    from aegis.research.barclips import clips_from_backtest_trades

    prepare_fn = signal_fn = None
    if entry == "pullback":
        from aegis.research.entries import prepare_pullback, sig_pullback_retest

        prepare_fn, signal_fn = prepare_pullback, sig_pullback_retest

    clips: list = []
    per_symbol: dict = {}
    for symbol, frame in frames.items():
        cfg = _replay_config(live_cfg, symbol)
        cfg["firehose_tp_pips"] = tp
        cfg["firehose_sl_pips"] = sl
        if entry == "pullback":
            cfg.update(
                {
                    "pullback_rr": rr,
                    "pullback_swing_bars": int(live_cfg.get("pullback_swing_bars", 20)),
                    "pullback_trend_ema": int(live_cfg.get("pullback_trend_ema", 240)),
                    "pullback_touch_bars": int(live_cfg.get("pullback_touch_bars", 10)),
                    "pullback_min_stop_pips": float(live_cfg.get("pullback_min_stop_pips", 3.0)),
                }
            )
        result = run_backtest(frame, cfg, prepare_fn=prepare_fn, signal_fn=signal_fn)
        got = clips_from_backtest_trades(result.trades, data_source="mt5_bars")
        clips.extend(got)
        per_symbol[symbol] = {"trades": int(result.total_trades), "clips": len(got)}
    return clips, per_symbol


def _clips_for_entry(
    frames: dict,
    live_cfg: dict,
    name: str,
    *,
    rr: float = 2.0,
    stop_mult: float = 1.5,
) -> tuple[list, dict]:
    """Replay one research entry family. Exits are ATR/R-multiple, never 1-pip/30-pip."""
    from aegis.backtest import run_backtest
    from aegis.research.barclips import clips_from_backtest_trades
    from aegis.research.entry_signals import entry_families

    prepare_fn, signal_fn = entry_families()[name]

    clips: list = []
    per_symbol: dict = {}
    for symbol, frame in frames.items():
        cfg = _replay_config(live_cfg, symbol)
        cfg["entry_rr"] = rr
        cfg["pullback_rr"] = rr
        cfg["entry_atr_stop_mult"] = stop_mult
        result = run_backtest(frame, cfg, prepare_fn=prepare_fn, signal_fn=signal_fn)
        got = clips_from_backtest_trades(result.trades, data_source="mt5_bars")
        clips.extend(got)
        per_symbol[symbol] = {"trades": int(result.total_trades), "clips": len(got)}
    return clips, per_symbol


def _bar_clips_from_mt5(live_cfg: dict, *, days: int, limit: int) -> tuple[list, dict]:
    frames, coverage = _fetch_bars(live_cfg, days=days, limit=limit)
    tp = float(live_cfg.get("firehose_tp_pips") or 1.0)
    sl = float(live_cfg.get("firehose_sl_pips") or 30.0)
    clips, per_symbol = _clips_for_geometry(frames, live_cfg, tp=tp, sl=sl)
    for symbol, info in per_symbol.items():
        coverage.setdefault(symbol, {}).update(info)
    return clips, coverage


def _write_ml_report(path: Path, trained: dict, cycle: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    wr = trained.get("holdout_win_rate")
    wr_s = "n/a" if wr is None else f"{100.0 * float(wr):.1f}%"
    body = (
        "# Research linear PnL filter\n\n"
        "Not Jansen ML. Not a 100% win-rate claim. Shadow only.\n\n"
        f"- hypothesis: {trained.get('hypothesis')}\n"
        f"- label: {trained.get('label')} (not_jansen_ml={trained.get('not_jansen_ml')})\n"
        f"- clips: {trained.get('n_clips')} train={trained.get('n_train')} "
        f"holdout={trained.get('n_holdout')} taken={trained.get('n_taken')}\n"
        f"- holdout E={trained.get('holdout_expectancy')} PF={trained.get('holdout_profit_factor')} "
        f"WR={wr_s} net={trained.get('holdout_net_pnl')}\n"
        f"- observed losses in the kept set: {trained.get('holdout_n_losses')} "
        f"(worst {trained.get('holdout_worst_loss')}) - a high WR here means the loss "
        f"tail was barely sampled\n"
        f"- always-take holdout E={trained.get('always_take_expectancy')} "
        f"PF={trained.get('always_take_profit_factor')}\n"
        f"- time split: train_max={trained.get('train_bar_max')} "
        f"holdout_min={trained.get('holdout_bar_min')}\n"
        f"- cycle decision: {cycle.get('decision')} ({cycle.get('reason')})\n"
        f"- rank_metric: {trained.get('rank_metric', 'holdout_expectancy')} "
        f"n_searches={trained.get('n_searches', 1)} best={trained.get('best')}\n"
        f"- data_source: {trained.get('data_source', 'live_journal')} "
        f"features={trained.get('feature_cols')}\n"
        f"- placed_orders={cycle.get('placed_orders')} mt5_touched={cycle.get('mt5_touched')} "
        f"promoted_live_yaml={cycle.get('promoted_live_yaml')}\n"
    )
    path.write_text(body, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Research-only PnL filter; never trades")
    parser.add_argument("--search", action="store_true")
    parser.add_argument("--bars", action="store_true", help="replay MT5 bars read-only for clips")
    parser.add_argument(
        "--payoff-sweep",
        action="store_true",
        help="replay several TP/SL geometries on the same bars and compare expectancy",
    )
    parser.add_argument(
        "--entries",
        action="store_true",
        help="replay research entry families (structure breakout / failed break / retest)",
    )
    parser.add_argument("--rr", type=float, default=2.0)
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--symbols", type=int, default=26)
    parser.add_argument("--round", default="r0")
    parser.add_argument(
        "--stack",
        action="store_true",
        help="six-book confluence entry + Prado meta-label filter (max selective WR attempt)",
    )
    parser.add_argument(
        "--purged",
        action="store_true",
        help="Prado/Jansen embargoed holdout split (research_proxy)",
    )
    args = parser.parse_args()
    journal = BOT / "reports" / "mt5_demo_firehose_hw_journal.jsonl"
    heartbeat = BOT / "reports" / "bot_heartbeat.json"
    risk = BOT / "reports" / "risk_state.json"
    deals = BOT / "optimizer" / "metrics" / "trades.jsonl"
    coverage: dict = {}
    live_cfg: dict = {}
    sweep: list = []
    if args.stack:
        from aegis.config import load_config

        live_cfg = load_config(BOT / PROTECTED_LIVE_YAML)
        frames, coverage = _fetch_bars(live_cfg, days=args.days, limit=args.symbols)
        clips, _ = _clips_for_entry(frames, live_cfg, "six_book_stack", rr=args.rr)
        if len(clips) < 40:
            raise SystemExit(
                f"six_book_stack produced only {len(clips)} clips; widen days/symbols or "
                "lower stack_min_votes in config"
            )
        trained = search_meta_label_filters(
            clips,
            round_id=args.round,
            data_source="mt5_bars",
            purged=True,
        )
        sweep = [
            {
                "entry": "six_book_stack",
                "clips": trained["n_clips"],
                "kept": trained["n_taken"],
                "losses_seen": trained["holdout_n_losses"],
                "filtered_expectancy": trained["holdout_expectancy"],
                "always_take_expectancy": trained["always_take_expectancy"],
                "win_rate": trained["holdout_win_rate"],
                "meta_label": trained.get("meta_label"),
            }
        ]
        _write_entry_report(BOT / "reports" / "research" / "six_book_stack.md", sweep)
    elif args.entries:
        from aegis.config import load_config
        from aegis.research.entry_signals import entry_families

        live_cfg = load_config(BOT / PROTECTED_LIVE_YAML)
        frames, coverage = _fetch_bars(live_cfg, days=args.days, limit=args.symbols)
        candidates = []
        for name in entry_families():
            clips, _ = _clips_for_entry(frames, live_cfg, name, rr=args.rr)
            if len(clips) < 60:
                sweep.append({"entry": name, "clips": len(clips), "skipped": "too few clips"})
                continue
            got = search_bar_clip_filters(
                clips,
                round_id=f"{args.round}_{name}",
                data_source="mt5_bars",
                purged=args.purged,
            )
            sweep.append(
                {
                    "entry": name,
                    "rr": args.rr,
                    "clips": got["n_clips"],
                    "kept": got["n_taken"],
                    "losses_seen": got["holdout_n_losses"],
                    "filtered_expectancy": got["holdout_expectancy"],
                    "always_take_expectancy": got["always_take_expectancy"],
                    "win_rate": got["holdout_win_rate"],
                }
            )
            candidates.append({**got, "entry": name})
        _write_entry_report(BOT / "reports" / "research" / "entry_families.md", sweep)
        best_result = pick_sweep_winner(candidates)
        if best_result is None:
            print(json.dumps({"entry_families": sweep, "winner": None}, indent=2, default=str))
            raise SystemExit(
                f"no entry family produced at least {MIN_SAMPLED_LOSSES} sampled losses"
            )
        trained = dict(best_result)
    elif args.payoff_sweep:
        from aegis.config import load_config

        live_cfg = load_config(BOT / PROTECTED_LIVE_YAML)
        frames, coverage = _fetch_bars(live_cfg, days=args.days, limit=args.symbols)
        candidates: list = []
        for tp, sl in PAYOFF_GRID:
            clips, _ = _clips_for_geometry(frames, live_cfg, tp=tp, sl=sl)
            if len(clips) < 60:
                sweep.append({"tp": tp, "sl": sl, "clips": len(clips), "skipped": "too few clips"})
                continue
            got = search_bar_clip_filters(
                clips,
                round_id=f"{args.round}_tp{tp:g}sl{sl:g}",
                data_source="mt5_bars",
                purged=args.purged,
            )
            wins = [p for p in got["holdout_pnls"] if p > 0]
            sweep.append(
                {
                    "tp": tp,
                    "sl": sl,
                    "clips": got["n_clips"],
                    "kept": got["n_taken"],
                    "losses_seen": got["holdout_n_losses"],
                    "filtered_expectancy": got["holdout_expectancy"],
                    "always_take_expectancy": got["always_take_expectancy"],
                    "win_rate": got["holdout_win_rate"],
                    "avg_win": (sum(wins) / len(wins)) if wins else None,
                }
            )
            candidates.append({**got, "tp": tp, "sl": sl})
        sweep_report = BOT / "reports" / "research" / "payoff_sweep.md"
        _write_sweep_report(sweep_report, sweep)
        best_result = pick_sweep_winner(candidates)
        if best_result is None:
            print(json.dumps({"payoff_sweep": sweep, "winner": None}, indent=2, default=str))
            raise SystemExit(
                f"no payoff produced at least {MIN_SAMPLED_LOSSES} sampled losses; "
                f"sweep written to {sweep_report}"
            )
        live_cfg = {
            **live_cfg,
            "firehose_tp_pips": best_result["tp"],
            "firehose_sl_pips": best_result["sl"],
        }
        trained = dict(best_result)
    elif args.bars:
        from aegis.config import load_config

        live_cfg = load_config(BOT / PROTECTED_LIVE_YAML)
        clips, coverage = _bar_clips_from_mt5(live_cfg, days=args.days, limit=args.symbols)
        if len(clips) < 40:
            raise SystemExit(
                f"only {len(clips)} bar clips; refusing to train on too little data"
            )
        trained = search_bar_clip_filters(
            clips, round_id=args.round, data_source="mt5_bars", purged=args.purged
        )
    elif args.search:
        trained = search_pnl_filters(journal, round_id=args.round, purged=args.purged)
    else:
        trained = train_pnl_filter(journal)
    pnls = trained.get("holdout_pnls") or [0.0]
    run_id = f"{trained['id']}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    worst_case = _worst_case_loss(pnls, live_cfg if args.bars else None)
    cycle = run_research_cycle(
        hypothesis=str(trained["hypothesis"]),
        metrics={
            "id": run_id,
            "expectancy": trained["holdout_expectancy"] or 0.0,
            "profit_factor": trained["holdout_profit_factor"] or 0.0,
            "n_trades": trained["n_taken"],
            "net_pnl": trained["holdout_net_pnl"],
            "win_rate": trained["holdout_win_rate"] or 0.0,
        },
        pnls=[float(x) for x in pnls],
        frame_fingerprint=config_fingerprint(
            {
                "n_clips": trained["n_clips"],
                "train_bar_max": trained["train_bar_max"],
                "holdout_bar_min": trained["holdout_bar_min"],
            }
        ),
        config={"id": run_id, "model": trained.get("best") or "ridge_pnl"},
        db_path=DEFAULT_REGISTRY,
        heartbeat_path=heartbeat,
        risk_path=risk,
        journal_path=journal if journal.is_file() else None,
        deals_path=deals if deals.is_file() else None,
        live_config_name=PROTECTED_LIVE_YAML,
        n_searches=int(trained.get("n_searches") or 1),
        worst_case_loss=worst_case,
        new_reason=f"ml search round {args.round}",
    )
    write_reports(
        BOT / "reports" / "research",
        heartbeat_path=heartbeat,
        risk_path=risk,
        journal_path=journal if journal.is_file() else None,
        deals_path=deals if deals.is_file() else None,
        champion=None,
        baseline=named_always_take_baseline(
            trained,
            kind=(
                "stack"
                if args.stack
                else "entries"
                if args.entries
                else "payoff"
                if args.payoff_sweep
                else "bars"
                if args.bars
                else "search"
                if args.search
                else "journal"
            ),
        ),
        last_decision=cycle,
    )
    _write_ml_report(BOT / "reports" / "research" / "ml_filter.md", trained, cycle)
    RESEARCH_DIR.mkdir(parents=True, exist_ok=True)
    out = {"trained": trained, "cycle": cycle, "coverage": coverage, "payoff_sweep": sweep}
    if args.payoff_sweep and sweep:
        _write_sweep_report(BOT / "reports" / "research" / "payoff_sweep.md", sweep)
    print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
