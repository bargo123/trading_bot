"""Durable bid/ask tick warehouse. Offline ingest only; never attached to the live runner."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable, Mapping

import pandas as pd

from aegis.research.dataplane import SCHEMA_VERSION, TICK_COLUMNS, ticks_frame

STORE_SCHEMA = "ticks.v1"

_SQL = """
CREATE TABLE IF NOT EXISTS ticks (
    symbol TEXT NOT NULL,
    ts_utc TEXT NOT NULL,
    ts_ms INTEGER NOT NULL,
    seq INTEGER NOT NULL,
    bid REAL NOT NULL,
    ask REAL NOT NULL,
    last REAL NOT NULL,
    tick_volume REAL NOT NULL,
    flags TEXT NOT NULL,
    source TEXT NOT NULL,
    timezone_name TEXT NOT NULL,
    quality TEXT NOT NULL,
    PRIMARY KEY (symbol, ts_utc, seq)
);
"""


class TickStoreError(ValueError):
    """Corrupt, incomplete, or non-finite tick payload."""


def _finite(value: Any) -> float:
    number = float(value)
    if number != number or number in (float("inf"), float("-inf")):
        raise TickStoreError("non-finite tick field")
    return number


class TickStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as con:
            con.executescript(_SQL)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.path))

    def append(
        self,
        rows: Iterable[Mapping[str, Any]],
        *,
        source: str,
        timezone_name: str,
        quality: str,
    ) -> dict[str, Any]:
        if not source or not timezone_name or not quality:
            raise TickStoreError("source, timezone_name, and quality are required")
        payload = list(rows)
        try:
            frame = ticks_frame(payload)
        except (KeyError, ValueError) as exc:
            raise TickStoreError(str(exc)) from exc
        records: list[tuple[Any, ...]] = []
        for row in frame.to_dict("records"):
            try:
                bid = _finite(row["bid"])
                ask = _finite(row["ask"])
                last = _finite(row["last"])
                vol = _finite(row["tick_volume"])
            except (TypeError, ValueError) as exc:
                raise TickStoreError("non-finite tick field") from exc
            if bid <= 0 or ask <= 0 or ask < bid:
                raise TickStoreError("crossed or non-positive quote")
            records.append(
                (
                    str(row["symbol"]),
                    pd.Timestamp(row["ts_utc"]).isoformat(),
                    int(row["ts_ms"]),
                    int(row["seq"]),
                    bid,
                    ask,
                    last,
                    vol,
                    str(row.get("flags") or ""),
                    source,
                    timezone_name,
                    quality,
                )
            )
        with self._connect() as con:
            con.executemany(
                "INSERT OR REPLACE INTO ticks VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                records,
            )
        blob = json.dumps(
            [{"s": r[0], "t": r[1], "q": r[3], "b": r[4], "a": r[5]} for r in records],
            separators=(",", ":"),
        ).encode("utf-8")
        return {
            "schema": STORE_SCHEMA,
            "dataplane": SCHEMA_VERSION,
            "source": source,
            "timezone_name": timezone_name,
            "quality": quality,
            "n": len(records),
            "fingerprint": hashlib.sha256(blob).hexdigest(),
            "volume_kind": "broker_tick_volume_proxy",
        }

    def load(self, symbol: str) -> pd.DataFrame:
        with self._connect() as con:
            cur = con.execute(
                "SELECT symbol, ts_utc, ts_ms, seq, bid, ask, last, tick_volume, flags, "
                "source, timezone_name, quality FROM ticks WHERE symbol = ? "
                "ORDER BY ts_utc, seq",
                (symbol,),
            )
            cols = [d[0] for d in cur.description]
            data = [dict(zip(cols, row)) for row in cur.fetchall()]
        if not data:
            empty = pd.DataFrame(columns=list(TICK_COLUMNS))
            empty.attrs["volume_kind"] = "broker_tick_volume_proxy"
            empty.attrs["quality"] = "empty"
            return empty
        frame = ticks_frame(data)
        frame.attrs["volume_kind"] = "broker_tick_volume_proxy"
        frame.attrs["source"] = data[0]["source"]
        frame.attrs["timezone_name"] = data[0]["timezone_name"]
        frame.attrs["quality"] = data[0]["quality"]
        return frame
