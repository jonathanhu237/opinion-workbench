import hashlib
import json
import os
from uuid import uuid4

import pytest
from enrichment_fixtures import PNG, content_payload, image_asset, write_file

from longtian_api.services.enrichment_models import (
    MAX_MANIFEST_BYTES,
    EnrichmentBudget,
    EnrichmentValidationError,
    ManifestDescriptor,
    evidence_fingerprint,
    validate_content,
)
from longtian_api.services.enrichment_staging import MediaSpool, MediaStagingError


def decoded(payload):
    return validate_content(
        payload,
        platform=payload["platform"],
        content_id=payload["content_id"],
        content_url=payload["content_url"],
        budget=EnrichmentBudget(),
    )


def test_constructing_spool_does_no_io_and_owned_files_clean_without_sibling_damage(
    tmp_path,
):
    root = tmp_path / "media"
    spool = MediaSpool(root)
    assert not root.exists()
    request_id = uuid4()
    operation = spool.create_operation(request_id)
    assert root.stat().st_mode & 0o777 == 0o700
    assert (root / request_id.hex).stat().st_mode & 0o777 == 0o700
    sibling = root / uuid4().hex
    sibling.mkdir(mode=0o700)
    sentinel = sibling / "user-data"
    sentinel.write_text("keep")
    payload = content_payload()
    asset = image_asset()
    payload.update(assets=[asset], detected_modalities=["text", "image"])
    path = write_file(root / request_id.hex, asset["asset_id"], PNG)
    result = operation.read_assets(decoded(payload), 6 * 1024 * 1024)
    assert result[0].data == PNG
    assert str(path) not in repr(result)
    operation.cleanup()
    operation.cleanup()
    assert not (root / request_id.hex).exists()
    assert sentinel.read_text() == "keep"


def test_large_multibyte_manifest_is_verified_without_text_truncation(tmp_path):
    operation = MediaSpool(tmp_path / "media").create_operation(uuid4())
    payload = content_payload()
    payload["text"] = {"title": "", "body": "🛠" * 20_000, "coverage": "complete"}
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    assert 64 * 1024 < len(raw) <= MAX_MANIFEST_BYTES
    handle = uuid4().hex
    write_file(tmp_path / "media" / operation.request_id.hex, handle, raw)
    descriptor = ManifestDescriptor(
        handle=handle,
        byte_size=len(raw),
        sha256=hashlib.sha256(raw).hexdigest(),
        mime_type="application/json",
    )
    content = decoded(operation.read_manifest(descriptor))
    assert content.text.body == "🛠" * 20_000
    operation.cleanup()


def test_native_writer_cannot_overwrite_or_escape_its_owned_scope(tmp_path):
    operation = MediaSpool(tmp_path / "native-media").create_operation(uuid4())
    asset = image_asset()
    operation.write_asset(asset["asset_id"], PNG)
    with pytest.raises(MediaStagingError):
        operation.write_asset(asset["asset_id"], b"overwrite")
    with pytest.raises(MediaStagingError):
        operation.write_asset("../user-data", PNG)
    payload = content_payload()
    payload.update(assets=[asset], detected_modalities=["text", "image"])
    assert operation.read_assets(decoded(payload), 6 * 1024 * 1024)[0].data == PNG
    operation.cleanup()


@pytest.mark.parametrize(
    "damage",
    [
        "symlink",
        "hardlink",
        "permissions",
        "size",
        "hash",
        "mime",
        "dimensions",
        "directory",
    ],
)
def test_asset_validation_fails_closed_and_never_follows_an_external_target(
    tmp_path, damage
):
    root = tmp_path / "media"
    operation = MediaSpool(root).create_operation(uuid4())
    payload = content_payload()
    asset = image_asset()
    directory = root / operation.request_id.hex
    path = write_file(directory, asset["asset_id"], PNG)
    sentinel = tmp_path / "outside"
    sentinel.write_bytes(PNG)
    sentinel.chmod(0o600)
    if damage in {"symlink", "hardlink", "directory"}:
        path.unlink()
        if damage == "symlink":
            path.symlink_to(sentinel)
        elif damage == "hardlink":
            os.link(sentinel, path)
        else:
            path.mkdir()
    elif damage == "permissions":
        path.chmod(0o644)
    elif damage == "size":
        asset["byte_size"] += 1
    elif damage == "hash":
        asset["sha256"] = "0" * 64
    elif damage == "mime":
        bad = b"<html>not media</html>"
        path.write_bytes(bad)
        asset.update(byte_size=len(bad), sha256=hashlib.sha256(bad).hexdigest())
    elif damage == "dimensions":
        asset["width"] = 2
    payload.update(assets=[asset], detected_modalities=["text", "image"])
    with pytest.raises(MediaStagingError) as caught:
        operation.read_assets(decoded(payload), 6 * 1024 * 1024)
    assert str(caught.value) == ""
    assert sentinel.read_bytes() == PNG
    if damage == "directory":
        with pytest.raises(MediaStagingError):
            operation.cleanup()
    else:
        operation.cleanup()
    assert sentinel.read_bytes() == PNG


