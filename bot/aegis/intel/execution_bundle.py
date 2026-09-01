"""Atomic, non-blocking runtime view of validated research output."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from threading import Lock
import time
from typing import Any, Callable, Mapping

from aegis.research.external_dag.bundles import ExecutionBundle


@dataclass(frozen=True)
class BundleRefreshResult:
    status: str
    reason: str = ""
    bundle_hash: str | None = None


class ExecutionContext:
    """One immutable bundle reference shared by all decision readers."""

    def __init__(self, *, clock: Callable[[], float] = time.time) -> None:
        self._clock = clock
        self._lock = Lock()
        self._snapshot: ExecutionBundle | None = None
        self._loaded_at: float | None = None

    def install(self, bundle: ExecutionBundle, *, loaded_at: float) -> None:
        bundle.validate_for_runtime()
        with self._lock:
            self._snapshot = bundle
            self._loaded_at = float(loaded_at)

    def snapshot(self) -> ExecutionBundle | None:
        # Reading one Python object reference is atomic.  The short lock makes
        # that guarantee explicit and keeps alternate Python runtimes safe.
        with self._lock:
            snapshot = self._snapshot
        if snapshot is not None and self._clock() >= snapshot.expires_at:
            return None
        return snapshot

    def model_for(
        self,
        symbol: str,
        side: str,
        mechanism: str,
        horizon_s: int,
    ) -> Mapping[str, Any] | None:
        snapshot = self.snapshot()
        symbol_key = str(symbol).upper().strip()
        horizon = int(horizon_s)
        if (
            snapshot is None
            or symbol_key not in snapshot.authorized_symbols
            or horizon not in snapshot.authorized_horizons_s
        ):
            return None
        per_symbol = snapshot.models.get(symbol_key)
        per_side = per_symbol.get(str(side).upper()) if isinstance(per_symbol, Mapping) else None
        per_mechanism = (
            per_side.get(str(mechanism)) if isinstance(per_side, Mapping) else None
        )
        if not isinstance(per_mechanism, Mapping):
            return None
        model = per_mechanism.get(str(horizon))
        return model if isinstance(model, Mapping) else None

    def runtime_metadata(
        self,
        symbol: str,
        side: str,
        mechanism: str,
        horizon_s: int,
    ) -> dict[str, Any] | None:
        snapshot = self.snapshot()
        model = self.model_for(symbol, side, mechanism, horizon_s)
        if snapshot is None or model is None:
            return None
        metadata = {
            "execution_bundle_hash": snapshot.bundle_hash,
            "research_bundle_hash": snapshot.research_bundle_hash,
            "dataset_hash": snapshot.dataset_hash,
            "validation_hash": snapshot.validation_hash,
            "model_artifact_hash": snapshot.model_artifact_hash,
            "target_definition": snapshot.target_definition,
            "book_algorithm_count": snapshot.book_algorithm_count,
            "book_context": snapshot.book_context,
            "p_captured_win": model.get("p_captured_win"),
        }
        provenance = snapshot.validation.get("research_provenance")
        if isinstance(provenance, Mapping):
            metadata["research_provenance"] = provenance
        return metadata


class ExecutionBundleLoader:
    """Refresh a context at runner checkpoints; never call from the hot path."""

    def __init__(
        self,
        path: str | Path,
        *,
        context: ExecutionContext,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.path = Path(path)
        self.context = context
        self.clock = clock
        self._last_signature: tuple[int, int] | None = None
        self._last_bundle_hash: str | None = None

    def refresh_if_changed(self) -> BundleRefreshResult:
        try:
            stat = self.path.stat()
        except FileNotFoundError:
            return BundleRefreshResult("MISSING", "execution_bundle_missing")
        except OSError as exc:
            return BundleRefreshResult("IGNORED_INVALID", f"stat_error:{type(exc).__name__}")
        signature = (int(stat.st_mtime_ns), int(stat.st_size))
        if signature == self._last_signature:
            return BundleRefreshResult("UNCHANGED", bundle_hash=self._last_bundle_hash)
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("execution bundle root must be an object")
            bundle = ExecutionBundle.from_dict(raw)
            if bundle.promotion_status != "EXECUTION_CANDIDATE":
                raise ValueError("execution bundle is not execution candidate")
            if bundle.target_definition != "captured_exit_replay":
                raise ValueError("execution bundle target is not executable")
            bundle.validate_for_runtime()
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            self._last_signature = signature
            return BundleRefreshResult(
                "IGNORED_INVALID", f"{type(exc).__name__}:{exc}", self._last_bundle_hash
            )
        self._last_signature = signature
        if self.clock() >= bundle.expires_at:
            return BundleRefreshResult("IGNORED_EXPIRED", "execution_bundle_expired")
        if bundle.bundle_hash == self._last_bundle_hash:
            return BundleRefreshResult("UNCHANGED", bundle_hash=bundle.bundle_hash)
        self.context.install(bundle, loaded_at=self.clock())
        self._last_bundle_hash = bundle.bundle_hash
        return BundleRefreshResult("LOADED", bundle_hash=bundle.bundle_hash)


__all__ = ["BundleRefreshResult", "ExecutionBundleLoader", "ExecutionContext"]
