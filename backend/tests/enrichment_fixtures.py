"""Small synthetic public-content fixtures; no browser or platform credentials."""

import base64
import hashlib
from pathlib import Path
from uuid import uuid4

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUB"
    "AScY42YAAAAASUVORK5CYII="
)


def content_payload(platform="wb", identity="12345", url=None):
    if platform != "wb":
        raise ValueError("only Weibo fixtures are supported")
    return {
        "schema_version": 1,
        "platform": platform,
        "content_id": identity,
        "content_url": url or f"https://m.weibo.cn/detail/{identity}",
        "acquired_at": 1_788_000_000_000,
        "extractor_version": "wb-enrichment-v1",
        "status": "ready",
        "text": {"title": "正文标题", "body": "完整的正文。", "coverage": "complete"},
        "detected_modalities": ["text"],
        "media_inventory_complete": True,
        "assets": [],
        "issues": [],
    }


def image_asset(data=PNG, **changes):
    handle = uuid4().hex
    return {
        "asset_id": handle,
        "position": 0,
        "kind": "image",
        "role": "content",
        "status": "ready",
        "blob_ref": handle,
        "sha256": hashlib.sha256(data).hexdigest(),
        "mime_type": "image/png",
        "byte_size": len(data),
        "width": 1,
        "height": 1,
        "duration_ms": None,
        "audio_track": "not_applicable",
        "coverage": "complete",
        "issue_code": None,
        **changes,
    }


def write_file(directory: Path, handle: str, data: bytes):
    path = directory / handle
    path.write_bytes(data)
    path.chmod(0o600)
    return path
