"""Stored material first; only an explicit new native acquisition may use Chrome."""

from contextlib import AsyncExitStack, asynccontextmanager

from longtian_api.repositories.content_materials import ContentMaterialRepository
from longtian_api.services.content_enrichment import ContentEnrichmentError
from longtian_api.services.settled_tasks import database_call
from longtian_api.services.stored_content import StoredContentSession


class ManualAcquisitionPause(Exception):
    """The durable parent holds the browser; do not settle this as item failure."""


class ManualContentSession:
    def __init__(self, attempt, *, enrichment, database, on_pause):
        self.attempt = attempt
        self.enrichment = enrichment
        self.materials = ContentMaterialRepository(database)
        self.on_pause = on_pause

    @asynccontextmanager
    async def item(self, *, run_id, result_id, expected_source):
        arguments = dict(
            run_id=run_id, result_id=result_id, expected_source=expected_source
        )
        async with AsyncExitStack() as stack:
            try:
                acquired = await stack.enter_async_context(
                    StoredContentSession(self.attempt, materials=self.materials).item(
                        **arguments
                    )
                )
            except ContentEnrichmentError as error:
                if (
                    error.code != "stored_content_unavailable"
                    or not self.enrichment.native_acquisition
                    or self.attempt.input is not None
                ):
                    raise
                if not self.enrichment.supports_platform(expected_source.platform):
                    raise ContentEnrichmentError("platform_not_supported") from None
                session = await stack.enter_async_context(self.enrichment.operation())

                async def save_progress(content, _media=()):
                    await database_call(self.materials.save, result_id, content)

                acquired = await stack.enter_async_context(
                    session.item(**arguments, on_content=save_progress)
                )
                if acquired.content is not None:
                    await save_progress(acquired.content)
                if acquired.outcome in (
                    "login_required",
                    "manual_challenge_required",
                    "platform_blocked_or_rate_limited",
                ):
                    await self.on_pause(self.attempt, session, acquired.outcome)
                    raise ManualAcquisitionPause from None
            yield acquired
