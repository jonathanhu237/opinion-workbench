"""One settings owner serializes edits and admission of AI operations."""

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from threading import Event, Lock
from typing import Protocol

from starlette.concurrency import run_in_threadpool

from longtian_api.database import Database
from longtian_api.repositories.ai_settings import (
    AISettingsRecord,
    AISettingsRepository,
    AISettingsStorageError,
)
from longtian_api.schemas.ai_settings import (
    AIConnectionResult,
    AISettings,
    AISettingsUpdate,
)
from longtian_api.services.ai_client import (
    AIClient,
    AIConfiguration,
    normalize_base_url,
)
from longtian_api.services.ai_credentials import (
    AICredentialError,
    AICredentialStore,
    valid_api_key,
)
from longtian_api.services.ai_errors import AIError


class AIClientProtocol(Protocol):
    async def test_connection(self, configuration: AIConfiguration) -> None: ...

    async def aclose(self) -> None: ...


class AISettingsService:
    def __init__(
        self,
        database: Database,
        *,
        repository: AISettingsRepository | None = None,
        credentials: AICredentialStore | None = None,
        client: AIClientProtocol | None = None,
    ) -> None:
        self._database = database
        self._repository = repository or AISettingsRepository(database)
        self._credentials = credentials or AICredentialStore(database.path.parent)
        self._client = client or AIClient()
        self._lock = Lock()
        self._active = Event()

    def initialize(self) -> None:
        self._database.initialize()

    async def shutdown(self) -> None:
        await self._client.aclose()

    @contextmanager
    def _storage_errors(self) -> Iterator[None]:
        try:
            yield
        except AISettingsStorageError:
            raise AIError("ai_settings_storage_unavailable") from None
        except AICredentialError:
            raise AIError("ai_credentials_unavailable") from None

    def read(self) -> AISettings:
        with self._lock, self._storage_errors():
            record = self._repository.read()
            if record is None:
                return AISettings(
                    base_url=None, model=None, has_api_key=False, revision=0
                )
            self._credentials.read(record.secret_ref)
            return self._projection(record)

    def save(self, payload: AISettingsUpdate) -> AISettings:
        base_url = normalize_base_url(payload.base_url)
        model = payload.model.strip()
        if (
            not model
            or len(model) > 200
            or any(ord(c) < 33 or ord(c) > 126 for c in model)
        ):
            raise AIError("invalid_ai_model")
        if payload.api_key is not None and not valid_api_key(
            payload.api_key.get_secret_value()
        ):
            raise AIError("invalid_ai_api_key")
        if not self._lock.acquire(blocking=False):
            raise AIError("ai_operation_active")
        try:
            if self._active.is_set():
                raise AIError("ai_operation_active")
            with self._storage_errors():
                previous = self._repository.read()
                if payload.api_key is None:
                    if previous is None or previous.base_url != base_url:
                        raise AIError("ai_api_key_required")
                    self._credentials.read(previous.secret_ref)
                    if previous.model == model:
                        return self._projection(previous)
                    reference = previous.secret_ref
                else:
                    reference = self._credentials.create(payload.api_key)
                record = AISettingsRecord(
                    base_url=base_url,
                    model=model,
                    secret_ref=reference,
                    revision=previous.revision + 1 if previous else 1,
                )
                try:
                    self._repository.replace(record)
                except BaseException:
                    if payload.api_key is not None:
                        self._remove_superseded(reference)
                    raise
                if previous is not None and previous.secret_ref != reference:
                    self._remove_superseded(previous.secret_ref)
                return self._projection(record)
        finally:
            self._lock.release()

    def _remove_superseded(self, reference: str) -> None:
        try:
            self._credentials.remove(reference)
        except AICredentialError:
            # A failed cleanup cannot roll back a committed replacement. Leave
            # only this exact orphan; never scan/delete guessed runtime files.
            pass

    @asynccontextmanager
    async def operation(self, revision: int) -> AsyncIterator[AIConfiguration]:
        """Reserve a stable configuration; release on success, error or cancellation.

        Admission is nonblocking on the event loop. Filesystem/SQLite reads run in
        the worker pool, after reservation, with no DB transaction held on network.
        """
        if not self._lock.acquire(blocking=False):
            raise AIError("ai_operation_active")
        try:
            if self._active.is_set():
                raise AIError("ai_operation_active")
            self._active.set()
        finally:
            self._lock.release()
        try:
            configuration = await run_in_threadpool(self._configuration, revision)
            yield configuration
        finally:
            # Event has its own short thread-safe lock; a simultaneous GET doing
            # storage I/O cannot block cleanup on the event loop.
            self._active.clear()

    def _configuration(self, revision: int) -> AIConfiguration:
        with self._storage_errors():
            record = self._repository.read()
            if record is None:
                raise AIError("ai_configuration_required")
            if record.revision != revision:
                raise AIError("ai_configuration_changed")
            return AIConfiguration(
                base_url=record.base_url,
                model=record.model,
                revision=record.revision,
                api_key=self._credentials.read(record.secret_ref),
            )

    async def test_connection(self, revision: int) -> AIConnectionResult:
        async with self.operation(revision) as configuration:
            await self._client.test_connection(configuration)
            return AIConnectionResult(revision=configuration.revision)

    @staticmethod
    def _projection(record: AISettingsRecord) -> AISettings:
        return AISettings(
            base_url=record.base_url,
            model=record.model,
            has_api_key=True,
            revision=record.revision,
        )
