import sqlite3
from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from longtian_api.database import (
    CURRENT_DATABASE_VERSION,
    DEFAULT_RULE_NAME,
    DEFAULT_RULE_TERMS,
    Database,
    DatabaseVersionError,
)
from longtian_api.main import create_app
from longtian_api.repositories.monitoring_rules import (
    MonitoringRuleRecord,
    MonitoringRuleRepositoryUnavailableError,
    PreparedMonitoringRule,
)
from longtian_api.schemas.monitoring_rules import MonitoringRuleCreate
from longtian_api.services.monitoring_rules import MonitoringRuleService
from longtian_api.services.platform_connections import PlatformConnectionService
from longtian_api.services.search_runs import SearchRunService

DEFAULT_RULE = {
    "id": 1,
    "terms": list(DEFAULT_RULE_TERMS),
    "name": DEFAULT_RULE_NAME,
    "issue_keywords": [],
    "monitoring_objects": list(DEFAULT_RULE_TERMS),
    "enabled": True,
}
INVALID_REQUEST = {"detail": {"code": "invalid_request", "message": "请求内容不正确。"}}


def _create_test_app(
    database_path: Path,
    *,
    platform_connection_service_factory: Callable[
        [], PlatformConnectionService
    ] = PlatformConnectionService,
):
    return create_app(
        platform_connection_service_factory=platform_connection_service_factory,
        monitoring_rule_service_factory=lambda: MonitoringRuleService(
            database_path=database_path
        ),
    )


def test_fresh_migration_configures_sqlite_and_seeds_exactly_once(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "nested" / "rules.sqlite3"
    service = MonitoringRuleService(database_path=database_path)

    service.initialize()
    service.initialize()

    assert service.list_rules().model_dump(mode="json") == {"rules": [DEFAULT_RULE]}
    configured_connection = Database(database_path).connect()
    try:
        assert configured_connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert (
            configured_connection.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
        )
    finally:
        configured_connection.close()
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (
            CURRENT_DATABASE_VERSION,
        )
        assert connection.execute("PRAGMA journal_mode").fetchone() == ("wal",)
        assert {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        } >= {"monitoring_rules", "monitoring_rule_terms"}
        assert {
            row[1]
            for row in connection.execute("PRAGMA index_list('monitoring_rules')")
        } >= {"ix_monitoring_rules_enabled_id"}


def test_deleted_migration_seed_is_not_recreated_on_restart(tmp_path: Path) -> None:
    database_path = tmp_path / "rules.sqlite3"
    first = MonitoringRuleService(database_path=database_path)
    first.initialize()
    first.delete_rule(1)

    second = MonitoringRuleService(database_path=database_path)
    second.initialize()

    assert second.list_rules().rules == []


def test_forward_database_version_fails_application_startup(tmp_path: Path) -> None:
    database_path = tmp_path / "future.sqlite3"
    with sqlite3.connect(database_path) as connection:
        connection.execute(f"PRAGMA user_version = {CURRENT_DATABASE_VERSION + 1}")

    with pytest.raises(DatabaseVersionError):
        with TestClient(_create_test_app(database_path)):
            pass


def test_crud_filtering_order_and_persistence_across_restart(tmp_path: Path) -> None:
    database_path = tmp_path / "rules.sqlite3"
    with TestClient(_create_test_app(database_path)) as client:
        created = client.post(
            "/api/v1/monitoring-rules",
            json={
                "name": "  重点地点  ",
                "issue_keywords": [],
                "monitoring_objects": ["  坪山大道  ", "学校"],
            },
        )
        assert created.status_code == 201
        assert created.json() == {
            "id": 2,
            "terms": ["坪山大道", "学校"],
            "name": "重点地点",
            "issue_keywords": [],
            "monitoring_objects": ["坪山大道", "学校"],
            "enabled": True,
        }

        replaced = client.put(
            "/api/v1/monitoring-rules/2",
            json={
                "name": "重点事件",
                "issue_keywords": [],
                "monitoring_objects": ["噪音扰民", "交通事故"],
                "enabled": False,
            },
        )
        assert replaced.status_code == 200
        assert replaced.json() == {
            "id": 2,
            "terms": ["噪音扰民", "交通事故"],
            "name": "重点事件",
            "issue_keywords": [],
            "monitoring_objects": ["噪音扰民", "交通事故"],
            "enabled": False,
        }

        assert client.get("/api/v1/monitoring-rules").json() == {
            "rules": [DEFAULT_RULE, replaced.json()]
        }
        assert client.get(
            "/api/v1/monitoring-rules", params={"enabled": True}
        ).json() == {"rules": [DEFAULT_RULE]}
        assert client.get(
            "/api/v1/monitoring-rules", params={"enabled": False}
        ).json() == {"rules": [replaced.json()]}

    with TestClient(_create_test_app(database_path)) as client:
        persisted = client.get("/api/v1/monitoring-rules")
        assert persisted.json() == {"rules": [DEFAULT_RULE, replaced.json()]}
        deleted = client.delete("/api/v1/monitoring-rules/2")
        assert deleted.status_code == 204
        assert deleted.content == b""

    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM monitoring_rule_terms WHERE rule_id = 2"
        ).fetchone() == (0,)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (
            {
                "name": "   ",
                "issue_keywords": [],
                "monitoring_objects": ["龙田街道"],
                "enabled": True,
            },
            "请输入规则名称。",
        ),
        (
            {
                "name": "规则",
                "issue_keywords": [],
                "monitoring_objects": [],
                "enabled": True,
            },
            "请至少输入一个监控对象。",
        ),
        (
            {
                "name": "规则",
                "issue_keywords": [],
                "monitoring_objects": ["   "],
                "enabled": True,
            },
            "监控对象不能为空。",
        ),
        (
            {
                "name": "名" * 81,
                "issue_keywords": [],
                "monitoring_objects": ["词"],
                "enabled": True,
            },
            "规则名称不能超过 80 个字符。",
        ),
        (
            {
                "name": "规则",
                "issue_keywords": [],
                "monitoring_objects": ["词" * 101],
                "enabled": True,
            },
            "监控对象不能超过 100 个字符。",
        ),
        (
            {
                "name": "规则",
                "issue_keywords": [],
                "monitoring_objects": [str(index) for index in range(101)],
            },
            "每条监控规则最多包含 100 个监控对象。",
        ),
    ],
)
def test_semantic_validation_has_stable_chinese_feedback(
    tmp_path: Path, payload: dict[str, object], message: str
) -> None:
    with TestClient(_create_test_app(tmp_path / "rules.sqlite3")) as client:
        response = client.post("/api/v1/monitoring-rules", json=payload)

    assert response.status_code == 422
    assert response.json() == {
        "detail": {"code": "invalid_monitoring_rule", "message": message}
    }


