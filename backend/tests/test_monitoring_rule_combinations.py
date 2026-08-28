import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from longtian_api import database as migrations
from longtian_api.database import CURRENT_DATABASE_VERSION, Database
from longtian_api.main import create_app
from longtian_api.repositories.search_batches import SearchBatchRepository
from longtian_api.repositories.search_runs import SearchRunRepository
from longtian_api.schemas.monitoring_rules import MonitoringRuleCreate
from longtian_api.services.monitoring_rules import (
    MonitoringRuleError,
    MonitoringRuleService,
    compose_monitoring_terms,
)


def _version_eight_database(path: Path) -> Database:
    database = Database(path)
    connection = database.connect()
    try:
        for migrate in (
            migrations._migrate_to_version_1,
            migrations._migrate_to_version_2,
            migrations._migrate_to_version_3,
            migrations._migrate_to_version_4,
            migrations._migrate_to_version_5,
            migrations._migrate_to_version_6,
            migrations._migrate_to_version_7,
            migrations._migrate_to_version_8,
        ):
            migrate(connection)
    finally:
        connection.close()
    return database


def test_v8_upgrade_preserves_every_old_row_and_deleted_seed(tmp_path: Path) -> None:
    database = _version_eight_database(tmp_path / "v8.sqlite3")
    with database.connect() as connection:
        connection.execute("DELETE FROM monitoring_rules WHERE id = 1")
        connection.execute(
            "INSERT INTO monitoring_rules VALUES (7, ?, ?, 0, ?, ?)",
            ("旧完整短语", "旧完整短语", "created", "updated"),
        )
        connection.executemany(
            "INSERT INTO monitoring_rule_terms "
            "(rule_id, value, normalized_value, position) VALUES (7, ?, ?, ?)",
            [
                (value, value.casefold(), index)
                for index, value in enumerate(("A  B", "龙田 噪音"))
            ],
        )
        connection.execute(
            "INSERT INTO ai_settings VALUES (1, ?, ?, ?, 3, ?)",
            ("https://example.com/v1", "fixture-model", "a" * 36, "settings-updated"),
        )
    with database.connect() as connection:
        # Seed via the historical v8 contract, not the modern v10 writer.
        connection.execute("""INSERT INTO search_runs VALUES
          (1, 7, 'wb', '历史规则', 2, 'completed_empty', 0,
           'created', 'started', 'finished'),
          (2, 7, 'wb', '批次历史', 1, 'queued', NULL, 'created', NULL, NULL)""")
        connection.execute("""INSERT INTO search_run_terms VALUES
          (1, 0, '历史 搜索词'), (2, 0, '原有 完整查询')""")
        connection.execute("""INSERT INTO search_batches VALUES
          (1, 7, '批次历史', 1, 'running', 0, 'created', 'started', NULL)""")
        connection.execute(
            "INSERT INTO search_batch_terms VALUES (1, 0, '原有 完整查询')"
        )
        connection.execute("""INSERT INTO search_batch_items VALUES
          (1, 0, 'wb', 'running', 'created', 'started', NULL),
          (1, 1, 'xhs', 'queued', 'created', NULL, NULL)""")
        connection.execute(
            "INSERT INTO search_batch_attempts VALUES (1, 0, 1, 2, 'created')"
        )
        old_tables = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
            )
        ]
        before = {
            table: connection.execute(
                f'SELECT * FROM "{table}" ORDER BY rowid'
            ).fetchall()  # noqa: S608 - test-owned schema names
            for table in old_tables
        }
        old_columns = {
            table: ", ".join(
                f'"{row[1]}"'
                for row in connection.execute(f'PRAGMA table_info("{table}")')
            )
            for table in old_tables
        }

    database.initialize()
    database.initialize()

    with database.connect() as connection:
        assert (
            connection.execute("PRAGMA user_version").fetchone()[0]
            == CURRENT_DATABASE_VERSION
        )
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert (
            connection.execute("SELECT * FROM monitoring_rule_issue_terms").fetchall()
            == []
        )
        for table in old_tables:
            assert (
                connection.execute(
                    f'SELECT {old_columns[table]} FROM "{table}" ORDER BY rowid'
                ).fetchall()
                == before[table]
            )  # noqa: S608 - test-owned schema names
        assert [
            tuple(row)
            for row in connection.execute(
                "SELECT execution_start_term_position, search_protocol_version "
                "FROM search_runs"
            )
        ] == [(0, 1), (0, 1)]
    service = MonitoringRuleService(database_path=database.path)
    rules = service.list_rules().rules
    assert len(rules) == 1
    assert rules[0].id == 7
    assert rules[0].enabled is False
    assert rules[0].monitoring_objects == rules[0].terms == ("A  B", "龙田 噪音")
    assert rules[0].issue_keywords == ()
    assert service.list_enabled() == ()
    runs, batches = SearchRunRepository(database), SearchBatchRepository(database)
    assert runs.get(1).terms == ("历史 搜索词",)
    assert runs.get(2).terms == batches.get(1).terms == ("原有 完整查询",)


