"""Restart-safe incremental market-evidence ingestion (P9, audited v2).

Cursor model (defect 3):
  raw_cursor   - newest COMPLETED bar observed per symbol (raw evidence stored)
  label_cursor - newest bar LABELLED into the analogue index

A bar observed in cycle N whose forward horizon has not matured yet stays
pending: the label_cursor does not advance past it, so a later cycle labels it
exactly once (dedupe by symbol/bar_time backs this up).

Warm-up (defect 4): the fetch window always includes history BEFORE the
pending targets so point-in-time state construction has >= WARMUP_BARS of
prior context; only NEW matured targets are appended.

Sampling (defect 5): every eligible matured observation is labelled (step=1).
No silent subsampling.

Point-in-time rules:
- the most recent (in-flight) bar per symbol is always excluded;
- a target is MATURED only when MATURITY_BARS completed bars exist after it,
  matching the forward-outcome simulator's horizon, so labels never depend on
  how many extra bars a later cycle happens to fetch;
- labels use only bars AFTER the target that already exist as completed data.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

CURSOR_SCHEMA = "ingest_cursor.v2"
WARMUP_BARS = 400          # prior history required for state construction
MATURITY_BARS = 120        # forward completed bars required before labelling


def load_cursor(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if isinstance(payload, dict) and payload.get("schema") == CURSOR_SCHEMA:
            return payload
    except (OSError, json.JSONDecodeError):
        pass
    # v1 cursors migrate: their single timestamp becomes both cursors.
    try:
        legacy = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        legacy = {}
    symbols = {}
    for sym, ts in (legacy.get("symbols") or {}).items():
        if isinstance(ts, str):
            symbols[str(sym).upper()] = {"raw_cursor": ts, "label_cursor": ts}
    return {"schema": CURSOR_SCHEMA, "symbols": symbols, "updated_utc": None}


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
    """Read-only fetch of recent M1 bars, completed bars only.

    The window INCLUDES pre-cursor history: it is the warm-up context for
    labelling, not a duplication source (targets are cursor-filtered later).
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
    if max_bars and len(frame) > int(max_bars):
        frame = frame.iloc[-int(max_bars):]
    return frame.reset_index(drop=True)


def append_raw_evidence(frame: pd.DataFrame, symbol: str, path: Path, *, since_utc: str | None) -> int:
    """Append-only source evidence for bars newer than the raw cursor."""
    if frame.empty:
        return 0
    rows = frame
    if since_utc:
        rows = rows[rows["time"] > pd.Timestamp(since_utc)]
    if rows.empty:
        return 0
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with path.open("a", encoding="utf-8") as fh:
        for _, row in rows.iterrows():
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


