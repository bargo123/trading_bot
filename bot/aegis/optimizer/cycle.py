"""One-shot optimizer cycle. Restartable. Separate lock from the paper runner."""
from __future__ import annotations

import logging
import subprocess
import sys
from typing import Any

from aegis.config import load_config
from aegis.optimizer.cursor_cli import maybe_propose_with_cursor
from aegis.optimizer.experiment import (
    accept_experiment,
    load_open_experiment,
    new_experiment_id,
    record_dry_run,
    reject_experiment,
    start_experiment,
)
from aegis.optimizer.hypothesis import (
    core_live_frozen_keys,
    patch_hits_frozen,
    pending_frozen_keys,
    pick_hypothesis,
)
from aegis.optimizer.knowledge import lookup_concept, mark_investigated
from aegis.optimizer.paths import BOT_ROOT, OPTIMIZER_DIR, OPTIMIZER_LOCK, ensure_runtime_dirs
from aegis.optimizer.promote import bot_open_count, promote_if_flat
from aegis.optimizer.research_gate import research_overlay_gate
from aegis.optimizer.snapshot import collect_snapshot
from aegis.optimizer.state import (
    ensure_memory,
    live_config_path,
    PENDING_PROMOTE,
    consumed_hypothesis_ids,
    record_failure,
    refresh_state_md,
    stored_best_expectancy,
)
from aegis.optimizer.walk_forward import (
    accept_gate,
    run_split_backtest,
    run_walk_forward,
    synthetic_ohlcv,
)
from aegis.paper_control import ProcessLock

logger = logging.getLogger(__name__)


def _stored_best_for_gate(live_cfg: dict[str, Any]) -> float | None:
    """Davey: do not rank 1/30 overlays against a different TP/SL champion."""
    if core_live_frozen_keys(live_cfg):
        return None
    return stored_best_expectancy()


