import asyncio
import json
import os
import sqlite3
import stat
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from schema_fixtures import create_legacy_schema

from longtian_api.database import CURRENT_DATABASE_VERSION, Database
from longtian_api.main import create_app
from longtian_api.repositories.ai_settings import AISettingsRepository
from longtian_api.schemas.ai_settings import AISettingsUpdate
from longtian_api.services.ai_client import AIConfiguration
from longtian_api.services.ai_credentials import AICredentialError, AICredentialStore
from longtian_api.services.ai_errors import AI_ERROR_CONTRACTS, AIError
from longtian_api.services.ai_settings import AISettingsService
from longtian_api.services.monitoring_rules import MonitoringRuleService

KEY = "fake-only-credential-sentinel"
URL = "https://api.example.com/v1"
PAYLOAD = {"base_url": URL, "model": "test-model", "api_key": KEY}
EMPTY = {"base_url": None, "model": None, "has_api_key": False, "revision": 0}
SAVED = {"base_url": URL, "model": "test-model", "has_api_key": True, "revision": 1}


class FakeClient:
    def __init__(self) -> None:
        self.calls = 0
        self.closed = False
        self.error: Exception | None = None

    async def test_connection(self, configuration: AIConfiguration) -> None:
        self.calls += 1
        assert configuration.model == "test-model"
        assert configuration.api_key.get_secret_value() == KEY
        if self.error:
            raise self.error

    async def aclose(self) -> None:
        self.closed = True


def make_service(tmp_path: Path, client: FakeClient | None = None) -> AISettingsService:
    service = AISettingsService(
        Database(tmp_path / "product.sqlite3"), client=client or FakeClient()
    )
    service.initialize()
    return service


def make_app(tmp_path: Path, fake: FakeClient, **kwargs):
    return create_app(
        monitoring_rule_service_factory=lambda: MonitoringRuleService(
            database_path=tmp_path / "product.sqlite3"
        ),
        ai_settings_service_factory=lambda database: AISettingsService(
            database, client=fake
        ),
        **kwargs,
    )


def assert_error(response, code: str) -> None:
    status, message = AI_ERROR_CONTRACTS[code]
    assert response.status_code == status
    assert response.json() == {"detail": {"code": code, "message": message}}
    assert KEY not in response.text


def test_settings_migration_is_additive_idempotent_and_has_constraints(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "product.sqlite3")
    create_legacy_schema(database, 7)
    with database.connect() as connection:
        before = connection.execute("SELECT * FROM monitoring_rules").fetchall()
    database.initialize()
    database.initialize()
    with database.connect() as connection:
        assert (
            connection.execute("PRAGMA user_version").fetchone()[0]
            == CURRENT_DATABASE_VERSION
        )
        assert connection.execute("SELECT * FROM monitoring_rules").fetchall() == before
        assert connection.execute("SELECT * FROM ai_settings").fetchall() == []
        for identity, revision in ((2, 1), (1, 0)):
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO ai_settings VALUES (?, ?, ?, ?, ?, ?)",
                    (identity, URL, "model", "a" * 32 + ".key", revision, "now"),
                )


def test_save_read_reopen_replace_and_test_never_return_secret(
    tmp_path: Path, caplog
) -> None:
    fake = FakeClient()
    with TestClient(make_app(tmp_path, fake), base_url="http://127.0.0.1") as client:
        assert client.get("/api/v1/ai-settings").json() == EMPTY
        saved = client.put("/api/v1/ai-settings", json=PAYLOAD)
        assert saved.status_code == 200
        assert saved.json() == SAVED
        assert saved.headers["cache-control"] == "no-store"
        assert client.get("/api/v1/ai-settings").json() == SAVED
        assert fake.calls == 0
        retained = client.put(
            "/api/v1/ai-settings",
            json={"base_url": URL + "/", "model": "test-model", "api_key": None},
        )
        assert retained.json() == SAVED
        result = client.post("/api/v1/ai-settings/test", json={"revision": 1})
        assert result.json() == {"status": "connected", "revision": 1}
        assert fake.calls == 1
    assert fake.closed
    reopened = FakeClient()
    with TestClient(
        make_app(tmp_path, reopened), base_url="http://localhost"
    ) as client:
        assert client.get("/api/v1/ai-settings").json() == SAVED
        assert reopened.calls == 0
        model = client.put(
            "/api/v1/ai-settings", json={"base_url": URL, "model": "other-model"}
        )
        assert model.json() == {**SAVED, "model": "other-model", "revision": 2}
        replaced = client.put("/api/v1/ai-settings", json=PAYLOAD)
        assert replaced.json() == {**SAVED, "revision": 3}
        # Re-entering even the same key is an explicit replacement revision.
        assert client.put("/api/v1/ai-settings", json=PAYLOAD).json()["revision"] == 4
    assert len(list((tmp_path / "secrets" / "ai").iterdir())) == 1
    for path in tmp_path.glob("product.sqlite3*"):
        assert KEY.encode() not in path.read_bytes()
    assert KEY not in caplog.text
    assert KEY not in repr(AISettingsUpdate(**PAYLOAD))
    assert "api_key" not in AISettingsUpdate(**PAYLOAD).model_dump_json()


