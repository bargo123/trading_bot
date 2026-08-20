"""Restart-safe incremental market-evidence ingestion (P9).

Every cycle ingests NEW COMPLETED M1 observations since a persisted cursor,
labels them only after their forward horizon has actually occurred inside the
fetched data (no lookahead), deduplicates by symbol/bar_time, appends raw
evidence, and merges labelled records into the analogue index incrementally.

Point-in-time rules:
- the most recent (in-flight) bar per symbol is always excluded;
- a bar is labelled using only bars AFTER it that already exist as completed
  observations in the same fetch;
- the cursor advances only to the newest COMPLETED bar ingested.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

CURSOR_SCHEMA = "ingest_cursor.v1"


def load_cursor(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if isinstance(payload, dict) and payload.get("schema") == CURSOR_SCHEMA:
            return payload
    except (OSError, json.JSONDecodeError):
        pass
    return {"schema": CURSOR_SCHEMA, "symbols": {}, "updated_utc": None}


def save_cursor(cursor: Mapping[str, Any], path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        **dict(cursor),
        "schema": CURSOR_SCHEMA,
        "updated_utc": datetime.now(timezone.utc).isoformat(),
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def fetch_completed_bars(eng, symbol: str, *, since_utc: str | None, max_bars: int = 3000, lookback_days: int = 3) -> pd.DataFrame:
    """Read-only fetch of recent M1 bars, completed bars only, strictly new.

    ``lookback_days`` bounds the fetch window (the engine takes calendar days);
    ``max_bars`` caps how many NEW bars a single cycle will accept, so a very
    old cursor cannot pull an unbounded history in one go.
    """
    bars = eng.bars(symbol, "1m", int(lookback_days))
    frame = pd.DataFrame(
        [
            {
                "time": bar.time,
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
            }
            for bar in bars
        ]
    )
    if frame.empty:
        return frame
    frame["time"] = pd.to_datetime(frame["time"], utc=True)
    frame = frame.sort_values("time").reset_index(drop=True)
    # Exclude the in-flight bar: it is not a completed observation yet.
    frame = frame.iloc[:-1]
    if since_utc:
        since = pd.Timestamp(since_utc)
        frame = frame[frame["time"] > since]
    if max_bars and len(frame) > int(max_bars):
        frame = frame.iloc[-int(max_bars):]
    return frame.reset_index(drop=True)


def append_raw_evidence(frame: pd.DataFrame, symbol: str, path: Path) -> int:
    """Append-only source evidence: one JSON line per completed bar."""
    if frame.empty:
        return 0
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with path.open("a", encoding="utf-8") as fh:
        for _, row in frame.iterrows():
            fh.write(
                json.dumps(
                    {
                        "symbol": str(symbol).upper(),
                        "time": str(row["time"]),
                        "open": float(row["open"]),
                        "high": float(row["high"]),
                        "low": float(row["low"]),
                        "close": float(row["close"]),
                        "volume": float(row["volume"]),
                    },
                    sort_keys=True,
                )
                + "\n"
            )
            written += 1
    return written


def index_record_keys(index_path: Path) -> set[tuple[str, str]]:
    """Existing (symbol, bar_time) pairs so merges dedupe cleanly."""
    try:
        payload = json.loads(Path(index_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    keys = set()
    for rec in payload.get("records") or []:
        keys.add((str(rec.get("symbol")), str(rec.get("bar_time"))))
    return keys


def merge_into_index(index_path: Path, new_rows: list[Mapping[str, Any]], *, provenance: str = "mt5_m1") -> dict[str, Any]:
    """Merge labelled rows into the analogue index, deduped, atomically."""
    index_path = Path(index_path)
    try:
        payload = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        payload = {"schema": "analogue_index.v1", "records": []}
    existing = {(str(r.get("symbol")), str(r.get("bar_time"))) for r in payload.get("records") or []}
    added = []
    for row in new_rows:
        key = (str(row.get("symbol")), str(row.get("bar_time")))
        if key in existing:
            continue
        existing.add(key)
        added.append(dict(row))
    if added:
        payload["records"] = list(payload.get("records") or []) + added
        payload["n"] = len(payload["records"])
        payload["provenance"] = provenance
        payload.setdefault("source", {})["incremental_updated_utc"] = datetime.now(timezone.utc).isoformat()
        tmp = index_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(index_path)
    return {"added": len(added), "total": payload.get("n", 0)}


def dataset_fingerprint(records: list[Mapping[str, Any]]) -> str:
    joined = "\n".join(
        json.dumps(r, sort_keys=True, default=str)
        for r in sorted(records, key=lambda r: (str(r.get("symbol")), str(r.get("bar_time"))))
    )
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def ingest_symbol(
    eng,
    symbol: str,
    *,
    cursor: dict[str, Any],
    pip_by_symbol: Mapping[str, float],
    raw_evidence_path: Path,
    index_path: Path,
    existing_keys: set[tuple[str, str]],
    max_bars: int = 3000,
    lookback_days: int = 3,
) -> dict[str, Any]:
    """Ingest one symbol: fetch -> raw append -> label -> merge -> cursor."""
    from aegis.research.analogues import build_analogues_from_m1

    since = (cursor.get("symbols") or {}).get(str(symbol).upper())
    frame = fetch_completed_bars(
        eng, symbol, since_utc=since, max_bars=max_bars, lookback_days=lookback_days
    )
    out: dict[str, Any] = {"symbol": str(symbol).upper(), "new_bars": int(len(frame))}
    if frame.empty:
        return out
    appended = append_raw_evidence(frame, symbol, raw_evidence_path)
    out["raw_appended"] = appended
    # Label only rows whose full forward horizon exists among completed bars.
    # build_analogues_from_m1 walks idx in [min_bars, len-5); anything it labels
    # used only completed future bars already present in this fetch. step=3 keeps
    # the per-cycle labelling cost bounded (state construction is the hot path).
    min_bars = min(400, max(50, len(frame) // 4))
    rows = build_analogues_from_m1(
        {str(symbol).upper(): frame},
        pip_by_symbol=dict(pip_by_symbol),
        min_bars=min_bars,
        step=3,
    )
    fresh = [
        r for r in rows
        if (str(r.get("symbol")), str(r.get("bar_time"))) not in existing_keys
    ]
    merge = merge_into_index(index_path, fresh)
    out["labelled"] = len(rows)
    out["index_added"] = merge["added"]
    out["last_bar"] = str(frame["time"].iloc[-1])
    return out