def label_matured_targets(
    frame: pd.DataFrame,
    *,
    symbol: str,
    pip: float,
    label_cursor: str | None,
    warmup_bars: int = WARMUP_BARS,
    maturity_bars: int = MATURITY_BARS,
) -> tuple[list[dict[str, Any]], str | None]:
    """Label every PENDING bar whose forward horizon has fully matured.

    Pending = bar_time > label_cursor. Matured = at least ``maturity_bars``
    completed bars follow it inside this window, so the label is identical no
    matter which cycle computes it (no lookahead, no timing dependence).

    Returns (rows, newest_labelled_iso). Bars too close to the window start
    for warm-up stay pending (label_cursor does not advance past them).
    """
    from aegis.research.analogues import _forward_outcome
    from aegis.research.analogues import signature_from_state
    from aegis.research.exit_hypotheses import thesis_geometry
    from aegis.research.market_state import build_market_state

    if frame.empty:
        return [], None
    times = frame["time"]
    if label_cursor:
        cutoff = pd.Timestamp(label_cursor)
        first_pending = int((times > cutoff).to_numpy().nonzero()[0][0]) if bool((times > cutoff).any()) else len(frame)
    else:
        first_pending = 0
    # Warm-up guard: targets before this index lack prior context in-window.
    start = max(first_pending, int(warmup_bars))
    last_matured = len(frame) - int(maturity_bars)  # exclusive bound
    rows: list[dict[str, Any]] = []
    newest: str | None = None
    for idx in range(start, max(start, last_matured)):
        hist = frame.iloc[: idx + 1]
        bar_time = times.iloc[idx]
        try:
            state = build_market_state(symbol=symbol, m1=hist)
        except ValueError:
            continue
        close = float(hist["close"].iloc[-1])
        m15 = state.structure.get("M15") or {}
        structure_kind = str(m15.get("kind") or "none")
        side = "buy" if close >= float(hist["close"].iloc[-2]) else "sell"
        if structure_kind == "breakout":
            resistance = m15.get("resistance")
            support = m15.get("support")
            if resistance is not None and close > float(resistance):
                side = "buy"
            elif support is not None and close < float(support):
                side = "sell"
        geometry = thesis_geometry(
            side=side,
            support=None if m15.get("support") is None else float(m15["support"]),
            resistance=None if m15.get("resistance") is None else float(m15["resistance"]),
            buffer=pip,
        )
        if geometry is None or geometry.invalidation_price is None:
            continue
        outcome = _forward_outcome(
            frame,
            start_idx=idx,
            side=side,
            invalidation=float(geometry.invalidation_price),
            target=geometry.target_price,
            pip=pip,
        )
        if outcome is None:
            continue
        sig = signature_from_state(state.as_dict(), side=side, setup=structure_kind)
        rows.append(
            {
                "bar_time": str(bar_time),
                "symbol": str(symbol).upper(),
                "side": side,
                "setup": structure_kind,
                "regime": sig["regime"],
                "structure": sig["structure"],
                "volatility": sig["volatility"],
                "session": sig["session"],
                "h1_direction": sig["h1_direction"],
                "m5_direction": sig["m5_direction"],
                "outcome": float(outcome),
            }
        )
        newest = str(bar_time)
    return rows, newest


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
    """Ingest one symbol: fetch -> raw append -> label matured -> merge -> cursors."""
    sym = str(symbol).upper()
    raw_cursor, label_cursor = cursor_timestamps(cursor, sym)
    entry: dict[str, str | None] = {
        "raw_cursor": raw_cursor,
        "label_cursor": label_cursor,
    }
    frame = fetch_completed_bars(
        eng, symbol, since_utc=None, max_bars=max_bars, lookback_days=lookback_days
    )
    out: dict[str, Any] = {"symbol": sym, "new_bars": 0, "raw_appended": 0,
                           "labelled": 0, "index_added": 0}
    if frame.empty:
        return out
    out["new_bars"] = int(len(frame))
    out["raw_appended"] = append_raw_evidence(
        frame, symbol, raw_evidence_path, since_utc=raw_cursor
    )
    rows, newest_labelled = label_matured_targets(
        frame, symbol=sym, pip=float(pip_by_symbol.get(symbol, 0.0001)),
        label_cursor=label_cursor,
    )
    fresh = [
        r for r in rows
        if (str(r.get("symbol")), str(r.get("bar_time"))) not in existing_keys
    ]
    merge = merge_into_index(index_path, fresh)
    out["labelled"] = len(rows)
    out["index_added"] = merge["added"]
    # Advance cursors ONLY over persisted observations.
    newest_raw = str(frame["time"].iloc[-1])
    entry["raw_cursor"] = newest_raw
    if newest_labelled:
        entry["label_cursor"] = newest_labelled
    cursor.setdefault("symbols", {})[sym] = entry
    out["raw_cursor"] = entry["raw_cursor"]
    out["label_cursor"] = entry.get("label_cursor")
    out["last_bar"] = newest_raw
    return out


def cursor_timestamps(cursor: Mapping[str, Any], symbol: str) -> tuple[str | None, str | None]:
    """Read v2 cursor bounds while tolerating legacy string-valued entries."""
    entry = (cursor.get("symbols") or {}).get(str(symbol).upper())
    if isinstance(entry, Mapping):
        return entry.get("raw_cursor"), entry.get("label_cursor")
    if isinstance(entry, str):
        return entry, entry
    return None, None
