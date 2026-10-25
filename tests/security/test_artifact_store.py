"""ArtifactStore boundary security (S5-T25): path traversal, symlink escape,
oversized streams, content-addressed dedup, tamper detection."""

import hashlib

import pytest
from agora_api.artifact_store import ArtifactTooLarge, LocalArtifactStore


async def _chunks(*parts: bytes):
    for p in parts:
        yield p


async def test_put_stream_computes_hash_and_dedups(tmp_path):
    store = LocalArtifactStore(tmp_path)
    blob1 = await store.put_stream(_chunks(b"hello ", b"world"))
    assert blob1.content_hash == hashlib.sha256(b"hello world").hexdigest()
    assert blob1.content_size == 11
    blob2 = await store.put_stream(_chunks(b"hello world"))
    assert blob2.storage_key == blob1.storage_key  # identical bytes dedup to one blob


async def test_oversized_stream_aborts_and_leaves_no_orphan_final_file(tmp_path):
    store = LocalArtifactStore(tmp_path)
    with pytest.raises(ArtifactTooLarge):
        await store.put_stream(_chunks(b"a" * 10, b"b" * 10), max_bytes=15)
    assert not any(store.blobs_dir.rglob("*"))
    assert not any(store.quarantine_dir.iterdir())  # temp file cleaned up on failure


async def test_storage_key_path_traversal_rejected(tmp_path):
    store = LocalArtifactStore(tmp_path)
    with pytest.raises(ValueError, match="escapes"):
        await store.open_stream("../../../../etc/passwd")
    with pytest.raises(ValueError, match="escapes"):
        await store.open_stream("sha256/../../secret")


async def test_verify_detects_tampering(tmp_path):
    store = LocalArtifactStore(tmp_path)
    blob = await store.put_stream(_chunks(b"original bytes"))
    assert await store.verify(blob.storage_key, blob.content_hash) is True
    (store.root / blob.storage_key).write_bytes(b"tampered")
    assert await store.verify(blob.storage_key, blob.content_hash) is False


async def test_stat_returns_none_for_missing_blob(tmp_path):
    store = LocalArtifactStore(tmp_path)
    assert await store.stat("sha256/ab/" + "0" * 64) is None


async def test_reupload_repairs_corruption_even_when_size_matches(tmp_path):
    store = LocalArtifactStore(tmp_path)
    blob = await store.put_stream(_chunks(b"original"))
    (tmp_path / blob.storage_key).write_bytes(b"tampered")
    assert not await store.verify(blob.storage_key, blob.content_hash)
    restored = await store.put_stream(_chunks(b"original"))
    assert restored == blob
    assert await store.verify(blob.storage_key, blob.content_hash)


async def test_missing_blob_fails_before_stream_is_returned(tmp_path):
    store = LocalArtifactStore(tmp_path)
    with pytest.raises(FileNotFoundError):
        await store.open_stream("sha256/ab/" + "0" * 64)