def test_normalized_duplicate_terms_are_rejected_without_silent_deduplication(
    tmp_path: Path,
) -> None:
    with TestClient(_create_test_app(tmp_path / "rules.sqlite3")) as client:
        response = client.post(
            "/api/v1/monitoring-rules",
            json={
                "name": "字母规则",
                "issue_keywords": [],
                "monitoring_objects": ["Ａ", " a "],
            },
        )

    assert response.status_code == 422
    assert response.json() == {
        "detail": {
            "code": "duplicate_monitoring_rule_term",
            "message": "监控对象不能重复，请检查后重试。",
        }
    }


def test_normalized_name_conflicts_on_create_and_update_are_atomic(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "rules.sqlite3"
    with TestClient(_create_test_app(database_path)) as client:
        first = client.post(
            "/api/v1/monitoring-rules",
            json={
                "name": " Ａbc ",
                "issue_keywords": [],
                "monitoring_objects": ["第一个"],
            },
        )
        assert first.status_code == 201
        assert first.json()["name"] == "Ａbc"

        conflict = client.post(
            "/api/v1/monitoring-rules",
            json={
                "name": "abc",
                "issue_keywords": [],
                "monitoring_objects": ["第二个"],
            },
        )
        assert conflict.status_code == 409
        assert conflict.json() == {
            "detail": {
                "code": "monitoring_rule_name_conflict",
                "message": "已存在同名监控规则。",
            }
        }

        other = client.post(
            "/api/v1/monitoring-rules",
            json={
                "name": "另一条",
                "issue_keywords": [],
                "monitoring_objects": ["原始关键词"],
            },
        ).json()
        update_conflict = client.put(
            f"/api/v1/monitoring-rules/{other['id']}",
            json={
                "name": "ABC",
                "issue_keywords": [],
                "monitoring_objects": ["替换关键词"],
                "enabled": False,
            },
        )
        assert update_conflict.status_code == 409
        unchanged = client.get("/api/v1/monitoring-rules").json()["rules"][-1]
        assert unchanged == other


@pytest.mark.parametrize(
    ("method", "path", "request_options"),
    [
        (
            "post",
            "/api/v1/monitoring-rules",
            {
                "json": {
                    "name": "规则",
                    "issue_keywords": [],
                    "monitoring_objects": ["词"],
                    "extra": "x",
                }
            },
        ),
        (
            "post",
            "/api/v1/monitoring-rules",
            {"json": {"name": 1, "issue_keywords": [], "monitoring_objects": ["词"]}},
        ),
        (
            "post",
            "/api/v1/monitoring-rules",
            {
                "json": {
                    "name": "规则",
                    "issue_keywords": [],
                    "monitoring_objects": "词",
                }
            },
        ),
        (
            "post",
            "/api/v1/monitoring-rules",
            {
                "json": {
                    "name": "规则",
                    "issue_keywords": [],
                    "monitoring_objects": ["词"],
                    "enabled": 1,
                }
            },
        ),
        (
            "post",
            "/api/v1/monitoring-rules",
            {"content": b'{"name":'},
        ),
        (
            "put",
            "/api/v1/monitoring-rules/0",
            {
                "json": {
                    "name": "规则",
                    "issue_keywords": [],
                    "monitoring_objects": ["词"],
                    "enabled": True,
                }
            },
        ),
        (
            "delete",
            "/api/v1/monitoring-rules/9223372036854775808",
            {},
        ),
        (
            "get",
            "/api/v1/monitoring-rules?enabled=not-a-boolean",
            {},
        ),
    ],
)
def test_structural_validation_uses_one_stable_request_envelope(
    tmp_path: Path,
    method: str,
    path: str,
    request_options: dict[str, object],
) -> None:
    with TestClient(_create_test_app(tmp_path / "rules.sqlite3")) as client:
        response = client.request(method, path, **request_options)

    assert response.status_code == 422
    assert response.json() == INVALID_REQUEST


@pytest.mark.parametrize("method", ["put", "delete"])
def test_missing_rule_has_stable_404(
    tmp_path: Path,
    method: str,
) -> None:
    request_options: dict[str, object] = {}
    if method == "put":
        request_options["json"] = {
            "name": "规则",
            "issue_keywords": [],
            "monitoring_objects": ["关键词"],
            "enabled": True,
        }
    with TestClient(_create_test_app(tmp_path / "rules.sqlite3")) as client:
        response = client.request(
            method, "/api/v1/monitoring-rules/999", **request_options
        )

    assert response.status_code == 404
    assert response.json() == {
        "detail": {
            "code": "monitoring_rule_not_found",
            "message": "未找到该监控规则。",
        }
    }


def test_failed_term_replacement_rolls_back_entire_rule_and_sanitizes_storage_error(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "private-sentinel" / "rules.sqlite3"
    with TestClient(_create_test_app(database_path)) as client:
        with sqlite3.connect(database_path) as connection:
            connection.execute(
                """
                CREATE TRIGGER fail_sentinel_term
                BEFORE INSERT ON monitoring_rule_terms
                WHEN NEW.value = '用户输入-sentinel'
                BEGIN
                  SELECT RAISE(ABORT, 'raw sqlite sentinel');
                END
                """
            )

        response = client.put(
            "/api/v1/monitoring-rules/1",
            json={
                "name": "不应保存的名称",
                "issue_keywords": [],
                "monitoring_objects": ["用户输入-sentinel"],
                "enabled": False,
            },
        )
        after_failure = client.get("/api/v1/monitoring-rules").json()

    assert response.status_code == 503
    assert response.json() == {
        "detail": {
            "code": "monitoring_rule_storage_unavailable",
            "message": "监控规则暂时无法读取或保存，请稍后重试。",
        }
    }
    serialized = response.text
    assert "private-sentinel" not in serialized
    assert "raw sqlite sentinel" not in serialized
    assert "用户输入-sentinel" not in serialized
    assert after_failure == {"rules": [DEFAULT_RULE]}


class UnavailableRepository:
    def initialize(self) -> None:
        pass

    def list(self, *, enabled: bool | None = None) -> tuple[MonitoringRuleRecord, ...]:
        del enabled
        raise MonitoringRuleRepositoryUnavailableError

    def create(self, rule: PreparedMonitoringRule) -> MonitoringRuleRecord:
        del rule
        raise MonitoringRuleRepositoryUnavailableError

    def replace(
        self, rule_id: int, rule: PreparedMonitoringRule
    ) -> MonitoringRuleRecord:
        del rule_id, rule
        raise MonitoringRuleRepositoryUnavailableError

    def delete(self, rule_id: int) -> None:
        del rule_id
        raise MonitoringRuleRepositoryUnavailableError


def test_unavailable_repository_is_a_sanitized_503(tmp_path: Path) -> None:
    service = MonitoringRuleService(repository=UnavailableRepository())
    with TestClient(
        create_app(
            monitoring_rule_service_factory=lambda: service,
            search_run_service_factory=lambda monitoring_rules, platform_connections: (
                SearchRunService(
                    monitoring_rules=monitoring_rules,
                    worker=platform_connections.worker,
                    browser_operations=platform_connections.browser_operations,
                    database_path=tmp_path / "search.sqlite3",
                )
            ),
        )
    ) as client:
        response = client.get("/api/v1/monitoring-rules")

    assert response.status_code == 503
    assert response.json() == {
        "detail": {
            "code": "monitoring_rule_storage_unavailable",
            "message": "监控规则暂时无法读取或保存，请稍后重试。",
        }
    }
    assert str(tmp_path) not in response.text


def test_enabled_service_boundary_preserves_term_order(tmp_path: Path) -> None:
    database_path = tmp_path / "rules.sqlite3"
    service = MonitoringRuleService(database_path=database_path)
    service.initialize()
    service.create_rule(
        MonitoringRuleCreate(
            name="已停用规则", monitoring_objects=["第二", "第一"], enabled=False
        )
    )

    enabled = service.list_enabled()

    assert [rule.id for rule in enabled] == [1]
    assert enabled[0].terms == DEFAULT_RULE_TERMS


def test_openapi_documents_monitoring_rule_contracts(tmp_path: Path) -> None:
    with TestClient(_create_test_app(tmp_path / "rules.sqlite3")) as client:
        document = client.get("/openapi.json").json()

    paths = document["paths"]
    assert paths["/api/v1/monitoring-rules"]["post"]["responses"]["201"]["content"][
        "application/json"
    ]["schema"] == {"$ref": "#/components/schemas/MonitoringRule"}
    assert (
        paths["/api/v1/monitoring-rules/{rule_id}"]["delete"]["responses"]["204"][
            "description"
        ]
        == "Successful Response"
    )
    for operation, statuses in (
        (paths["/api/v1/monitoring-rules"]["get"], ("422", "503")),
        (paths["/api/v1/monitoring-rules"]["post"], ("409", "422", "503")),
        (
            paths["/api/v1/monitoring-rules/{rule_id}"]["put"],
            ("404", "409", "422", "503"),
        ),
        (
            paths["/api/v1/monitoring-rules/{rule_id}"]["delete"],
            ("404", "422", "503"),
        ),
    ):
        for status_code in statuses:
            assert operation["responses"][status_code]["content"]["application/json"][
                "schema"
            ] == {"$ref": "#/components/schemas/MonitoringRuleErrorResponse"}


def test_rule_crud_never_launches_the_platform_worker(
    tmp_path: Path, monkeypatch
) -> None:
    async def fail_if_model_called(*_args, **_kwargs):
        raise AssertionError("Monitoring rules must not call a model")

    monkeypatch.setattr(
        "longtian_api.services.ai_client.AIClient.complete_text", fail_if_model_called
    )

    platform_service = PlatformConnectionService()
    with TestClient(
        _create_test_app(
            tmp_path / "rules.sqlite3",
            platform_connection_service_factory=lambda: platform_service,
        )
    ) as client:
        assert client.get("/api/v1/monitoring-rules").status_code == 200
        assert (
            client.post(
                "/api/v1/monitoring-rules",
                json={
                    "name": "独立规则",
                    "issue_keywords": ["问题"],
                    "monitoring_objects": ["独立关键词"],
                },
            ).status_code
            == 201
        )
        assert (
            client.put(
                "/api/v1/monitoring-rules/2",
                json={
                    "name": "保存规则",
                    "monitoring_objects": ["甲", "乙"],
                    "issue_keywords": ["问题一", "问题二"],
                    "enabled": False,
                },
            ).status_code
            == 200
        )
        assert client.get("/api/v1/monitoring-rules").json()["rules"][-1]["terms"] == [
            "甲 问题一",
            "甲 问题二",
            "乙 问题一",
            "乙 问题二",
        ]
        assert client.delete("/api/v1/monitoring-rules/2").status_code == 204