def test_endpoint_change_requires_key_and_failed_commit_keeps_previous_key(
    tmp_path: Path, monkeypatch
) -> None:
    database = Database(tmp_path / "product.sqlite3")
    repository = AISettingsRepository(database)
    service = AISettingsService(database, client=FakeClient(), repository=repository)
    service.initialize()
    service.save(AISettingsUpdate(**PAYLOAD))
    old = repository.read()
    assert old is not None
    for changed in (
        "https://api.example.com/v2",
        "https://other.example.com/v1",
        "https://api.example.com:444/v1",
    ):
        with pytest.raises(AIError, match="ai_api_key_required"):
            service.save(AISettingsUpdate(base_url=changed, model="test-model"))

    class CommitFailure(sqlite3.Connection):
        def execute(self, sql, parameters=()):
            if sql == "COMMIT":
                raise sqlite3.OperationalError("fake secret SQL /private/path " + KEY)
            return super().execute(sql, parameters)

    def failed_connection():
        connection = sqlite3.connect(
            database.path, isolation_level=None, factory=CommitFailure
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    monkeypatch.setattr(database, "connect", failed_connection)
    with pytest.raises(AIError, match="ai_settings_storage_unavailable"):
        service.save(AISettingsUpdate(**{**PAYLOAD, "api_key": "fake-replacement"}))
    assert repository.read() == old
    assert [path.name for path in (tmp_path / "secrets" / "ai").iterdir()] == [
        old.secret_ref
    ]
    assert service.read().model_dump() == SAVED
    asyncio.run(service.test_connection(1))


def test_ai_client_close_failure_still_shuts_down_existing_services(
    tmp_path: Path, monkeypatch
) -> None:
    class FailingCloseClient(FakeClient):
        async def aclose(self) -> None:
            self.closed = True
            raise RuntimeError("simulated AI client close failure")

    fake = FailingCloseClient()
    application = make_app(tmp_path, fake)
    shutdowns = []
    with pytest.raises(RuntimeError, match="simulated AI client close failure"):
        with TestClient(application):
            for name in (
                "search_batch_service",
                "search_run_service",
                "platform_connection_service",
            ):
                service = getattr(application.state, name)
                shutdown = AsyncMock(wraps=service.shutdown)
                monkeypatch.setattr(service, "shutdown", shutdown)
                shutdowns.append(shutdown)
    assert fake.closed
    for shutdown in shutdowns:
        shutdown.assert_awaited_once()


def test_storage_failure_does_not_replace_old_record(
    tmp_path: Path, monkeypatch
) -> None:
    service = make_service(tmp_path)
    service.save(AISettingsUpdate(**PAYLOAD))

    def fail_sync(_descriptor):
        raise OSError("fake private file " + KEY)

    monkeypatch.setattr(os, "fsync", fail_sync)
    with pytest.raises(AIError, match="ai_credentials_unavailable"):
        service.save(AISettingsUpdate(**PAYLOAD))
    assert service.read().model_dump() == SAVED
    assert len(list((tmp_path / "secrets" / "ai").iterdir())) == 1


def test_missing_key_is_an_error_and_can_be_replaced(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    service.save(AISettingsUpdate(**PAYLOAD))
    key_file = next((tmp_path / "secrets" / "ai").iterdir())
    key_file.unlink()
    with pytest.raises(AIError, match="ai_credentials_unavailable"):
        service.read()
    with pytest.raises(AIError, match="ai_credentials_unavailable"):
        service.save(AISettingsUpdate(base_url=URL, model="new-model"))
    assert service.save(AISettingsUpdate(**PAYLOAD)).revision == 2


def test_credential_modes_path_validation_and_safe_removal(tmp_path: Path) -> None:
    store = AICredentialStore(tmp_path)
    reference = store.create(SecretStr(KEY))
    directory = tmp_path / "secrets" / "ai"
    path = directory / reference
    assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    assert stat.S_IMODE(directory.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert store.read(reference).get_secret_value() == KEY
    for bad in ("../outside.key", str(path), "not-a-reference"):
        with pytest.raises(AICredentialError):
            store.read(bad)
        with pytest.raises(AICredentialError):
            store.remove(bad)
    path.chmod(0o644)
    with pytest.raises(AICredentialError):
        store.read(reference)
    with pytest.raises(AICredentialError):
        store.remove(reference)
    path.chmod(0o600)
    extra = directory / "unrelated"
    extra.write_text("untouched")
    store.remove(reference)
    assert extra.read_text() == "untouched"


@pytest.mark.parametrize(
    "kind",
    ["directory", "file", "runtime", "hardlink", "world_writable", "wrong_owner"],
)
def test_secret_store_rejects_unsafe_ownership_and_symlinks(
    tmp_path: Path, kind: str, monkeypatch
) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir(mode=0o700)
    store = AICredentialStore(runtime)
    reference = store.create(SecretStr(KEY))
    directory = runtime / "secrets" / "ai"
    path = directory / reference
    if kind == "directory":
        directory.rename(runtime / "moved")
        directory.symlink_to(runtime / "moved", target_is_directory=True)
    elif kind == "file":
        path.rename(directory / "moved")
        path.symlink_to(directory / "moved")
    elif kind == "runtime":
        alias = tmp_path / "alias"
        alias.symlink_to(runtime, target_is_directory=True)
        store = AICredentialStore(alias)
    elif kind == "hardlink":
        os.link(path, directory / "extra")
    elif kind == "wrong_owner":
        current = os.geteuid()
        monkeypatch.setattr(os, "geteuid", lambda: current + 1)
    else:
        directory.chmod(0o755)
    with pytest.raises(AICredentialError):
        store.read(reference)


@pytest.mark.parametrize(
    "data", [b"", b"contains space", b"bad\nkey", b"\xff", b"a" * 4097]
)
def test_corrupt_secret_is_not_an_unconfigured_success(
    tmp_path: Path, data: bytes
) -> None:
    store = AICredentialStore(tmp_path)
    reference = store.create(SecretStr(KEY))
    (tmp_path / "secrets" / "ai" / reference).write_bytes(data)
    with pytest.raises(AICredentialError):
        store.read(reference)


@pytest.mark.parametrize(
    "payload",
    [
        {**PAYLOAD, "extra": KEY},
        {**PAYLOAD, "model": 1},
        {**PAYLOAD, "api_key": 123},
        {**PAYLOAD, "api_key": [KEY]},
        {"base_url": URL},
        [KEY],
    ],
)
def test_strict_request_errors_are_redacted(tmp_path: Path, payload, caplog) -> None:
    with TestClient(
        make_app(tmp_path, FakeClient()), base_url="http://127.0.0.1"
    ) as client:
        assert_error(client.put("/api/v1/ai-settings", json=payload), "invalid_request")
        assert_error(
            client.put(
                "/api/v1/ai-settings",
                content='{ "api_key": "' + KEY,
                headers={"Content-Type": "application/json"},
            ),
            "invalid_request",
        )
        assert_error(
            client.post("/api/v1/ai-settings/test", json={"revision": "1"}),
            "invalid_request",
        )
    assert KEY not in caplog.text


def test_semantic_and_revision_errors(tmp_path: Path) -> None:
    with TestClient(
        make_app(tmp_path, FakeClient()), base_url="http://127.0.0.1"
    ) as client:
        assert_error(
            client.post("/api/v1/ai-settings/test", json={"revision": 1}),
            "ai_configuration_required",
        )
        assert_error(
            client.put(
                "/api/v1/ai-settings", json={"base_url": URL, "model": "test-model"}
            ),
            "ai_api_key_required",
        )
        for field, value, code in (
            ("base_url", "http://localhost/v1", "invalid_ai_base_url"),
            ("model", " ", "invalid_ai_model"),
            ("api_key", " ", "invalid_ai_api_key"),
            ("api_key", "", "invalid_ai_api_key"),
        ):
            assert_error(
                client.put("/api/v1/ai-settings", json={**PAYLOAD, field: value}), code
            )
        client.put("/api/v1/ai-settings", json=PAYLOAD)
        assert_error(
            client.post("/api/v1/ai-settings/test", json={"revision": 2}),
            "ai_configuration_changed",
        )


@pytest.mark.parametrize(
    "headers",
    [
        {"Origin": "null"},
        {"Origin": "https://evil.example"},
        {"Origin": "http://localhost:9999"},
        {"Host": "evil.example"},
        {"Host": "localhost.evil.example"},
        {"Origin": "http://127.0.0.1/path"},
        {"Origin": "http://127.0.0.1?"},
        {"Sec-Fetch-Site": "cross-site"},
    ],
)
def test_mutation_origin_and_host_guards(tmp_path: Path, headers) -> None:
    fake = FakeClient()
    with TestClient(make_app(tmp_path, fake), base_url="http://127.0.0.1") as client:
        assert_error(
            client.put("/api/v1/ai-settings", json=PAYLOAD, headers=headers),
            "ai_request_forbidden",
        )
        assert_error(
            client.post(
                "/api/v1/ai-settings/test", json={"revision": 1}, headers=headers
            ),
            "ai_request_forbidden",
        )
        assert client.get("/api/v1/ai-settings").json() == EMPTY
        assert fake.calls == 0


def test_local_clients_and_explicit_frontend_origin_are_allowed_but_json_required(
    tmp_path: Path,
) -> None:
    with TestClient(
        make_app(
            tmp_path,
            FakeClient(),
            ai_frontend_origins=("http://localhost:5173", "https://evil.example"),
        ),
        base_url="http://127.0.0.1",
    ) as client:
        for origin in (None, "http://127.0.0.1", "http://localhost:5173"):
            response = client.put(
                "/api/v1/ai-settings",
                json=PAYLOAD,
                headers={"Origin": origin} if origin else {},
            )
            assert response.status_code == 200
        assert_error(
            client.put(
                "/api/v1/ai-settings",
                json=PAYLOAD,
                headers={"Origin": "https://evil.example"},
            ),
            "ai_request_forbidden",
        )
        assert_error(
            client.put(
                "/api/v1/ai-settings",
                content=json.dumps(PAYLOAD),
                headers={"Content-Type": "text/plain"},
            ),
            "ai_json_required",
        )


def test_all_provider_errors_and_unexpected_errors_are_sanitized(
    tmp_path: Path, caplog
) -> None:
    fake = FakeClient()
    with TestClient(make_app(tmp_path, fake), base_url="http://127.0.0.1") as client:
        client.put("/api/v1/ai-settings", json=PAYLOAD)
        for code in (
            "ai_authentication_failed",
            "ai_model_not_found",
            "ai_rate_limited",
            "ai_provider_unavailable",
            "ai_timeout",
            "ai_invalid_response",
            "ai_unsupported_input",
            "ai_request_too_large",
            "ai_destination_forbidden",
        ):
            fake.error = AIError(code)
            assert_error(
                client.post("/api/v1/ai-settings/test", json={"revision": 1}), code
            )
        fake.error = RuntimeError("/private/file " + KEY)
        assert_error(
            client.post("/api/v1/ai-settings/test", json={"revision": 1}),
            "ai_provider_unavailable",
        )
        fake.error = None
        assert (
            client.post("/api/v1/ai-settings/test", json={"revision": 1}).status_code
            == 200
        )
    assert KEY not in caplog.text


def test_operation_lease_prevents_rotation_overlap_and_releases_on_cancellation(
    tmp_path: Path,
) -> None:
    service = make_service(tmp_path)
    service.save(AISettingsUpdate(**PAYLOAD))

    async def exercise():
        entered = asyncio.Event()
        hold = asyncio.Event()

        async def operation():
            async with service.operation(1) as configuration:
                assert KEY not in repr(configuration)
                entered.set()
                await hold.wait()

        task = asyncio.create_task(operation())
        await entered.wait()
        with pytest.raises(AIError, match="ai_operation_active"):
            await asyncio.to_thread(service.save, AISettingsUpdate(**PAYLOAD))
        with pytest.raises(AIError, match="ai_operation_active"):
            async with service.operation(1):
                pytest.fail("overlapping operation admitted")
        assert (await asyncio.to_thread(service.read)).revision == 1
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        with pytest.raises(AIError, match="ai_configuration_changed"):
            async with service.operation(9):
                pytest.fail("stale configuration admitted")
        assert (await service.test_connection(1)).revision == 1
        assert (
            await asyncio.to_thread(service.save, AISettingsUpdate(**PAYLOAD))
        ).revision == 2

    asyncio.run(exercise())
