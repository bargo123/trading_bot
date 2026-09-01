#!/usr/bin/env python3
"""Compact live index and batched Parquet storage for Watcher studies."""
from __future__ import annotations

import gzip
import json
import os
import time
from pathlib import Path
from typing import Any, Iterable, Mapping

INDEX_FILE = "blocked_strategy_studies_index.jsonl"
PENDING_FILE = "blocked_strategy_studies_pending.jsonl"
PARQUET_DIR = "blocked_strategy_studies_parquet"
ARCHIVE_DIR = "archives"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _strategies(study: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [dict(row) for row in study.get("strategies", []) if isinstance(row, Mapping)]


def _opinion_counts(strategies: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    counts = {"BUY": 0, "SELL": 0, "NO_TRADE": 0, "NOT_APPLICABLE": 0}
    for row in strategies:
        opinion = _text(row.get("opinion")).upper()
        if opinion in counts:
            counts[opinion] += 1
    return counts


def compact_study_index(study: Mapping[str, Any]) -> dict[str, Any]:
    strategies = _strategies(study)
    result = {key: value for key, value in study.items() if key != "strategies"}
    result["strategy_count"] = study.get("strategy_count") or len(strategies)
    result["opinion_counts"] = _opinion_counts(strategies)
    return result


def _append_json(path: Path, record: Mapping[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(record), sort_keys=True, default=str) + "\n")


def append_study(report_dir: Path, study: Mapping[str, Any]) -> None:
    """Write one small live index row and one crash-recoverable pending study."""
    root = Path(report_dir)
    root.mkdir(parents=True, exist_ok=True)
    pending_path = root / PENDING_FILE
    try:
        pending_offset = pending_path.stat().st_size
    except OSError:
        pending_offset = 0
    _append_json(pending_path, study)
    index_row = compact_study_index(study)
    index_row["pending_offset"] = pending_offset
    _append_json(root / INDEX_FILE, index_row)


def _parquet_modules():
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:  # pragma: no cover - exercised in environments without the optional runtime dependency
        raise RuntimeError("Parquet Watcher storage requires pyarrow") from exc
    return pa, pq


def _write_parquet_batch(report_dir: Path, studies: list[dict[str, Any]], *, now: float | None = None) -> Path | None:
    if not studies:
        return None
    pa, pq = _parquet_modules()
    root = Path(report_dir)
    parquet_dir = root / PARQUET_DIR
    parquet_dir.mkdir(parents=True, exist_ok=True)
    stamp = f"{int(time.time() if now is None else now)}_{time.time_ns()}"
    study_path = parquet_dir / f"batch_{stamp}.studies.parquet"
    strategy_path = parquet_dir / f"batch_{stamp}.strategies.parquet"
    study_tmp = study_path.with_suffix(study_path.suffix + ".tmp")
    strategy_tmp = strategy_path.with_suffix(strategy_path.suffix + ".tmp")
    study_rows = []
    strategy_rows = []
    for study in studies:
        study_id = _text(study.get("study_id"))
        if not study_id:
            continue
        metadata = {key: value for key, value in study.items() if key != "strategies"}
        study_rows.append({"study_id": study_id, "study_json": json.dumps(metadata, sort_keys=True, default=str)})
        for position, strategy in enumerate(_strategies(study)):
            strategy_rows.append({
                "study_id": study_id,
                "strategy_position": position,
                "strategy_json": json.dumps(strategy, sort_keys=True, default=str),
            })
    if not study_rows:
        return None
    try:
        study_schema = pa.schema([("study_id", pa.string()), ("study_json", pa.string())])
        strategy_schema = pa.schema([
            ("study_id", pa.string()),
            ("strategy_position", pa.int32()),
            ("strategy_json", pa.string()),
        ])
        pq.write_table(pa.Table.from_pylist(study_rows, schema=study_schema), study_tmp, compression="zstd")
        if strategy_rows:
            pq.write_table(pa.Table.from_pylist(strategy_rows, schema=strategy_schema), strategy_tmp, compression="zstd")
        os.replace(study_tmp, study_path)
        if strategy_rows:
            os.replace(strategy_tmp, strategy_path)
        return study_path
    except Exception:
        for path in (study_tmp, strategy_tmp, study_path, strategy_path):
            try:
                path.unlink()
            except OSError:
                pass
        raise


def flush_pending_to_parquet(report_dir: Path, *, now: float | None = None) -> Path | None:
    root = Path(report_dir)
    pending_path = root / PENDING_FILE
    if not pending_path.is_file():
        return None
    studies: dict[str, dict[str, Any]] = {}
    try:
        with pending_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    study = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(study, Mapping) and _text(study.get("study_id")):
                    studies[_text(study["study_id"])] = dict(study)
    except OSError:
        return None
    batch = _write_parquet_batch(root, list(studies.values()), now=now)
    if batch is not None:
        pending_path.write_text("", encoding="utf-8")
    return batch


def load_pending_offset_index(report_dir: Path) -> dict[str, int]:
    """Map pending study IDs to byte offsets without decoding full study rows.

    Older pending files predate ``pending_offset`` in the compact index.  Their
    append order matches the tail of the index, so line offsets can be paired
    with those IDs and then validated by ``load_study_from_pending``.
    """
    root = Path(report_dir)
    pending_path = root / PENDING_FILE
    index_path = root / INDEX_FILE
    if not pending_path.is_file() or not index_path.is_file():
        return {}
    try:
        offsets: list[int] = []
        with pending_path.open("rb") as handle:
            while True:
                offset = handle.tell()
                line = handle.readline()
                if not line:
                    break
                if line.strip():
                    offsets.append(offset)
        index_ids: list[str] = []
        with index_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(row, Mapping) and _text(row.get("study_id")):
                    index_ids.append(_text(row["study_id"]))
    except OSError:
        return {}
    if not offsets or len(index_ids) < len(offsets):
        return {}
    return {
        study_id: offset
        for study_id, offset in zip(index_ids[-len(offsets):], offsets)
    }


def _jsonl(path: Path) -> Iterable[dict[str, Any]]:
    if not path.is_file():
        return
    try:
        opener = gzip.open if path.suffix == ".gz" else Path.open
        with opener(path, "rt", encoding="utf-8") if path.suffix == ".gz" else opener(path, encoding="utf-8") as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(row, dict):
                    yield row
    except OSError:
        return


def load_study_index(report_dir: Path) -> list[dict[str, Any]]:
    root = Path(report_dir)
    records: dict[str, dict[str, Any]] = {}
    paths = sorted((root / ARCHIVE_DIR).glob("blocked_strategy_studies_index_*.jsonl.gz"))
    paths.append(root / INDEX_FILE)
    for path in paths:
        for row in _jsonl(path):
            study_id = _text(row.get("study_id"))
            if study_id:
                records[study_id] = row
    return list(records.values())


def load_study_from_pending(
    report_dir: Path, study_id: str, *, offset: int | None = None
) -> dict[str, Any] | None:
    path = Path(report_dir) / PENDING_FILE
    if offset is not None:
        try:
            with path.open("rb") as handle:
                handle.seek(int(offset))
                line = handle.readline()
            row = json.loads(line.decode("utf-8"))
            if isinstance(row, dict) and _text(row.get("study_id")) == study_id:
                return row
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
            pass
    for row in _jsonl(path):
        if _text(row.get("study_id")) == study_id:
            return row
    return None


def load_study_from_parquet(report_dir: Path, study_id: str) -> dict[str, Any] | None:
    pa, pq = _parquet_modules()
    del pa
    root = Path(report_dir) / PARQUET_DIR
    if not root.is_dir():
        return None
    metadata: dict[str, Any] | None = None
    matching_strategy_path: Path | None = None
    for path in sorted(root.glob("batch_*.studies.parquet")):
        table = pq.read_table(path, filters=[("study_id", "=", study_id)], columns=["study_id", "study_json"])
        for row in table.to_pylist():
            if row.get("study_id") == study_id:
                try:
                    value = json.loads(row["study_json"])
                except (TypeError, json.JSONDecodeError):
                    continue
                if isinstance(value, dict):
                    metadata = value
                    matching_strategy_path = path.with_name(path.name.replace(".studies.parquet", ".strategies.parquet"))
    if metadata is None:
        return None
    strategies: list[tuple[int, dict[str, Any]]] = []
    if matching_strategy_path is not None and matching_strategy_path.is_file():
        table = pq.read_table(
            matching_strategy_path,
            filters=[("study_id", "=", study_id)],
            columns=["study_id", "strategy_position", "strategy_json"],
        )
        for row in table.to_pylist():
            if row.get("study_id") != study_id:
                continue
            try:
                value = json.loads(row["strategy_json"])
            except (TypeError, json.JSONDecodeError):
                continue
            if isinstance(value, dict):
                strategies.append((int(row.get("strategy_position") or 0), value))
    result = dict(metadata)
    result["strategies"] = [value for _, value in sorted(strategies)]
    result.setdefault("strategy_count", len(result["strategies"]))
    return result


def migrate_legacy_jsonl(report_dir: Path, source: Path, *, batch_size: int = 25, now: float | None = None) -> tuple[int, int]:
    """Convert a legacy full-study JSONL file into compact index plus Parquet batches."""
    root = Path(report_dir)
    root.mkdir(parents=True, exist_ok=True)
    studies: list[dict[str, Any]] = []
    study_count = 0
    batch_count = 0
    for row in _jsonl(Path(source)):
        if not _text(row.get("study_id")):
            continue
        _append_json(root / INDEX_FILE, compact_study_index(row))
        studies.append(row)
        study_count += 1
        if len(studies) >= batch_size:
            _write_parquet_batch(root, studies, now=now)
            studies = []
            batch_count += 1
    if studies:
        _write_parquet_batch(root, studies, now=now)
        batch_count += 1
    return study_count, batch_count
