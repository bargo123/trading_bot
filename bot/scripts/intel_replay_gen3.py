#!/usr/bin/env python3
"""Replay GEN3 filters on CORE trade records (signal-bar features only).

Used when a second MT5 initialize/copy_rates would hang the research process.
Records come from a prior MT5-bar CORE backtest (loss_db + win_db). Skipping a
trade does not resimulate fill of later bars — conservative vs a full path
backtest. Gate is still OOS expectancy after costs, not WR.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd

from aegis.intel.decide import intel_allows
from aegis.intel.paths import INTEL_DIR
from aegis.intel.runner import GEN3


def _load_records() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name in ("loss_db/rows.jsonl", "win_db/rows.jsonl"):
        path = INTEL_DIR / name
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    rows.sort(key=lambda r: str(r.get("entry_time") or ""))
    return rows


def _row(rec: dict[str, Any]) -> pd.Series:
    feat = dict(rec.get("features") or {})
    feat["open"] = feat.get("open", rec.get("entry"))
    feat["close"] = feat.get("close", rec.get("entry"))
    return pd.Series(feat)


def _kept(records: list[dict[str, Any]], patch: dict[str, Any]) -> list[dict[str, Any]]:
    cfg = {"firehose_tp_pips": 1.0, "firehose_pip_size": 0.0001, **patch}
    out = []
    for rec in records:
        side = str(rec.get("side") or "")
        if intel_allows(_row(rec), cfg, side):
            out.append(rec)
    return out


def _stats(records: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(records)
    if n == 0:
        return {"n": 0, "wr": None, "e": None, "pnl": 0.0, "wins": 0, "losses": 0}
    wins = [r for r in records if r.get("win")]
    pnl = float(sum(float(r.get("pnl") or 0) for r in records))
    e = float(sum(float(r.get("r") or 0) for r in records) / n)
    return {
        "n": n,
        "wins": len(wins),
        "losses": n - len(wins),
        "wr": 100.0 * len(wins) / n,
        "e": e,
        "pnl": pnl,
    }


def _split(records: list[dict[str, Any]], frac: float = 0.7) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    cut = max(1, int(len(records) * frac))
    return records[:cut], records[cut:]


def run_replay() -> dict[str, Any]:
    records = _load_records()
    is_rows, oos_rows = _split(records)
    core_full = _stats(records)
    core_oos = _stats(oos_rows)
    experiments = []
    best = None
    for spec in GEN3:
        kept_full = _kept(records, spec["patch"])
        kept_oos = _kept(oos_rows, spec["patch"])
        full = _stats(kept_full)
        oos = _stats(kept_oos)
        oos_e = float(oos["e"] or 0.0)
        base_e = float(core_oos["e"] or 0.0)
        oos_n = int(oos["n"] or 0)
        accept = oos_e > base_e and oos_n >= 8 and float(full["pnl"]) >= float(core_full["pnl"])
        row = {
            "id": spec["id"],
            "hypothesis": spec["hypothesis"],
            "patch": spec["patch"],
            "decision": "accept" if accept else "reject",
            "reason": (
                f"replay OOS E {oos_e:.4f} vs CORE {base_e:.4f}, n={oos_n}, "
                f"full pnl {full['pnl']:.2f} vs {core_full['pnl']:.2f}"
            ),
            "full": full,
            "oos": oos,
            "wins_sacrificed": core_full["wins"] - full["wins"],
            "losses_avoided": core_full["losses"] - full["losses"],
        }
        experiments.append(row)
        if accept and (best is None or oos_e > float((best.get("oos") or {}).get("e") or 0)):
            best = row
    # Live-like: rsi_ext already on. Incremental must beat that OOS E too.
    rsi_spec = next(s for s in experiments if s["id"] == "intel_rsi_ext")
    rsi_oos_e = float((rsi_spec.get("oos") or {}).get("e") or 0)
    for row in experiments:
        if row["id"] == "intel_rsi_ext":
            row["beats_live_rsi_ext"] = None
            continue
        cand_e = float((row.get("oos") or {}).get("e") or 0)
        row["beats_live_rsi_ext"] = bool(row["decision"] == "accept" and cand_e > rsi_oos_e)
        if row["decision"] == "accept" and cand_e <= rsi_oos_e:
            row["decision"] = "reject"
            row["reason"] += f" (does not beat live rsi_ext OOS E {rsi_oos_e:.4f})"
    promote = [r for r in experiments if r["decision"] == "accept" and r.get("beats_live_rsi_ext")]
    if not promote and rsi_spec["decision"] == "accept":
        promote = []  # rsi_ext already live; don't re-promote
    return {
        "method": "chronological_trade_replay",
        "note": (
            "Signal-bar features only. Skipping a 30-pip hold does not free those "
            "bars for later CORE sprays. Conservative vs path-dependent backtest."
        ),
        "n_records": len(records),
        "core_full": core_full,
        "core_oos": core_oos,
        "challenger": (best or {}).get("id") if best else None,
        "promote": [p["id"] for p in promote],
        "experiments": experiments,
        "ts": datetime.now(timezone.utc).isoformat(),
    }


def main() -> None:
    out = run_replay()
    path = INTEL_DIR / "gen3_replay.json"
    path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(json.dumps(out, indent=2, default=str))
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
