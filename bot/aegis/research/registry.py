"""Append-only experiment registry. Failed rows are never deleted."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aegis.research.paths import DEFAULT_REGISTRY, ensure_research_dirs

_SCHEMA = """
CREATE TABLE IF NOT EXISTS experiments (
    id TEXT PRIMARY KEY,
    ts_utc TEXT NOT NULL,
    hypothesis TEXT NOT NULL,
    parent_id TEXT,
    status TEXT NOT NULL,
    code_commit TEXT,
    config_fingerprint TEXT NOT NULL,
    dataset_fingerprint TEXT NOT NULL,
    similarity_key TEXT NOT NULL,
    provenance_json TEXT,
    params_json TEXT,
    metrics_json TEXT,
    wr REAL,
    expectancy REAL,
    profit_factor REAL,
    max_drawdown_pct REAL,
    tail_loss REAL,
    n_trades INTEGER,
    rejection_reason TEXT,
    new_reason TEXT
);
CREATE INDEX IF NOT EXISTS idx_experiments_sim ON experiments(similarity_key);
"""


class EquivalentExperimentError(ValueError):
    """Retry of a rejected equivalent experiment without an explicit new reason."""


class DuplicateExperimentError(ValueError):
    """This experiment id is already stored; the registry is append-only."""


def similarity_key(config_fingerprint: str, dataset_fingerprint: str, hypothesis: str) -> str:
    hypo = " ".join(str(hypothesis).lower().split())
    return f"{config_fingerprint}:{dataset_fingerprint}:{hypo}"


class ExperimentRegistry:
    def __init__(self, path: Path | None = None) -> None:
        ensure_research_dirs()
        self.path = Path(path) if path is not None else DEFAULT_REGISTRY
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as con:
            con.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(str(self.path))
        con.row_factory = sqlite3.Row
        return con

    def record(self, row: dict[str, Any]) -> str:
        cfg_fp = str(row["config_fingerprint"])
        ds_fp = str(row["dataset_fingerprint"])
        hypothesis = str(row.get("hypothesis") or "")
        key = similarity_key(cfg_fp, ds_fp, hypothesis)
        new_reason = str(row.get("new_reason") or "").strip()
        with self._connect() as con:
            prior = con.execute(
                "SELECT id, status FROM experiments WHERE similarity_key = ?",
                (key,),
            ).fetchall()
            if prior and not new_reason:
                if any(str(p["status"]) == "rejected" for p in prior):
                    raise EquivalentExperimentError(
                        "equivalent rejected experiment exists; pass new_reason to retry"
                    )
            if con.execute(
                "SELECT 1 FROM experiments WHERE id = ?", (str(row["id"]),)
            ).fetchone():
                raise DuplicateExperimentError(
                    f"experiment id {str(row['id'])!r} already recorded; mint a new id"
                )
            metrics = dict(row.get("metrics") or {})
            for k in ("net_pnl", "win_rate", "expectancy", "profit_factor", "n_trades"):
                if k in row and k not in metrics:
                    metrics[k] = row[k]
            payload = {
                "id": str(row["id"]),
                "ts_utc": str(row.get("ts_utc") or datetime.now(timezone.utc).isoformat()),
                "hypothesis": hypothesis,
                "parent_id": row.get("parent_id"),
                "status": str(row.get("status") or "open"),
                "code_commit": row.get("code_commit"),
                "config_fingerprint": cfg_fp,
                "dataset_fingerprint": ds_fp,
                "similarity_key": key,
                "provenance_json": json.dumps(row.get("provenance") or {}, default=str),
                "params_json": json.dumps(row.get("params") or row.get("patch") or {}, default=str),
                "metrics_json": json.dumps(metrics, default=str),
                "wr": row.get("win_rate") if row.get("win_rate") is not None else row.get("wr"),
                "expectancy": row.get("expectancy"),
                "profit_factor": row.get("profit_factor"),
                "max_drawdown_pct": row.get("max_drawdown_pct"),
                "tail_loss": row.get("tail_loss"),
                "n_trades": row.get("n_trades"),
                "rejection_reason": row.get("rejection_reason"),
                "new_reason": new_reason or None,
            }
            con.execute(
                """
                INSERT INTO experiments (
                    id, ts_utc, hypothesis, parent_id, status, code_commit,
                    config_fingerprint, dataset_fingerprint, similarity_key,
                    provenance_json, params_json, metrics_json,
                    wr, expectancy, profit_factor, max_drawdown_pct, tail_loss,
                    n_trades, rejection_reason, new_reason
                ) VALUES (
                    :id, :ts_utc, :hypothesis, :parent_id, :status, :code_commit,
                    :config_fingerprint, :dataset_fingerprint, :similarity_key,
                    :provenance_json, :params_json, :metrics_json,
                    :wr, :expectancy, :profit_factor, :max_drawdown_pct, :tail_loss,
                    :n_trades, :rejection_reason, :new_reason
                )
                """,
                payload,
            )
        return str(row["id"])

    def all_rows(self) -> list[dict[str, Any]]:
        with self._connect() as con:
            rows = con.execute("SELECT * FROM experiments ORDER BY ts_utc, id").fetchall()
        return [self._row_dict(r) for r in rows]

    def get(self, experiment_id: str) -> dict[str, Any] | None:
        with self._connect() as con:
            row = con.execute(
                "SELECT * FROM experiments WHERE id = ?", (experiment_id,)
            ).fetchone()
        return self._row_dict(row) if row is not None else None

    @staticmethod
    def _row_dict(row: sqlite3.Row) -> dict[str, Any]:
        out = dict(row)
        try:
            metrics = json.loads(out.get("metrics_json") or "{}")
        except json.JSONDecodeError:
            metrics = {}
        if isinstance(metrics, dict):
            out.setdefault("metrics", metrics)
            for k, v in metrics.items():
                out.setdefault(k, v)
        return out

    def export_jsonl(self, path: Path) -> int:
        rows = self.all_rows()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, default=str) + "\n")
        return len(rows)
