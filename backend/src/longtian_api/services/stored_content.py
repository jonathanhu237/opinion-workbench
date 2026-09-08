"""Offline evidence session. It cannot acquire a browser or read media files."""

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
from longtian_api.services.settled_tasks import database_call


class StoredContentSession:
    def __init__(self, attempt, *, materials):
        self.attempt = attempt
        self.materials = materials

    @asynccontextmanager
    async def item(self, *, run_id, result_id, expected_source):
        saved = self.attempt.input
        content = await database_call(self.materials.material, self.attempt)
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
        # Keep historical media metadata readable, but never open or repair a
        # local original after the media capability has been retired.
        yield EnrichmentItem(
            source=expected_source,
            outcome="completed",
            content=content,
            input_fingerprint=evidence_fingerprint(content),
            media=(),
        )