@pytest.mark.parametrize(
    "handle", ["../outside", "/tmp/outside", "a/b", "a" * 32, "0" * 32]
)
def test_manifest_handles_are_only_random_uuid4_hex(tmp_path, handle):
    with pytest.raises((EnrichmentValidationError, ValueError)):
        ManifestDescriptor(
            handle=handle, byte_size=1, sha256="0" * 64, mime_type="application/json"
        )


def test_root_and_operation_swap_cannot_redirect_cleanup(tmp_path):
    root = tmp_path / "media"
    operation = MediaSpool(root).create_operation(uuid4())
    original = root / operation.request_id.hex
    renamed = root / "preserved-original"
    original.rename(renamed)
    original.mkdir(mode=0o700)
    sentinel = original / uuid4().hex
    sentinel.write_text("not this operation")
    with pytest.raises(MediaStagingError):
        operation.cleanup()
    assert sentinel.read_text() == "not this operation"
    assert renamed.exists()


@pytest.mark.parametrize("kind", ["mode", "symlink", "ancestor-symlink"])
def test_unsafe_roots_are_rejected(tmp_path, kind):
    root = tmp_path / "media"
    if kind == "mode":
        root.mkdir(mode=0o755)
    else:
        target = tmp_path / "target"
        target.mkdir(mode=0o700)
        root.symlink_to(target, target_is_directory=True)
        if kind == "ancestor-symlink":
            root = root / "nested"
    with pytest.raises(MediaStagingError):
        MediaSpool(root).create_operation(uuid4())


def test_duplicate_json_keys_are_not_accepted_in_manifest(tmp_path):
    operation = MediaSpool(tmp_path / "media").create_operation(uuid4())
    raw = b'{"schema_version":1,"schema_version":1}'
    handle = uuid4().hex
    write_file(tmp_path / "media" / operation.request_id.hex, handle, raw)
    descriptor = ManifestDescriptor(
        handle=handle,
        byte_size=len(raw),
        sha256=hashlib.sha256(raw).hexdigest(),
        mime_type="application/json",
    )
    with pytest.raises(MediaStagingError):
        operation.read_manifest(descriptor)
    operation.cleanup()


def test_fingerprint_ignores_handles_and_time_but_not_source_evidence():
    payload = content_payload()
    payload.update(assets=[image_asset()], detected_modalities=["text", "image"])
    before = evidence_fingerprint(decoded(payload))
    payload["acquired_at"] += 1
    handle = uuid4().hex
    payload["assets"][0].update(asset_id=handle, blob_ref=handle)
    assert evidence_fingerprint(decoded(payload)) == before
    payload["text"]["body"] += "新进展"
    assert evidence_fingerprint(decoded(payload)) != before


@pytest.mark.parametrize("replace_operation", [False, True])
def test_allocation_fsync_failure_cleans_only_its_proven_empty_directory(
    tmp_path, monkeypatch, replace_operation
):
    root = tmp_path / "media"
    root.mkdir(mode=0o700)
    sibling = root / uuid4().hex
    sibling.mkdir(mode=0o700)
    sentinel = sibling / "keep"
    sentinel.write_text("unchanged")
    request_id = uuid4()

    def fail_fsync(_descriptor):
        if replace_operation:
            (root / request_id.hex).rename(root / "old-operation")
            (root / request_id.hex).mkdir(mode=0o700)
        raise OSError("synthetic fsync failure")

    monkeypatch.setattr(os, "fsync", fail_fsync)
    with pytest.raises(MediaStagingError, match="^$"):
        MediaSpool(root).create_operation(request_id)
    assert (root / request_id.hex).exists() is replace_operation
    assert sentinel.read_text() == "unchanged"
    assert root.exists()
    if replace_operation:
        assert (root / "old-operation").exists()