def _load_bars(cfg: dict[str, Any], *, no_mt5: bool, lookback_days: int | None = None) -> tuple[Any, str]:
    symbol = str((cfg.get("symbols") or [cfg.get("symbol")])[0])
    tf = str(cfg.get("timeframe") or "1m")
    days = int(lookback_days or cfg.get("lookback_days") or 5)
    if not no_mt5:
        try:
            from aegis.engines import create_engine

            eng = create_engine(cfg)
            if hasattr(eng, "connect_readonly"):
                eng.connect_readonly()
            else:
                eng.connect()
            bars = eng.bars(symbol, tf, days)
            rows = [
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
            import pandas as pd

            df = pd.DataFrame(rows)
            if len(df) >= 80:
                return df, "mt5_bars"
        except Exception as exc:
            logger.warning("optimizer bars MT5 fallback: %s", exc)
    if no_mt5:
        return synthetic_ohlcv(), "synthetic"
    try:
        from aegis.data import fetch_ohlcv

        ysym = symbol if "=" in symbol else f"{symbol}=X"
        df = fetch_ohlcv(ysym, tf if tf != "1m" else "1h", max(days, 30))
        return df, "yahoo"
    except Exception as exc:
        logger.warning("optimizer bars Yahoo fallback to synthetic: %s", exc)
        return synthetic_ohlcv(), "synthetic"


def _run_pytest(subset: list[str], extra: list[str] | None = None) -> tuple[bool, str]:
    cmd = [sys.executable, "-m", "pytest", "-q", *subset, *(extra or [])]
    proc = subprocess.run(cmd, cwd=str(BOT_ROOT), capture_output=True, text=True)
    ok = proc.returncode == 0
    tail = ((proc.stdout or "") + "\n" + (proc.stderr or ""))[-4000:]
    return ok, tail


def run_cycle(
    *,
    dry_run: bool = False,
    no_mt5: bool = False,
    with_cursor: bool = False,
    skip_pytest: bool = False,
) -> dict[str, Any]:
    ensure_runtime_dirs()
    lock = ProcessLock(OPTIMIZER_LOCK)
    if not lock.try_acquire():
        return {"ok": True, "skipped": True, "reason": "optimizer lock held"}
    try:
        mem = ensure_memory()
        opt_cfg = mem["opt_cfg"]
        live_path = live_config_path(opt_cfg)
        cfg = load_config(mem["accepted"] if mem["accepted"].exists() else live_path)
        snap = collect_snapshot(
            cfg,
            no_mt5=no_mt5,
            lookback_days=int(opt_cfg.get("lookback_days") or 14),
        )
        promo_retry: dict[str, Any] = {"skipped": True}
        if not dry_run and (OPTIMIZER_DIR / PENDING_PROMOTE).exists():
            promo_retry = promote_if_flat(
                live_config=live_path, dry_run=False, restart=False
            )
            if promo_retry.get("promoted"):
                cfg = load_config(mem["accepted"] if mem["accepted"].exists() else live_path)
        cursor_info = maybe_propose_with_cursor(
            enabled=with_cursor or bool(opt_cfg.get("with_cursor"))
        )

        open_rec = None if dry_run else load_open_experiment()
        rejected = consumed_hypothesis_ids()
        frozen: set[str] = set()
        try:
            live_cfg = load_config(live_path)
            frozen |= core_live_frozen_keys(live_cfg)
            if (OPTIMIZER_DIR / PENDING_PROMOTE).exists():
                frozen |= pending_frozen_keys(live_cfg, cfg)
        except Exception:
            frozen |= {"firehose_tp_pips", "firehose_sl_pips"}
        if open_rec and open_rec.get("id"):
            hypo = {
                "id": str(open_rec.get("hypothesis_id") or open_rec["id"]),
                "weakness": open_rec.get("weakness") or "high_wr_neg_e",
                "patch": open_rec.get("patch") or {},
                "rationale": open_rec.get("rationale") or "resume open experiment",
            }
            exp_id = str(open_rec["id"])
            resumed = True
        else:
            hypo = None
            proposal = cursor_info.get("proposal") if isinstance(cursor_info, dict) else None
            if (
                isinstance(proposal, dict)
                and str(proposal.get("id")) not in rejected
                and not patch_hits_frozen(proposal.get("patch"), frozen)
            ):
                hypo = proposal
            if hypo is None:
                hypo = pick_hypothesis(snap, cfg, rejected, blocked_keys=frozen)
            resumed = False
            if hypo is None:
                refresh_state_md({"next_step": "No untested hypotheses left."})
                return {
                    "ok": True,
                    "skipped": True,
                    "reason": "no remaining hypotheses",
                    "snapshot": {"mt5_ok": snap.get("mt5_ok"), "metrics": snap.get("metrics")},
                    "cursor": cursor_info,
                    "promote": promo_retry,
                }
            book = lookup_concept(str(hypo["weakness"]))
            exp_id = new_experiment_id(str(hypo["id"]))
            meta = {
                "hypothesis_id": hypo["id"],
                "hypothesis": hypo["rationale"],
                "rationale": hypo["rationale"],
                "weakness": hypo["weakness"],
                "book_file": book["book_file"],
                "snippet_hash": book["snippet_hash"],
                "concept": book["concept"],
            }
            if dry_run:
                from aegis.optimizer.experiment import apply_patch

                df, data_src = _load_bars(
                    cfg,
                    no_mt5=no_mt5,
                    lookback_days=int(opt_cfg.get("lookback_days") or 14),
                )
                is_frac = float(opt_cfg.get("is_fraction") or 0.7)
                cand_cfg = apply_patch(cfg, hypo["patch"])
                base_split = run_split_backtest(df, cfg, is_fraction=is_frac)
                cand_split = run_split_backtest(df, cand_cfg, is_fraction=is_frac)
                ok, reason = accept_gate(
                    base_split["oos"],
                    cand_split["oos"],
                    min_trades=int(opt_cfg.get("min_trades") or 20),
                    dd_tolerance_pct=float(opt_cfg.get("dd_tolerance_pct") or 2.0),
                    stored_best_e=_stored_best_for_gate(cfg),
                )
                if ok:
                    ok, reason = research_overlay_gate(cand_split["oos"], data_source=data_src)
                record = {
                    "id": exp_id,
                    "patch": hypo["patch"],
                    **meta,
                }
                record_dry_run(
                    record,
                    {
                        "live_metrics": snap.get("metrics"),
                        "note": "dry-run: no YAML patch, no promote",
                        "data_source": data_src,
                        "would_accept": ok,
                        "gate_reason": reason,
                    },
                )
                mark_investigated(book["concept"], book["book_file"])
                refresh_state_md({"next_step": f"Next real cycle would try {hypo['id']}."})
                return {
                    "ok": True,
                    "dry_run": True,
                    "experiment_id": exp_id,
                    "hypothesis": hypo,
                    "book": book,
                    "would_accept": ok,
                    "gate_reason": reason,
                    "data_source": data_src,
                    "snapshot": {
                        "mt5_ok": snap.get("mt5_ok"),
                        "mt5_error": snap.get("mt5_error"),
                        "metrics": snap.get("metrics"),
                        "spread_skips": snap.get("spread_skips"),
                    },
                    "cursor": cursor_info,
                }
            record = start_experiment(
                exp_id=exp_id,
                accepted_src=mem["accepted"],
                patch=hypo["patch"],
                meta=meta,
            )
            open_rec = record

        book = lookup_concept(str(hypo["weakness"]))
        mark_investigated(book["concept"], book["book_file"])

        if not skip_pytest:
            subset = list(opt_cfg.get("pytest_subset") or ["tests/test_paper_control.py"])
            extra = list(opt_cfg.get("pytest_extra_args") or [])
            py_ok, py_tail = _run_pytest(subset, extra)
            if not py_ok:
                record_failure("pytest", "subset failed", {"tail": py_tail[-1500:]})
                if not dry_run:
                    reject_experiment(open_rec, {}, "pytest subset failed")
                refresh_state_md({"next_step": "Fix pytest failures before the next cycle."})
                return {"ok": False, "reason": "pytest failed", "log": py_tail[-1500:]}

        df, data_src = _load_bars(
            cfg,
            no_mt5=no_mt5,
            lookback_days=int(opt_cfg.get("lookback_days") or 14),
        )
        from aegis.config import load_config as _load
        from aegis.optimizer.experiment import checkpoint_dir

        baseline_cfg = cfg
        cand_path = checkpoint_dir(exp_id) / "candidate.yaml"
        candidate_cfg = _load(cand_path) if cand_path.exists() else cfg
        is_frac = float(opt_cfg.get("is_fraction") or 0.7)
        base_split = run_split_backtest(df, baseline_cfg, is_fraction=is_frac)
        cand_split = run_split_backtest(df, candidate_cfg, is_fraction=is_frac)
        folds = int(opt_cfg.get("walk_forward_folds") or 0)
        wf = run_walk_forward(df, candidate_cfg, folds=folds) if folds >= 2 else []
        ok, reason = accept_gate(
            base_split["oos"],
            cand_split["oos"],
            min_trades=int(opt_cfg.get("min_trades") or 20),
            dd_tolerance_pct=float(opt_cfg.get("dd_tolerance_pct") or 2.0),
            stored_best_e=_stored_best_for_gate(load_config(live_path)),
        )
        if ok:
            ok, reason = research_overlay_gate(cand_split["oos"], data_source=data_src)
        comparison = {
            "data_source": data_src,
            "baseline": base_split,
            "candidate": cand_split,
            "walk_forward": wf,
            "accept": ok,
            "reason": reason,
        }
        open_n = bot_open_count()
        if ok:
            accepted = accept_experiment(open_rec, cand_split["oos"], bot_open=open_n)
            promo = {"skipped": True}
            if not accepted.get("pending_promote"):
                promo = promote_if_flat(live_config=live_path, dry_run=False, restart=False)
            refresh_state_md({"next_step": f"Accepted {exp_id}. {reason}"})
            return {
                "ok": True,
                "decision": "accept",
                "experiment_id": exp_id,
                "resumed": resumed,
                "comparison": comparison,
                "promote": promo,
                "cursor": cursor_info,
            }
        rejected_rec = reject_experiment(open_rec, cand_split["oos"], reason)
        refresh_state_md({"next_step": f"Rejected {exp_id}: {reason}"})
        return {
            "ok": True,
            "decision": "reject",
            "experiment_id": exp_id,
            "resumed": resumed,
            "record": rejected_rec.get("id"),
            "comparison": comparison,
            "cursor": cursor_info,
        }
    except Exception as exc:
        logger.exception("optimizer cycle failed")
        record_failure("cycle", str(exc))
        return {"ok": False, "error": str(exc)}
    finally:
        lock.release()
