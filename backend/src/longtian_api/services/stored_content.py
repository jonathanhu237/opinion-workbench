"""Offline evidence session. It cannot acquire a browser or read media files."""

from contextlib import asynccontextmanager
from uuid import uuid4

from longtian_api.services.content_enrichment import (
    ContentEnrichmentError,
    EnrichmentItem,
)
from longtian_api.services.enrichment_models import (
    EnrichedContent,
    EnrichmentIssue,
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
        # Validate the persisted material before projecting it.  The original
        # fingerprint is the lookup/ownership fence for this attempt; the
        # text-only projection below deliberately receives a new fingerprint
        # and is saved by the caller before it can reach the model or report.
        if evidence_fingerprint(content) != self.attempt.input_fingerprint:
            raise ContentEnrichmentError("stored_content_unavailable")
        # Historical rows may still describe downloaded images or videos.  The
        # retired media capability must not make those bytes/metadata appear as
        # evidence in a new report, while the original material remains
        # readable for old reports and migrations.  Project only at this new
        # execution boundary and retain an explicit gap for the discarded
        # inventory.
        content = _text_only_projection(content)
        yield EnrichmentItem(
            source=expected_source,
            outcome="completed",
            content=content,
            input_fingerprint=evidence_fingerprint(content),
            media=(),
        )


def _text_only_projection(content: EnrichedContent) -> EnrichedContent:
    """Drop historical media evidence without mutating the stored material."""
    media_present = bool(content.assets) or any(
        modality in {"image", "video", "audio", "unknown"}
        for modality in content.detected_modalities
    )
    if not media_present:
        return content

    issues = [
        issue
        for issue in content.issues
        if issue.asset_position is None
        and issue.code
        in {"text_incomplete", "text_unavailable", "text_limit", "structure_changed"}
    ]
    if not any(issue.code == "asset_unavailable" for issue in issues):
        issues.append(EnrichmentIssue(code="asset_unavailable", asset_position=None))
    text_available = bool(content.text.title.strip() or content.text.body.strip())
    status = "partial" if text_available else "unavailable"
    return EnrichedContent.model_validate(
        {
            **content.model_dump(mode="python"),
            "status": status,
            "detected_modalities": ["text"],
            "media_inventory_complete": True,
            "assets": [],
            "issues": [issue.model_dump(mode="python") for issue in issues],
        }
    )
