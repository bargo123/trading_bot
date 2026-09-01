"""Atomic content-addressed storage for external research artifacts."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Mapping

from .contracts import ArtifactEnvelope, canonical_json, content_hash


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ArtifactIntegrityError(ValueError):
    """Raised when a stored artifact no longer matches its identity."""


class ArtifactStore:
    """Write-once content-addressed JSON artifacts beneath one root."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, artifact_hash: str) -> Path:
        normalized = str(artifact_hash).lower()
        if not _SHA256_RE.fullmatch(normalized):
            raise ValueError("artifact hash must be a lowercase SHA-256 digest")
        return self.root / f"{normalized}.json"

    def put(
        self,
        *,
        producer: str,
        schema: str,
        payload: Mapping[str, Any],
        provenance: Mapping[str, Any] | None = None,
    ) -> ArtifactEnvelope:
        material = {
            "schema_version": "aegis.external_artifact.v1",
            "producer": str(producer),
            "schema": str(schema),
            "payload": dict(payload),
            "provenance": dict(provenance or {}),
        }
        digest = content_hash(material)
        envelope = ArtifactEnvelope(
            producer=material["producer"],
            schema=material["schema"],
            payload=material["payload"],
            provenance=material["provenance"],
            content_hash=digest,
        )
        target = self.path_for(digest)
        if target.exists():
            return self.get(digest)
        encoded = canonical_json(envelope.as_dict())
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=self.root,
            prefix=f".{digest}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
        return envelope

    def get(self, artifact_hash: str) -> ArtifactEnvelope:
        path = self.path_for(artifact_hash)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            material = {
                "schema_version": raw["schema_version"],
                "producer": raw["producer"],
                "schema": raw["schema"],
                "payload": raw["payload"],
                "provenance": raw["provenance"],
            }
        except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ArtifactIntegrityError("artifact is unreadable or malformed") from exc
        actual = content_hash(material)
        recorded = str(raw.get("content_hash") or "")
        if actual != artifact_hash or recorded != artifact_hash:
            raise ArtifactIntegrityError("artifact content hash mismatch")
        return ArtifactEnvelope(
            producer=str(material["producer"]),
            schema=str(material["schema"]),
            payload=dict(material["payload"]),
            provenance=dict(material["provenance"]),
            content_hash=artifact_hash,
            schema_version=str(material["schema_version"]),
        )


__all__ = ["ArtifactIntegrityError", "ArtifactStore"]
