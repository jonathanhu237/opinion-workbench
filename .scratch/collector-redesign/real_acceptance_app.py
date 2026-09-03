"""Disposable local app harness for the bounded live Weibo acceptance.

This file is intentionally kept under .scratch and is not product code.  It
uses a fresh SQLite database, the project's native collector, and the existing
AI configuration/credential store without copying credential files.
"""

import os
import sqlite3
import sys
from pathlib import Path

import uvicorn

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend" / "src"))

from longtian_api.database import Database  # noqa: E402
from longtian_api.main import create_app  # noqa: E402
from longtian_api.services.ai_credentials import AICredentialStore  # noqa: E402
from longtian_api.services.ai_settings import AISettingsService  # noqa: E402
from longtian_api.services.monitoring_rules import MonitoringRuleService  # noqa: E402
from longtian_api.services.native_chrome import native_collector_factory  # noqa: E402
from longtian_api.services.platform_connections import (  # noqa: E402
    PlatformConnectionService,
)


def prepare_database(path: Path) -> Database:
    database = Database(path)
    database.initialize()
    connection = database.connect()
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "DELETE FROM monitoring_rule_terms WHERE rule_id = 1 AND value <> ?",
            ("龙田街道",),
        )
        source = sqlite3.connect(ROOT / "runtime" / "longtian.sqlite3")
        try:
            source.row_factory = sqlite3.Row
            settings = source.execute(
                "SELECT base_url, model, secret_ref, revision, updated_at "
                "FROM ai_settings WHERE id = 1"
            ).fetchone()
        finally:
            source.close()
        if settings is None:
            raise RuntimeError("The existing AI configuration is unavailable.")
        connection.execute(
            "INSERT INTO ai_settings "
            "(id, base_url, model, secret_ref, revision, updated_at) "
            "VALUES (1, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET base_url=excluded.base_url, "
            "model=excluded.model, secret_ref=excluded.secret_ref, "
            "revision=excluded.revision, updated_at=excluded.updated_at",
            tuple(settings),
        )
        connection.execute("COMMIT")
    except BaseException:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()
    return database


def collector_factory(**kwargs):
    collector = native_collector_factory(**kwargs)
    # Acceptance budget: one term, one rendered search page, and a bounded
    # browser request/time envelope.  Do not widen this to fill missing media.
    collector.max_pages = 1
    collector.max_requests = 300
    collector.timeout_seconds = 60
    return collector


def build_app():
    root = Path(os.environ["LONGTIAN_REAL_TEST_ROOT"]).resolve()
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    database = prepare_database(root / "api.sqlite3")
    profile = ROOT / "runtime" / "browser" / "managed-chrome"
    credential_runtime = ROOT / "runtime"
    return create_app(
        platform_connection_service_factory=lambda: PlatformConnectionService(
            browser_profile_dir=profile,
            collector_factory=collector_factory,
        ),
        monitoring_rule_service_factory=lambda: MonitoringRuleService(
            database_path=database.path
        ),
        ai_settings_service_factory=lambda db: AISettingsService(
            db, credentials=AICredentialStore(credential_runtime)
        ),
        automation_workflow_available=False,
    )


app = build_app()


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=18143, log_level="warning")
