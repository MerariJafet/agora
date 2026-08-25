"""ArtifactStore boundary (S5-T11/T12, ADR-0028).

Vendor-neutral interface: `LocalArtifactStore` is the Sprint 05
implementation (deterministic, zero extra infra, no paid credential — see
sprint-05-plan.md for why a MinIO/S3 adapter was not added this sprint). Any
future S3-compatible adapter implements the same `ArtifactStore` protocol
without callers changing.

Streaming discipline (S5-T12):
- SHA-256 and byte count are computed incrementally as chunks arrive —
  the file is never fully buffered in process memory.
- A configurable byte cap aborts the stream (and deletes the partial file)
  the moment it is exceeded — before "uncontrolled resource consumption",
  not after.
- Bytes land in a quarantine temp file first; only a stream that completes
  and passes validation is atomically renamed into its final content-
  addressed location. A crash mid-upload leaves an orphaned temp file, never
  a half-written "final" blob.
- Storage keys are always AGORA-generated (`sha256/<hex>`), never derived
  from a client-supplied filename — content-addressing also gives free
  deduplication (S5-T27).
"""

import hashlib
import os
import tempfile
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

DEFAULT_MAX_BYTES = 200 * 1024 * 1024  # 200 MB per-file ceiling, configurable
CHUNK_SIZE = 1024 * 1024  # 1 MB read chunks


class ArtifactTooLarge(Exception):
    def __init__(self, limit: int):
        self.limit = limit
        super().__init__(f"artifact exceeds the {limit} byte limit")


@dataclass(frozen=True)
class StoredBlob:
    content_hash: str
    content_size: int
    storage_key: str


class ArtifactStore(Protocol):
    async def put_stream(
        self, chunks: AsyncIterator[bytes], *, max_bytes: int = DEFAULT_MAX_BYTES
    ) -> StoredBlob: ...

    async def open_stream(self, storage_key: str) -> AsyncIterator[bytes]: ...

    async def stat(self, storage_key: str) -> int | None: ...

    async def verify(self, storage_key: str, expected_hash: str) -> bool: ...


class LocalArtifactStore:
    """Filesystem-backed, content-addressed store under `root`."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.blobs_dir = self.root / "sha256"
        self.quarantine_dir = self.root / "_quarantine"
        self.blobs_dir.mkdir(parents=True, exist_ok=True)
        self.quarantine_dir.mkdir(parents=True, exist_ok=True)

    def _final_path(self, content_hash: str) -> Path:
        return self.blobs_dir / content_hash[:2] / content_hash

    async def put_stream(
        self, chunks: AsyncIterator[bytes], *, max_bytes: int = DEFAULT_MAX_BYTES
    ) -> StoredBlob:
        hasher = hashlib.sha256()
        size = 0
        fd, tmp_name = tempfile.mkstemp(dir=self.quarantine_dir)
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "wb") as tmp_file:
                async for chunk in chunks:
                    size += len(chunk)
                    if size > max_bytes:
                        raise ArtifactTooLarge(max_bytes)
                    hasher.update(chunk)
                    tmp_file.write(chunk)
            content_hash = hasher.hexdigest()
            final_path = self._final_path(content_hash)
            final_path.parent.mkdir(parents=True, exist_ok=True)
            if final_path.exists():
                # Content-addressed dedup: identical bytes already stored.
                # Verify the existing blob's size before discarding the
                # upload, so a hash collision (astronomically unlikely) or
                # prior corruption cannot silently masquerade as a match.
                if final_path.stat().st_size == size:
                    tmp_path.unlink(missing_ok=True)
                    return StoredBlob(
                        content_hash, size, f"sha256/{content_hash[:2]}/{content_hash}"
                    )
            os.replace(tmp_path, final_path)  # atomic on the same filesystem
            return StoredBlob(content_hash, size, f"sha256/{content_hash[:2]}/{content_hash}")
        except BaseException:
            tmp_path.unlink(missing_ok=True)
            raise

    async def open_stream(self, storage_key: str) -> AsyncIterator[bytes]:
        path = self._safe_resolve(storage_key)

        async def _iter() -> AsyncIterator[bytes]:
            with path.open("rb") as fh:
                while chunk := fh.read(CHUNK_SIZE):
                    yield chunk

        return _iter()

    async def stat(self, storage_key: str) -> int | None:
        path = self._safe_resolve(storage_key)
        return path.stat().st_size if path.exists() else None

    async def verify(self, storage_key: str, expected_hash: str) -> bool:
        path = self._safe_resolve(storage_key)
        if not path.exists():
            return False
        hasher = hashlib.sha256()
        with path.open("rb") as fh:
            while chunk := fh.read(CHUNK_SIZE):
                hasher.update(chunk)
        return hasher.hexdigest() == expected_hash

    def _safe_resolve(self, storage_key: str) -> Path:
        """Storage keys are AGORA-generated (`sha256/xx/<hash>`), but resolve
        defensively anyway: reject anything that would escape `blobs_dir`."""
        candidate = (self.root / storage_key).resolve()
        try:
            candidate.relative_to(self.blobs_dir.resolve())
        except ValueError:
            raise ValueError("storage_key escapes the artifact store root") from None
        return candidate


_store: LocalArtifactStore | None = None


def get_artifact_store() -> LocalArtifactStore:
    global _store
    if _store is None:
        from agora_api.config import get_settings

        _store = LocalArtifactStore(Path(get_settings().artifact_store_root).expanduser())
    return _store
