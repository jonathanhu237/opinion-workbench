"""Offline evidence session. It cannot acquire a browser or download anything."""

from contextlib import asynccontextmanager
from uuid import uuid4

from longtian_api.services.content_enrichment import (
    ContentEnrichmentError,
    EnrichmentItem,
)
from longtian_api.services.enrichment_models import (
    EnrichedContent,
    evidence_fingerprint,
)
from longtian_api.services.enrichment_staging import ValidatedMedia
from longtian_api.services.settled_tasks import database_call


class StoredContentSession:
    def __init__(self, attempt, *, cache=None):
        self.attempt = attempt
        self.cache = cache

    @asynccontextmanager
    async def item(self, *, run_id, result_id, expected_source):
        saved = self.attempt.input
        content = (
            await database_call(self.cache.material, self.attempt)
            if self.cache
            else None
        )
        if (
            saved is not None
            and saved.extractor_version == f"{expected_source.platform}-enrichment-v1"
            and content is None
        ):
            assets = []
            issues = []
            for asset in saved.assets:
                handle = uuid4().hex
                assets.append(
                    {
                        **asset.model_dump(),
                        "asset_id": handle,
                        "role": "content",
                        "blob_ref": handle if asset.status == "ready" else None,
                    }
                )
            for code in saved.issues:
                positions = [
                    asset.position for asset in saved.assets if asset.issue_code == code
                ]
                issues.extend(
                    {"code": code, "asset_position": position}
                    for position in (positions or [None])
                )
            content = EnrichedContent(
                schema_version=1,
                platform=expected_source.platform,
                content_id=expected_source.platform_content_id,
                content_url=expected_source.content_url,
                acquired_at=saved.acquired_at,
                extractor_version=saved.extractor_version,
                status=saved.status,
                text=saved.text,
                detected_modalities=saved.detected_modalities,
                media_inventory_complete=saved.media_inventory_complete,
                assets=assets,
                issues=issues,
            )
            if evidence_fingerprint(content) != self.attempt.input_fingerprint:
                content = None
        if content is None:
            raise ContentEnrichmentError("stored_content_unavailable")
        if evidence_fingerprint(content) != self.attempt.input_fingerprint:
            raise ContentEnrichmentError("stored_content_unavailable")
        lease = (
            await database_call(
                self.cache.acquire, self.attempt.source.result_id, content.assets
            )
            if self.cache
            else None
        )
        try:
            data = lease.data if lease else {}
            content = with_available_media(content, data)
            yield EnrichmentItem(
                source=expected_source,
                outcome="completed",
                content=content,
                input_fingerprint=evidence_fingerprint(content),
                media=tuple(
                    ValidatedMedia(
                        asset.asset_id, asset.mime_type, data[asset.position]
                    )
                    for asset in content.assets
                    if asset.position in data
                ),
            )
        finally:
            if lease:
                await database_call(lease.close)


def with_available_media(content, data):
    """Do not change historical input or implicitly fetch a lost original."""
    missing = [
        asset
        for asset in content.assets
        if asset.status == "ready" and asset.position not in data
    ]
    if not missing:
        return content
    payload = content.model_dump()
    payload["status"] = "partial"
    for asset in missing:
        value = payload["assets"][asset.position]
        value.update(
            status="unavailable",
            blob_ref=None,
            sha256=None,
            mime_type=None,
            byte_size=None,
            width=None,
            height=None,
            duration_ms=None,
            audio_track="not_applicable" if asset.kind == "image" else "unknown",
            coverage="unknown",
            issue_code="asset_unavailable",
        )
        payload["issues"].append(
            {"code": "asset_unavailable", "asset_position": asset.position}
        )
    return EnrichedContent.model_validate(payload)