def test_v9_partial_migration_rolls_back_table_and_version(tmp_path: Path) -> None:
    database = _version_eight_database(tmp_path / "rollback.sqlite3")

    class FailingVersionConnection(sqlite3.Connection):
        def execute(self, sql, parameters=()):
            if sql == "PRAGMA user_version = 9":
                raise sqlite3.OperationalError("fixture migration failure")
            return super().execute(sql, parameters)

    connection = sqlite3.connect(
        database.path, isolation_level=None, factory=FailingVersionConnection
    )
    try:
        with pytest.raises(sqlite3.OperationalError):
            migrations._migrate_to_version_9(connection)
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 8
        assert (
            connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE name = 'monitoring_rule_issue_terms'"
            ).fetchone()
            is None
        )
        assert (
            connection.execute("SELECT COUNT(*) FROM monitoring_rules").fetchone()[0]
            == 1
        )
    finally:
        connection.close()
    database.initialize()


@pytest.mark.parametrize(
    ("objects", "issues", "expected"),
    [
        (
            ["龙田街道", "竹坑社区"],
            ["噪音", "积水"],
            ("龙田街道 噪音", "龙田街道 积水", "竹坑社区 噪音", "竹坑社区 积水"),
        ),
        (["  A  B  ", "旧 完整查询"], [], ("A  B", "旧 完整查询")),
        ([" Ａ  B "], [" C D "], ("Ａ  B C D",)),
        (["\u0085A B\u001c", "\ufeff完整短语"], [], ("A B", "\ufeff完整短语")),
        (["𠮷" * 98], ["水"], ("𠮷" * 98 + " 水",)),
    ],
)
def test_pure_composition_preserves_order_spaces_and_codepoints(
    objects, issues, expected
) -> None:
    assert compose_monitoring_terms(objects, issues) == expected


@pytest.mark.parametrize(
    ("objects", "issues", "code"),
    [
        ([], [], "invalid_monitoring_rule"),
        ([" "], [], "invalid_monitoring_rule"),
        (["A"], [" "], "invalid_monitoring_rule"),
        (["A" * 101], [], "invalid_monitoring_rule"),
        (["A"], ["B" * 101], "invalid_monitoring_rule"),
        (["A" * 99], ["B"], "invalid_monitoring_rule"),
        (["\0" + "𠮷" * 100], [], "invalid_monitoring_rule"),
        (["A"], ["\0" + "𠮷" * 100], "invalid_monitoring_rule"),
        (["A"], ["\0" + "𠮷" * 98], "invalid_monitoring_rule"),
        (["Ａ", " a "], [], "duplicate_monitoring_rule_term"),
        (["A"], ["Straße", "STRASSE"], "duplicate_monitoring_rule_term"),
        (["Σ", "ς"], [], "duplicate_monitoring_rule_term"),
        (["A", "A B"], ["B C", "C"], "duplicate_monitoring_rule_term"),
        (["Ａ", "A B"], ["B C", "C"], "duplicate_monitoring_rule_term"),
        ([str(index) for index in range(101)], [], "invalid_monitoring_rule"),
        (["A"], [str(index) for index in range(101)], "invalid_monitoring_rule"),
        (
            [str(index) for index in range(11)],
            [str(index) for index in range(10)],
            "invalid_monitoring_rule",
        ),
    ],
)
def test_invalid_groups_or_generated_terms_fail_without_silent_deduplication(
    objects, issues, code
) -> None:
    with pytest.raises(MonitoringRuleError) as raised:
        compose_monitoring_terms(objects, issues)
    assert raised.value.status_code == 422
    assert raised.value.code == code


@pytest.mark.parametrize("count", [20, 21, 100])
def test_valid_save_counts_are_not_limited_to_execution_cap(
    tmp_path: Path, count: int
) -> None:
    service = MonitoringRuleService(database_path=tmp_path / "limits.sqlite3")
    service.initialize()
    rule = service.create_rule(
        MonitoringRuleCreate(
            name="数量边界",
            monitoring_objects=["对象"],
            issue_keywords=[str(index) for index in range(count)],
        )
    )
    assert len(rule.terms) == count
    assert rule.terms[-1] == f"对象 {count - 1}"


@pytest.mark.parametrize(
    ("objects", "issues", "terms"),
    [
        (["\0"], [], ["\0"]),
        (["对象"], ["\0"], ["对象 \0"]),
        (["A"], ["\0" + "𠮷" * 97], ["A \0" + "𠮷" * 97]),
    ],
)
def test_both_groups_preserve_nul_values_with_unicode_length_limits(
    tmp_path: Path, objects: list[str], issues: list[str], terms: list[str]
) -> None:
    app = create_app(
        monitoring_rule_service_factory=lambda: MonitoringRuleService(
            database_path=tmp_path / "nul-values.sqlite3"
        )
    )
    payload = {
        "name": "字符边界",
        "monitoring_objects": objects,
        "issue_keywords": issues,
        "enabled": True,
    }
    with TestClient(app) as client:
        response = client.post("/api/v1/monitoring-rules", json=payload)
        assert response.status_code == 201
        expected = {"id": response.json()["id"], **payload, "terms": terms}
        assert response.json() == expected
    with TestClient(app) as client:
        assert client.get("/api/v1/monitoring-rules").json()["rules"][-1] == expected


