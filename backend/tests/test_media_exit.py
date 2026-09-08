"""Regression coverage for the one-way media-cache retirement."""

import os
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from enrichment_fixtures import content_payload
from fastapi.testclient import TestClient
from summary_fixtures import seed_run

from longtian_api.database import Database, DatabaseVersionError
from longtian_api.main import create_app
from longtian_api.repositories.content_materials import ContentMaterialRepository
from longtian_api.repositories.search_runs import SearchRunRepository
from longtian_api.services import media_cleanup
from longtian_api.services.enrichment_models import (
    EnrichedContent,
    evidence_fingerprint,
)
from longtian_api.services.media_cleanup import purge_managed_media
from longtian_api.services.monitoring_rules import MonitoringRuleService


def _cache_tables(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE media_cache_owner (
            id INTEGER PRIMARY KEY CHECK(id=1),
            device INTEGER NOT NULL,
            inode INTEGER NOT NULL
        );
        CREATE TABLE media_cache_policy (
            id INTEGER PRIMARY KEY CHECK(id=1),
            retention_days INTEGER NOT NULL,
            capacity_mib INTEGER NOT NULL,
            revision INTEGER NOT NULL
        );
        CREATE TABLE media_cache_entries (
            sha256 TEXT PRIMARY KEY,
            handle TEXT NOT NULL UNIQUE,
            byte_size INTEGER NOT NULL,
            mime_type TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            state TEXT NOT NULL,
            device INTEGER,
            inode INTEGER
        );
        CREATE TABLE media_cache_bindings (
            content_id INTEGER NOT NULL,
            sha256 TEXT NOT NULL,
            PRIMARY KEY(content_id, sha256)
        );
        """
    )


def _owned_original(database: Database, data: bytes = b"media") -> Path:
    root = database.path.parent / "original-media"
    root.mkdir(mode=0o700)
    handle = "a" * 32
    file = root / handle
    file.write_bytes(data)
    file.chmod(0o600)
    root_info = root.stat()
    file_info = file.stat()
    with database.connect() as connection:
        connection.execute(
            "INSERT INTO media_cache_owner VALUES (1, ?, ?)",
            (root_info.st_dev, root_info.st_ino),
        )
        connection.execute(
            "INSERT INTO media_cache_entries VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "b" * 64,
                handle,
                len(data),
                "image/png",
                1,
                "ready",
                file_info.st_dev,
                file_info.st_ino,
            ),
        )
    return file


def test_v37_upgrade_removes_cache_tables_but_keeps_text_and_history(tmp_path):
    database = Database(tmp_path / "legacy.sqlite3")
    database.initialize()
    source_run_id = seed_run(database, 1)
    source = SearchRunRepository(database).get_result_source(
        run_id=source_run_id, result_id=1
    )
    content = EnrichedContent.model_validate(
        content_payload(
            identity=source.platform_content_id, url=source.content_url
        )
    )
    ContentMaterialRepository(database).save(1, content)

    with database.connect() as connection:
        _cache_tables(connection)
        original = _owned_original(database)
        connection.execute("PRAGMA user_version = 37")

    database.initialize()
    database.initialize()

    with database.connect() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 38
        assert connection.execute(
            "SELECT content_json FROM content_materials WHERE content_id=1"
        ).fetchone()[0]
        assert connection.execute(
            "SELECT id FROM search_contents WHERE id=1"
        ).fetchone()[0] == 1
        for table in (
            "media_cache_owner",
            "media_cache_policy",
            "media_cache_entries",
            "media_cache_bindings",
        ):
            assert connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchone() is None
    assert not original.exists()

    material = ContentMaterialRepository(database).material(
        SimpleNamespace(
            source=source,
            input_fingerprint=evidence_fingerprint(content),
        )
    )
    assert material is not None and material.text.body == content.text.body


def test_cleanup_removes_owned_files_and_preserves_mixed_entries(tmp_path):
    database = Database(tmp_path / "cleanup.sqlite3")
    database.initialize()
    with database.connect() as connection:
        _cache_tables(connection)
    managed = _owned_original(database)
    original_root = managed.parent
    note = original_root / "keep.txt"
    note.write_text("do not remove")
    note.chmod(0o600)

    spool = tmp_path / "media"
    spool.mkdir(mode=0o700)
    operation = spool / uuid4().hex
    operation.mkdir(mode=0o700)
    staged = operation / ("c" * 32)
    staged.write_bytes(b"staged")
    staged.chmod(0o600)
    staged_note = operation / "keep.txt"
    staged_note.write_text("do not remove")
    staged_note.chmod(0o600)
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "secret.txt"
    secret.write_text("do not follow")
    escape = operation / "escape"
    escape.symlink_to(outside, target_is_directory=True)

    with database.connect() as connection:
        first = purge_managed_media(tmp_path, connection=connection)
    assert first["complete"] is False
    assert not managed.exists() and note.exists()
    assert not staged.exists() and staged_note.exists()
    assert original_root.exists() and operation.exists()
    assert secret.read_text() == "do not follow" and escape.is_symlink()

    note.unlink()
    staged_note.unlink()
    escape.unlink()
    secret.unlink()
    outside.rmdir()
    with database.connect() as connection:
        second = purge_managed_media(tmp_path, connection=connection)
    assert second["complete"] is True
    assert not original_root.exists() and not spool.exists()
    with database.connect() as connection:
        third = purge_managed_media(tmp_path, connection=connection)
    assert third == {
        "removed_roots": [],
        "removed_files": 0,
        "errors": [],
        "retryable_errors": [],
        "complete": True,
    }


def test_v37_upgrade_keeps_unmanaged_mixed_entries_without_blocking(tmp_path):
    database = Database(tmp_path / "mixed-upgrade.sqlite3")
    database.initialize()
    with database.connect() as connection:
        _cache_tables(connection)
        managed = _owned_original(database)
        note = managed.parent / "keep.txt"
        note.write_text("do not remove")
        note.chmod(0o600)
        connection.execute("PRAGMA user_version = 37")

    database.initialize()

    with database.connect() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 38
        assert connection.execute(
            "SELECT 1 FROM sqlite_master WHERE name='media_cache_entries'"
        ).fetchone() is None
    assert not managed.exists()
    assert note.exists()


def test_v37_upgrade_retries_owned_delete_after_transient_failure(
    tmp_path, monkeypatch
):
    database = Database(tmp_path / "retry-upgrade.sqlite3")
    database.initialize()
    with database.connect() as connection:
        _cache_tables(connection)
        managed = _owned_original(database)
        connection.execute("PRAGMA user_version = 37")

    real_unlink = os.unlink

    def fail_unlink(*args, **kwargs):
        raise PermissionError("synthetic delete failure")

    monkeypatch.setattr(media_cleanup.os, "unlink", fail_unlink)
    with pytest.raises(DatabaseVersionError, match="media cleanup"):
        database.initialize()
    with database.connect() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 37
        assert connection.execute(
            "SELECT 1 FROM sqlite_master WHERE name='media_cache_entries'"
        ).fetchone() is not None
    assert managed.exists()

    monkeypatch.setattr(media_cleanup.os, "unlink", real_unlink)
    database.initialize()
    with database.connect() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 38
        assert connection.execute(
            "SELECT 1 FROM sqlite_master WHERE name='media_cache_entries'"
        ).fetchone() is None
    assert not managed.exists()


def test_v37_upgrade_retries_owned_delete_after_scan_failure(tmp_path, monkeypatch):
    database = Database(tmp_path / "scan-retry-upgrade.sqlite3")
    database.initialize()
    with database.connect() as connection:
        _cache_tables(connection)
        managed = _owned_original(database)
        connection.execute("PRAGMA user_version = 37")

    real_scandir = os.scandir

    def fail_scandir(*args, **kwargs):
        del args, kwargs
        raise OSError("synthetic scan failure")

    monkeypatch.setattr(media_cleanup.os, "scandir", fail_scandir)
    with pytest.raises(DatabaseVersionError, match="media cleanup"):
        database.initialize()
    with database.connect() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 37
        assert connection.execute(
            "SELECT 1 FROM sqlite_master WHERE name='media_cache_entries'"
        ).fetchone() is not None
    assert managed.exists()

    monkeypatch.setattr(media_cleanup.os, "scandir", real_scandir)
    database.initialize()
    with database.connect() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 38
        assert connection.execute(
            "SELECT 1 FROM sqlite_master WHERE name='media_cache_entries'"
        ).fetchone() is None
    assert not managed.exists()


def test_media_cache_routes_and_runtime_service_are_gone(tmp_path):
    app = create_app(
        monitoring_rule_service_factory=lambda: MonitoringRuleService(
            database_path=tmp_path / "api.sqlite3"
        )
    )
    with TestClient(app, base_url="http://127.0.0.1") as client:
        assert client.get("/api/v1/media-cache-settings").status_code == 404
        assert client.get("/api/v1/content-analyses/1/media/0").status_code == 404
        assert not hasattr(app.state, "media_cache")