def test_groups_roundtrip_toggle_and_atomic_issue_failure(tmp_path: Path) -> None:
    path = tmp_path / "groups.sqlite3"
    app = create_app(
        monitoring_rule_service_factory=lambda: MonitoringRuleService(
            database_path=path
        )
    )
    payload = {
        "name": "双组规则",
        "monitoring_objects": ["甲", "乙"],
        "issue_keywords": ["噪音", "积水"],
        "enabled": True,
    }
    with TestClient(app) as client:
        response = client.post("/api/v1/monitoring-rules", json=payload)
        assert response.status_code == 201
        expected = {
            "id": response.json()["id"],
            **payload,
            "terms": ["甲 噪音", "甲 积水", "乙 噪音", "乙 积水"],
        }
        assert response.json() == expected
        rule_url = f"/api/v1/monitoring-rules/{expected['id']}"
        toggled = client.put(rule_url, json={**payload, "enabled": False})
        assert toggled.status_code == 200
        expected["enabled"] = False
        assert toggled.json() == expected
    with TestClient(app) as client:
        assert client.get("/api/v1/monitoring-rules").json()["rules"][-1] == expected
        with sqlite3.connect(path) as connection:
            connection.execute("""
                CREATE TRIGGER reject_issue
                BEFORE INSERT ON monitoring_rule_issue_terms
                WHEN NEW.value = 'failure-input'
                BEGIN
                  SELECT RAISE(ABORT, 'private-sql-sentinel');
                END
                """)
        failure = client.put(
            rule_url,
            json={
                **payload,
                "name": "不可保存",
                "monitoring_objects": ["已更改"],
                "issue_keywords": ["failure-input"],
            },
        )
        assert failure.status_code == 503
        assert failure.json() == {
            "detail": {
                "code": "monitoring_rule_storage_unavailable",
                "message": "监控规则暂时无法读取或保存，请稍后重试。",
            }
        }
        assert client.get("/api/v1/monitoring-rules").json()["rules"][-1] == expected
        created_failure = client.post(
            "/api/v1/monitoring-rules",
            json={**payload, "name": "创建失败", "issue_keywords": ["failure-input"]},
        )
        assert created_failure.status_code == 503
        assert len(client.get("/api/v1/monitoring-rules").json()["rules"]) == 2
        assert client.delete(rule_url).status_code == 204
        with sqlite3.connect(path) as connection:
            assert (
                connection.execute(
                    "SELECT COUNT(*) FROM monitoring_rule_issue_terms"
                ).fetchone()[0]
                == 0
            )


@pytest.mark.parametrize(
    ("method", "overrides"),
    [
        ("post", {"terms": ["legacy"]}),
        ("post", {"monitoring_objects": None}),
        ("post", {"monitoring_objects": "A"}),
        ("post", {"monitoring_objects": [1]}),
        ("post", {"issue_keywords": None}),
        ("post", {"issue_keywords": "B"}),
        ("post", {"issue_keywords": [False]}),
        ("put", {"terms": ["readonly"]}),
    ],
)
def test_new_api_rejects_wrong_group_types_and_readonly_terms(
    tmp_path: Path, method: str, overrides
) -> None:
    app = create_app(
        monitoring_rule_service_factory=lambda: MonitoringRuleService(
            database_path=tmp_path / "strict.sqlite3"
        )
    )
    with TestClient(app) as client:
        response = client.request(
            method,
            "/api/v1/monitoring-rules" + ("/1" if method == "put" else ""),
            json={
                "name": "规则",
                "monitoring_objects": ["A"],
                "issue_keywords": [],
                "enabled": True,
                **overrides,
            },
        )
        assert response.status_code == 422
        assert response.json() == {
            "detail": {"code": "invalid_request", "message": "请求内容不正确。"}
        }


def test_create_defaults_and_replace_requires_both_groups(tmp_path: Path) -> None:
    app = create_app(
        monitoring_rule_service_factory=lambda: MonitoringRuleService(
            database_path=tmp_path / "defaults.sqlite3"
        )
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/monitoring-rules",
            json={"name": "对象搜索", "monitoring_objects": ["A B"]},
        )
        assert response.status_code == 201
        assert response.json() == {
            "id": 2,
            "name": "对象搜索",
            "monitoring_objects": ["A B"],
            "issue_keywords": [],
            "terms": ["A B"],
            "enabled": True,
        }
        for payload in (
            {"name": "旧客户端", "terms": ["A"]},
            {"name": "缺少分组", "monitoring_objects": ["A"], "enabled": True},
        ):
            assert (
                client.put("/api/v1/monitoring-rules/2", json=payload).status_code
                == 422
            )
        document = client.get("/openapi.json").json()["components"]["schemas"]
        assert set(document["MonitoringRuleReplace"]["required"]) == {
            "name",
            "monitoring_objects",
            "issue_keywords",
            "enabled",
        }
        assert set(document["MonitoringRule"]["properties"]) == {
            "id",
            "name",
            "monitoring_objects",
            "issue_keywords",
            "terms",
            "enabled",
        }
